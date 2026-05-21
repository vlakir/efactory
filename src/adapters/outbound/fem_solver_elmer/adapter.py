"""
Elmer FEM 2D-planar magnetostatic adapter (T133 Phase 1+2 — 2D infrastructure).

Реализует `MagneticFieldSolver` outbound port методом energy / J·A:
  W_per_depth = 0.5 · J_density · ∫_Primary A_z dA   (single-coil)
  Lp = 2 · W_per_depth · core_depth / I_ref²

Параллельный к `GetDpFemSolver` (T113/T129): тот же port, та же mesh
pipeline (Gmsh `.msh` через `ElmerGrid 14 2 -autoclean -out`), отличается
solver backend (MgDyn2D vs GetDP linear) и outer BC treatment (Infinity
BC Robin-type vs Dirichlet A=0).

**⚠️ 2D-planar inherent precision limitation** (T133 Phase 3 empirical
finding, см. auto-memory `feedback_fem_2d_inherent_gap_to_zhang`):
На E-core fixture (OPT 6П14П SE: Nanoperm 8000, μ_r=8000 linear)
этот adapter даёт **Lp = 19.65 H** vs PyOM ZHANG analytical 6.96 H
(+182%). Это **physics, не bug** — ZHANG reluctance model предполагает
fully closed magnetic circuit (100% flux в iron), 2D-planar FEM
inherently включает 3D leakage/fringing effects. T113 GetDP split-coil
+ Dirichlet даёт +242%. **Никакой 2D-planar вариант не попадает в
acceptance ±25% к ZHANG**; closure требует 3D mesh (T133 Phase 3+,
`emit_e_core_geo_3d` + `MagnetoDynamics` Whitney AV solver).

**Где 2D adapter остаётся полезным:**
- **2D-axisymmetric** для toroidal/pot cores (separate emit_* function,
  не сделана).
- **Leakage расчёты** (T135) — gap reluctance не в leakage path.
- **Cross-validation backend** для GetDP linear self-consistency
  на same fixture (numerical reproducibility check).
- **Quick prototyping** — сравнение топологий без полного 3D mesh.

**Nonlinear-frohlich path (T133 Phase 2) — known instability:** на
pilot probe (DC bias 50 mA) Elmer Newton iteration падает с
`IEEE_UNDERFLOW_FLAG IEEE_DENORMAL STOP 1`. Path сохранён как
infrastructure для возможного refinement, но не для production
acceptance без debugging.

Адаптерные ограничения:
- `material_model='linear'` — production-ready (с known inherent gap).
- `material_model='nonlinear-frohlich'` — infrastructure-only,
  numerical instability на low DC bias.
- E-core shapes only (через `ECoreDimensions.from_pyom_core`).
- One operating point, не sweep.
- Single-coil topology: только Primary энергизована (`+Jz`), Secondary
  трактуется как air. Отличается от T113 split-coil.

Pipeline:
  1. PyOM `calculate_core_data(shape, material, gapping)` → core dims.
  2. `emit_e_core_geo(dims)` → .geo (shared с GetDP).
  3. `gmsh -2 -format msh22 .geo -o .msh` (subprocess).
  4. `ElmerGrid 14 2 .msh -autoclean -out mesh-elmer/` (subprocess —
     auto-memory `feedback_elmer_2d_keyword_pitfalls`: -autoclean
     обязателен для predictable Body/Boundary numbering).
  5. `sif_template.render_magnetostatic_sif_linear(...)` → case.sif.
  6. `ElmerSolver case.sif` (subprocess; cwd = work_dir).
  7. Parse `scalars.dat` — body int A для Primary mask.
  8. Lp = 2 · J · depth · ∫_Primary A dS / I_ref²
     = N · depth · ∫_Primary A dS / (A_window · I_ref).
"""

from __future__ import annotations

import asyncio
import re
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Any, Literal, get_args

