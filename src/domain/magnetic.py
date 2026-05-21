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
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

FemMethod = Literal['linear', 'nonlinear-frohlich']

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


class WindingSection(BaseModel):
    """
    Одна секция в interleaved sandwich-намотке (T132).

    `winding_name` ссылается на `Winding.name` родительского компонента
    (валидируется в `MagneticComponent`). `layer_count=None` — adapter
    позволяет PyOM автоматически распределить turns между секциями
    с одинаковым именем.
    """

    model_config = _FROZEN

    winding_name: str = Field(..., min_length=1)
    layer_count: Annotated[int, Field(ge=1)] | None = None


class InterleavingPattern(BaseModel):
    """
    Sandwich-секционный layout обмоток на bobbin'е (T132).

    `sections` — физический порядок секций (например, P-S-P-S-P для
    типового 5-section hi-end audio OPT). PyOM `wind` использует единые
    inter-section insulation и bobbin margin для всей конструкции —
    per-section overrides пока вне scope (PyOM API ограничение,
    см. probe T132 Analyze §W3).
    """

    model_config = _FROZEN

    sections: tuple[WindingSection, ...] = Field(..., min_length=1)
    inter_section_thickness_m: Annotated[float, Field(ge=0)] = 25e-6
    bobbin_margin_m: Annotated[float, Field(ge=0)] = 0.001

    @property
    def pattern(self) -> tuple[str, ...]:
        """Имена обмоток в физическом порядке секций (read-only view)."""
        return tuple(s.winding_name for s in self.sections)


class MagneticComponent(BaseModel):
    """Полная спецификация магнитного компонента для analytical+FEM расчётов."""

    model_config = _FROZEN

    name: str = Field(..., min_length=1)
    core: Core
    windings: tuple[Winding, ...] = Field(..., min_length=1)
    operating_point: OperatingPoint
    # T132: опциональный sandwich-layout. None → backward compat для
    # T113/T129 use cases (magnetizing inductance / FEM), которые работают
    # без layered coil. Required для `analyze_interleaved_leakage`.
    section_layout: InterleavingPattern | None = None

    @model_validator(mode='after')
    def _validate_section_layout_names(self) -> Self:
        if self.section_layout is None:
            return self
        winding_names = {w.name for w in self.windings}
        for section in self.section_layout.sections:
            if section.winding_name not in winding_names:
                msg = (
                    f'section_layout references unknown winding '
                    f'{section.winding_name!r}; '
                    f'available windings: {sorted(winding_names)}'
                )
                raise ValueError(msg)
        return self

    @property
    def primary_winding(self) -> Winding:
        """Первая обмотка с isolation_side=PRIMARY (raises если нет)."""
        for w in self.windings:
            if w.isolation_side is IsolationSide.PRIMARY:
                return w
        msg = f'no primary winding in component {self.name!r}'
        raise ValueError(msg)


class LeakageInductanceResult(BaseModel):
    """
    Результат расчёта leakage inductance Lσ (T132).

    `source_winding` — имя обмотки, относительно которой считается
    leakage; `leakage_to[target]` — Lσ от source к target [H].
    Для пары (primary, secondary) содержит ровно один элемент.
    `coupling_factor` k ∈ [0, 1]: k = √(1 - Lσ/L_self) (идеальный
    трансформатор → k=1, полностью развязанный → k=0).
    """

    model_config = _FROZEN

    source_winding: str = Field(..., min_length=1)
    leakage_to: dict[str, Annotated[float, Field(ge=0)]] = Field(..., min_length=1)
    coupling_factor: Annotated[float, Field(ge=0, le=1)]


class MagneticVerificationResult(BaseModel):
    """
    Результат расчёта индуктивности с опциональной FEM-верификацией.

    `analytical_inductance_h` — обязательное поле (фастпуть PyOM).
    `fem_inductance_h` — None, если FEM не запускался (verify_with_fem=False).
    `relative_difference` — |FEM - analytical| / analytical; None если FEM не было.
    `discrepancy_flagged` — True, если relative_difference > threshold
    (default 10%, см. `DEFAULT_DISCREPANCY_THRESHOLD`).
    `fem_method` — выбранная FEM формулировка ("linear" или
    "nonlinear-frohlich"); None если FEM не запускался. Diagnostic поле
    из T129 — для downstream consumer'ов и логов.
    `peak_flux_density_t` — max |B| в Iron region [T]; None если FEM
    не запускался или диагностика не реализована (T129 Phase B —
    оставлено как None, реализация через GetDP point sampling
    в follow-up).
    """

    model_config = _FROZEN

    component_name: str = Field(..., min_length=1)
    analytical_inductance_h: Annotated[float, Field(ge=0)]
    fem_inductance_h: Annotated[float, Field(ge=0)] | None = None
    relative_difference: Annotated[float, Field(ge=0)] | None = None
    discrepancy_flagged: bool = False
    discrepancy_threshold: Annotated[float, Field(gt=0)] = DEFAULT_DISCREPANCY_THRESHOLD
    fem_method: FemMethod | None = None
    peak_flux_density_t: Annotated[float, Field(ge=0)] | None = None
