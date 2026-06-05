"""
MarkdownGridReportWriter — render `OffGridReport` to disk (T187).

Layout: `<out_root>/<UTC-ISO-ts>/report.md`. Sortирует endpoints
по |Δ| убывая — большие drift'ы сверху, приоритет для ручного fix
в KiCad GUI (когда T187 detector используется для hand-edited
schematics, не для built-in templates which T187 made clean).
Timestamp с microseconds для безопасности при concurrent runs (T029 N2).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from domain.grid import OffGridEndpoint, OffGridReport


class MarkdownGridReportWriter:
    async def write(self, report: OffGridReport, out_root: Path) -> Path:
        return await asyncio.to_thread(self._write_sync, report, out_root)

    def _write_sync(self, report: OffGridReport, out_root: Path) -> Path:
        stamp = report.timestamp.strftime('%Y-%m-%dT%H-%M-%S.%f')
        target_dir = out_root / stamp
        target_dir.mkdir(parents=True, exist_ok=True)
        report_path = target_dir / 'report.md'
        report_path.write_text(_render(report), encoding='utf-8')
        return report_path


def _render(report: OffGridReport) -> str:
    lines: list[str] = []
    lines.append(f'# Off-Grid Report — {report.schematic_path.name}')
    lines.append('')
    lines.append(f'- **Schematic:** {report.schematic_path}')
    lines.append(f'- **Timestamp:** {report.timestamp.isoformat()}')
    lines.append(f'- **KiCad version:** {report.kicad_version}')
    lines.append(f'- **Connection grid:** {float(report.grid_step_mm):.3f} mm')
    lines.append(f'- **Off-grid endpoints:** {report.count}')
    lines.append('')

    if report.count == 0:
        lines.append('All pin / wire endpoints on connection grid. ✓')
        lines.append('')
        return '\n'.join(lines) + '\n'

    sorted_eps = sorted(
        report.endpoints,
        key=lambda ep: ep.max_abs_delta_mm,
        reverse=True,
    )

    lines.append('## Endpoints')
    lines.append('')
    lines.append('Sorted by |Δ| descending — top entries are the priority for')
    lines.append('manual fix in KiCad GUI (drag-snap-to-grid per item).')
    lines.append('')
    lines.append(
        '| # | Kind | Description | Pos (mm) | Nearest grid (mm) | Δ (mm) | UUID |'
    )
    lines.append('|---:|---|---|---|---|---|---|')
    for idx, ep in enumerate(sorted_eps, start=1):
        lines.append(_render_row(idx, ep))
    lines.append('')

    return '\n'.join(lines) + '\n'


def _render_row(idx: int, ep: OffGridEndpoint) -> str:
    x, y = ep.pos
    nx, ny = ep.nearest_grid
    dx, dy = ep.delta_mm
    return (
        f'| {idx} | {ep.kind} | {ep.description} | '
        f'{x:.4f}, {y:.4f} | {nx:.4f}, {ny:.4f} | '
        f'{dx:+.4f}, {dy:+.4f} | {ep.uuid} |'
    )


__all__ = ['MarkdownGridReportWriter']
