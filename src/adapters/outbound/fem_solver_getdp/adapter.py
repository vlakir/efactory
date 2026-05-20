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

from adapters.outbound.fem_solver_getdp.geometry import (
    ECoreDimensions,
    emit_e_core_geo,
)
from adapters.outbound.fem_solver_getdp.material import (
    DEFAULT_NUM_POINTS,
    FrohlichBHCurve,
)
from adapters.outbound.fem_solver_getdp.pro_template import (
    render_magnetostatic_pro,
    render_magnetostatic_pro_nonlinear,
)
from ports.outbound.magnetic_field_solver import (
    MagneticFieldSolverFailedError,
    MagneticFieldSolverUnavailableError,
    UnsupportedGeometryError,
)

if TYPE_CHECKING:
    from domain.magnetic import MagneticComponent

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

    async def solve_inductance(self, component: MagneticComponent) -> float:
        """Async wrapper над blocking subprocess pipeline."""
        return await asyncio.to_thread(self._solve_blocking, component)

    def _solve_blocking(self, component: MagneticComponent) -> float:
        core_full = self._compute_core_data(component)
        dims = self._extract_e_core_dims(component, core_full)

        with TemporaryDirectory(
            prefix='efactory-getdp-',
            dir=self._work_dir_root,
        ) as tmp:
            work_dir = Path(tmp)
            geo_path = work_dir / 'geometry.geo'
            msh_path = work_dir / 'geometry.msh'
            pro_path = work_dir / 'magnetostatic.pro'
            energy_path = work_dir / 'energy_per_depth.txt'

            geo_path.write_text(emit_e_core_geo(dims))
            # area_window = window_w × window_h (m²); J_density считается в .pro
            pro_path.write_text(
                self._render_pro(
                    component=component,
                    n_primary=component.primary_winding.number_turns,
                    area_window=dims.window_w * dims.window_h,
                ),
            )

            self._run_gmsh(geo_path, msh_path, work_dir)
            self._run_getdp(pro_path, msh_path, work_dir)

            energy_per_depth = self._parse_energy(energy_path)
            total_energy = energy_per_depth * dims.core_depth
            return 2.0 * total_energy / (DEFAULT_I_REF**2)

    def _render_pro(
        self,
        component: MagneticComponent,
        n_primary: int,
        area_window: float,
    ) -> str:
        """Выбор linear vs nonlinear-Frohlich .pro по `material_model`."""
        if self._material_model == 'linear':
            return render_magnetostatic_pro(
                mur_iron=self._mur_iron,
                n_primary=n_primary,
                i_ref=DEFAULT_I_REF,
                area_window=area_window,
            )
        mu_initial, b_sat = self._extract_frohlich_params(
            component.core.material_name,
        )
        curve = FrohlichBHCurve.from_pyom_material(
            mu_initial=mu_initial,
            b_sat=b_sat,
            num_points=self._num_bh_points,
        )
        return render_magnetostatic_pro_nonlinear(
            bh_list_literal=curve.as_getdp_list_literal(),
            n_primary=n_primary,
            i_ref=DEFAULT_I_REF,
            area_window=area_window,
        )

    def _extract_frohlich_params(self, material_name: str) -> tuple[float, float]:
        """
        Read (mu_initial, B_sat) из PyOM `get_core_materials()`.

        PyOM 1.3.10 MAS schema:
        - `material.permeability.initial` обычно list (varies frequency),
          но может быть dict в старых данных. Берём первое entry
          (low-frequency, temperature=25°C по convention).
        - `material.saturation` обычно list (varies temperature) с
          `magneticFluxDensity` ключом; может быть dict. Берём первое.

        Raises:
            LookupError: если material не найден, либо required поля
                пусты/отсутствуют.

        """
        for mat in self._pyom.get_core_materials():
            if mat.get('name') == material_name:
                return (
                    _read_initial_permeability(mat, material_name),
                    _read_saturation_flux_density(mat, material_name),
                )
        msg = (
            f'material {material_name!r} не найден в PyOM catalog (get_core_materials)'
        )
        raise LookupError(msg)

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
    def _parse_energy(energy_path: Path) -> float:
        if not energy_path.exists():
            msg = f'getdp не создал {energy_path.name} — PostOperation failed?'
            raise MagneticFieldSolverFailedError(msg)
        # Format Table OnGlobal scalar — последняя non-empty строка с числами,
        # последний валидный float — energy per depth (J/m). Pilot Stage B+C
        # парсинг логика.
        text = energy_path.read_text()
        for line in reversed(text.splitlines()):
            tokens = line.split()
            if not tokens:
                continue
            for tok in reversed(tokens):
                try:
                    return float(tok)
                except ValueError:
                    continue
        msg = f'energy_per_depth.txt не содержит float values: {text!r}'
        raise MagneticFieldSolverFailedError(msg)


def _first_entry(
    raw: object,
    field_path: str,
    material_name: str,
) -> dict[str, Any]:
    """
    Извлечь первое (или единственное) entry из PyOM list/dict-поля.

    LookupError — поле пусто или отсутствует.
    TypeError    — поле есть, но shape не list/dict (malformed material data).
    """
    if isinstance(raw, list):
        if not raw:
            msg = f'material {material_name!r}: {field_path} список пуст'
            raise LookupError(msg)
        return raw[0]
    if isinstance(raw, dict):
        return raw
    if raw is None:
        msg = f'material {material_name!r}: {field_path} отсутствует'
        raise LookupError(msg)
    msg = (
        f'material {material_name!r}: {field_path} имеет неожиданный shape '
        f'({type(raw).__name__}); ожидался list или dict'
    )
    raise TypeError(msg)


def _read_initial_permeability(mat: dict[str, Any], material_name: str) -> float:
    """Pull `permeability.initial[0].value` (or scalar dict fallback)."""
    perm = mat.get('permeability') or {}
    entry = _first_entry(perm.get('initial'), 'permeability.initial', material_name)
    value = entry.get('value')
    if value is None:
        msg = f'material {material_name!r}: permeability.initial[0].value is null'
        raise LookupError(msg)
    return float(value)


def _read_saturation_flux_density(mat: dict[str, Any], material_name: str) -> float:
    """Pull `saturation[0].magneticFluxDensity` (or scalar dict fallback)."""
    entry = _first_entry(mat.get('saturation'), 'saturation', material_name)
    b_sat = entry.get('magneticFluxDensity')
    if b_sat is None:
        msg = f'material {material_name!r}: saturation[0].magneticFluxDensity is null'
        raise LookupError(msg)
    return float(b_sat)