from adapters.outbound.fem_common import (
    ECoreDimensions,
    emit_e_core_geo,
    emit_e_core_geo_3d,
    extract_frohlich_params,
)
from adapters.outbound.fem_solver_elmer.sif_template import (
    render_magnetostatic_sif_linear,
    render_magnetostatic_sif_linear_3d,
    render_magnetostatic_sif_nonlinear,
)
from domain.material import DEFAULT_NUM_POINTS, FrohlichBHCurve
from ports.outbound.magnetic_field_solver import (
    FemSolveOutcome,
    MagneticFieldSolverFailedError,
    MagneticFieldSolverUnavailableError,
    UnsupportedGeometryError,
)

if TYPE_CHECKING:
    from domain.magnetic import MagneticComponent


DEFAULT_MUR_IRON = 8000.0  # Nanoperm-class μ_initial — linear approximation
DEFAULT_I_REF = 1.0  # reference current 1 A для self-inductance

# T129 conventions reused (auto-memory + spec): central-diff ΔI = max(1%
# относительной амплитуды, 0.1 mA absolute floor для zero-bias probe).
DELTA_I_FLOOR_A = 0.0001
DELTA_I_REL = 0.01

MaterialModel = Literal['linear', 'nonlinear-frohlich']
_VALID_MATERIAL_MODELS: tuple[MaterialModel, ...] = get_args(MaterialModel)

Dimensionality = Literal['2d', '3d']
_VALID_DIMENSIONALITIES: tuple[Dimensionality, ...] = get_args(Dimensionality)

# Empirical baselines на OPT 6П14П SE (T133 Phase 3 acceptance probes
# 2026-05-21 в efactory:linux). Используются integration test'ами как
# regression baselines (drift ±5%). PyOM ZHANG analytical reference = 6.96 H.
EMPIRICAL_LP_OPT_6P14P_SE_LINEAR_H = 19.65  # 2D single-coil + InfBC (+182%)
# 3D linear с gaps + Phase 3d.2 mesh refinement (20μm gap / 5mm max):
# 10K nodes / 51K tetra, ~14 s runtime. Lp = 6.04 H = -13.3% к ZHANG —
# **acceptance ±25% [5.22, 8.70] achieved**, target ±10% [6.26, 7.65]
# близок (off by 3.5%). vs Phase 3d.1 coarse mesh (453 nodes) которая
# давала 4.07 H = -41.5% — refinement дал factor 1.48× improvement.
EMPIRICAL_LP_OPT_6P14P_SE_LINEAR_3D_H = 6.04


