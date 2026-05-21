"""
GetDP+Gmsh 2D-planar magnetostatic FEM adapter (T113 Phase 2C).

Реализует `MagneticFieldSolver` outbound port методом energy:
  L_p = 2 W / I_ref²
где W = energy_per_depth × core_depth (J), energy_per_depth — output
GetDP Mag2D Resolution.

Pipeline:
  1. PyOM `calculate_core_data(shape, material, gapping)` → core dims
     (E-core processedDescription).
  2. `geometry.emit_e_core_geo(dims)` → .geo (2D-planar front view,
     7 Physical Surfaces + outer Dirichlet boundary).
  3. `gmsh -2 -format msh22 .geo -o .msh` (subprocess).
  4. `pro_template.render(...)` → .pro с substituted params.
  5. `getdp .pro -msh .msh -solve Mag2D` (subprocess).
  6. Parse `energy_per_depth.txt` (Format Table OnGlobal — single value).
  7. Lp = 2 × energy × core_depth / I_ref²

Phase 2C MVP ограничения (documented в `UnsupportedGeometryError`):
- Только E-core shapes (`processedDescription.columns` count ≥ 2,
  `windingWindows` count ≥ 1). Toroidal/U/PQ/EC/RM — T127 BACKLOG.
- Линейный μ_r (default 8000 для Nanoperm-class). Nonlinear B-H —
  T128 BACKLOG.
- Один operating point, не sweep. Multi-OP — будущее follow-up.
"""

from __future__ import annotations

import asyncio
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Any, Literal, get_args

from adapters.outbound.fem_common import (
    ECoreDimensions,
    emit_e_core_geo,
    extract_frohlich_params,
)
from adapters.outbound.fem_solver_getdp.pro_template import (
    render_magnetostatic_pro,
    render_magnetostatic_pro_nonlinear,
)
from domain.material import (
    DEFAULT_NUM_POINTS,
    FrohlichBHCurve,
)
from ports.outbound.magnetic_field_solver import (
    FemSolveOutcome,
    MagneticFieldSolverFailedError,
    MagneticFieldSolverUnavailableError,
    UnsupportedGeometryError,
)

if TYPE_CHECKING:
    from domain.magnetic import MagneticComponent


DELTA_I_FLOOR_A = 0.0001  # абсолютный пол ΔI (A) — 0.1 mA для zero-bias probe
DELTA_I_REL = 0.01  # 1% от |I_dc| — industry standard для incremental-L AC probe
# Revision 2 (T129 Phase B, spec Q1 revision 2): старая формула
# max(0.05·|I_dc|, 0.1 A) miscalibrated для I_dc ≈ 10-100 mA (typical tube
# audio OPT) — floor становился больше I_dc, central diff вырождался в
# secant от нуля. См. spec.md «Q1 — DC-bias method» revision 2.

DEFAULT_MUR_IRON = 8000.0  # Nanoperm-class μ_initial — linear approximation
DEFAULT_I_REF = 1.0  # reference current 1 A для self-inductance

MaterialModel = Literal['linear', 'nonlinear-frohlich']
_VALID_MATERIAL_MODELS: tuple[MaterialModel, ...] = get_args(MaterialModel)


