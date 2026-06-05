"""Unit tests for MarkdownSimReportWriter (T035 Phase 2.3)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from adapters.outbound.sim_report_markdown import writer as writer_module
from adapters.outbound.sim_report_markdown.writer import MarkdownSimReportWriter
from domain.publication import (
    MeasurementSummary,
    ParametricSweepPoint,
    ParametricSweepSection,
    PublicationLang,
    SimulationResultsBundle,
)
from domain.simulation import AcSweep, TimeSeries

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

# ─────────────────────────── fixtures ────────────────────────────


def _utc(year: int = 2026, month: int = 6, day: int = 5, hour: int = 18) -> datetime:
    return datetime(year, month, day, hour, 30, 45, tzinfo=UTC)


def _ts(signal: str = 'v(load)') -> TimeSeries:
    return TimeSeries(
        time=(0.0, 1e-6, 2e-6, 3e-6),
        traces={signal: (0.0, 0.5, 1.0, 0.5)},
    )


def _ac(signal: str = 'v(load)') -> AcSweep:
    return AcSweep(
        frequency=(1.0, 10.0, 100.0, 1000.0),
        traces_real={signal: (1.0, 0.95, 0.9, 0.85)},
        traces_imag={signal: (0.0, 0.0, 0.0, 0.0)},
    )


def _basic_bundle(**overrides: object) -> SimulationResultsBundle:
    base: dict[str, object] = {
        'project': 'se-amp',
        'efactory_version': '0.3.0-dev',
        'publication_timestamp': _utc(),
    }
    base.update(overrides)
    return SimulationResultsBundle.model_validate(base)


@pytest.fixture
def fake_render(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    """Patch publication-plot render functions in the writer module.

    Returns list of recorded calls; each is dict with keys
    `kind` (tran/ac/sweep), `output` (Path), `lang` (PublicationLang),
    plus kind-specific extras.
    """
    calls: list[dict[str, object]] = []

    def _fake_tran(series, *, signal, output, lang, title=None):  # noqa: ANN001,ANN202,ARG001
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b'\x89PNG fake-tran')
        calls.append(
            {'kind': 'tran', 'signal': signal, 'output': output, 'lang': lang},
        )
        return output

    def _fake_ac(sweep, *, signal, output, lang, title=None):  # noqa: ANN001,ANN202,ARG001
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b'\x89PNG fake-ac')
        calls.append(
            {'kind': 'ac', 'signal': signal, 'output': output, 'lang': lang},
        )
        return output

    def _fake_sweep(  # noqa: ANN202
        rows,  # noqa: ANN001
        *,
        x_param,  # noqa: ANN001
        y_field,  # noqa: ANN001
        output,  # noqa: ANN001
        lang,  # noqa: ANN001
        group_by=None,  # noqa: ANN001
        x_scale='auto',  # noqa: ANN001,ARG001
        title=None,  # noqa: ANN001,ARG001
    ):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b'\x89PNG fake-sweep')
        calls.append(
            {
                'kind': 'sweep',
                'x_param': x_param,
                'y_field': y_field,
                'group_by': group_by,
                'rows_len': len(rows),
                'output': output,
                'lang': lang,
            },
        )
        return output

    monkeypatch.setattr(
        writer_module, 'render_time_series_publication_png', _fake_tran,
    )
    monkeypatch.setattr(
        writer_module, 'render_ac_sweep_publication_png', _fake_ac,
    )
    monkeypatch.setattr(
        writer_module, 'render_sweep_plot_publication_png', _fake_sweep,
    )
    return calls


# ─────────────────────────── basic output ────────────────────────────


async def test_write_creates_report_md(
    tmp_path: Path, fake_render: list[dict[str, object]],
) -> None:
    bundle = _basic_bundle()
    writer = MarkdownSimReportWriter()

    artifacts = await writer.write(
        bundle, out_dir=tmp_path / 'out', lang=PublicationLang.RU,
    )

    assert artifacts.report_md.is_file()
    assert artifacts.report_md.name == 'report.md'


async def test_write_creates_plots_dir(
    tmp_path: Path, fake_render: list[dict[str, object]],
) -> None:
    bundle = _basic_bundle()
    writer = MarkdownSimReportWriter()

    await writer.write(
        bundle, out_dir=tmp_path / 'out', lang=PublicationLang.RU,
    )

    assert (tmp_path / 'out' / 'plots').is_dir()


# ─────────────────────────── metadata ────────────────────────────


async def test_write_ru_metadata_contains_russian_section_title(
    tmp_path: Path, fake_render: list[dict[str, object]],
) -> None:
    writer = MarkdownSimReportWriter()
    artifacts = await writer.write(
        _basic_bundle(), out_dir=tmp_path / 'out', lang=PublicationLang.RU,
    )
    content = artifacts.report_md.read_text(encoding='utf-8')
    assert '## Метаданные' in content
    assert '# Отчёт о симуляции — se-amp' in content


async def test_write_en_metadata_contains_english_section_title(
    tmp_path: Path, fake_render: list[dict[str, object]],
) -> None:
    writer = MarkdownSimReportWriter()
    artifacts = await writer.write(
        _basic_bundle(), out_dir=tmp_path / 'out', lang=PublicationLang.EN,
    )
    content = artifacts.report_md.read_text(encoding='utf-8')
    assert '## Metadata' in content
    assert '# Simulation Report — se-amp' in content


async def test_write_metadata_shows_iso_publication_timestamp(
    tmp_path: Path, fake_render: list[dict[str, object]],
) -> None:
    writer = MarkdownSimReportWriter()
    bundle = _basic_bundle(
        publication_timestamp=datetime(2026, 6, 5, 18, 30, 45, tzinfo=UTC),
    )
    artifacts = await writer.write(
        bundle, out_dir=tmp_path / 'out', lang=PublicationLang.EN,
    )
    assert '2026-06-05T18:30:45+00:00' in artifacts.report_md.read_text()


async def test_write_metadata_shows_source_sim_ts_when_set(
    tmp_path: Path, fake_render: list[dict[str, object]],
) -> None:
    writer = MarkdownSimReportWriter()
    bundle = _basic_bundle(
        source_simulation_timestamp=datetime(2026, 6, 5, 17, 0, 0, tzinfo=UTC),
    )
    artifacts = await writer.write(
        bundle, out_dir=tmp_path / 'out', lang=PublicationLang.EN,
    )
    content = artifacts.report_md.read_text(encoding='utf-8')
    assert '2026-06-05T17:00:00+00:00' in content


async def test_write_metadata_shows_fresh_run_when_source_ts_none(
    tmp_path: Path, fake_render: list[dict[str, object]],
) -> None:
    writer = MarkdownSimReportWriter()
    artifacts = await writer.write(
        _basic_bundle(), out_dir=tmp_path / 'out', lang=PublicationLang.RU,
    )
    content = artifacts.report_md.read_text(encoding='utf-8')
    assert 'свежий прогон' in content


# ─────────────────────────── TRAN section ────────────────────────────


async def test_write_tran_section_present_with_signals(
    tmp_path: Path, fake_render: list[dict[str, object]],
) -> None:
    writer = MarkdownSimReportWriter()
    bundle = _basic_bundle(tran=_ts('v(load)'), tran_signals=('v(load)',))

    artifacts = await writer.write(
        bundle, out_dir=tmp_path / 'out', lang=PublicationLang.RU,
    )

    content = artifacts.report_md.read_text(encoding='utf-8')
    assert '## Анализ переходных процессов' in content
    tran_calls = [c for c in fake_render if c['kind'] == 'tran']
    assert len(tran_calls) == 1
    assert tran_calls[0]['signal'] == 'v(load)'


async def test_write_tran_section_omitted_when_signals_empty(
    tmp_path: Path, fake_render: list[dict[str, object]],
) -> None:
    writer = MarkdownSimReportWriter()
    bundle = _basic_bundle(tran=_ts())  # tran_signals defaults to ()
    artifacts = await writer.write(
        bundle, out_dir=tmp_path / 'out', lang=PublicationLang.RU,
    )
    assert '## Анализ переходных процессов' not in artifacts.report_md.read_text()


async def test_write_tran_section_references_plot_via_relative_path(
    tmp_path: Path, fake_render: list[dict[str, object]],
) -> None:
    writer = MarkdownSimReportWriter()
    bundle = _basic_bundle(tran=_ts(), tran_signals=('v(load)',))
    artifacts = await writer.write(
        bundle, out_dir=tmp_path / 'out', lang=PublicationLang.EN,
    )
    content = artifacts.report_md.read_text()
    assert '](plots/tran-v_load_.png)' in content or '](plots/tran-v_load.png)' in content


# ─────────────────────────── AC section ────────────────────────────


async def test_write_ac_section_present_with_signals(
    tmp_path: Path, fake_render: list[dict[str, object]],
) -> None:
    writer = MarkdownSimReportWriter()
    bundle = _basic_bundle(ac_sweep=_ac(), ac_signals=('v(load)',))
    artifacts = await writer.write(
        bundle, out_dir=tmp_path / 'out', lang=PublicationLang.RU,
    )
    content = artifacts.report_md.read_text()
    assert 'AC sweep' in content or 'Малосигнальный' in content
    ac_calls = [c for c in fake_render if c['kind'] == 'ac']
    assert len(ac_calls) == 1


async def test_write_ac_section_omitted_when_signals_empty(
    tmp_path: Path, fake_render: list[dict[str, object]],
) -> None:
    writer = MarkdownSimReportWriter()
    bundle = _basic_bundle(ac_sweep=_ac())
    artifacts = await writer.write(
        bundle, out_dir=tmp_path / 'out', lang=PublicationLang.RU,
    )
    assert 'Малосигнальный' not in artifacts.report_md.read_text()


# ─────────────────────── parametric sweep section ───────────────────────


def _section(name: str = 'gain vs R1') -> ParametricSweepSection:
    return ParametricSweepSection(
        name=name,
        x_param='R1',
        y_field='gain',
        rows=(
            ParametricSweepPoint(parameters={'R1': '1k'}, values={'gain': 10.0}),
            ParametricSweepPoint(parameters={'R1': '2k'}, values={'gain': 12.0}),
        ),
    )


async def test_write_sweep_section_present(
    tmp_path: Path, fake_render: list[dict[str, object]],
) -> None:
    writer = MarkdownSimReportWriter()
    bundle = _basic_bundle(parametric_sweeps=(_section(),))
    artifacts = await writer.write(
        bundle, out_dir=tmp_path / 'out', lang=PublicationLang.RU,
    )
    content = artifacts.report_md.read_text()
    assert '## Параметрические свипы' in content
    assert '### gain vs R1' in content
    sweep_calls = [c for c in fake_render if c['kind'] == 'sweep']
    assert len(sweep_calls) == 1
    assert sweep_calls[0]['x_param'] == 'R1'
    assert sweep_calls[0]['y_field'] == 'gain'
    assert sweep_calls[0]['rows_len'] == 2


async def test_write_sweep_section_with_group_by_passes_to_render(
    tmp_path: Path, fake_render: list[dict[str, object]],
) -> None:
    writer = MarkdownSimReportWriter()
    section = ParametricSweepSection(
        name='gain vs R1 by C1',
        x_param='R1',
        y_field='gain',
        group_by='C1',
        rows=(
            ParametricSweepPoint(
                parameters={'R1': '1k', 'C1': '1u'}, values={'gain': 10.0},
            ),
        ),
    )
    bundle = _basic_bundle(parametric_sweeps=(section,))
    await writer.write(
        bundle, out_dir=tmp_path / 'out', lang=PublicationLang.RU,
    )
    sweep_calls = [c for c in fake_render if c['kind'] == 'sweep']
    assert sweep_calls[0]['group_by'] == 'C1'


# ─────────────────────────── magnetics M-thin ────────────────────────────


async def test_write_magnetics_missing_when_path_none(
    tmp_path: Path, fake_render: list[dict[str, object]],
) -> None:
    writer = MarkdownSimReportWriter()
    artifacts = await writer.write(
        _basic_bundle(), out_dir=tmp_path / 'out', lang=PublicationLang.RU,
    )
    content = artifacts.report_md.read_text()
    assert 'Магнитные артефакты не найдены' in content


async def test_write_magnetics_missing_when_file_does_not_exist(
    tmp_path: Path, fake_render: list[dict[str, object]],
) -> None:
    writer = MarkdownSimReportWriter()
    bundle = _basic_bundle(
        magnetics_summary_path=tmp_path / 'nonexistent' / 'summary.json',
    )
    artifacts = await writer.write(
        bundle, out_dir=tmp_path / 'out', lang=PublicationLang.RU,
    )
    assert 'Магнитные артефакты не найдены' in artifacts.report_md.read_text()


async def test_write_magnetics_invalid_when_not_json(
    tmp_path: Path, fake_render: list[dict[str, object]],
) -> None:
    summary = tmp_path / 'summary.json'
    summary.write_text('not json at all {{{', encoding='utf-8')
    writer = MarkdownSimReportWriter()
    bundle = _basic_bundle(magnetics_summary_path=summary)

    artifacts = await writer.write(
        bundle, out_dir=tmp_path / 'out', lang=PublicationLang.RU,
    )
    assert 'формат не распознан' in artifacts.report_md.read_text()


async def test_write_magnetics_table_rendered_when_valid_json(
    tmp_path: Path, fake_render: list[dict[str, object]],
) -> None:
    summary = tmp_path / 'summary.json'
    summary.write_text(
        json.dumps(
            {
                'schema_version': 1,
                'fem_inductance_h': 6.95,
                'peak_flux_density_t': 0.42,
                'fem_method': 'linear',
                'relative_difference': 0.025,
            },
        ),
        encoding='utf-8',
    )
    writer = MarkdownSimReportWriter()
    bundle = _basic_bundle(magnetics_summary_path=summary)

    artifacts = await writer.write(
        bundle, out_dir=tmp_path / 'out', lang=PublicationLang.RU,
    )
    content = artifacts.report_md.read_text()
    assert '## Магнитные компоненты' in content
    assert 'Индуктивность L_self' in content
    assert '6.95' in content
    assert 'Гн' in content
    assert 'B_peak' in content
    assert 'Тл' in content
    assert 'linear' in content
    assert '2.50' in content  # relative_difference * 100


async def test_write_magnetics_table_en_uses_si_units(
    tmp_path: Path, fake_render: list[dict[str, object]],
) -> None:
    summary = tmp_path / 'summary.json'
    summary.write_text(
        json.dumps(
            {
                'fem_inductance_h': 1.5,
                'peak_flux_density_t': 0.3,
            },
        ),
        encoding='utf-8',
    )
    writer = MarkdownSimReportWriter()
    bundle = _basic_bundle(magnetics_summary_path=summary)
    artifacts = await writer.write(
        bundle, out_dir=tmp_path / 'out', lang=PublicationLang.EN,
    )
    content = artifacts.report_md.read_text()
    assert 'Self-inductance L' in content
    assert '| 1.5 | H |' in content
    assert '| 0.3 | T |' in content


async def test_write_magnetics_invalid_when_json_lacks_known_fields(
    tmp_path: Path, fake_render: list[dict[str, object]],
) -> None:
    summary = tmp_path / 'summary.json'
    summary.write_text(json.dumps({'unrelated_field': 42}), encoding='utf-8')
    writer = MarkdownSimReportWriter()
    bundle = _basic_bundle(magnetics_summary_path=summary)
    artifacts = await writer.write(
        bundle, out_dir=tmp_path / 'out', lang=PublicationLang.RU,
    )
    assert 'формат не распознан' in artifacts.report_md.read_text()


# ─────────────────────────── measurements ────────────────────────────


async def test_write_measurements_section_rendered_as_markdown_table(
    tmp_path: Path, fake_render: list[dict[str, object]],
) -> None:
    bundle = _basic_bundle(
        measurements=(
            MeasurementSummary(name='gain_v_per_v', value=12.5, unit='V/V'),
            MeasurementSummary(
                name='thd_percent', value=0.034, unit='%', description='THD',
            ),
        ),
    )
    writer = MarkdownSimReportWriter()
    artifacts = await writer.write(
        bundle, out_dir=tmp_path / 'out', lang=PublicationLang.EN,
    )
    content = artifacts.report_md.read_text()
    assert '## Measurements summary' in content
    assert '| Metric | Value | Unit | Description |' in content
    assert '| gain_v_per_v | 12.5 | V/V |' in content
    assert '| thd_percent | 0.034 | % | THD |' in content


async def test_write_measurements_omitted_when_empty(
    tmp_path: Path, fake_render: list[dict[str, object]],
) -> None:
    writer = MarkdownSimReportWriter()
    artifacts = await writer.write(
        _basic_bundle(), out_dir=tmp_path / 'out', lang=PublicationLang.RU,
    )
    assert '## Сводка измерений' not in artifacts.report_md.read_text()


# ─────────────────────────── artifacts return ────────────────────────────


async def test_write_returns_artifacts_with_plot_paths(
    tmp_path: Path, fake_render: list[dict[str, object]],
) -> None:
    writer = MarkdownSimReportWriter()
    bundle = _basic_bundle(
        tran=_ts(), tran_signals=('v(load)',),
        ac_sweep=_ac(), ac_signals=('v(load)',),
    )
    artifacts = await writer.write(
        bundle, out_dir=tmp_path / 'out', lang=PublicationLang.RU,
    )
    assert len(artifacts.plots) == 2
    for p in artifacts.plots:
        assert p.is_file()


async def test_write_returns_source_simulation_ts_passthrough(
    tmp_path: Path, fake_render: list[dict[str, object]],
) -> None:
    source_ts = datetime(2026, 6, 5, 17, 0, 0, tzinfo=UTC)
    bundle = _basic_bundle(source_simulation_timestamp=source_ts)
    writer = MarkdownSimReportWriter()
    artifacts = await writer.write(
        bundle, out_dir=tmp_path / 'out', lang=PublicationLang.EN,
    )
    assert artifacts.source_simulation_ts == source_ts


async def test_write_returns_no_tables(
    tmp_path: Path, fake_render: list[dict[str, object]],
) -> None:
    writer = MarkdownSimReportWriter()
    artifacts = await writer.write(
        _basic_bundle(), out_dir=tmp_path / 'out', lang=PublicationLang.RU,
    )
    assert artifacts.tables == ()
