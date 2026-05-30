"""
Delta-VO для bridge edit-and-resim (T021).

`GainDelta`, `BandwidthDelta`, `ThdDelta` — обёртки над парой
`(before, after)` соответствующего T023-измерения. Хранят уже
вычисленную абсолютную и относительную дельту по «главному» полю
метрики (`value_db` для gain, `bandwidth_hz` для bandwidth,
`thd_percent` для thd).

Инварианты (validators):
* `after is None` ⇔ measure упало после edit'ов; в этом случае
  `delta_absolute` и `delta_relative_percent` — `None`, а
  `failed_reason` — обязательный непустой str.
* `after is not None` ⇒ `delta_absolute` — обязательный float,
  `failed_reason` — `None`.
* `delta_relative_percent` `None` если `before.<metric_field>` == 0
  (избегаем «деления на ноль» / NaN-сериализации в JSON);
  NaN-значение явно запрещено.

Domain — без знания о JSON-сериализации; ответственность renderer'а
(text/JSON в CLI слое).
"""

from __future__ import annotations

import math
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from domain.measurement import (
    BandwidthMeasurement,
    GainMeasurement,
    ThdMeasurement,
)

_FROZEN = ConfigDict(frozen=True, extra='forbid')


def _compute_relative_percent(
    before_value: float,
    after_value: float,
) -> float | None:
    if before_value == 0.0:
        return None
    return ((after_value - before_value) / before_value) * 100.0


def _validate_after_consistency(model: _DeltaBase) -> _DeltaBase:
    if model.after is None:
        if model.delta_absolute is not None:
            msg = 'delta_absolute must be None when after is None'
            raise ValueError(msg)
        if model.delta_relative_percent is not None:
            msg = 'delta_relative_percent must be None when after is None'
            raise ValueError(msg)
        if not model.failed_reason:
            msg = 'failed_reason is required when after is None'
            raise ValueError(msg)
    else:
        if model.delta_absolute is None:
            msg = 'delta_absolute must be set when after is set'
            raise ValueError(msg)
        if model.failed_reason is not None:
            msg = 'failed_reason must be None when after is set'
            raise ValueError(msg)
    if model.delta_relative_percent is not None and math.isnan(
        model.delta_relative_percent
    ):
        msg = 'delta_relative_percent must not be NaN'
        raise ValueError(msg)
    if model.delta_absolute is not None and math.isnan(model.delta_absolute):
        msg = 'delta_absolute must not be NaN'
        raise ValueError(msg)
    return model


class _DeltaBase(BaseModel):
    """Общая часть Delta-VO; concrete-классы добавляют `before`/`after`."""

    model_config = _FROZEN

    delta_absolute: float | None
    delta_relative_percent: float | None
    failed_reason: Annotated[str, Field(min_length=1)] | None = None

    # Concrete-классы переопределяют `before` / `after` / `metric_field`.
    # Аннотации здесь нужны mypy, чтобы видел поля на base уровне.
    before: object
    after: object | None
    metric_field: str


class GainDelta(_DeltaBase):
    """Дельта `GainMeasurement` по полю `value_db` (gain в dB)."""

    model_config = _FROZEN

    before: GainMeasurement
    after: GainMeasurement | None
    metric_field: Literal['value_db'] = 'value_db'

    @model_validator(mode='after')
    def _check_after_consistency(self) -> Self:
        _validate_after_consistency(self)
        return self

    @classmethod
    def from_measurements(
        cls,
        *,
        before: GainMeasurement,
        after: GainMeasurement,
    ) -> Self:
        delta_abs = after.value_db - before.value_db
        return cls(
            before=before,
            after=after,
            delta_absolute=delta_abs,
            delta_relative_percent=_compute_relative_percent(
                before.value_db,
                after.value_db,
            ),
            failed_reason=None,
        )

    @classmethod
    def from_failed_after(
        cls,
        *,
        before: GainMeasurement,
        reason: str,
    ) -> Self:
        return cls(
            before=before,
            after=None,
            delta_absolute=None,
            delta_relative_percent=None,
            failed_reason=reason,
        )


class BandwidthDelta(_DeltaBase):
    """Дельта `BandwidthMeasurement` по полю `bandwidth_hz`."""

    model_config = _FROZEN

    before: BandwidthMeasurement
    after: BandwidthMeasurement | None
    metric_field: Literal['bandwidth_hz'] = 'bandwidth_hz'

    @model_validator(mode='after')
    def _check_after_consistency(self) -> Self:
        _validate_after_consistency(self)
        return self

    @classmethod
    def from_measurements(
        cls,
        *,
        before: BandwidthMeasurement,
        after: BandwidthMeasurement,
    ) -> Self:
        delta_abs = after.bandwidth_hz - before.bandwidth_hz
        return cls(
            before=before,
            after=after,
            delta_absolute=delta_abs,
            delta_relative_percent=_compute_relative_percent(
                before.bandwidth_hz,
                after.bandwidth_hz,
            ),
            failed_reason=None,
        )

    @classmethod
    def from_failed_after(
        cls,
        *,
        before: BandwidthMeasurement,
        reason: str,
    ) -> Self:
        return cls(
            before=before,
            after=None,
            delta_absolute=None,
            delta_relative_percent=None,
            failed_reason=reason,
        )


class ThdDelta(_DeltaBase):
    """Дельта `ThdMeasurement` по полю `thd_percent`."""

    model_config = _FROZEN

    before: ThdMeasurement
    after: ThdMeasurement | None
    metric_field: Literal['thd_percent'] = 'thd_percent'

    @model_validator(mode='after')
    def _check_after_consistency(self) -> Self:
        _validate_after_consistency(self)
        return self

    @classmethod
    def from_measurements(
        cls,
        *,
        before: ThdMeasurement,
        after: ThdMeasurement,
    ) -> Self:
        delta_abs = after.thd_percent - before.thd_percent
        return cls(
            before=before,
            after=after,
            delta_absolute=delta_abs,
            delta_relative_percent=_compute_relative_percent(
                before.thd_percent,
                after.thd_percent,
            ),
            failed_reason=None,
        )

    @classmethod
    def from_failed_after(
        cls,
        *,
        before: ThdMeasurement,
        reason: str,
    ) -> Self:
        return cls(
            before=before,
            after=None,
            delta_absolute=None,
            delta_relative_percent=None,
            failed_reason=reason,
        )


__all__ = ['BandwidthDelta', 'GainDelta', 'ThdDelta']
