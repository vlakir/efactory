"""
THD-spectrum domain VOs (T131 Phase C).

`ThdSweepSpec` — input для `analyze_distortion_spectrum` use case:
описывает магнитный компонент (с его B-H curve и геометрией) + матрицу
(frequencies × output_powers) + связь с netlist'ом (целевой subckt-name,
input source ref, calibration constant).

`ThdMeasurementPoint` — одна cell спектра: (freq, target_power, измеренный
power, THD%, dominant harmonic n, harmonics-list из `FourierResult`).

`ThdSpectrum` — full sweep result: имя компонента + tuple of points +
runtime.
"""

from __future__ import annotations

from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from adapters.outbound.fem_solver_getdp.material import FrohlichBHCurve
from domain.magnetic import MagneticComponent
from domain.simulation import HarmonicSample

_FROZEN = ConfigDict(frozen=True, extra='forbid', arbitrary_types_allowed=True)


class ThdSweepSpec(BaseModel):
    """
    Input спецификация для `analyze_distortion_spectrum`.

    Содержит magnetic component + B-H curve + параметры sweep'а
    (frequencies, powers) + параметры netlist-связки (target subckt,
    input source, calibration constant).

    Caller отвечает за корректность calibration constant
    `voltage_per_root_power` (V_peak / √W): это произведение
    sqrt(2·R_load) и линейного inverse-gain усилителя. Для linear
    усилителя 1:1 на 8 Ω: `voltage_per_root_power = √16 = 4.0`.
    """

    model_config = _FROZEN

    component: MagneticComponent
    bh_curve: FrohlichBHCurve
    # Core geometry (PyOM lookup на стороне caller'а):
    a_core_m2: Annotated[float, Field(gt=0.0)]
    l_path_m: Annotated[float, Field(gt=0.0)]
    # DCR обмоток для R_pri / R_sec subckt-аргументов:
    r_primary_ohm: Annotated[float, Field(ge=0.0)]
    r_secondary_ohm: Annotated[float, Field(ge=0.0)]
    # Связь с netlist'ом:
    target_subckt_name: str = Field(min_length=1)
    input_source_ref: str = Field(min_length=1)
    load_ohm: Annotated[float, Field(gt=0.0)] = 8.0
    signal_node: str = Field(default='v(load)', min_length=1)
    voltage_per_root_power: Annotated[float, Field(gt=0.0)]
    # Sweep matrix:
    frequencies_hz: tuple[float, ...] = Field(min_length=1)
    output_powers_w: tuple[float, ...] = Field(min_length=1)
    # Прогон-параметры:
    # n_harmonics ≥ 3: нужна хотя бы одна harmonic-строка с n≥2, чтобы
    # `dominant_harmonic_n` в результирующих ThdMeasurementPoint был
    # well-defined (DC=0, fundamental=1, n=2 — первая «настоящая» гармоника).
    n_harmonics: Annotated[int, Field(ge=3, le=20)] = 10
    periods_per_run: Annotated[int, Field(ge=2, le=200)] = 10
    samples_per_period: Annotated[int, Field(ge=20, le=10_000)] = 100

    @model_validator(mode='after')
    def _check_positive_frequencies_and_powers(self) -> Self:
        for f in self.frequencies_hz:
            if f <= 0.0:
                msg = f'ThdSweepSpec: frequencies_hz must be > 0, got {f!r}'
                raise ValueError(msg)
        for p in self.output_powers_w:
            if p <= 0.0:
                msg = f'ThdSweepSpec: output_powers_w must be > 0, got {p!r}'
                raise ValueError(msg)
        return self

    @property
    def cell_count(self) -> int:
        """Количество (freq, power) cells = len(freqs)·len(powers)."""
        return len(self.frequencies_hz) * len(self.output_powers_w)


class ThdMeasurementPoint(BaseModel):
    """
    Один cell спектра: одна частота × одна target output power.

    `measured_power_w` — фактическая мощность в нагрузке, derived из
    fundamental magnitude / √2 (peak→rms) и `load_ohm`. Может отличаться
    от `target_power_w` (single-pass calibration ±20%).

    `dominant_harmonic_n` — индекс гармоники с максимальной normalized
    amplitude среди n≥2 (DC и fundamental исключены).
    """

    model_config = _FROZEN

    frequency_hz: Annotated[float, Field(gt=0.0)]
    target_power_w: Annotated[float, Field(gt=0.0)]
    measured_power_w: Annotated[float, Field(ge=0.0)]
    thd_percent: Annotated[float, Field(ge=0.0)]
    dominant_harmonic_n: Annotated[int, Field(ge=2)]
    harmonics: tuple[HarmonicSample, ...] = Field(min_length=1)


class ThdSpectrum(BaseModel):
    """Full sweep result: компонент + tuple of measurement points + runtime."""

    model_config = _FROZEN

    component_name: str = Field(min_length=1)
    points: tuple[ThdMeasurementPoint, ...] = Field(min_length=1)
    runtime_seconds: Annotated[float, Field(ge=0.0)]

    def find_closest(
        self,
        *,
        frequency_hz: float,
        target_power_w: float,
        power_tolerance: float = 0.20,
    ) -> ThdMeasurementPoint:
        """
        Найти точку, ближайшую к (freq, power) в пределах relative tolerance.

        Сравнение по freq — exact (sweep matrix задаёт конкретные freqs);
        по power — `|measured - target| / target ≤ power_tolerance`.
        Raises ValueError, если подходящей точки нет.
        """
        candidates = [
            p
            for p in self.points
            if p.frequency_hz == frequency_hz
            and abs(p.measured_power_w - target_power_w) / target_power_w
            <= power_tolerance
        ]
        if not candidates:
            msg = (
                f'no measurement point near frequency={frequency_hz} Hz, '
                f'target_power={target_power_w} W within '
                f'±{power_tolerance * 100:.0f}% tolerance'
            )
            raise ValueError(msg)
        return min(
            candidates,
            key=lambda p: abs(p.measured_power_w - target_power_w),
        )


__all__ = ['ThdMeasurementPoint', 'ThdSpectrum', 'ThdSweepSpec']