class GetDpFemSolver:
    """
    `MagneticFieldSolver` adapter поверх GetDP+Gmsh subprocesses.

    Args:
        pyom_module: загруженный PyOpenMagnetics (из
            `load_pyopenmagnetics()` PyOM adapter) — для
            `calculate_core_data` чтобы извлечь E-core dimensions
            и `get_core_materials()` для Frohlich-Kennelly параметров.
        gmsh_bin: путь к gmsh binary (default — поиск в PATH).
        getdp_bin: путь к getdp binary (default — поиск в PATH).
        mur_iron: linear relative permeability iron region. По умолчанию
            8000 (Nanoperm-class μ_initial). Используется только в
            `material_model='linear'`.
        material_model: формулировка материала Iron region. `'linear'`
            (back-compat, T113 baseline) — constant μ_r; `'nonlinear-
            frohlich'` (T129) — tabulated ν(B) от Frohlich-Kennelly
            кривой через GetDP `InterpolationLinear` + Picard
            `IterativeLoop`. (μ_initial, B_sat) читаются из PyOM
            `get_core_materials()` для `component.core.material_name`.
        num_bh_points: количество точек в Frohlich BH-таблице
            (default 16; ≥10 по спеке).
        work_dir_root: корень для временных work_dir (mesh, .pro,
            output). None — fresh `TemporaryDirectory` per call.

    """

    def __init__(
        self,
        pyom_module: Any,  # noqa: ANN401  - dynamic .so module
        *,
        gmsh_bin: str = 'gmsh',
        getdp_bin: str = 'getdp',
        mur_iron: float = DEFAULT_MUR_IRON,
        material_model: MaterialModel = 'linear',
        num_bh_points: int = DEFAULT_NUM_POINTS,
        work_dir_root: Path | None = None,
    ) -> None:
        if material_model not in _VALID_MATERIAL_MODELS:
            msg = (
                f'material_model должен быть одним из '
                f'{_VALID_MATERIAL_MODELS!r}, получено {material_model!r}'
            )
            raise ValueError(msg)
        self._pyom = pyom_module
        self._gmsh = gmsh_bin
        self._getdp = getdp_bin
        self._mur_iron = mur_iron
        self._material_model: MaterialModel = material_model
        self._num_bh_points = num_bh_points
        self._work_dir_root = work_dir_root

    @property
    def material_model(self) -> MaterialModel:
        return self._material_model

    async def solve(self, component: MagneticComponent) -> FemSolveOutcome:
        """Async wrapper над blocking subprocess pipeline."""
        return await asyncio.to_thread(self._solve_blocking, component)

    def _solve_blocking(self, component: MagneticComponent) -> FemSolveOutcome:
        core_full = self._compute_core_data(component)
        dims = self._extract_e_core_dims(component, core_full)

        with TemporaryDirectory(
            prefix='efactory-getdp-',
            dir=self._work_dir_root,
        ) as tmp:
            work_dir = Path(tmp)
            geo_path = work_dir / 'geometry.geo'
            msh_path = work_dir / 'geometry.msh'
            geo_path.write_text(emit_e_core_geo(dims))
            self._run_gmsh(geo_path, msh_path, work_dir)

            n_primary = component.primary_winding.number_turns
            area_window = dims.window_w * dims.window_h

            if self._material_model == 'linear':
                return self._solve_linear(
                    work_dir=work_dir,
                    msh_path=msh_path,
                    n_primary=n_primary,
                    area_window=area_window,
                    core_depth=dims.core_depth,
                )
            return self._solve_nonlinear_central_diff(
                component=component,
                work_dir=work_dir,
                msh_path=msh_path,
                n_primary=n_primary,
                area_window=area_window,
                core_depth=dims.core_depth,
            )

    def _solve_linear(
        self,
        *,
        work_dir: Path,
        msh_path: Path,
        n_primary: int,
        area_window: float,
        core_depth: float,
    ) -> FemSolveOutcome:
        """T113 baseline: energy method, L_p = 2·W/I²."""
        pro_path = work_dir / 'magnetostatic.pro'
        energy_path = work_dir / 'energy_per_depth.txt'
        pro_path.write_text(
            render_magnetostatic_pro(
                mur_iron=self._mur_iron,
                n_primary=n_primary,
                i_ref=DEFAULT_I_REF,
                area_window=area_window,
            ),
        )
        self._run_getdp(pro_path, msh_path, work_dir)
        energy_per_depth = self._parse_value(energy_path)
        total_energy = energy_per_depth * core_depth
        l_p = 2.0 * total_energy / (DEFAULT_I_REF**2)
        return FemSolveOutcome(inductance_h=l_p, method='linear')

    def _solve_nonlinear_central_diff(
        self,
        *,
        component: MagneticComponent,
        work_dir: Path,
        msh_path: Path,
        n_primary: int,
        area_window: float,
        core_depth: float,
    ) -> FemSolveOutcome:
        """
        2 nonlinear solve'а вокруг operating point; L_inc = (Φ₊−Φ₋)/ΔI.

        Central finite difference O(ΔI²) использует только outer probes
        (`I_dc ± ΔI/2`). Middle solve `I_dc` спека предусматривала для
        peak_flux_density_t diagnostic, но Phase B оставила peak=None
        (follow-up T-ID); поэтому middle solve удалён — bit-identical
        L_inc, ~33% runtime saved (ultrareview bug_003).
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
        bh_literal = curve.as_getdp_list_literal()

        i_dc = component.operating_point.primary_dc_bias_a
        delta_i = max(DELTA_I_REL * abs(i_dc), DELTA_I_FLOOR_A)
        currents = (
            i_dc - 0.5 * delta_i,
            i_dc + 0.5 * delta_i,
        )

        fluxes = tuple(
            self._run_nonlinear_probe(
                work_dir=work_dir,
                msh_path=msh_path,
                tag=tag,
                bh_literal=bh_literal,
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
            peak_flux_density_t=None,  # diagnostic — follow-up T-ID
        )

    def _run_nonlinear_probe(
        self,
        *,
        work_dir: Path,
        msh_path: Path,
        tag: str,
        bh_literal: str,
        n_primary: int,
        i_value: float,
        area_window: float,
        core_depth: float,
    ) -> float:
        """Один nonlinear solve в subdir, возвращает Ψ (полный, не per-depth)."""
        sub_dir = work_dir / f'solve_{tag}'
        sub_dir.mkdir()
        pro_path = sub_dir / 'magnetostatic.pro'
        flux_path = sub_dir / 'flux_linkage.txt'
        pro_path.write_text(
            render_magnetostatic_pro_nonlinear(
                bh_list_literal=bh_literal,
                n_primary=n_primary,
                i_ref=i_value,
                area_window=area_window,
            ),
        )
        self._run_getdp(pro_path, msh_path, sub_dir)
        flux_per_depth = self._parse_value(flux_path)
        return flux_per_depth * core_depth

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
                f'Phase 2C adapter поддерживает только E-core shapes; '
                f'shape={component.core.shape_name!r} не имеет ожидаемой '
                f'структуры processedDescription (columns/windingWindows): '
                f'{exc}'
            )
            raise UnsupportedGeometryError(msg) from exc

    def _run_gmsh(self, geo: Path, msh: Path, cwd: Path) -> None:
        try:
            res = subprocess.run(
                [
                    self._gmsh,
                    '-2',
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

    def _run_getdp(self, pro: Path, msh: Path, cwd: Path) -> None:
        try:
            res = subprocess.run(
                [
                    self._getdp,
                    str(pro),
                    '-msh',
                    str(msh),
                    '-solve',
                    'Mag2D',
                ],
                cwd=cwd,
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:
            msg = (
                f'getdp binary {self._getdp!r} не найден в PATH; '
                f'установите getdp apt-package'
            )
            raise MagneticFieldSolverUnavailableError(msg) from exc
        if res.returncode != 0:
            msg = f'getdp failed (rc={res.returncode}): stderr={res.stderr[-500:]!r}'
            raise MagneticFieldSolverFailedError(msg)

    @staticmethod
    def _parse_value(out_path: Path) -> float:
        """Last float in last non-empty line of GetDP `Print[ ..., Format Table ]`."""
        if not out_path.exists():
            msg = f'getdp не создал {out_path.name} — PostOperation failed?'
            raise MagneticFieldSolverFailedError(msg)
        text = out_path.read_text()
        for line in reversed(text.splitlines()):
            tokens = line.split()
            if not tokens:
                continue
            for tok in reversed(tokens):
                try:
                    return float(tok)
                except ValueError:
                    continue
        msg = f'{out_path.name} не содержит float values: {text!r}'
        raise MagneticFieldSolverFailedError(msg)
