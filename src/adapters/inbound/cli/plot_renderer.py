"""
ASCII plot renderer для CLI bridge plot (T024).

Использует `plotext` для terminal-friendly графиков. Render-функции
возвращают строку (через `plotext.build()`), что облегчает тестирование
без захвата stdout. CLI команда печатает результат как есть.

Два типа графиков:
- `render_ac_sweep` — |H(f)| в dB vs частота (log-scale x).
- `render_time_series` — signal vs time (linear scale).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import plotext as plt

if TYPE_CHECKING:
    from domain.simulation import AcSweep, TimeSeries


_DEFAULT_WIDTH = 80
_DEFAULT_HEIGHT = 20


def render_ac_sweep(
    sweep: AcSweep,
    *,
    signal: str,
    width: int = _DEFAULT_WIDTH,
    height: int = _DEFAULT_HEIGHT,
    title: str | None = None,
) -> str:
    """
    Render AC sweep как АЧХ (магнитуда в dB vs log-частота).

    Args:
        sweep: `AcSweep` domain VO (частоты + real/imag traces).
        signal: trace name (case-insensitive fallback). `v(load)` и т.п.
        width: ширина графика в символах (default 80).
        height: высота в строках (default 20).
        title: title графика; default — `'|H(f)|: <signal>'`.

    Returns:
        Готовая ASCII-картинка (multiline string).

    Raises:
        ValueError: signal не найден в sweep.

    """
    real = _trace_or_raise(sweep.traces_real, signal)
    imag = _trace_or_raise(sweep.traces_imag, signal)
    magnitudes_db = [_db(math.hypot(r, i)) for r, i in zip(real, imag, strict=True)]
    freqs = list(sweep.frequency)

    plt.clear_figure()
    plt.plotsize(width, height)
    plt.title(title if title is not None else f'|H(f)|: {signal}')
    plt.xlabel('frequency, Hz (log)')
    plt.ylabel('magnitude, dB')
    plt.xscale('log')
    plt.plot(freqs, magnitudes_db)
    return plt.build()


def render_time_series(
    series: TimeSeries,
    *,
    signal: str,
    width: int = _DEFAULT_WIDTH,
    height: int = _DEFAULT_HEIGHT,
    title: str | None = None,
) -> str:
    """
    Render TRAN waveform (signal vs time).

    Args:
        series: `TimeSeries` domain VO (time + named traces).
        signal: trace name (case-insensitive fallback).
        width: ширина в символах (default 80).
        height: высота в строках (default 20).
        title: title графика; default — `'<signal> vs time'`.

    Returns:
        ASCII waveform.

    Raises:
        ValueError: signal не найден.

    """
    trace = _trace_or_raise(series.traces, signal)
    time = list(series.time)

    plt.clear_figure()
    plt.plotsize(width, height)
    plt.title(title if title is not None else f'{signal} vs time')
    plt.xlabel('time, s')
    plt.ylabel(signal)
    plt.plot(time, list(trace))
    return plt.build()


def _trace_or_raise(
    traces: dict[str, tuple[float, ...]],
    name: str,
) -> tuple[float, ...]:
    if name in traces:
        return traces[name]
    lower_map = {k.lower(): v for k, v in traces.items()}
    if name.lower() in lower_map:
        return lower_map[name.lower()]
    available = ', '.join(sorted(traces))
    msg = (
        f'plot_renderer: signal {name!r} not found in simulator output; '
        f'available: [{available}]'
    )
    raise ValueError(msg)


_DB_FLOOR = -200.0  # ~10⁻¹⁰ magnitude floor — plotext не умеет infinity


def _db(linear: float) -> float:
    if linear <= 0.0:
        return _DB_FLOOR
    value = 20.0 * math.log10(linear)
    return max(value, _DB_FLOOR)


__all__ = ['render_ac_sweep', 'render_time_series']
