"""
Publication-grade plot renderers (T035 Phase 2.2).

300 DPI matplotlib PNG'и с `--lang ru|en` i18n axis labels для
`/export-sim-report`. Параллельны функциям preview-уровня в
`plot_renderer.py` (ASCII через plotext + PNG @ 120 DPI).

Три render-функции для трёх типов анализа:

- `render_time_series_publication_png` — TRAN waveform.
- `render_ac_sweep_publication_png` — АЧХ (Bode magnitude в dB,
  log-x axis).
- `render_sweep_plot_publication_png` — parametric sweep (X vs Y,
  optional `group_by` для multi-line plot).

Helper `build_*_figure` функции выделены ради testability: позволяют
inspect ax.get_xlabel() / ax.get_ylabel() / ax.get_title() без
side effect savefig + close.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Literal

import matplotlib as mpl
from matplotlib import pyplot as plt

from adapters.inbound.cli.plot_renderer import (
    _db,
    _detect_x_scale,
    _trace_or_raise,
)
from adapters.inbound.cli.spice_units import parse_spice_number
from domain.publication import PublicationLang

if TYPE_CHECKING:
    from pathlib import Path

    from matplotlib.axes import Axes
    from matplotlib.figure import Figure

    from application.bridge_sweep import SweepRun
    from domain.simulation import AcSweep, DcSweep, TimeSeries


_PUBLICATION_DPI = 300
_PUBLICATION_FIGSIZE = (10, 6)


AXIS_LABELS: dict[PublicationLang, dict[str, str]] = {
    PublicationLang.RU: {
        'time_s': 'время, с',
        'magnitude_db': 'магнитуда, дБ',
        'frequency_log_hz': 'частота, Гц (лог.)',
        'vs_time': 'от времени',
        'vs_dc_sweep': 'от развёртки',
        'tf_title_prefix': '|H(f)|',
        'grouped_by': 'группировка по',
        'dc_sweep_var': 'переменная развёртки',
    },
    PublicationLang.EN: {
        'time_s': 'time, s',
        'magnitude_db': 'magnitude, dB',
        'frequency_log_hz': 'frequency, Hz (log)',
        'vs_time': 'vs time',
        'vs_dc_sweep': 'vs DC sweep',
        'tf_title_prefix': '|H(f)|',
        'grouped_by': 'grouped by',
        'dc_sweep_var': 'sweep variable',
    },
}


# ──────────────────────────── public render API ─────────────────────────────


def render_time_series_publication_png(
    series: TimeSeries,
    *,
    signal: str,
    output: Path,
    lang: PublicationLang,
    title: str | None = None,
) -> Path:
    """Render TRAN waveform → PNG @ 300 DPI."""
    fig = build_time_series_figure(series, signal=signal, lang=lang, title=title)
    return _save_publication_png(fig, output)


def render_ac_sweep_publication_png(
    sweep: AcSweep,
    *,
    signal: str,
    output: Path,
    lang: PublicationLang,
    title: str | None = None,
) -> Path:
    """Render АЧХ (|H(f)| в dB) → PNG @ 300 DPI, log-x."""
    fig = build_ac_sweep_figure(sweep, signal=signal, lang=lang, title=title)
    return _save_publication_png(fig, output)


def render_dc_sweep_publication_png(
    sweep: DcSweep,
    *,
    signal: str,
    output: Path,
    lang: PublicationLang,
    title: str | None = None,
) -> Path:
    """Render DC transfer curve (T188) → PNG @ 300 DPI."""
    fig = build_dc_sweep_figure(sweep, signal=signal, lang=lang, title=title)
    return _save_publication_png(fig, output)


def render_sweep_plot_publication_png(
    rows: list[SweepRun],
    *,
    x_param: str,
    y_field: str,
    output: Path,
    lang: PublicationLang,
    group_by: str | None = None,
    x_scale: Literal['auto', 'linear', 'log'] = 'auto',
    title: str | None = None,
) -> Path:
    """Render parametric sweep → PNG @ 300 DPI с optional group_by lines."""
    fig = build_sweep_plot_figure(
        rows,
        x_param=x_param,
        y_field=y_field,
        lang=lang,
        group_by=group_by,
        x_scale=x_scale,
        title=title,
    )
    return _save_publication_png(fig, output)


# ────────────────────────── figure builders (testable) ──────────────────────


def build_time_series_figure(
    series: TimeSeries,
    *,
    signal: str,
    lang: PublicationLang,
    title: str | None,
) -> Figure:
    trace = _trace_or_raise(series.traces, signal)
    time = list(series.time)
    labels = AXIS_LABELS[lang]
    fig, ax = _new_publication_figure()
    ax.plot(time, list(trace))
    ax.set_xlabel(labels['time_s'])
    ax.set_ylabel(signal)
    effective_title = title if title is not None else f'{signal} {labels["vs_time"]}'
    ax.set_title(effective_title)
    ax.grid(visible=True, linestyle=':', alpha=0.4)
    return fig


def build_dc_sweep_figure(
    sweep: DcSweep,
    *,
    signal: str,
    lang: PublicationLang,
    title: str | None,
) -> Figure:
    """Build matplotlib Figure для DC transfer curve (T188)."""
    trace = _trace_or_raise(sweep.traces, signal)
    sweep_values = list(sweep.sweep_values)
    labels = AXIS_LABELS[lang]
    fig, ax = _new_publication_figure()
    ax.plot(sweep_values, list(trace))
    ax.set_xlabel(sweep.sweep_variable)
    ax.set_ylabel(signal)
    effective_title = (
        title if title is not None else f'{signal} {labels["vs_dc_sweep"]}'
    )
    ax.set_title(effective_title)
    ax.grid(visible=True, linestyle=':', alpha=0.4)
    return fig


def build_ac_sweep_figure(
    sweep: AcSweep,
    *,
    signal: str,
    lang: PublicationLang,
    title: str | None,
) -> Figure:
    real = _trace_or_raise(sweep.traces_real, signal)
    imag = _trace_or_raise(sweep.traces_imag, signal)
    magnitudes_db = [_db(math.hypot(r, i)) for r, i in zip(real, imag, strict=True)]
    freqs = list(sweep.frequency)
    labels = AXIS_LABELS[lang]
    fig, ax = _new_publication_figure()
    ax.set_xscale('log')
    ax.plot(freqs, magnitudes_db)
    ax.set_xlabel(labels['frequency_log_hz'])
    ax.set_ylabel(labels['magnitude_db'])
    effective_title = (
        title if title is not None else f'{labels["tf_title_prefix"]}: {signal}'
    )
    ax.set_title(effective_title)
    ax.grid(visible=True, which='both', linestyle=':', alpha=0.4)
    return fig


def build_sweep_plot_figure(
    rows: list[SweepRun],
    *,
    x_param: str,
    y_field: str,
    lang: PublicationLang,
    group_by: str | None,
    x_scale: Literal['auto', 'linear', 'log'],
    title: str | None,
) -> Figure:
    valid_rows = [r for r in rows if r.error is None and r.values is not None]
    if not valid_rows:
        msg = 'build_sweep_plot_figure: no valid rows to plot'
        raise ValueError(msg)
    if y_field not in (valid_rows[0].values or {}):
        available = ', '.join(sorted(valid_rows[0].values or {}))
        msg = (
            f'build_sweep_plot_figure: y_field {y_field!r} not in values; '
            f'available: [{available}]'
        )
        raise ValueError(msg)

    traces: dict[str, list[tuple[float, float]]] = {}
    for run in valid_rows:
        try:
            x_val = parse_spice_number(run.parameters[x_param])
        except (ValueError, KeyError) as exc:
            msg = (
                f'build_sweep_plot_figure: param {x_param!r}='
                f'{run.parameters.get(x_param)!r} is not numeric SPICE value: {exc}'
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
        msg = 'build_sweep_plot_figure: no numeric Y data after filtering'
        raise ValueError(msg)

    all_xs = [x for trace in traces.values() for (x, _) in trace]
    effective_scale = _detect_x_scale(all_xs) if x_scale == 'auto' else x_scale

    labels = AXIS_LABELS[lang]
    fig, ax = _new_publication_figure()
    if effective_scale == 'log':
        ax.set_xscale('log')
    for label, points in sorted(traces.items()):
        points.sort(key=lambda p: p[0])
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        if group_by is not None:
            ax.plot(xs, ys, label=f'{group_by}={label}', marker='o', linestyle='-')
        else:
            ax.plot(xs, ys, marker='o', linestyle='-')
    ax.set_xlabel(x_param)
    ax.set_ylabel(y_field)
    if title is None:
        title = f'{y_field} vs {x_param}'
        if group_by is not None:
            title += f' ({labels["grouped_by"]} {group_by})'
    ax.set_title(title)
    ax.grid(visible=True, which='both', linestyle=':', alpha=0.4)
    if group_by is not None:
        ax.legend(loc='best')
    return fig


# ──────────────────────────── matplotlib helpers ────────────────────────────


def _new_publication_figure() -> tuple[Figure, Axes]:
    mpl.use('Agg', force=True)
    fig, ax = plt.subplots(figsize=_PUBLICATION_FIGSIZE, dpi=_PUBLICATION_DPI)
    return fig, ax


def _save_publication_png(fig: Figure, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output, format='png', dpi=_PUBLICATION_DPI)
    plt.close(fig)
    return output.resolve()


__all__ = [
    'AXIS_LABELS',
    'build_ac_sweep_figure',
    'build_dc_sweep_figure',
    'build_sweep_plot_figure',
    'build_time_series_figure',
    'render_ac_sweep_publication_png',
    'render_dc_sweep_publication_png',
    'render_sweep_plot_publication_png',
    'render_time_series_publication_png',
]
