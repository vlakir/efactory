"""
Elmer FEM 2D-planar magnetostatic adapter (T133 Phase 1 — linear mode).

Реализует `MagneticFieldSolver` outbound port методом energy / J·A:
  W_per_depth = 0.5 · J_density · ∫_Primary A_z dA   (single-coil)
  Lp = 2 · W_per_depth · core_depth / I_ref²

Параллельный к `GetDpFemSolver` (T113/T129): тот же port, та же mesh
pipeline (Gmsh `.msh` через `ElmerGrid 14 2 -autoclean -out`), отличается
solver backend и outer BC treatment (Infinity BC vs Dirichlet).

Phase 1 ограничения:
- **Linear `material_model='linear'` only.** Nonlinear `H-B Curve` —
  Phase 2.
- E-core shapes (через `ECoreDimensions.from_pyom_core`); другие shape
  classes — будущее follow-up.
- One operating point, не sweep.
- Single-coil topology: только Primary энергизована (`+Jz`), Secondary
  трактуется как air (no source). Отличается от T113 split-coil.

Pipeline:
  1. PyOM `calculate_core_data(shape, material, gapping)` → core dims.
  2. `emit_e_core_geo(dims)` → .geo (shared с GetDP).
  3. `gmsh -2 -format msh22 .geo -o .msh` (subprocess).
  4. `ElmerGrid 14 2 .msh -autoclean -out mesh-elmer/` (subprocess —
     auto-memory feedback_elmer_2d_keyword_pitfalls: -autoclean
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
)
from adapters.outbound.fem_solver_elmer.sif_template import (
    render_magnetostatic_sif_linear,
)
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

# Phase 1 = linear-only. Phase 2 добавит 'nonlinear-frohlich' literal.
MaterialModel = Literal['linear']
_VALID_MATERIAL_MODELS: tuple[MaterialModel, ...] = get_args(MaterialModel)


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
        material_model: формулировка материала. Phase 1 — только
            `'linear'`; Phase 2 добавит `'nonlinear-frohlich'`.
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
        self._elmer_grid = elmer_grid_bin
        self._elmer_solver = elmer_solver_bin
        self._mur_iron = mur_iron
        self._material_model: MaterialModel = material_model
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
            prefix='efactory-elmer-',
            dir=self._work_dir_root,
        ) as tmp:
            work_dir = Path(tmp)
            geo_path = work_dir / 'geometry.geo'
            msh_path = work_dir / 'geometry.msh'
            geo_path.write_text(emit_e_core_geo(dims))
            self._run_gmsh(geo_path, msh_path, work_dir)
            self._run_elmer_grid(msh_path, work_dir)

            n_primary = component.primary_winding.number_turns
            area_window = dims.window_w * dims.window_h
            return self._solve_linear(
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
