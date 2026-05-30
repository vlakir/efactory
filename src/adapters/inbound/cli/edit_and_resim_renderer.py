"""
Renderer для `bridge edit-and-resim` (T021 Phase B).

Два формата (Q-H → b):
* **text** — aligned plain-text таблица «metric / field / before /
  after / Δ / Δ%». Включает шапку с project / schematic / edits.
* **json** — pretty-print через `EditAndResimReport.model_dump_json(indent=2)`.
  Полные `before` / `after` Measurement-объекты включаются (Q-H → b),
  чтобы programmatic consumer мог вычислить любую производную метрику.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.measurement_delta import (
    BandwidthDelta,
    GainDelta,
    ThdDelta,
)

if TYPE_CHECKING:
    from application.edit_and_resim_with_delta import EditAndResimReport


_NONE_MARK = '—'
_FAILED_MARK = 'FAILED'
_METRIC_NAME: dict[type, str] = {
    GainDelta: 'gain',
    BandwidthDelta: 'bandwidth',
    ThdDelta: 'thd',
}
# Границы fixed-point форматирования: вне диапазона переключаемся
# на scientific notation (читать колонку с 0.0001234 в %.3f нельзя).
_FIXED_MIN = 0.001
_FIXED_MAX = 1e5


def render_edit_and_resim_json(report: EditAndResimReport) -> str:
    """Pretty-print JSON — для programmatic consumers."""
    return report.model_dump_json(indent=2)


def render_edit_and_resim_text(report: EditAndResimReport) -> str:
    """
    Aligned plain-text таблица.

    Шапка: Project (если задан) / Schematic / Edits. Таблица: одна
    строка на каждый delta + опциональная sub-строка `failed_reason`
    при `after is None`.
    """
    header_lines: list[str] = []
    if report.project is not None:
        header_lines.append(f'Project: {report.project}')
    header_lines.append(f'Schematic: {report.schematic}')
    edits_str = ', '.join(f'{ref}={val}' for ref, val in report.edits)
    header_lines.append(f'Edits: {edits_str}')

    columns = ('Metric', 'Field', 'Before', 'After', 'Δ', 'Δ%')
    rows: list[tuple[str, str, str, str, str, str]] = []
    # Парные «sub-rows» для failure-причины: индекс → текст, печатается
    # вторым строчным после соответствующей основной строки.
    sub_rows: dict[int, str] = {}

    for delta in report.deltas:
        metric_name = _METRIC_NAME.get(type(delta), '?')
        field_name = delta.metric_field
        before_value = _value_of(delta, side='before')
        before_str = _format_number(before_value)
        if delta.after is None:
            after_str = _FAILED_MARK
            delta_abs_str = _NONE_MARK
            delta_pct_str = _NONE_MARK
            sub_rows[len(rows)] = delta.failed_reason or 'unknown failure'
        else:
            after_value = _value_of(delta, side='after')
            after_str = _format_number(after_value)
            delta_abs_str = _format_signed(delta.delta_absolute)
            delta_pct_str = _format_signed_percent(delta.delta_relative_percent)
        rows.append(
            (
                metric_name,
                field_name,
                before_str,
                after_str,
                delta_abs_str,
                delta_pct_str,
            ),
        )

    widths = [
        max(len(columns[i]), max((len(r[i]) for r in rows), default=0))
        for i in range(len(columns))
    ]
    header_row = '  '.join(c.ljust(widths[i]) for i, c in enumerate(columns))
    separator = '  '.join('─' * w for w in widths)

    body_lines: list[str] = [header_row, separator]
    for idx, row in enumerate(rows):
        body_lines.append(
            '  '.join(cell.ljust(widths[i]) for i, cell in enumerate(row)),
        )
        if idx in sub_rows:
            indent = ' ' * (widths[0] + widths[1] + widths[2] + 6)
            body_lines.append(f'{indent}{sub_rows[idx]}')

    return '\n'.join([*header_lines, '', *body_lines, ''])


def _value_of(
    delta: GainDelta | BandwidthDelta | ThdDelta,
    *,
    side: str,
) -> float:
    measurement = delta.before if side == 'before' else delta.after
    if measurement is None:  # pragma: no cover (caller checks)
        msg = 'after is None — handled by failed-row branch'
        raise ValueError(msg)
    if isinstance(delta, GainDelta):
        return float(measurement.value_db)  # type: ignore[union-attr]
    if isinstance(delta, BandwidthDelta):
        return float(measurement.bandwidth_hz)  # type: ignore[union-attr]
    if isinstance(delta, ThdDelta):
        return float(measurement.thd_percent)  # type: ignore[union-attr]
    msg = f'unknown delta type: {type(delta).__name__}'  # pragma: no cover
    raise TypeError(msg)


def _format_number(value: float) -> str:
    """Fixed-point в `[_FIXED_MIN; _FIXED_MAX)`, иначе scientific."""
    if value == 0.0:
        return '0.000'
    abs_v = abs(value)
    if _FIXED_MIN <= abs_v < _FIXED_MAX:
        return f'{value:.3f}'
    return f'{value:.3e}'


def _format_signed(value: float | None) -> str:
    if value is None:
        return _NONE_MARK
    if value == 0.0:
        return '0.000'
    abs_v = abs(value)
    if _FIXED_MIN <= abs_v < _FIXED_MAX:
        return f'{value:+.3f}'
    return f'{value:+.3e}'


def _format_signed_percent(value: float | None) -> str:
    if value is None:
        return _NONE_MARK
    return f'{value:+.2f}%'


__all__ = ['render_edit_and_resim_json', 'render_edit_and_resim_text']
