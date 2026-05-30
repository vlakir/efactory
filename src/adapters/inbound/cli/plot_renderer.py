"""
ASCII plot renderer для CLI bridge plot (T024) + sweep (T022 Phase C).

Использует `plotext` для terminal-friendly графиков. Render-функции
возвращают строку (через `plotext.build()`), что облегчает тестирование
без захвата stdout. CLI команда печатает результат как есть.

Три типа графиков:
- `render_ac_sweep` — |H(f)| в dB vs частота (log-scale x), T024.
- `render_time_series` — signal vs time (linear scale), T024.
- `render_sweep_plot` — parametric sweep Y vs X с optional `group_by`
  для 2-парам sweep'ов, T022 Phase C.

X-scale auto-detect (T022 Analyze A8): log-space algorithm на
sorted values; `_detect_x_scale` экспортирован для тестируемости.
"""

from __future__ import annotations

import math
import statistics
from typing import TYPE_CHECKING, Literal

import plotext as plt

from adapters.inbound.cli.spice_units import parse_spice_number

if TYPE_CHECKING:
    from application.bridge_sweep import SweepRun
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


# ────────── T022 Phase C: parametric sweep plot ──────────


# Thresholds для auto-detect log vs linear (Analyze A8, log-space algorithm).
_LOG_DIFF_STDEV_OVER_MEAN_THRESHOLD = 0.10
_LOG_MEAN_DIFF_THRESHOLD = 0.18  # ≈ log10(1.5), порог «geometric series»
_MIN_VALUES_FOR_DETECTION = 3  # < 3 values → linear (insufficient data).


def _detect_x_scale(values: list[float]) -> Literal['linear', 'log']:
    """
    Auto-detect log vs linear X-axis (Analyze A8 log-space algorithm).

    Алгоритм:
    1. Filter positive, sort ascending.
    2. N < 3 (или non-positive) → linear (insufficient data).
    3. `log10_vals = [log10(v) for v in sorted]`,
       `diffs = consecutive diffs`.
    4. Если `stdev(diffs) / mean(diffs) < 0.10` И `mean(diffs) > 0.18`
       → log (geometric series). Иначе → linear.
    """
    positive = sorted(v for v in values if v > 0.0)
    if len(positive) != len(values) or len(positive) < _MIN_VALUES_FOR_DETECTION:
        return 'linear'
    log_vals = [math.log10(v) for v in positive]
    diffs = [log_vals[i + 1] - log_vals[i] for i in range(len(log_vals) - 1)]
    mean_diff = statistics.mean(diffs)
    if mean_diff <= 0.0:
        return 'linear'
    stdev_diff = statistics.stdev(diffs) if len(diffs) > 1 else 0.0
    cv = stdev_diff / mean_diff
    is_geometric = (
        cv < _LOG_DIFF_STDEV_OVER_MEAN_THRESHOLD
        and mean_diff > _LOG_MEAN_DIFF_THRESHOLD
    )
    return 'log' if is_geometric else 'linear'


def render_sweep_plot(
    rows: list[SweepRun],
    *,
    x_param: str,
    y_field: str,
    group_by: str | None = None,
    x_scale: Literal['auto', 'linear', 'log'] = 'auto',
    width: int = _DEFAULT_WIDTH,
    height: int = _DEFAULT_HEIGHT,
    title: str | None = None,
) -> str:
    """
    Render parametric sweep (T022 Phase C, Q-E → b).

    Single-param: X = swept value (parsed `parse_spice_number`),
    Y = `y_field` из `values`.

    Two-param (`group_by` != None): одна линия на значение `group_by`-
    параметра, label = `<group_by>=<value>`.

    Failed combinations (run.error) — пропускаются (не plot'аются).
    Non-numeric param values — `ValueError` (caller disables plot).

    Args:
        rows: SweepRun list.
        x_param: parameter name (column key in run.parameters).
        y_field: metric column key (in run.values).
        group_by: optional second-param name для multi-line plot.
        x_scale: `auto` (Analyze A8 detect) / `linear` / `log`.
        width: plot width в символах (default 80).
        height: plot height в строках (default 20).
        title: plot title; default — `'<y_field> vs <x_param>'`.

    Raises:
        ValueError: x_param не parse'ится, y_field missing, no valid rows.

    """
    valid_rows = [r for r in rows if r.error is None and r.values is not None]
    if not valid_rows:
        msg = 'render_sweep_plot: no valid rows to plot'
        raise ValueError(msg)
    # Check y_field присутствует.
    if y_field not in (valid_rows[0].values or {}):
        available = ', '.join(sorted(valid_rows[0].values or {}))
        msg = (
            f'render_sweep_plot: y_field {y_field!r} not in values; '
            f'available: [{available}]'
        )
        raise ValueError(msg)

    # Группируем по group_by (если задан); либо single-trace.
    traces: dict[str, list[tuple[float, float]]] = {}
    for run in valid_rows:
        try:
            x_val = parse_spice_number(run.parameters[x_param])
        except (ValueError, KeyError) as exc:
            msg = (
                f'render_sweep_plot: param {x_param!r}={run.parameters.get(x_param)!r} '
                f'is not numeric SPICE value: {exc}'
            )
            raise ValueError(msg) from exc
        y_raw = (run.values or {}).get(y_field)
        if not isinstance(y_raw, (int, float)):
            continue
        y_val = float(y_raw)
        key = (
            run.parameters[group_by]
            if group_by is not None and group_by in run.parameters
            else ''
        )
        traces.setdefault(key, []).append((x_val, y_val))

    if not traces or all(len(pts) == 0 for pts in traces.values()):
        msg = 'render_sweep_plot: no numeric Y data after filtering'
        raise ValueError(msg)

    # X-scale auto-detect — на union всех X values.
    all_xs = [x for trace in traces.values() for (x, _) in trace]
    effective_scale = _detect_x_scale(all_xs) if x_scale == 'auto' else x_scale

    plt.clear_figure()
    plt.plotsize(width, height)
    plt.title(
        title
        if title is not None
        else f'{y_field} vs {x_param}'
        + (f' (grouped by {group_by})' if group_by else '')
    )
    plt.xlabel(x_param)
    plt.ylabel(y_field)
    if effective_scale == 'log':
        plt.xscale('log')
    for label, points in sorted(traces.items()):
        points.sort(key=lambda p: p[0])
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        if group_by is not None:
            plt.plot(xs, ys, label=f'{group_by}={label}')
        else:
            plt.plot(xs, ys)
    return plt.build()


__all__ = [
    '_detect_x_scale',
    'render_ac_sweep',
    'render_sweep_plot',
    'render_time_series',
]
