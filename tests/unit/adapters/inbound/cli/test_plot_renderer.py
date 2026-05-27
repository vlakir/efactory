"""Unit-тесты ASCII plot renderer (T024)."""

from __future__ import annotations

import math
import re

import pytest

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')


def _strip_ansi(s: str) -> str:
    """plotext возвращает coloured output; visible width = без escape codes."""
    return _ANSI_RE.sub('', s)

from adapters.inbound.cli.plot_renderer import (
    render_ac_sweep,
    render_time_series,
)
from domain.simulation import AcSweep, TimeSeries


def _flat_ac_sweep(
    *, magnitude_db: float = 0.0, signal: str = 'v(load)',
) -> AcSweep:
    """Flat АЧХ — magnitude такая, что 20·log10(|H|) ≈ magnitude_db."""
    linear = 10 ** (magnitude_db / 20.0)
    freqs = (1.0, 10.0, 100.0, 1000.0, 10000.0)
    return AcSweep(
        frequency=freqs,
        traces_real={signal: tuple(linear for _ in freqs)},
        traces_imag={signal: tuple(0.0 for _ in freqs)},
    )


def _sine_time_series(
    *,
    signal: str = 'v(load)',
    n_samples: int = 100,
    period_s: float = 1e-3,
    amplitude: float = 1.0,
) -> TimeSeries:
    time = tuple(i * period_s / n_samples for i in range(n_samples))
    trace = tuple(
        amplitude * math.sin(2.0 * math.pi * t / period_s) for t in time
    )
    return TimeSeries(time=time, traces={signal: trace})


def test_render_ac_sweep_returns_non_empty_string() -> None:
    sweep = _flat_ac_sweep(magnitude_db=0.0)

    result = render_ac_sweep(sweep, signal='v(load)')

    assert result
    assert isinstance(result, str)


def test_render_ac_sweep_includes_signal_in_title() -> None:
    sweep = _flat_ac_sweep()

    result = render_ac_sweep(sweep, signal='v(load)')

    assert 'v(load)' in result


def test_render_ac_sweep_custom_title() -> None:
    sweep = _flat_ac_sweep()

    result = render_ac_sweep(sweep, signal='v(load)', title='Custom Plot')

    assert 'Custom Plot' in result


def test_render_ac_sweep_respects_width() -> None:
    """Каждая строка вывода <= width (символов в plotext-canvas).

    На flat data plotext не умеет вычислять axis ticks; даём lightly
    rolling АЧХ для смыслового sanity check.
    """
    sweep = AcSweep(
        frequency=(1.0, 10.0, 100.0, 1000.0, 10000.0),
        traces_real={'v(load)': (1.0, 0.95, 0.9, 0.85, 0.8)},
        traces_imag={'v(load)': (0.0, 0.0, 0.0, 0.0, 0.0)},
    )
    width = 60

    result = render_ac_sweep(sweep, signal='v(load)', width=width, height=15)

    visible_lines = [_strip_ansi(line) for line in result.splitlines()]
    # plotext-canvas + axis labels; допуск 20 на оси/labels вокруг canvas.
    assert max(len(line) for line in visible_lines) <= width + 20


def test_render_ac_sweep_case_insensitive_signal_lookup() -> None:
    sweep = _flat_ac_sweep(signal='V(LOAD)')

    result = render_ac_sweep(sweep, signal='v(load)')

    assert result


def test_render_ac_sweep_raises_on_missing_signal() -> None:
    sweep = _flat_ac_sweep(signal='v(other)')

    with pytest.raises(ValueError, match='v\\(missing\\)'):
        render_ac_sweep(sweep, signal='v(missing)')


def test_render_time_series_returns_non_empty_string() -> None:
    ts = _sine_time_series()

    result = render_time_series(ts, signal='v(load)')

    assert result
    assert isinstance(result, str)


def test_render_time_series_includes_signal_in_title() -> None:
    ts = _sine_time_series()

    result = render_time_series(ts, signal='v(load)')

    assert 'v(load)' in result


def test_render_time_series_custom_title() -> None:
    ts = _sine_time_series()

    result = render_time_series(ts, signal='v(load)', title='Custom TS')

    assert 'Custom TS' in result


def test_render_time_series_case_insensitive_signal() -> None:
    ts = _sine_time_series(signal='V(LOAD)')

    result = render_time_series(ts, signal='v(load)')

    assert result


def test_render_time_series_raises_on_missing_signal() -> None:
    ts = _sine_time_series(signal='v(other)')

    with pytest.raises(ValueError, match='v\\(missing\\)'):
        render_time_series(ts, signal='v(missing)')


def test_render_ac_sweep_handles_zero_magnitude_safely() -> None:
    """В zero |H| → log10 → -inf, plotext должен справиться без crash."""
    sweep = AcSweep(
        frequency=(1.0, 10.0),
        traces_real={'v(load)': (0.0, 1e-10)},
        traces_imag={'v(load)': (0.0, 0.0)},
    )

    result = render_ac_sweep(sweep, signal='v(load)')

    assert result
