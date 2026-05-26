"""
Measurement-VO для bridge measure use cases (T023).

Три независимых VO (не объединены в discriminated union — Clarify Q-A):
`GainMeasurement` для `bridge measure gain`, `BandwidthMeasurement` для
`bridge measure bandwidth`, `ThdMeasurement` для `bridge measure thd`.
Каждый возвращает «число + контекст измерения» — частоту/диапазон,
input/output signal, режим (small vs large) и т.п.

Signal-поля используют SPICE-нотацию (`v(<node>)`, `i(<element>)`),
передаются ngspice'у напрямую (Analyze A5). Domain — без знания о
JSON-сериализации; SimResult writer (T016) кладёт VO-поля в
`metrics: dict[str, Any]` (Analyze A7).
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

_FROZEN = ConfigDict(frozen=True, extra='forbid')


class GainMeasurement(BaseModel):
    """
    Gain в точке частоты — small-signal AC или large-signal TRAN RMS.

    `mode='small'`: AC analysis с n_points=2 workaround (Analyze A2);
    `value_db = 20·log10(|H(f)|)`. `v_in_peak` остаётся None.

    `mode='large'`: TRAN с sin-source `v_in_peak`, `value_linear =
    rms(V_out) / rms(V_in)`. Может отличаться от small-mode при approach
    к clipping / saturation.
    """

    model_config = _FROZEN

    value_db: float
    value_linear: Annotated[float, Field(gt=0.0)]
    frequency_hz: Annotated[float, Field(gt=0.0)]
    mode: Literal['small', 'large']
    input_signal: str = Field(min_length=1)
    output_signal: str = Field(min_length=1)
    v_in_peak: Annotated[float, Field(gt=0.0)] | None = None

    @model_validator(mode='after')
    def _check_v_in_peak_required_for_large_mode(self) -> Self:
        if self.mode == 'large' and self.v_in_peak is None:
            msg = 'GainMeasurement: v_in_peak required for mode="large"'
            raise ValueError(msg)
        return self


class BandwidthMeasurement(BaseModel):
    """
    Полоса пропускания по `-N dB` относительно reference midpoint.

    `midpoint_source='auto'`: midband = max|H(f)| по AC sweep'у;
    `midpoint_source='ref_freq'`: midband = |H(ref_freq_hz)| (typical
    1 kHz для audio). `bandwidth_hz` = `f_high_hz - f_low_hz`,
    проверяется validator'ом для consistency.
    """

    model_config = _FROZEN

    f_low_hz: Annotated[float, Field(gt=0.0)]
    f_high_hz: Annotated[float, Field(gt=0.0)]
    bandwidth_hz: Annotated[float, Field(gt=0.0)]
    ref_db: float
    midpoint_db: float
    midpoint_source: Literal['auto', 'ref_freq']
    ref_freq_hz: Annotated[float, Field(gt=0.0)] | None = None
    passband_signal: str = Field(min_length=1)
    input_signal: str = Field(min_length=1)

    @model_validator(mode='after')
    def _check_band_consistency(self) -> Self:
        if self.f_high_hz <= self.f_low_hz:
            msg = (
                f'BandwidthMeasurement: f_high_hz ({self.f_high_hz}) must '
                f'be greater than f_low_hz ({self.f_low_hz}).'
            )
            raise ValueError(msg)
        expected = self.f_high_hz - self.f_low_hz
        tolerance = 1e-9 * max(expected, 1.0)
        if abs(self.bandwidth_hz - expected) > tolerance:
            msg = (
                f'BandwidthMeasurement: bandwidth_hz ({self.bandwidth_hz}) '
                f'must equal f_high_hz - f_low_hz ({expected}).'
            )
            raise ValueError(msg)
        return self

    @model_validator(mode='after')
    def _check_ref_freq_set_for_ref_source(self) -> Self:
        if self.midpoint_source == 'ref_freq' and self.ref_freq_hz is None:
            msg = (
                'BandwidthMeasurement: ref_freq_hz must be set when '
                'midpoint_source="ref_freq".'
            )
            raise ValueError(msg)
        return self


class ThdMeasurement(BaseModel):
    """
    THD одной частоты — output use case'а `measure_thd` (Q-D → независимый,
    не wrapper T131).

    Строится из `FourierResult` (`domain.simulation`) extraction'ом
    fundamental + dominant harmonic (n ≥ 2 по max normalized).
    `measured_power_w` — фактическая мощность в нагрузке, derived из
    fundamental rms² / R_load (caller передаёт R_load в use case).
    """

    model_config = _FROZEN

    thd_percent: Annotated[float, Field(ge=0.0)]
    fundamental_hz: Annotated[float, Field(gt=0.0)]
    v_in_peak: Annotated[float, Field(gt=0.0)]
    measured_power_w: Annotated[float, Field(ge=0.0)]
    dominant_harmonic_n: Annotated[int, Field(ge=2)]
    dominant_harmonic_percent: Annotated[float, Field(ge=0.0)]
    signal: str = Field(min_length=1)
    n_harmonics: Annotated[int, Field(ge=3, le=20)]


__all__ = ['BandwidthMeasurement', 'GainMeasurement', 'ThdMeasurement']
