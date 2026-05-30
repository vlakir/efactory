"""
SweepTableRenderer — pure-function renderers для bridge sweep output
(T022 Phase C, A5).

Три формата: text (aligned plain-text table), CSV (RFC 4180 via stdlib),
JSON (pretty-print indent=2).

Колонки определяются metric (A5 mapping):
- `op`:        param columns + union of all `values` keys per row.
- `gain`:      param columns + [gain_db, gain_linear].
- `bandwidth`: param columns + [f_low_hz, f_high_hz, bandwidth_hz].
- `thd`:       param columns + [thd_percent, dominant_harmonic_n,
                                dominant_harmonic_percent].

Failed combination (run.error is not None) → метрические колонки
получают `''` (CSV/text — пустая строка) или сериализуются с
`error: ...` ключом (JSON).
"""

from __future__ import annotations

import csv
import io
import json
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from application.bridge_sweep import SweepRun


MetricKind = Literal['op', 'gain', 'bandwidth', 'thd']

_FIXED_METRIC_COLUMNS: dict[MetricKind, tuple[str, ...]] = {
    'gain': ('gain_db', 'gain_linear'),
    'bandwidth': ('f_low_hz', 'f_high_hz', 'bandwidth_hz'),
    'thd': ('thd_percent', 'dominant_harmonic_n', 'dominant_harmonic_percent'),
}

# Placeholder для missing/failed cells в text format.
_MISSING_TEXT = '-'


def _param_columns(rows: list[SweepRun]) -> list[str]:
    if not rows:
        return []
    return list(rows[0].parameters)


def _metric_columns(rows: list[SweepRun], metric: MetricKind) -> list[str]:
    if metric == 'op':
        # Union all keys из всех rows.values (excluding None values).
        keys: set[str] = set()
        for run in rows:
            if run.values is not None:
                keys.update(run.values.keys())
        return sorted(keys)
    return list(_FIXED_METRIC_COLUMNS[metric])


def _format_value(value: float | str | None, *, missing: str) -> str:
    if value is None:
        return missing
    if isinstance(value, float):
        # Compact representation, %.4g for OP-style traces.
        return f'{value:.4g}'
    return str(value)


def _row_cells(
    run: SweepRun,
    metric_cols: list[str],
    *,
    missing: str,
) -> list[str]:
    """Build CSV/text row cells (parameters first, metric next)."""
    param_cells = [run.parameters[k] for k in run.parameters]
    if run.error is not None or run.values is None:
        metric_cells = [missing] * len(metric_cols)
    else:
        metric_cells = [
            _format_value(run.values.get(c), missing=missing) for c in metric_cols
        ]
    return [*param_cells, *metric_cells]


# ────────── text format ──────────


def render_sweep_text(rows: list[SweepRun], metric: MetricKind) -> str:
    """
    Aligned plain-text таблица (без library `tabulate`).

    Failed combination → метрические колонки = `'FAILED: <reason>'` на
    последней метрической позиции, остальные — `'-'`. Это компромисс
    между визибильностью ошибки и колоночным align.
    """
    if not rows:
        return ''
    param_cols = _param_columns(rows)
    metric_cols = _metric_columns(rows, metric)
    columns = [*param_cols, *metric_cols]

    # Build all cells matrix (including FAILED marker special-case).
    all_cells: list[list[str]] = [list(columns)]  # header row
    for run in rows:
        if run.error is not None:
            param_cells = [run.parameters[k] for k in param_cols]
            tail = ([f'FAILED: {run.error}'] if metric_cols else []) + [
                _MISSING_TEXT
            ] * (len(metric_cols) - 1)
            all_cells.append([*param_cells, *tail[: len(metric_cols)]])
        else:
            all_cells.append(_row_cells(run, metric_cols, missing=_MISSING_TEXT))

    # Compute column widths (longest cell per column).
    widths = [max(len(row[i]) for row in all_cells) for i in range(len(columns))]
    formatted_lines = [
        '  '.join(cell.ljust(w) for cell, w in zip(row, widths, strict=True))
        for row in all_cells
    ]
    return '\n'.join(formatted_lines)


# ────────── CSV format ──────────


def render_sweep_csv(rows: list[SweepRun], metric: MetricKind) -> str:
    """RFC 4180 CSV (stdlib `csv.writer`). Failed cells = empty string."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator='\n')
    if not rows:
        return ''
    param_cols = _param_columns(rows)
    metric_cols = _metric_columns(rows, metric)
    writer.writerow([*param_cols, *metric_cols])
    for run in rows:
        writer.writerow(_row_cells(run, metric_cols, missing=''))
    return buf.getvalue()


# ────────── JSON format ──────────


def render_sweep_json(rows: list[SweepRun], metric: MetricKind) -> str:
    """List[dict[col, value]] с pretty-print (indent=2). Failed: +error key."""
    out: list[dict[str, float | str | int | None]] = []
    for run in rows:
        record: dict[str, float | str | int | None] = dict(run.parameters)
        if run.error is not None:
            record['error'] = run.error
        elif run.values is not None:
            metric_cols = _metric_columns([run], metric)
            for col in metric_cols:
                record[col] = run.values.get(col)
        out.append(record)
    return json.dumps(out, indent=2, ensure_ascii=False)


__all__ = [
    'render_sweep_csv',
    'render_sweep_json',
    'render_sweep_text',
]
