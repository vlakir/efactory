"""
MarkdownErcReportWriter — render `ErcReport` to disk (T029).

Layout: `<out_root>/<UTC-ISO-ts>/report.md` plus a sidecar copy of the
raw JSON if the caller passes it through. Timestamp uses microseconds
to avoid collisions on concurrent runs (spec N2).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from domain.erc import ErcSeverity

if TYPE_CHECKING:
    from pathlib import Path

    from domain.erc import ErcReport, ErcViolation


class MarkdownErcReportWriter:
    async def write(self, report: ErcReport, out_root: Path) -> Path:
        return await asyncio.to_thread(self._write_sync, report, out_root)

    def _write_sync(self, report: ErcReport, out_root: Path) -> Path:
        stamp = report.timestamp.strftime('%Y-%m-%dT%H-%M-%S.%f')
        target_dir = out_root / stamp
        target_dir.mkdir(parents=True, exist_ok=True)
        report_path = target_dir / 'report.md'
        report_path.write_text(_render(report), encoding='utf-8')
        return report_path


def _render(report: ErcReport) -> str:
    lines: list[str] = []
    lines.append(f'# ERC Report — {report.schematic_path.name}')
    lines.append('')
    lines.append(f'- **Schematic:** {report.schematic_path}')
    lines.append(f'- **Timestamp:** {report.timestamp.isoformat()}')
    lines.append(f'- **KiCad version:** {report.kicad_version}')
    lines.append(
        f'- **Summary:** errors={report.error_count}, '
        f'warnings={report.warning_count}, '
        f'exclusions={report.exclusion_count}'
    )
    lines.append('')

    if report.violations:
        lines.append('## Violations')
        lines.append('')
        for severity in (
            ErcSeverity.ERROR,
            ErcSeverity.WARNING,
            ErcSeverity.EXCLUSION,
        ):
            for v in report.violations:
                if v.severity is severity:
                    lines.extend(_render_violation(v))

    if report.ignored_checks:
        lines.append('## Ignored Checks')
        lines.append('')
        lines.append(
            '*Checks excluded by KiCad GUI (`.kicad_pro` exclusions or '
            'built-in ignored severities):*',
        )
        lines.append('')
        lines.extend(f'- `{ic.key}` — {ic.description}' for ic in report.ignored_checks)
        lines.append('')

    return '\n'.join(lines) + '\n'


def _render_violation(v: ErcViolation) -> list[str]:
    count = len(v.items) or 1
    lines = [f'### {v.severity.value}: {v.type} (×{count})', '']
    if v.description:
        lines.append(f'*Description:* {v.description}')
        lines.append('')
    if v.items:
        lines.append('| Symbol | Pos | UUID |')
        lines.append('|---|---|---|')
        for item in v.items:
            x, y = item.pos
            lines.append(
                f'| {item.description} | {x:.4f}, {y:.4f} | {item.uuid} |',
            )
        lines.append('')
    return lines


__all__ = ['MarkdownErcReportWriter']
