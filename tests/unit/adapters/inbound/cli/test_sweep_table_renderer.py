"""SweepTableRenderer: text/csv/json output (T022 Phase C, A5)."""

from __future__ import annotations

import json

import pytest

from adapters.inbound.cli.sweep_table_renderer import (
    render_sweep_csv,
    render_sweep_json,
    render_sweep_text,
)
from application.bridge_sweep import SweepRun
from domain.simulation import SimulationResult


def _run(
    parameters: dict[str, str],
    values: dict[str, float | str | None] | None,
    error: str | None = None,
    result: SimulationResult | None = None,
) -> SweepRun:
    return SweepRun(
        parameters=parameters,
        result=result,
        values=values,
        error=error,
    )


# ────────── text format ──────────


def test_text_op_header_includes_param_and_op_columns() -> None:
    rows = [
        _run({'R1': '1k'}, {'v(in)': 1.0, 'v(out)': 0.5}),
        _run({'R1': '10k'}, {'v(in)': 1.0, 'v(out)': 0.91}),
    ]
    text = render_sweep_text(rows, metric='op')
    lines = text.splitlines()
    header = lines[0]
    # Param column first, op signals follow (alphabetical for stability).
    assert header.startswith('R1')
    assert 'v(in)' in header
    assert 'v(out)' in header


def test_text_op_data_rows_aligned() -> None:
    rows = [
        _run({'R1': '1k'}, {'v(in)': 1.0, 'v(out)': 0.5}),
        _run({'R1': '10k'}, {'v(in)': 1.0, 'v(out)': 0.91}),
    ]
    text = render_sweep_text(rows, metric='op')
    lines = text.splitlines()
    # 1 header + 2 data lines.
    assert len(lines) == 3
    # Параметры присутствуют в data rows.
    assert any('1k' in ln for ln in lines[1:])
    assert any('10k' in ln for ln in lines[1:])


def test_text_gain_fixed_columns() -> None:
    rows = [
        _run({'R1': '1k'}, {'gain_db': 20.0, 'gain_linear': 10.0}),
        _run({'R1': '10k'}, {'gain_db': 6.02, 'gain_linear': 2.0}),
    ]
    text = render_sweep_text(rows, metric='gain')
    header = text.splitlines()[0]
    assert 'R1' in header
    assert 'gain_db' in header
    assert 'gain_linear' in header


def test_text_bandwidth_fixed_columns() -> None:
    rows = [
        _run({'R1': '1k'}, {
            'f_low_hz': 20.0, 'f_high_hz': 20000.0, 'bandwidth_hz': 19980.0,
        }),
    ]
    text = render_sweep_text(rows, metric='bandwidth')
    header = text.splitlines()[0]
    for col in ('f_low_hz', 'f_high_hz', 'bandwidth_hz'):
        assert col in header


def test_text_thd_fixed_columns() -> None:
    rows = [
        _run({'R1': '1k'}, {
            'thd_percent': 5.0, 'dominant_harmonic_n': 2,
            'dominant_harmonic_percent': 4.95,
        }),
    ]
    text = render_sweep_text(rows, metric='thd')
    header = text.splitlines()[0]
    for col in ('thd_percent', 'dominant_harmonic_n', 'dominant_harmonic_percent'):
        assert col in header


def test_text_failed_combination_shows_failed_marker() -> None:
    rows = [
        _run({'R1': '1k'}, {'v(out)': 0.5}),
        _run({'R1': '10k'}, None, error='sim failed: singular matrix'),
    ]
    text = render_sweep_text(rows, metric='op')
    lines = text.splitlines()
    # Failed row should contain FAILED marker.
    failed = [ln for ln in lines if 'FAILED' in ln]
    assert len(failed) == 1
    assert '10k' in failed[0]


def test_text_op_missing_signal_in_one_combo_shows_none() -> None:
    """Union ключей; missing → None placeholder."""
    rows = [
        _run({'R1': '1k'}, {'v(in)': 1.0, 'v(out)': 0.5}),
        _run({'R1': '10k'}, {'v(in)': 1.0}),  # v(out) missing
    ]
    text = render_sweep_text(rows, metric='op')
    lines = text.splitlines()
    # Header all-3 columns.
    assert 'v(out)' in lines[0]
    # Last row has missing-marker for v(out).
    last = lines[-1]
    assert any(marker in last for marker in ('-', 'None', 'N/A'))


