"""Unit tests for publication-grade plot renderers (T035 Phase 2.2)."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pytest
from matplotlib import pyplot as plt
from PIL import Image

from adapters.inbound.cli.publication_plots import (
    AXIS_LABELS,
    build_ac_sweep_figure,
    build_sweep_plot_figure,
    build_time_series_figure,
    render_ac_sweep_publication_png,
    render_sweep_plot_publication_png,
    render_time_series_publication_png,
)
from application.bridge_sweep import SweepRun
from domain.publication import PublicationLang
from domain.simulation import AcSweep, TimeSeries

if TYPE_CHECKING:
    from pathlib import Path


# ───────────────────────────── fixtures / helpers ────────────────────────────


def _flat_ac_sweep(*, signal: str = 'v(load)') -> AcSweep:
    """Slightly-rolling АЧХ для тестов publication-render."""
    freqs = (1.0, 10.0, 100.0, 1000.0, 10000.0)
    real = (1.0, 0.95, 0.9, 0.85, 0.8)
    imag = (0.0, 0.0, 0.0, 0.0, 0.0)
    return AcSweep(
        frequency=freqs,
        traces_real={signal: real},
        traces_imag={signal: imag},
    )


def _sine_time_series(
    *,
    signal: str = 'v(load)',
    n_samples: int = 50,
    period_s: float = 1e-3,
) -> TimeSeries:
    time = tuple(i * period_s / n_samples for i in range(n_samples))
    trace = tuple(math.sin(2.0 * math.pi * t / period_s) for t in time)
    return TimeSeries(time=time, traces={signal: trace})


def _sweep_runs_single_param() -> list[SweepRun]:
    return [
        SweepRun(
            parameters={'R1': str(r)},
            result=None,
            values={'gain_v_per_v': float(g)},
            error=None,
        )
        for r, g in [(1000, 10.0), (2200, 12.5), (4700, 14.8), (10000, 16.0)]
    ]


def _sweep_runs_two_param_grouped() -> list[SweepRun]:
    """2-параметрический sweep: R1 × C1, два значения C1 — две линии."""
    return [
        SweepRun(
            parameters={'R1': str(r), 'C1': str(c)},
            result=None,
            values={'gain_v_per_v': float(g)},
            error=None,
        )
        for r, c, g in [
            (1000, '1u', 10.0),
            (2200, '1u', 12.0),
            (4700, '1u', 13.5),
            (1000, '10u', 14.0),
            (2200, '10u', 15.5),
            (4700, '10u', 16.0),
        ]
    ]


# ───────────────────────────── AXIS_LABELS structure ─────────────────────────


def test_axis_labels_ru_uses_cyrillic_for_time_axis() -> None:
    assert AXIS_LABELS[PublicationLang.RU]['time_s'] == 'время, с'


def test_axis_labels_ru_uses_cyrillic_for_magnitude_axis() -> None:
    assert AXIS_LABELS[PublicationLang.RU]['magnitude_db'] == 'магнитуда, дБ'


def test_axis_labels_ru_uses_cyrillic_for_frequency_axis() -> None:
    assert AXIS_LABELS[PublicationLang.RU]['frequency_log_hz'] == 'частота, Гц (лог.)'


def test_axis_labels_en_uses_english_for_time_axis() -> None:
    assert AXIS_LABELS[PublicationLang.EN]['time_s'] == 'time, s'


def test_axis_labels_en_uses_english_for_magnitude_axis() -> None:
    assert AXIS_LABELS[PublicationLang.EN]['magnitude_db'] == 'magnitude, dB'


def test_axis_labels_en_uses_english_for_frequency_axis() -> None:
    assert AXIS_LABELS[PublicationLang.EN]['frequency_log_hz'] == 'frequency, Hz (log)'


def test_axis_labels_ru_and_en_share_same_keys() -> None:
    assert AXIS_LABELS[PublicationLang.RU].keys() == AXIS_LABELS[PublicationLang.EN].keys()


# ──────────────────────────── build_time_series_figure ────────────────────────


def test_build_time_series_figure_ru_labels_axes_in_russian() -> None:
    ts = _sine_time_series()

    fig = build_time_series_figure(ts, signal='v(load)', lang=PublicationLang.RU, title=None)

    ax = fig.axes[0]
    assert ax.get_xlabel() == 'время, с'
    assert ax.get_ylabel() == 'v(load)'
    assert 'от времени' in ax.get_title()
    plt.close(fig)


def test_build_time_series_figure_en_labels_axes_in_english() -> None:
    ts = _sine_time_series()

    fig = build_time_series_figure(ts, signal='v(load)', lang=PublicationLang.EN, title=None)

    ax = fig.axes[0]
    assert ax.get_xlabel() == 'time, s'
    assert ax.get_ylabel() == 'v(load)'
    assert 'vs time' in ax.get_title()
    plt.close(fig)


def test_build_time_series_figure_custom_title_overrides_default() -> None:
    ts = _sine_time_series()

    fig = build_time_series_figure(
        ts,
        signal='v(load)',
        lang=PublicationLang.RU,
        title='Кастомный заголовок',
    )

    assert fig.axes[0].get_title() == 'Кастомный заголовок'
    plt.close(fig)


def test_build_time_series_figure_raises_on_missing_signal() -> None:
    ts = _sine_time_series()

    with pytest.raises(ValueError, match='v\\(missing\\)'):
        build_time_series_figure(
            ts, signal='v(missing)', lang=PublicationLang.RU, title=None,
        )


# ──────────────────────────── build_ac_sweep_figure ──────────────────────────


def test_build_ac_sweep_figure_ru_labels_axes_in_russian() -> None:
    sweep = _flat_ac_sweep()

    fig = build_ac_sweep_figure(sweep, signal='v(load)', lang=PublicationLang.RU, title=None)

    ax = fig.axes[0]
    assert ax.get_xlabel() == 'частота, Гц (лог.)'
    assert ax.get_ylabel() == 'магнитуда, дБ'
    assert ax.get_xscale() == 'log'
    assert '|H(f)|' in ax.get_title()
    assert 'v(load)' in ax.get_title()
    plt.close(fig)


def test_build_ac_sweep_figure_en_labels_axes_in_english() -> None:
    sweep = _flat_ac_sweep()

    fig = build_ac_sweep_figure(sweep, signal='v(load)', lang=PublicationLang.EN, title=None)

    ax = fig.axes[0]
    assert ax.get_xlabel() == 'frequency, Hz (log)'
    assert ax.get_ylabel() == 'magnitude, dB'
    plt.close(fig)


def test_build_ac_sweep_figure_raises_on_missing_signal() -> None:
    sweep = _flat_ac_sweep(signal='v(other)')

    with pytest.raises(ValueError, match='v\\(missing\\)'):
        build_ac_sweep_figure(
            sweep, signal='v(missing)', lang=PublicationLang.RU, title=None,
        )


# ──────────────────────────── build_sweep_plot_figure ────────────────────────


def test_build_sweep_plot_figure_single_param_uses_user_xlabel_ylabel() -> None:
    runs = _sweep_runs_single_param()

    fig = build_sweep_plot_figure(
        runs,
        x_param='R1',
        y_field='gain_v_per_v',
        lang=PublicationLang.RU,
        group_by=None,
        x_scale='auto',
        title=None,
    )

    ax = fig.axes[0]
    assert ax.get_xlabel() == 'R1'
    assert ax.get_ylabel() == 'gain_v_per_v'
    assert 'gain_v_per_v' in ax.get_title()
    assert 'R1' in ax.get_title()
    plt.close(fig)


def test_build_sweep_plot_figure_two_param_groups_with_legend() -> None:
    runs = _sweep_runs_two_param_grouped()

    fig = build_sweep_plot_figure(
        runs,
        x_param='R1',
        y_field='gain_v_per_v',
        lang=PublicationLang.RU,
        group_by='C1',
        x_scale='auto',
        title=None,
    )

    ax = fig.axes[0]
    legend = ax.get_legend()
    assert legend is not None
    legend_texts = [t.get_text() for t in legend.get_texts()]
    assert any('C1=1u' in t for t in legend_texts)
    assert any('C1=10u' in t for t in legend_texts)
    plt.close(fig)


def test_build_sweep_plot_figure_two_param_title_uses_localized_grouped_by() -> None:
    runs = _sweep_runs_two_param_grouped()

    fig = build_sweep_plot_figure(
        runs,
        x_param='R1',
        y_field='gain_v_per_v',
        lang=PublicationLang.RU,
        group_by='C1',
        x_scale='auto',
        title=None,
    )
    assert 'группировка по' in fig.axes[0].get_title()
    plt.close(fig)


def test_build_sweep_plot_figure_x_scale_log_explicit() -> None:
    runs = _sweep_runs_single_param()

    fig = build_sweep_plot_figure(
        runs,
        x_param='R1',
        y_field='gain_v_per_v',
        lang=PublicationLang.EN,
        group_by=None,
        x_scale='log',
        title=None,
    )

    assert fig.axes[0].get_xscale() == 'log'
    plt.close(fig)


def test_build_sweep_plot_figure_raises_when_no_valid_rows() -> None:
    runs = [
        SweepRun(
            parameters={'R1': '1k'},
            result=None,
            values=None,
            error='export failed',
        ),
    ]

    with pytest.raises(ValueError, match='no valid rows'):
        build_sweep_plot_figure(
            runs,
            x_param='R1',
            y_field='gain_v_per_v',
            lang=PublicationLang.RU,
            group_by=None,
            x_scale='auto',
            title=None,
        )


def test_build_sweep_plot_figure_raises_when_y_field_missing() -> None:
    runs = _sweep_runs_single_param()

    with pytest.raises(ValueError, match='y_field'):
        build_sweep_plot_figure(
            runs,
            x_param='R1',
            y_field='not_a_field',
            lang=PublicationLang.RU,
            group_by=None,
            x_scale='auto',
            title=None,
        )


# ───────────────────────── PNG output: DPI = 300 (SC-4) ──────────────────────


def test_render_time_series_publication_png_dpi_is_300(tmp_path: Path) -> None:
    ts = _sine_time_series()
    out = tmp_path / 'tran.png'

    result_path = render_time_series_publication_png(
        ts, signal='v(load)', output=out, lang=PublicationLang.RU,
    )

    assert result_path == out.resolve()
    assert out.is_file()
    with Image.open(out) as img:
        # matplotlib stores DPM internally → читается ≈299.9994.
        # SC-4 acceptance: 300 DPI (vs 120 preview), не bit-exact.
        dpi_x, dpi_y = img.info['dpi']
        assert dpi_x == pytest.approx(300.0, abs=0.01)
        assert dpi_y == pytest.approx(300.0, abs=0.01)


def test_render_ac_sweep_publication_png_dpi_is_300(tmp_path: Path) -> None:
    sweep = _flat_ac_sweep()
    out = tmp_path / 'ac.png'

    render_ac_sweep_publication_png(
        sweep, signal='v(load)', output=out, lang=PublicationLang.EN,
    )

    with Image.open(out) as img:
        # matplotlib stores DPM internally → читается ≈299.9994.
        # SC-4 acceptance: 300 DPI (vs 120 preview), не bit-exact.
        dpi_x, dpi_y = img.info['dpi']
        assert dpi_x == pytest.approx(300.0, abs=0.01)
        assert dpi_y == pytest.approx(300.0, abs=0.01)


def test_render_sweep_plot_publication_png_dpi_is_300(tmp_path: Path) -> None:
    runs = _sweep_runs_single_param()
    out = tmp_path / 'sweep.png'

    render_sweep_plot_publication_png(
        runs,
        x_param='R1',
        y_field='gain_v_per_v',
        output=out,
        lang=PublicationLang.RU,
    )

    with Image.open(out) as img:
        # matplotlib stores DPM internally → читается ≈299.9994.
        # SC-4 acceptance: 300 DPI (vs 120 preview), не bit-exact.
        dpi_x, dpi_y = img.info['dpi']
        assert dpi_x == pytest.approx(300.0, abs=0.01)
        assert dpi_y == pytest.approx(300.0, abs=0.01)


def test_render_creates_parent_dir_if_missing(tmp_path: Path) -> None:
    ts = _sine_time_series()
    out = tmp_path / 'nested' / 'subdir' / 'tran.png'

    render_time_series_publication_png(
        ts, signal='v(load)', output=out, lang=PublicationLang.RU,
    )

    assert out.is_file()
