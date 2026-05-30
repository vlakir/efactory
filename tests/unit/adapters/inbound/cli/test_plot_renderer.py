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


# ────────── T022 Phase C: render_sweep_plot ──────────


from application.bridge_sweep import SweepRun
from adapters.inbound.cli.plot_renderer import (
    _detect_x_scale,
    render_sweep_plot,
)


def _row(parameters: dict[str, str], values: dict[str, float | str | None]) -> SweepRun:
    return SweepRun(parameters=parameters, result=None, values=values)


# X-scale auto-detect (Analyze A8: log-space algorithm).


def test_detect_x_scale_linear_for_arithmetic_progression() -> None:
    # 100, 200, 300, 400 — arithmetic → linear.
    values = [100.0, 200.0, 300.0, 400.0]
    assert _detect_x_scale(values) == 'linear'


def test_detect_x_scale_log_for_geometric_progression() -> None:
    # 10, 100, 1000, 10000 — ratio ×10 → log.
    values = [10.0, 100.0, 1000.0, 10000.0]
    assert _detect_x_scale(values) == 'log'


def test_detect_x_scale_log_for_e12_subset() -> None:
    # 1k, 4.7k, 22k, 100k — quasi-geometric ratio ~4.7 → log.
    values = [1000.0, 4700.0, 22000.0, 100000.0]
    assert _detect_x_scale(values) == 'log'


def test_detect_x_scale_linear_for_close_values() -> None:
    # 470, 680, 820, 1000 — ratio ~1.4, mean log10-diff ~0.07 < 0.18 → linear.
    values = [470.0, 680.0, 820.0, 1000.0]
    assert _detect_x_scale(values) == 'linear'


def test_detect_x_scale_linear_for_n_lt_3() -> None:
    assert _detect_x_scale([10.0, 100.0]) == 'linear'
    assert _detect_x_scale([1.0]) == 'linear'
    assert _detect_x_scale([]) == 'linear'


def test_detect_x_scale_robust_to_unsorted_input() -> None:
    """A8: sorting before detection."""
    sorted_log = _detect_x_scale([10.0, 100.0, 1000.0])
    unsorted = _detect_x_scale([1000.0, 10.0, 100.0])
    assert sorted_log == unsorted == 'log'


def test_detect_x_scale_linear_for_non_positive() -> None:
    # log10 undefined для ≤ 0 — fallback linear.
    assert _detect_x_scale([-1.0, 0.0, 1.0]) == 'linear'
    assert _detect_x_scale([0.0, 100.0, 1000.0]) == 'linear'


# render_sweep_plot — single-param.


def test_render_sweep_plot_single_param_returns_string() -> None:
    rows = [
        _row({'R1': '100'}, {'gain_db': 10.0}),
        _row({'R1': '200'}, {'gain_db': 13.0}),
        _row({'R1': '300'}, {'gain_db': 15.0}),
    ]
    result = render_sweep_plot(rows, x_param='R1', y_field='gain_db')
    assert isinstance(result, str)
    assert result


def test_render_sweep_plot_skips_failed_rows() -> None:
    rows = [
        _row({'R1': '100'}, {'gain_db': 10.0}),
        SweepRun(parameters={'R1': '200'}, result=None, values=None, error='sim fail'),
        _row({'R1': '300'}, {'gain_db': 15.0}),
    ]
    result = render_sweep_plot(rows, x_param='R1', y_field='gain_db')
    assert result  # не должен crash


def test_render_sweep_plot_two_param_multiline() -> None:
    """Q-E → b: group_by=2nd param → одна линия на значение."""
    rows = [
        _row({'R1': '1k', 'C1': '100n'}, {'gain_db': 10.0}),
        _row({'R1': '10k', 'C1': '100n'}, {'gain_db': 13.0}),
        _row({'R1': '1k', 'C1': '1u'}, {'gain_db': 8.0}),
        _row({'R1': '10k', 'C1': '1u'}, {'gain_db': 11.0}),
    ]
    result = render_sweep_plot(
        rows, x_param='R1', y_field='gain_db', group_by='C1',
    )
    assert isinstance(result, str)
    assert result


def test_render_sweep_plot_explicit_x_scale_log() -> None:
    rows = [
        _row({'R1': '100'}, {'gain_db': 10.0}),
        _row({'R1': '1k'}, {'gain_db': 13.0}),
        _row({'R1': '10k'}, {'gain_db': 15.0}),
    ]
    result = render_sweep_plot(
        rows, x_param='R1', y_field='gain_db', x_scale='log',
    )
    assert result


def test_render_sweep_plot_raises_on_non_numeric_param() -> None:
    """Plot disabled при unparseable param value."""
    rows = [
        _row({'model': 'KP-507'}, {'gain_db': 10.0}),
        _row({'model': 'KP-509'}, {'gain_db': 13.0}),
    ]
    with pytest.raises(ValueError, match='numeric'):
        render_sweep_plot(rows, x_param='model', y_field='gain_db')


def test_render_sweep_plot_raises_on_missing_y_field() -> None:
    rows = [
        _row({'R1': '100'}, {'gain_db': 10.0}),
        _row({'R1': '200'}, {'gain_db': 13.0}),
    ]
    with pytest.raises(ValueError, match='y_field'):
        render_sweep_plot(rows, x_param='R1', y_field='missing_field')
