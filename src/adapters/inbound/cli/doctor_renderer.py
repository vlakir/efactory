"""
Human-readable рендер `DoctorReport` (T036).

Pure-function: `render_doctor_report(report) -> str`. Без I/O,
полностью покрыто unit-тестами.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.doctor import CheckStatus

if TYPE_CHECKING:
    from domain.doctor import DoctorCheck, DoctorReport


_STATUS_MARKER: dict[CheckStatus, str] = {
    CheckStatus.OK: '[OK]',
    CheckStatus.WARN: '[WARN]',
    CheckStatus.FAIL: '[FAIL]',
}

_CATEGORY_TITLE: dict[str, str] = {
    'toolchain': 'Toolchain versions',
    'gui': 'GUI passthrough',
    'mounts': 'Mounts',
    'runtime': 'Runtime constraints',
    'host': 'Host environment',
}


def render_doctor_report(report: DoctorReport) -> str:
    """
    Сгенерировать human-readable отчёт. Stable layout — категории
    в canonical-порядке, проверки внутри — в порядке появления.
    """
    lines: list[str] = []
    lines.append('efactory doctor')
    lines.append('===============')
    lines.append('')

    for category, checks in report.iter_categories():
        title = _CATEGORY_TITLE.get(category, category)
        lines.append(f'## {title}')
        max_name = max(len(c.name) for c in checks)
        lines.extend(_render_check(check, name_width=max_name) for check in checks)
        lines.append('')

    lines.append(_render_summary(report))
    return '\n'.join(lines)


def _render_check(check: DoctorCheck, *, name_width: int) -> str:
    marker = _STATUS_MARKER[check.status]
    return f'  {marker:<6} {check.name:<{name_width}}  {check.detail}'


def _render_summary(report: DoctorReport) -> str:
    counts = dict.fromkeys(CheckStatus, 0)
    for check in report.checks:
        counts[check.status] += 1
    worst = report.worst_status
    return (
        f'Summary: {counts[CheckStatus.OK]} OK, '
        f'{counts[CheckStatus.WARN]} WARN, '
        f'{counts[CheckStatus.FAIL]} FAIL '
        f'-> worst={worst.value}'
    )


__all__ = ['render_doctor_report']
