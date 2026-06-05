"""DC sweep section в MarkdownSimReportWriter (T188)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from adapters.outbound.sim_report_markdown.writer import MarkdownSimReportWriter
from domain.publication import PublicationLang, SimulationResultsBundle
from domain.simulation import DcSweep


def _bundle_with_dc() -> SimulationResultsBundle:
    return SimulationResultsBundle(
        project='dc-test',
        efactory_version='0.3.0',
        publication_timestamp=datetime.now(UTC),
        dc_sweep=DcSweep(
            sweep_variable='v-sweep',
            sweep_values=(0.0, 0.5, 1.0, 1.5, 2.0),
            traces={
                'v(out)': (0.0, 0.4, 0.8, 1.2, 1.6),
                'v(in)': (0.0, 0.5, 1.0, 1.5, 2.0),
            },
        ),
        dc_signals=('v(out)',),
    )


@pytest.mark.asyncio
async def test_dc_section_rendered_ru(tmp_path: Path) -> None:
    writer = MarkdownSimReportWriter()
    out_dir = tmp_path / 'sim-report'
    artifacts = await writer.write(
        _bundle_with_dc(), out_dir=out_dir, lang=PublicationLang.RU
    )
    report = artifacts.report_md.read_text(encoding='utf-8')
    assert '## DC-развёртка (transfer characteristic)' in report
    assert '![v(out)](plots/dc-v_out.png)' in report
    assert (out_dir / 'plots' / 'dc-v_out.png').is_file()


@pytest.mark.asyncio
async def test_dc_section_rendered_en(tmp_path: Path) -> None:
    writer = MarkdownSimReportWriter()
    out_dir = tmp_path / 'sim-report'
    artifacts = await writer.write(
        _bundle_with_dc(), out_dir=out_dir, lang=PublicationLang.EN
    )
    report = artifacts.report_md.read_text(encoding='utf-8')
    assert '## DC sweep (transfer characteristic)' in report
    assert len(artifacts.plots) == 1
