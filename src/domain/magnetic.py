"""
MagneticComponent / MagneticVerificationResult — T113 Phase 2 domain VO.

Magnetic toolkit для efactory: представление магнитного компонента
(core + обмотки + operating point) и результат верификации индуктивности
(analytical от PyOpenMagnetics + опциональный FEM cross-check от GetDP).

Domain-уровень — без знания о PyOM MAS-schema или GetDP .pro формате.
Адаптеры конвертируют MagneticComponent в свои внутренние представления.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

_FROZEN = ConfigDict(frozen=True, extra='forbid')

# Threshold ±10% для acceptance "FEM matches analytical" — см. T113 spec
# §"Decision criteria" и Phase 2 acceptance.
DEFAULT_DISCREPANCY_THRESHOLD = 0.10


class GapType(StrEnum):
    """Тип воздушного зазора в магнитном сердечнике."""

    SUBTRACTIVE = 'subtractive'  # gap вырезан из материала (стандарт E-core)
    ADDITIVE = 'additive'  # gap добавлен между двумя половинами
    RESIDUAL = 'residual'  # остаточный gap по технологии


class IsolationSide(StrEnum):
    """Сторона изоляции обмотки (соответствует PyOM convention)."""

    PRIMARY = 'primary'
    SECONDARY = 'secondary'


class Core(BaseModel):
    """
    Магнитный сердечник: shape + material + gapping.

    `shape_name` и `material_name` — это имена из PyOpenMagnetics catalog
    (см. `get_core_shape_names()`, `get_core_material_names()`). Адаптеры
    лукапят полное описание сердечника через PyOM API.
    """

    model_config = _FROZEN

    shape_name: str = Field(..., min_length=1)
    material_name: str = Field(..., min_length=1)
    # PyOM bobbin catalog name (e.g. "Bobbin E42/15"). PyOM
    # calculate_inductance_from_number_turns_and_gapping валидирует
    # наличие bobbin в coil; адаптер выполняет lookup через PyOM
    # get_bobbins(). None — для use cases без PyOM-обвязки (например,
    # raw FEM с готовой mesh).
    bobbin_name: str | None = None
    gap_length_m: Annotated[float, Field(ge=0)] = 0.0
    gap_type: GapType = GapType.SUBTRACTIVE


class Winding(BaseModel):
    """Одна обмотка магнитного компонента."""

    model_config = _FROZEN

    name: str = Field(..., min_length=1)
    number_turns: Annotated[int, Field(ge=1)]
    isolation_side: IsolationSide
    # PyOM wire catalog name; None — адаптер выбирает sane default
    wire_name: str | None = None


class OperatingPoint(BaseModel):
    """Электрический рабочий режим magnetic component."""

    model_config = _FROZEN

    name: str = 'default'
    frequency_hz: Annotated[float, Field(gt=0)]
    ambient_temperature_c: float = 25.0
    # Primary winding excitation (упрощённое представление для MVP).
    primary_peak_voltage_v: Annotated[float, Field(ge=0)]
    primary_dc_bias_a: float = 0.0
    primary_ac_peak_a: Annotated[float, Field(ge=0)] = 0.0


class MagneticComponent(BaseModel):
    """Полная спецификация магнитного компонента для analytical+FEM расчётов."""

    model_config = _FROZEN

    name: str = Field(..., min_length=1)
    core: Core
    windings: tuple[Winding, ...] = Field(..., min_length=1)
    operating_point: OperatingPoint

    @property
    def primary_winding(self) -> Winding:
        """Первая обмотка с isolation_side=PRIMARY (raises если нет)."""
        for w in self.windings:
            if w.isolation_side is IsolationSide.PRIMARY:
                return w
        msg = f'no primary winding in component {self.name!r}'
        raise ValueError(msg)


class MagneticVerificationResult(BaseModel):
    """
    Результат расчёта индуктивности с опциональной FEM-верификацией.

    `analytical_inductance_h` — обязательное поле (фастпуть PyOM).
    `fem_inductance_h` — None, если FEM не запускался (verify_with_fem=False).
    `relative_difference` — |FEM - analytical| / analytical; None если FEM не было.
    `discrepancy_flagged` — True, если relative_difference > threshold
    (default 10%, см. `DEFAULT_DISCREPANCY_THRESHOLD`).
    """

    model_config = _FROZEN

    component_name: str = Field(..., min_length=1)
    analytical_inductance_h: Annotated[float, Field(ge=0)]
    fem_inductance_h: Annotated[float, Field(ge=0)] | None = None
    relative_difference: Annotated[float, Field(ge=0)] | None = None
    discrepancy_flagged: bool = False
    discrepancy_threshold: Annotated[float, Field(gt=0)] = DEFAULT_DISCREPANCY_THRESHOLD
