"""
PyOM-catalog-based geometry resolution для analytical leakage (T132 Phase C).

Extracts core dims, winding window, wire outer diameter, и computes
estimated winding thickness через PyOM lookup paths (`calculate_core_
data`, `find_wire_by_name`) — все catalog-only, без FEM mesh (mesh
backend broken, см. T135).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from domain.magnetic import MagneticComponent


class GeometryResolutionError(Exception):
    """Не удалось извлечь геометрию из PyOM catalog."""


class CoreGeometry(BaseModel):
    """
    Резолверный результат: scalar dims из PyOM catalog в одном VO.

    Все поля в метрах:
    - `column_width_m` — радиальная ширина центрального столба (E-core
      dimension `F`).
    - `column_depth_m` — длина пакета (stack length, PyOM
      `processedDescription.depth`).
    - `window_height_m` — высота winding window в axial направлении
      (= b_w в Erickson formula).
    - `window_width_m` — радиальная ширина winding window.
    - `mean_turn_length_m` — приблизительный MLT для расчёта Lσ.
    """

    model_config = ConfigDict(frozen=True, extra='forbid')

    column_width_m: float = Field(..., gt=0)
    column_depth_m: float = Field(..., gt=0)
    window_height_m: float = Field(..., gt=0)
    window_width_m: float = Field(..., gt=0)
    mean_turn_length_m: float = Field(..., gt=0)


def _extract_dim_m(dim: dict[str, Any], name: str) -> float:
    """
    PyOM dimension struct ({min, max, nominal}) → scalar [m].

    Predence: nominal > avg(min, max) > min/max alone. Raise если
    нет ни одного валидного значения.
    """
    nominal = dim.get('nominal')
    if nominal is not None:
        return float(nominal)
    minv = dim.get('minimum')
    maxv = dim.get('maximum')
    if minv is not None and maxv is not None:
        return (float(minv) + float(maxv)) / 2.0
    if minv is not None:
        return float(minv)
    if maxv is not None:
        return float(maxv)
    msg = f'PyOM dimension {name!r} has no scalar value: {dim}'
    raise GeometryResolutionError(msg)


def resolve_wire_outer_diameter_m(pyom_module: Any, wire_name: str) -> float:  # noqa: ANN401
    """Look up outer (enamelled) wire diameter в catalog [m]."""
    try:
        wire = pyom_module.find_wire_by_name(wire_name)
    except Exception as exc:
        msg = f'PyOM wire lookup {wire_name!r} failed: {exc}'
        raise GeometryResolutionError(msg) from exc
    if not isinstance(wire, dict):
        msg = (
            f'PyOM find_wire_by_name {wire_name!r} returned non-dict: '
            f'{type(wire).__name__}'
        )
        raise GeometryResolutionError(msg)
    od = wire.get('outerDiameter')
    if not isinstance(od, dict):
        msg = f'PyOM wire {wire_name!r} has no outerDiameter dict'
        raise GeometryResolutionError(msg)
    return _extract_dim_m(od, 'outerDiameter')


def resolve_core_geometry(
    pyom_module: Any,  # noqa: ANN401
    component: MagneticComponent,
) -> CoreGeometry:
    """
    Извлечь геометрические dims через PyOM `calculate_core_data`.

    Возвращает `CoreGeometry`. Raises `GeometryResolutionError` если
    PyOM ответ не содержит ожидаемых полей (например, нестандартная
    форма сердечника без `F` dimension).
    """
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
        core_full = pyom_module.calculate_core_data(core_fd, True)  # noqa: FBT003
    except Exception as exc:
        msg = (
            f'PyOM calculate_core_data failed для '
            f'{component.core.shape_name!r}/{component.core.material_name!r}: '
            f'{exc}'
        )
        raise GeometryResolutionError(msg) from exc

    pd = core_full.get('processedDescription') or {}
    fd = core_full.get('functionalDescription') or {}
    shape = fd.get('shape') or {}
    shape_dims = shape.get('dimensions') or {}

    f_dim = shape_dims.get('F')
    if not isinstance(f_dim, dict):
        msg = (
            f'PyOM core {component.core.shape_name!r} missing dimension '
            f'F (central pillar radial width)'
        )
        raise GeometryResolutionError(msg)
    column_width_m = _extract_dim_m(f_dim, 'F')

    depth = pd.get('depth')
    if depth is None or depth <= 0:
        msg = (
            f'PyOM core {component.core.shape_name!r} missing valid '
            f'processedDescription.depth (stack length)'
        )
        raise GeometryResolutionError(msg)
    column_depth_m = float(depth)

    ww_list = pd.get('windingWindows') or []
    if not ww_list:
        msg = (
            f'PyOM core {component.core.shape_name!r} has empty '
            f'processedDescription.windingWindows'
        )
        raise GeometryResolutionError(msg)
    ww = ww_list[0]
    window_height_m = float(ww.get('height') or 0)
    window_width_m = float(ww.get('width') or 0)
    if window_height_m <= 0 or window_width_m <= 0:
        msg = (
            f'PyOM core {component.core.shape_name!r} windingWindow '
            f'has non-positive dims: height={window_height_m}, '
            f'width={window_width_m}'
        )
        raise GeometryResolutionError(msg)

    # MLT approximation: perimeter of bobbin column cross-section.
    # Hurley §4.4: MLT ≈ 2·(column_w + column_d) + π·avg_winding_radial_offset.
    # Для conservative estimate без знания winding thickness, используем
    # window_width_m / 2 как proxy для среднего radial offset.
    mlt = 2.0 * (column_width_m + column_depth_m) + math.pi * (window_width_m / 2.0)

    return CoreGeometry(
        column_width_m=column_width_m,
        column_depth_m=column_depth_m,
        window_height_m=window_height_m,
        window_width_m=window_width_m,
        mean_turn_length_m=mlt,
    )


def estimate_winding_thickness_m(
    *,
    total_turns: int,
    wire_outer_diameter_m: float,
    window_height_m: float,
) -> float:
    """
    Оценить радиальную толщину обмотки в окне.

    `b_p_or_s = layers × wire_OD`, где `layers = ceil(total_turns /
    floor(window_height / wire_OD))`. Это conservative estimate без
    учёта inter-layer insulation и fill-factor coupling — точность
    в пределах ±20-30%, что попадает в spec acceptance ±25%.

    Returns 0.0 для `total_turns == 0`. Raises `GeometryResolutionError`
    если wire OD >= window_height (физически не помещается).
    """
    if total_turns == 0:
        return 0.0
    if wire_outer_diameter_m <= 0:
        msg = f'wire_outer_diameter_m must be > 0 (got {wire_outer_diameter_m})'
        raise GeometryResolutionError(msg)
    if wire_outer_diameter_m >= window_height_m:
        msg = (
            f'wire OD {wire_outer_diameter_m} >= window height '
            f'{window_height_m} — wire too thick for bobbin'
        )
        raise GeometryResolutionError(msg)

    turns_per_layer = int(window_height_m // wire_outer_diameter_m)
    if turns_per_layer == 0:
        msg = (
            f'wire OD {wire_outer_diameter_m} too close to window height '
            f'{window_height_m}: turns_per_layer rounds to 0'
        )
        raise GeometryResolutionError(msg)
    layers = math.ceil(total_turns / turns_per_layer)
    return layers * wire_outer_diameter_m