# ────────── CSV format ──────────


def test_csv_op_format() -> None:
    rows = [
        _run({'R1': '1k'}, {'v(in)': 1.0, 'v(out)': 0.5}),
        _run({'R1': '10k'}, {'v(in)': 1.0, 'v(out)': 0.91}),
    ]
    csv_text = render_sweep_csv(rows, metric='op')
    lines = csv_text.strip().splitlines()
    # Header + 2 data rows.
    assert len(lines) == 3
    header = lines[0].split(',')
    assert 'R1' in header
    assert 'v(in)' in header
    assert 'v(out)' in header


def test_csv_gain_columns_fixed() -> None:
    rows = [
        _run({'R1': '1k'}, {'gain_db': 20.0, 'gain_linear': 10.0}),
    ]
    csv_text = render_sweep_csv(rows, metric='gain')
    header = csv_text.strip().splitlines()[0].split(',')
    assert header == ['R1', 'gain_db', 'gain_linear']


def test_csv_failed_row_blank_metric_columns() -> None:
    rows = [
        _run({'R1': '1k'}, {'gain_db': 20.0, 'gain_linear': 10.0}),
        _run({'R1': '10k'}, None, error='sim failed'),
    ]
    csv_text = render_sweep_csv(rows, metric='gain')
    lines = csv_text.strip().splitlines()
    # Failed row has empty metric cells but parameter cell filled.
    failed_row = lines[2].split(',')
    assert failed_row[0] == '10k'
    # gain_db and gain_linear empty (or sentinel).
    assert failed_row[1] == '' or failed_row[1] == 'None'
    assert failed_row[2] == '' or failed_row[2] == 'None'


# ────────── JSON format ──────────


def test_json_op_format_parseable() -> None:
    rows = [
        _run({'R1': '1k'}, {'v(in)': 1.0, 'v(out)': 0.5}),
        _run({'R1': '10k'}, {'v(in)': 1.0, 'v(out)': 0.91}),
    ]
    json_text = render_sweep_json(rows, metric='op')
    parsed = json.loads(json_text)
    assert isinstance(parsed, list)
    assert len(parsed) == 2
    assert parsed[0]['R1'] == '1k'
    assert parsed[0]['v(in)'] == pytest.approx(1.0)
    assert parsed[0]['v(out)'] == pytest.approx(0.5)


def test_json_gain_format() -> None:
    rows = [
        _run({'R1': '1k', 'C1': '100n'}, {'gain_db': 20.0, 'gain_linear': 10.0}),
    ]
    parsed = json.loads(render_sweep_json(rows, metric='gain'))
    assert parsed[0]['R1'] == '1k'
    assert parsed[0]['C1'] == '100n'
    assert parsed[0]['gain_db'] == pytest.approx(20.0)


def test_json_failed_row_has_error_key() -> None:
    rows = [
        _run({'R1': '10k'}, None, error='sim failed: singular matrix'),
    ]
    parsed = json.loads(render_sweep_json(rows, metric='op'))
    assert parsed[0]['R1'] == '10k'
    assert 'error' in parsed[0]
    assert 'singular' in parsed[0]['error']


def test_json_indent_pretty() -> None:
    """Spec FR: JSON pretty-print indent=2."""
    rows = [_run({'R1': '1k'}, {'v(in)': 1.0})]
    text = render_sweep_json(rows, metric='op')
    # Pretty-printed JSON has newlines.
    assert '\n' in text


# ────────── empty rows edge case ──────────


def test_text_empty_rows() -> None:
    text = render_sweep_text([], metric='op')
    # Может быть header-only или empty; не должен raise.
    assert isinstance(text, str)


def test_csv_empty_rows() -> None:
    csv_text = render_sweep_csv([], metric='gain')
    # Empty CSV — header line или пустая строка.
    assert isinstance(csv_text, str)


def test_json_empty_rows() -> None:
    json_text = render_sweep_json([], metric='op')
    parsed = json.loads(json_text)
    assert parsed == []
