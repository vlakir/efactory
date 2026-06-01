"""
Phase-margin domain VOs (T153 Phase B.1).

Четыре frozen Pydantic-VO для use case `measure_phase_margin` и
auto-detect feedback loop:

* `PhaseMarginMeasurement` — основной результат: PM в градусах,
  частота unity-gain crossover, метод injection, класс стабильности.
* `PhaseMarginDelta` — T021 family pattern: обёртка над парой
  `(before, after)`. Хранит уже вычисленную дельту по `margin_deg`.
* `AutoDetectInfo` — результат graph analyzer auto-detect break node.
* `FeedbackCycle` — internal VO graph analyzer, описывает один цикл
  обратной связи: ноды, элементы, suggested break point + confidence.

Inheritance / коды-DRY заметка: `_validate_after_consistency` и
`_compute_relative_percent` — повтор аналогов из `measurement_delta`
для избежания cross-module private import (T153 BACKLOG: consolidate
при добавлении 5-го Delta-типа либо в Phase F refactor).

Domain — без знания о JSON-сериализации; ответственность renderer'а.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from domain.simulation import AcSweep

_FROZEN = ConfigDict(frozen=True, extra='forbid')


InjectionMethod = Literal[
    'middlebrook_voltage',
    'middlebrook_current',
    'tian',
    'rosenstark_return_ratio',
]


StabilityClass = Literal['high', 'adequate', 'marginal', 'risky']


# ----------------------------------------------------- domain errors ----


class LoopBreakNodeNotFoundError(ValueError):
    """
    Explicit break edge `(node, element_ref)` не найден в netlist'е.

    Raised when:
    * `break_element_ref` отсутствует в top-level элементных строках;
    * `break_node` отсутствует среди pin'ов указанного элемента.

    Phase B.4: explicit-override-only path. В Phase B.5 auto-detect
    может raise тот же error при rejected confidence (для consistency).
    """


class NoUnityGainCrossoverError(ValueError):
    """
    Loop gain `|T(jω)|` нигде не пересекает unity (0 dB) сверху вниз.

    Включает edge cases:
    * `|T|` всегда ≤ 1 во всём свеппе (Spec Q5=a — «loop gain below
      unity; nothing to measure»);
    * `|T|` поднимается выше 1 и обратно опускается, но без чистого
      DOWNWARD crossing'а 0 dB (non-monotonic edge case).

    Не путать с `LoopGainAlwaysAboveUnityError`: тот — для случая когда
    `|T|` всегда > 1.
    """


class LoopGainAlwaysAboveUnityError(ValueError):
    """
    Loop gain `|T(jω)|` всегда > 1 во всём свеппе.

    Spec Q5=c — actionable error: «расширь `--f-high`». Crossover лежит
    за верхней границей текущего sweep'а.
    """


class NoFeedbackLoopDetectedError(ValueError):
    """
    Auto-detect не нашёл feedback loop в netlist'е.

    Spec Q3=b — actionable error: «no feedback loop detected; if loop
    exists, please pass --loop-break-node + --loop-break-element
    explicitly». Raised в `detect_feedback_break_node` use case'е
    (Phase B.5).
    """


class AutoDetectConfidenceTooLowError(ValueError):
    """
    Auto-detect нашёл feedback loop, но confidence ниже threshold.

    Spec §3 «Loop break», C4 convention — в non-TTY caller получает
    actionable error «auto-detect confidence below threshold, please
    pass --loop-break-node + --loop-break-element explicitly».

    В TTY-mode use case вместо этой ошибки возвращает confirmation
    prompt (Phase B.6).
    """


class AutoDetectRejectedError(ValueError):
    """
    Auto-detect нашёл feedback loop, но caller-provided confirmation
    callback вернул False.

    Phase B.5.x — `measure_phase_margin` делегирует threshold policy
    callback'у (W7 lean: `Callable[[AutoDetectInfo], bool]`). Если
    callback решает отклонить кандидата (низкая confidence в non-TTY,
    user отказался в interactive TTY и т.п.) — use case прерывается
    этой ошибкой. Сообщение содержит chosen edge + confidence для
    actionable CLI hint.
    """


# Spec §5 (Clarify Q10=b) stability thresholds в градусах.
_STABILITY_HIGH_MIN_DEG = 60.0
_STABILITY_ADEQUATE_MIN_DEG = 45.0
_STABILITY_MARGINAL_MIN_DEG = 30.0


def _expected_stability_class(margin_deg: float) -> StabilityClass:
    """Mapping margin → stability class (Spec §5, Q10=b)."""
    if margin_deg > _STABILITY_HIGH_MIN_DEG:
        return 'high'
    if margin_deg > _STABILITY_ADEQUATE_MIN_DEG:
        return 'adequate'
    if margin_deg > _STABILITY_MARGINAL_MIN_DEG:
        return 'marginal'
    return 'risky'


def _compute_relative_percent(
    before_value: float,
    after_value: float,
) -> float | None:
    if before_value == 0.0:
        return None
    return ((after_value - before_value) / before_value) * 100.0


# ----------------------------------------------------- AutoDetectInfo ----


class AutoDetectInfo(BaseModel):
    """
    Результат auto-detect break edge графовым анализатором.

    Edge определяется парой `(chosen_node, chosen_element_ref)` —
    ровно один wire в circuit graph (ADR-T153d, 2026-06-01).
    """

    model_config = _FROZEN

    chosen_node: Annotated[str, Field(min_length=1)]
    chosen_element_ref: Annotated[str, Field(min_length=1)]
    confidence: Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]
    alternatives: tuple[tuple[str, str, float], ...] = ()
    algorithm_notes: str = ''

    @model_validator(mode='after')
    def _check_alternatives(self) -> Self:
        for idx, (node, element_ref, conf) in enumerate(self.alternatives):
            if not node:
                msg = (
                    f'AutoDetectInfo.alternatives[{idx}]: node name must '
                    f'be a non-empty string.'
                )
                raise ValueError(msg)
            if not element_ref:
                msg = (
                    f'AutoDetectInfo.alternatives[{idx}]: element_ref must '
                    f'be a non-empty string.'
                )
                raise ValueError(msg)
            if math.isnan(conf):
                msg = f'AutoDetectInfo.alternatives[{idx}]: confidence must not be NaN.'
                raise ValueError(msg)
            if not (0.0 <= conf <= 1.0):
                msg = (
                    f'AutoDetectInfo.alternatives[{idx}]: confidence '
                    f'{conf!r} must be in [0, 1].'
                )
                raise ValueError(msg)
        return self


# `measure_phase_margin` auto-detect path передаёт `AutoDetectInfo`
# в callback; True → accept, False → `AutoDetectRejectedError`.
# W7 (T153 spec analyze): callable type alias, не Protocol/ABC —
# one-method interface, port overkill.
type ConfirmationCallback = Callable[[AutoDetectInfo], bool]


# ------------------------------------------------------- FeedbackCycle ----


class FeedbackCycle(BaseModel):
    """
    Один цикл обратной связи в схеме (internal к graph analyzer).

    Используется как промежуточное VO между `parse(netlist)` и
    `score_break_candidates(cycles)` (ADR-T153b).

    Suggested break edge — пара `(suggested_break_node,
    suggested_break_element_ref)` (ADR-T153d, 2026-06-01).
    """

    model_config = _FROZEN

    nodes: tuple[str, ...] = Field(min_length=1)
    elements: tuple[str, ...] = Field(min_length=1)
    forward_path_score: Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]
    feedback_path_score: Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]
    suggested_break_node: Annotated[str, Field(min_length=1)]
    suggested_break_element_ref: Annotated[str, Field(min_length=1)]
    confidence: Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]

    @model_validator(mode='after')
    def _check_break_node_in_nodes(self) -> Self:
        if self.suggested_break_node not in self.nodes:
            msg = (
                f'FeedbackCycle: suggested_break_node '
                f'{self.suggested_break_node!r} not in nodes '
                f'{list(self.nodes)!r}.'
            )
            raise ValueError(msg)
        return self

    @model_validator(mode='after')
    def _check_break_element_in_elements(self) -> Self:
        if self.suggested_break_element_ref not in self.elements:
            msg = (
                f'FeedbackCycle: suggested_break_element_ref '
                f'{self.suggested_break_element_ref!r} not in elements '
                f'{list(self.elements)!r}.'
            )
            raise ValueError(msg)
        return self


# ---------------------------------------------- PhaseMarginMeasurement ----


class PhaseMarginMeasurement(BaseModel):
    """
    Phase margin одной точки измерения для feedback-схемы.

    `margin_deg = 180° + phase_at_unity_crossover` (Spec §5).
    Стабильность маркируется `stability_class` (Spec Q10=b mapping).
    """

    model_config = _FROZEN

    margin_deg: Annotated[float, Field(ge=-180.0, le=360.0, allow_inf_nan=False)]
    crossover_hz: Annotated[float, Field(gt=0.0, allow_inf_nan=False)]
    measured_at_node: Annotated[str, Field(min_length=1)]
    injection_method: InjectionMethod
    stability_class: StabilityClass
    gain_margin_db: Annotated[float | None, Field(allow_inf_nan=False)] = None
    phase_crossover_hz: Annotated[float | None, Field(gt=0.0, allow_inf_nan=False)] = (
        None
    )
    extra_crossovers_hz: tuple[float, ...] = ()
    sweep_dataset: AcSweep | None = None
    auto_detect_info: AutoDetectInfo | None = None

    @model_validator(mode='after')
    def _check_stability_class_consistent(self) -> Self:
        expected = _expected_stability_class(self.margin_deg)
        if self.stability_class != expected:
            msg = (
                f'PhaseMarginMeasurement: stability_class '
                f'{self.stability_class!r} inconsistent with margin_deg '
                f'{self.margin_deg!r} (expected {expected!r}).'
            )
            raise ValueError(msg)
        return self

    @model_validator(mode='after')
    def _check_extra_crossovers_positive(self) -> Self:
        for idx, value in enumerate(self.extra_crossovers_hz):
            if math.isnan(value):
                msg = (
                    f'PhaseMarginMeasurement.extra_crossovers_hz[{idx}]: '
                    f'must not be NaN.'
                )
                raise ValueError(msg)
            if value <= 0.0:
                msg = (
                    f'PhaseMarginMeasurement.extra_crossovers_hz[{idx}]: '
                    f'{value!r} must be > 0.'
                )
                raise ValueError(msg)
        return self


# ---------------------------------------------------- PhaseMarginDelta ----


class PhaseMarginDelta(BaseModel):
    """
    Дельта `PhaseMarginMeasurement` по полю `margin_deg`.

    T021 family pattern (`GainDelta` / `BandwidthDelta` / `ThdDelta`):
    `before` обязателен, `after is None ⇔ failed_reason set`.

    Note: spec §5 формально допускает `before: ... | None`, но T021
    flow `EditAndResimWithDelta` строго прерывается `BaselineFailedError`
    до edit'ов — `before=None` не достижимо. Следуем T021 для
    consistency.
    """

    model_config = _FROZEN

    before: PhaseMarginMeasurement
    after: PhaseMarginMeasurement | None
    delta_absolute: Annotated[float | None, Field(allow_inf_nan=False)]
    delta_relative_percent: Annotated[float | None, Field(allow_inf_nan=False)]
    failed_reason: Annotated[str, Field(min_length=1)] | None = None
    metric_field: Literal['margin_deg'] = 'margin_deg'

    @model_validator(mode='after')
    def _check_after_consistency(self) -> Self:
        if self.after is None:
            if self.delta_absolute is not None:
                msg = 'delta_absolute must be None when after is None'
                raise ValueError(msg)
            if self.delta_relative_percent is not None:
                msg = 'delta_relative_percent must be None when after is None'
                raise ValueError(msg)
            if not self.failed_reason:
                msg = 'failed_reason is required when after is None'
                raise ValueError(msg)
        else:
            if self.delta_absolute is None:
                msg = 'delta_absolute must be set when after is set'
                raise ValueError(msg)
            if self.failed_reason is not None:
                msg = 'failed_reason must be None when after is set'
                raise ValueError(msg)
        return self

    @classmethod
    def from_measurements(
        cls,
        *,
        before: PhaseMarginMeasurement,
        after: PhaseMarginMeasurement,
    ) -> Self:
        delta_abs = after.margin_deg - before.margin_deg
        return cls(
            before=before,
            after=after,
            delta_absolute=delta_abs,
            delta_relative_percent=_compute_relative_percent(
                before.margin_deg,
                after.margin_deg,
            ),
            failed_reason=None,
        )

    @classmethod
    def from_failed_after(
        cls,
        *,
        before: PhaseMarginMeasurement,
        reason: str,
    ) -> Self:
        return cls(
            before=before,
            after=None,
            delta_absolute=None,
            delta_relative_percent=None,
            failed_reason=reason,
        )