class ElmerFemSolver:
    """
    `MagneticFieldSolver` adapter поверх Elmer FEM subprocess pipeline.

    Args:
        pyom_module: загруженный PyOpenMagnetics module — для
            `calculate_core_data` (E-core dims extraction).
        gmsh_bin: путь к gmsh binary (default — поиск в PATH).
        elmer_grid_bin: путь к ElmerGrid binary.
        elmer_solver_bin: путь к ElmerSolver binary.
        mur_iron: linear relative permeability iron region. По умолчанию
            8000 (Nanoperm-class μ_initial). Phase 1 only path.
        material_model: формулировка материала. `'linear'` (Phase 1) —
            constant `μ_r` Iron; `'nonlinear-frohlich'` (Phase 2) —
            tabulated H-B Curve от FrohlichBHCurve + Newton iteration +
            DC-bias central-diff на 2-х nonlinear solve'ах.
        num_bh_points: количество точек в Frohlich BH-таблице
            (Phase 2; default 16; используется при `material_model=
            'nonlinear-frohlich'`).
        work_dir_root: корень для временных work_dir. None — fresh
            `TemporaryDirectory` per call.

    """

    def __init__(
        self,
        pyom_module: Any,  # noqa: ANN401  - dynamic .so module
        *,
        gmsh_bin: str = 'gmsh',
        elmer_grid_bin: str = 'ElmerGrid',
        elmer_solver_bin: str = 'ElmerSolver',
        mur_iron: float = DEFAULT_MUR_IRON,
        material_model: MaterialModel = 'linear',
        dimensionality: Dimensionality = '2d',
        num_bh_points: int = DEFAULT_NUM_POINTS,
        work_dir_root: Path | None = None,
    ) -> None:
        if material_model not in _VALID_MATERIAL_MODELS:
            msg = (
                f'material_model должен быть одним из '
                f'{_VALID_MATERIAL_MODELS!r}, получено {material_model!r}'
            )
            raise ValueError(msg)
        if dimensionality not in _VALID_DIMENSIONALITIES:
            msg = (
                f'dimensionality должен быть одним из '
                f'{_VALID_DIMENSIONALITIES!r}, получено {dimensionality!r}'
            )
            raise ValueError(msg)
        if dimensionality == '3d' and material_model == 'nonlinear-frohlich':
            msg = (
                '3D nonlinear-frohlich path не реализован в Phase 3c '
                '(используйте 2D nonlinear-frohlich или 3D linear).'
            )
            raise NotImplementedError(msg)
        self._pyom = pyom_module
        self._gmsh = gmsh_bin
        self._elmer_grid = elmer_grid_bin
        self._elmer_solver = elmer_solver_bin
        self._mur_iron = mur_iron
        self._material_model: MaterialModel = material_model
        self._dimensionality: Dimensionality = dimensionality
        self._num_bh_points = num_bh_points
        self._work_dir_root = work_dir_root

    @property
    def material_model(self) -> MaterialModel:
        return self._material_model

    @property
    def dimensionality(self) -> Dimensionality:
        return self._dimensionality

    async def solve(self, component: MagneticComponent) -> FemSolveOutcome:
        """Async wrapper над blocking subprocess pipeline."""
        return await asyncio.to_thread(self._solve_blocking, component)

    def _solve_blocking(self, component: MagneticComponent) -> FemSolveOutcome:
        core_full = self._compute_core_data(component)
        dims = self._extract_e_core_dims(component, core_full)

        with TemporaryDirectory(
            prefix='efactory-elmer-',
            dir=self._work_dir_root,
        ) as tmp:
            work_dir = Path(tmp)
            geo_path = work_dir / 'geometry.geo'
            msh_path = work_dir / 'geometry.msh'
            if self._dimensionality == '2d':
                geo_path.write_text(emit_e_core_geo(dims))
                self._run_gmsh(geo_path, msh_path, work_dir, dim=2)
            else:
                geo_path.write_text(emit_e_core_geo_3d(dims))
                self._run_gmsh(geo_path, msh_path, work_dir, dim=3)
            self._run_elmer_grid(msh_path, work_dir)

            n_primary = component.primary_winding.number_turns
            area_window = dims.window_w * dims.window_h
            if self._dimensionality == '3d':
                # Constructor enforces material_model == 'linear' для 3d.
                return self._solve_linear_3d(
                    work_dir=work_dir,
                    n_primary=n_primary,
                    area_window=area_window,
                )
            if self._material_model == 'linear':
                return self._solve_linear(
                    work_dir=work_dir,
                    n_primary=n_primary,
                    area_window=area_window,
                    core_depth=dims.core_depth,
                )
            return self._solve_nonlinear_central_diff(
                component=component,
                work_dir=work_dir,
                n_primary=n_primary,
                area_window=area_window,
                core_depth=dims.core_depth,
            )

    def _solve_linear(
        self,
        *,
        work_dir: Path,
        n_primary: int,
        area_window: float,
        core_depth: float,
    ) -> FemSolveOutcome:
        """Linear mode: Lp = N·depth·∫_Primary A dS / (A_window·I_ref)."""
        sif_path = work_dir / 'case.sif'
        scalars_path = work_dir / 'scalars.dat'
        sif_path.write_text(
            render_magnetostatic_sif_linear(
                mur_iron=self._mur_iron,
                n_primary=n_primary,
                i_ref=DEFAULT_I_REF,
                area_window=area_window,
            ),
        )
        self._run_elmer_solver(sif_path, work_dir)
        int_a_primary = self._parse_body_int_a(scalars_path)
        l_p = n_primary * core_depth * int_a_primary / (area_window * DEFAULT_I_REF)
        return FemSolveOutcome(inductance_h=l_p, method='linear')

    def _solve_linear_3d(
        self,
        *,
        work_dir: Path,
        n_primary: int,
        area_window: float,
    ) -> FemSolveOutcome:
        """
        3D linear: Whitney AV + CalcFields → energy → Lp = 2·W/I².

        Не использует core_depth (3D mesh already includes z-extent;
        energy integral возвращает full 3D total energy в Joules).
        """
        sif_path = work_dir / 'case.sif'
        scalars_path = work_dir / 'scalars.dat'
        sif_path.write_text(
            render_magnetostatic_sif_linear_3d(
                mur_iron=self._mur_iron,
                n_primary=n_primary,
                i_ref=DEFAULT_I_REF,
                area_window=area_window,
            ),
        )
        self._run_elmer_solver(sif_path, work_dir)
        em_energy_j = self._parse_field_energy(scalars_path)
        l_p = 2.0 * em_energy_j / (DEFAULT_I_REF**2)
        return FemSolveOutcome(inductance_h=l_p, method='linear')

    def _solve_nonlinear_central_diff(
        self,
        *,
        component: MagneticComponent,
        work_dir: Path,
        n_primary: int,
        area_window: float,
        core_depth: float,
    ) -> FemSolveOutcome:
        """
        2 nonlinear solve'а вокруг operating point; L_inc = (Φ₊−Φ₋)/ΔI.

        Reuses T129 GetDP convention (auto-memory `feedback_fem_split_coil_dc_bias`,
        spec Q1 revision 2): ΔI = max(0.01·|I_dc|, 0.0001 A), central-diff.
        """
        try:
            mu_initial, b_sat = extract_frohlich_params(
                self._pyom,
                component.core.material_name,
            )
        except (LookupError, TypeError) as exc:
            msg = (
                f'Frohlich material params extraction failed для '
                f'{component.core.material_name!r}: {exc}'
            )
            raise MagneticFieldSolverFailedError(msg) from exc
        curve = FrohlichBHCurve.from_pyom_material(
            mu_initial=mu_initial,
            b_sat=b_sat,
            num_points=self._num_bh_points,
        )
        hb_pairs = curve.h_b_pairs()

        i_dc = component.operating_point.primary_dc_bias_a
        delta_i = max(DELTA_I_REL * abs(i_dc), DELTA_I_FLOOR_A)
        currents = (i_dc - 0.5 * delta_i, i_dc + 0.5 * delta_i)

        fluxes = tuple(
            self._run_nonlinear_probe(
                work_dir=work_dir,
                tag=tag,
                hb_pairs=hb_pairs,
                n_primary=n_primary,
                i_value=i_value,
                area_window=area_window,
                core_depth=core_depth,
            )
            for tag, i_value in zip(('minus', 'plus'), currents, strict=True)
        )
        flux_minus, flux_plus = fluxes
        l_inc = (flux_plus - flux_minus) / delta_i
        return FemSolveOutcome(
            inductance_h=l_inc,
            method='nonlinear-frohlich',
            peak_flux_density_t=None,
        )

    def _run_nonlinear_probe(
        self,
        *,
        work_dir: Path,
        tag: str,
        hb_pairs: tuple[tuple[float, float], ...],
        n_primary: int,
        i_value: float,
        area_window: float,
        core_depth: float,
    ) -> float:
        """Один nonlinear solve в subdir, возвращает Ψ (full flux linkage)."""
        sub_dir = work_dir / f'solve_{tag}'
        sub_dir.mkdir()
        # Symlink mesh-elmer/ в sub_dir (Mesh DB referenced как "." в .sif).
        (sub_dir / 'mesh-elmer').symlink_to(work_dir / 'mesh-elmer')
        sif_path = sub_dir / 'case.sif'
        scalars_path = sub_dir / 'scalars.dat'
        sif_path.write_text(
            render_magnetostatic_sif_nonlinear(
                h_b_pairs=hb_pairs,
                n_primary=n_primary,
                i_value=i_value,
                area_window=area_window,
            ),
        )
        self._run_elmer_solver(sif_path, sub_dir)
        int_a_primary = self._parse_body_int_a(scalars_path)
        # Flux linkage Ψ = N · depth · ∫_(Primary) A dS / A_window.
        return n_primary * core_depth * int_a_primary / area_window

    def _compute_core_data(self, component: MagneticComponent) -> dict[str, Any]:
        core_fd = {
            'functionalDescription': {
                'type': 'two-piece set',
                'material': component.core.material_name,
                'shape': component.core.shape_name,
                'gapping': [
                    {
                        'type': component.core.gap_type.value,
                        'length': component.core.gap_length_m,
                    },
                ],
                'numberStacks': 1,
            },
        }
        try:
            return self._pyom.calculate_core_data(
                core_fd,
                True,  # noqa: FBT003  - PyOM C++ binding не принимает kwargs
            )
        except Exception as exc:
            msg = (
                f'PyOM calculate_core_data failed for shape='
                f'{component.core.shape_name!r}: {exc}'
            )
            raise MagneticFieldSolverFailedError(msg) from exc

    def _extract_e_core_dims(
        self,
        component: MagneticComponent,
        core_full: dict[str, Any],
    ) -> ECoreDimensions:
        try:
            return ECoreDimensions.from_pyom_core(core_full)
        except (KeyError, IndexError, TypeError) as exc:
            msg = (
                f'Phase 1 adapter поддерживает только E-core shapes; '
                f'shape={component.core.shape_name!r} не имеет ожидаемой '
                f'структуры processedDescription (columns/windingWindows): '
                f'{exc}'
            )
            raise UnsupportedGeometryError(msg) from exc

    def _run_gmsh(self, geo: Path, msh: Path, cwd: Path, *, dim: int = 2) -> None:
        """Run gmsh; `dim=2` для 2D-planar, `dim=3` для 3D extrude."""
        try:
            res = subprocess.run(
                [
                    self._gmsh,
                    f'-{dim}',
                    '-format',
                    'msh22',
                    str(geo),
                    '-o',
                    str(msh),
                ],
                cwd=cwd,
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:
            msg = (
                f'gmsh binary {self._gmsh!r} не найден в PATH; '
                f'установите gmsh apt-package'
            )
            raise MagneticFieldSolverUnavailableError(msg) from exc
        if res.returncode != 0 or not msh.exists():
            msg = f'gmsh failed (rc={res.returncode}): stderr={res.stderr[-500:]!r}'
            raise MagneticFieldSolverFailedError(msg)

    def _run_elmer_grid(self, msh: Path, cwd: Path) -> None:
        """
        Convert Gmsh .msh → Elmer mesh DB через ElmerGrid 14 2 -autoclean.

        -autoclean (auto-memory feedback_elmer_2d_keyword_pitfalls): renumber
        Physical tags в 1-indexed sequential для predictable .sif templates.
        Без флага Target Boundaries / Target Bodies требуют original Gmsh tags.
        """
        try:
            res = subprocess.run(
                [
                    self._elmer_grid,
                    '14',
                    '2',
                    str(msh),
                    '-autoclean',
                    '-out',
                    'mesh-elmer',
                ],
                cwd=cwd,
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:
            msg = (
                f'ElmerGrid binary {self._elmer_grid!r} не найден в PATH; '
                f'установите elmerfem-csc apt-package (PPA)'
            )
            raise MagneticFieldSolverUnavailableError(msg) from exc
        header_path = cwd / 'mesh-elmer' / 'mesh.header'
        if res.returncode != 0 or not header_path.exists():
            msg = (
                f'ElmerGrid failed (rc={res.returncode}): stderr={res.stderr[-500:]!r}'
            )
            raise MagneticFieldSolverFailedError(msg)

    def _run_elmer_solver(self, sif: Path, cwd: Path) -> None:
        """
        Run ElmerSolver. ВАЖНО (auto-memory feedback_elmer_savescalars_quirks):
        ElmerSolver exit-status НЕ отражает FATAL errors; нужно sif-side
        FATAL parsing — но для T133 Phase 1 linear path достаточно проверить
        rc + наличие scalars.dat.
        """
        try:
            res = subprocess.run(
                [self._elmer_solver, str(sif)],
                cwd=cwd,
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:
            msg = (
                f'ElmerSolver binary {self._elmer_solver!r} не найден в PATH; '
                f'установите elmerfem-csc apt-package (PPA)'
            )
            raise MagneticFieldSolverUnavailableError(msg) from exc
        if res.returncode != 0:
            msg = (
                f'ElmerSolver failed (rc={res.returncode}): '
                f'stderr={res.stderr[-500:]!r}'
            )
            raise MagneticFieldSolverFailedError(msg)
        # FATAL parsing: rc=0 даже при `Load: FATAL: Can't find procedure`
        # (auto-memory). Грепаем stderr+stdout на ERROR / FATAL.
        merged = (res.stdout or '') + '\n' + (res.stderr or '')
        if re.search(r'\bFATAL\b|ERROR::', merged):
            tail = merged[-500:]
            msg = f'ElmerSolver reported FATAL/ERROR (rc=0): {tail!r}'
            raise MagneticFieldSolverFailedError(msg)

    @staticmethod
    def _parse_field_energy(scalars_path: Path) -> float:
        """
        Parse `scalars.dat` от MagnetoDynamicsCalcFields.

        `MagnetoDynamicsCalcFields` auto-injects `res: electromagnetic
        field energy` как последнюю numeric column в SaveScalars output
        (после user variables + auto `res: eddy current power`).
        Для 3D template = column 3 (1 user var + 2 auto).

        Returns:
            Magnetic field energy в Joules (positive scalar).

        """
        if not scalars_path.exists():
            msg = (
                f'ElmerSolver не создал {scalars_path.name} — '
                f'MagnetoDynamicsCalcFields или SaveScalars failed?'
            )
            raise MagneticFieldSolverFailedError(msg)
        text = scalars_path.read_text()
        for line in reversed(text.splitlines()):
            tokens = line.split()
            if not tokens:
                continue
            # Last numeric column = electromagnetic field energy (Joules).
            try:
                return float(tokens[-1])
            except ValueError:
                continue
        msg = f'{scalars_path.name} не содержит float values: {text!r}'
        raise MagneticFieldSolverFailedError(msg)

    @staticmethod
    def _parse_body_int_a(scalars_path: Path) -> float:
        """
        Parse `scalars.dat` от SaveScalars body int A.

        Format (Elmer 26.2 SaveScalars):
        - .names companion file описывает columns (header).
        - .dat файл содержит одну строку чисел per timestep / iteration.
        - Для steady-state с одним solver-step — одна строка с одним числом
          (Variable 1 / Operator body int / Mask "PrimaryRegion").
        """
        if not scalars_path.exists():
            msg = (
                f'ElmerSolver не создал {scalars_path.name} — '
                f'SaveScalars solver failed? Проверьте mask Name match '
                f'body-property "PrimaryRegion".'
            )
            raise MagneticFieldSolverFailedError(msg)
        text = scalars_path.read_text()
        for line in reversed(text.splitlines()):
            tokens = line.split()
            if not tokens:
                continue
            for tok in reversed(tokens):
                try:
                    return float(tok)
                except ValueError:
                    continue
        msg = f'{scalars_path.name} не содержит float values: {text!r}'
        raise MagneticFieldSolverFailedError(msg)
