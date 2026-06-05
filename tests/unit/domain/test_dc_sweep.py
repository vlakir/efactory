"""Unit tests `DcSweepAnalysis` + `DcSweep` (T188)."""

from __future__ import annotations

import pytest

from domain.simulation import DcSweep, DcSweepAnalysis, SimulationResult


def test_dc_sweep_analysis_minimal() -> None:
    a = DcSweepAnalysis(source='V1', start=0.0, stop=5.0, step=0.1)
    assert a.type == 'dc'
    assert a.source == 'V1'
    assert a.step == 0.1


def test_dc_sweep_analysis_negative_range() -> None:
    a = DcSweepAnalysis(source='V1', start=5.0, stop=0.0, step=0.1)
    assert a.start > a.stop  # ngspice supports descending


def test_dc_sweep_analysis_rejects_equal_start_stop() -> None:
    with pytest.raises(ValueError, match='must differ from'):
        DcSweepAnalysis(source='V1', start=1.0, stop=1.0, step=0.1)


def test_dc_sweep_analysis_step_must_be_positive() -> None:
    with pytest.raises(ValueError):
        DcSweepAnalysis(source='V1', start=0.0, stop=5.0, step=0.0)
    with pytest.raises(ValueError):
        DcSweepAnalysis(source='V1', start=0.0, stop=5.0, step=-0.1)


def test_dc_sweep_result_minimal() -> None:
    r = DcSweep(
        sweep_variable='v-sweep',
        sweep_values=(0.0, 0.5, 1.0),
        traces={'v(out)': (0.0, 0.4, 0.8)},
    )
    assert r.sweep_values == (0.0, 0.5, 1.0)


def test_dc_sweep_trace_length_mismatch_rejected() -> None:
    with pytest.raises(ValueError, match='samples but sweep_values has 3'):
        DcSweep(
            sweep_variable='v-sweep',
            sweep_values=(0.0, 0.5, 1.0),
            traces={'v(out)': (0.0, 0.4)},  # 2 vs 3
        )


def test_simulation_result_dc_sweep_branch() -> None:
    sr = SimulationResult(
        dc_sweep=DcSweep(
            sweep_variable='v-sweep',
            sweep_values=(0.0, 1.0),
            traces={'v(out)': (0.0, 5.0)},
        ),
    )
    assert sr.dc_sweep is not None
    assert sr.operating_points is None


def test_simulation_result_rejects_two_branches() -> None:
    with pytest.raises(ValueError, match='exactly one'):
        SimulationResult(
            operating_points={'v(out)': 1.0},
            dc_sweep=DcSweep(
                sweep_variable='V',
                sweep_values=(0.0, 1.0),
                traces={'v(out)': (0.0, 5.0)},
            ),
        )
