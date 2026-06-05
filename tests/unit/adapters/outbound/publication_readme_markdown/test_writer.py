"""Unit tests for MarkdownPublicationReadmeWriter (T035 Phase 2.4)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from adapters.outbound.publication_readme_markdown.writer import (
    MarkdownPublicationReadmeWriter,
)
from domain.publication import (
    PublicationBundle,
    PublicationLang,
    SchematicPublicationArtifacts,
    SheetArtifactSet,
    SimReportArtifacts,
)

if TYPE_CHECKING:
    from pathlib import Path


def _sheet(out_dir: Path, sheet_name: str = 'demo') -> SheetArtifactSet:
    return SheetArtifactSet(
        sheet_name=sheet_name,
        svg=out_dir / 'schematic' / 'color' / 'per-sheet' / f'{sheet_name}.svg',
        pdf=out_dir / 'schematic' / 'color' / 'per-sheet' / f'{sheet_name}.pdf',
        png=out_dir / 'schematic' / 'color' / 'per-sheet' / f'{sheet_name}.png',
    )


def _schematic_per_sheet_only(
    out_dir: Path,
) -> SchematicPublicationArtifacts:
    color = (_sheet(out_dir, 'demo'),)
    bw = (
        SheetArtifactSet(
            sheet_name='demo',
            svg=out_dir / 'schematic' / 'bw' / 'per-sheet' / 'demo.svg',
            pdf=out_dir / 'schematic' / 'bw' / 'per-sheet' / 'demo.pdf',
            png=out_dir / 'schematic' / 'bw' / 'per-sheet' / 'demo.png',
        ),
    )
    return SchematicPublicationArtifacts(
        color_per_sheet=color,
        bw_per_sheet=bw,
        color_combined=None,
        bw_combined=None,
    )


def _schematic_with_combined(out_dir: Path) -> SchematicPublicationArtifacts:
    color = (_sheet(out_dir, 'demo'),)
    bw = (
        SheetArtifactSet(
            sheet_name='demo',
            svg=out_dir / 'schematic' / 'bw' / 'per-sheet' / 'demo.svg',
            pdf=out_dir / 'schematic' / 'bw' / 'per-sheet' / 'demo.pdf',
            png=out_dir / 'schematic' / 'bw' / 'per-sheet' / 'demo.png',
        ),
    )
    return SchematicPublicationArtifacts(
        color_per_sheet=color,
        bw_per_sheet=bw,
        color_combined=out_dir / 'schematic' / 'color' / 'combined' / 'demo.pdf',
        bw_combined=out_dir / 'schematic' / 'bw' / 'combined' / 'demo.pdf',
    )


def _sim_report(
    out_dir: Path,
    *,
    n_plots: int = 2,
    source_ts: datetime | None = None,
    tables: tuple[Path, ...] = (),
) -> SimReportArtifacts:
    plots_dir = out_dir / 'sim-report' / 'plots'
    plots = tuple(plots_dir / f'plot{i}.png' for i in range(1, n_plots + 1))
    return SimReportArtifacts(
        report_md=out_dir / 'sim-report' / 'report.md',
        plots=plots,
        tables=tables,
        source_simulation_ts=source_ts,
    )


def _bundle(
    out_dir: Path,
    *,
    lang: PublicationLang = PublicationLang.RU,
    schematic: SchematicPublicationArtifacts | None = None,
    sim_report: SimReportArtifacts | None = None,
) -> PublicationBundle:
    if schematic is None and sim_report is None:
        schematic = _schematic_per_sheet_only(out_dir)
    return PublicationBundle(
        project='se-amp',
        timestamp=datetime(2026, 6, 5, 18, 45, 30, tzinfo=UTC),
        efactory_version='0.3.0-dev',
        lang=lang,
        schematic=schematic,
        sim_report=sim_report,
    )


# ─────────────────────────── basic ────────────────────────────


async def test_write_creates_readme_md_in_out_dir(tmp_path: Path) -> None:
    out_dir = tmp_path / 'pub'
    writer = MarkdownPublicationReadmeWriter()

    path = await writer.write(_bundle(out_dir), out_dir=out_dir)

    assert path == out_dir / 'README.md'
    assert path.is_file()


async def test_write_creates_out_dir_if_missing(tmp_path: Path) -> None:
    out_dir = tmp_path / 'pub' / 'nested'
    writer = MarkdownPublicationReadmeWriter()

    path = await writer.write(_bundle(out_dir), out_dir=out_dir)

    assert path.is_file()


# ─────────────────────────── metadata ────────────────────────────


async def test_write_ru_has_russian_title_and_section(tmp_path: Path) -> None:
    out_dir = tmp_path / 'pub'
    writer = MarkdownPublicationReadmeWriter()
    path = await writer.write(
        _bundle(out_dir, lang=PublicationLang.RU), out_dir=out_dir,
    )
    content = path.read_text(encoding='utf-8')
    assert '# Публикация — se-amp' in content
    assert '## Метаданные' in content
    assert '- **Язык:** ru' in content


async def test_write_en_has_english_title_and_section(tmp_path: Path) -> None:
    out_dir = tmp_path / 'pub'
    writer = MarkdownPublicationReadmeWriter()
    path = await writer.write(
        _bundle(out_dir, lang=PublicationLang.EN), out_dir=out_dir,
    )
    content = path.read_text(encoding='utf-8')
    assert '# Publication — se-amp' in content
    assert '## Metadata' in content
    assert '- **Language:** en' in content


async def test_write_metadata_has_iso_timestamp_and_version(tmp_path: Path) -> None:
    out_dir = tmp_path / 'pub'
    writer = MarkdownPublicationReadmeWriter()
    path = await writer.write(_bundle(out_dir), out_dir=out_dir)
    content = path.read_text(encoding='utf-8')
    assert '2026-06-05T18:45:30+00:00' in content
    assert '0.3.0-dev' in content


# ─────────────────────────── schematic ────────────────────────────


async def test_write_schematic_section_has_color_and_bw_subsections(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / 'pub'
    writer = MarkdownPublicationReadmeWriter()
    path = await writer.write(
        _bundle(out_dir, lang=PublicationLang.RU), out_dir=out_dir,
    )
    content = path.read_text(encoding='utf-8')
    assert '## Схема (publication-grade)' in content
    assert '### Цветная версия' in content
    assert '### Чёрно-белая версия' in content
    assert '#### По листам (per-sheet)' in content


async def test_write_schematic_table_lists_per_sheet_files(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / 'pub'
    writer = MarkdownPublicationReadmeWriter()
    path = await writer.write(_bundle(out_dir), out_dir=out_dir)
    content = path.read_text(encoding='utf-8')
    # Relative paths from out_dir.
    assert 'schematic/color/per-sheet/demo.svg' in content
    assert 'schematic/color/per-sheet/demo.pdf' in content
    assert 'schematic/color/per-sheet/demo.png' in content
    assert 'schematic/bw/per-sheet/demo.svg' in content


async def test_write_schematic_no_combined_block_when_combined_paths_none(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / 'pub'
    writer = MarkdownPublicationReadmeWriter()
    path = await writer.write(_bundle(out_dir), out_dir=out_dir)
    content = path.read_text(encoding='utf-8')
    assert 'Объединённый PDF' not in content
    assert 'Combined PDF' not in content


async def test_write_schematic_combined_block_present_when_paths_set(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / 'pub'
    writer = MarkdownPublicationReadmeWriter()
    bundle = _bundle(out_dir, schematic=_schematic_with_combined(out_dir))
    path = await writer.write(bundle, out_dir=out_dir)
    content = path.read_text(encoding='utf-8')
    assert '#### Объединённый PDF' in content
    assert 'schematic/color/combined/demo.pdf' in content
    assert 'schematic/bw/combined/demo.pdf' in content


async def test_write_no_schematic_section_when_schematic_none(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / 'pub'
    writer = MarkdownPublicationReadmeWriter()
    bundle = _bundle(out_dir, schematic=None, sim_report=_sim_report(out_dir))
    path = await writer.write(bundle, out_dir=out_dir)
    content = path.read_text(encoding='utf-8')
    assert '## Схема' not in content
    assert '## Schematic' not in content


# ─────────────────────────── sim-report ────────────────────────────


async def test_write_sim_report_section_lists_report_md_and_plots(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / 'pub'
    writer = MarkdownPublicationReadmeWriter()
    bundle = _bundle(
        out_dir, sim_report=_sim_report(out_dir, n_plots=3),
    )
    path = await writer.write(bundle, out_dir=out_dir)
    content = path.read_text(encoding='utf-8')
    assert '## Отчёт о симуляции' in content
    assert 'sim-report/report.md' in content
    assert 'sim-report/plots/plot1.png' in content
    assert 'sim-report/plots/plot3.png' in content
    assert '3 ' in content  # plot count


async def test_write_sim_report_plot_count_singular_when_one(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / 'pub'
    writer = MarkdownPublicationReadmeWriter()
    bundle = _bundle(
        out_dir, sim_report=_sim_report(out_dir, n_plots=1),
        lang=PublicationLang.EN,
    )
    path = await writer.write(bundle, out_dir=out_dir)
    content = path.read_text(encoding='utf-8')
    assert '1 plot ' in content


async def test_write_sim_report_tables_block_says_none_when_empty(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / 'pub'
    writer = MarkdownPublicationReadmeWriter()
    bundle = _bundle(
        out_dir, sim_report=_sim_report(out_dir, tables=()),
    )
    path = await writer.write(bundle, out_dir=out_dir)
    content = path.read_text(encoding='utf-8')
    assert 'отсутствуют' in content or 'none' in content


async def test_write_sim_report_lists_tables_when_present(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / 'pub'
    writer = MarkdownPublicationReadmeWriter()
    bundle = _bundle(
        out_dir,
        sim_report=_sim_report(
            out_dir, tables=(out_dir / 'sim-report' / 'tables' / 'summary.md',),
        ),
    )
    path = await writer.write(bundle, out_dir=out_dir)
    content = path.read_text(encoding='utf-8')
    assert 'sim-report/tables/summary.md' in content


async def test_write_sim_report_source_ts_present_when_set(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / 'pub'
    writer = MarkdownPublicationReadmeWriter()
    bundle = _bundle(
        out_dir,
        sim_report=_sim_report(
            out_dir, source_ts=datetime(2026, 6, 5, 17, 0, 0, tzinfo=UTC),
        ),
    )
    path = await writer.write(bundle, out_dir=out_dir)
    content = path.read_text(encoding='utf-8')
    assert '2026-06-05T17:00:00+00:00' in content


async def test_write_sim_report_source_ts_says_fresh_run_when_none(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / 'pub'
    writer = MarkdownPublicationReadmeWriter()
    bundle = _bundle(
        out_dir, sim_report=_sim_report(out_dir, source_ts=None),
    )
    path = await writer.write(bundle, out_dir=out_dir)
    content = path.read_text(encoding='utf-8')
    assert 'свежий прогон' in content


async def test_write_no_sim_report_section_when_sim_report_none(
    tmp_path: Path,
) -> None:
    out_dir = tmp_path / 'pub'
    writer = MarkdownPublicationReadmeWriter()
    path = await writer.write(_bundle(out_dir, sim_report=None), out_dir=out_dir)
    content = path.read_text(encoding='utf-8')
    assert 'Отчёт о симуляции' not in content
    assert 'Simulation report' not in content


# ─────────────────────────── trailing note ────────────────────────────


async def test_write_has_trailing_note_section(tmp_path: Path) -> None:
    out_dir = tmp_path / 'pub'
    writer = MarkdownPublicationReadmeWriter()
    path = await writer.write(_bundle(out_dir), out_dir=out_dir)
    content = path.read_text(encoding='utf-8')
    assert '## Примечание' in content
    assert 'efactory T035' in content


async def test_write_returns_path_pointing_at_readme(tmp_path: Path) -> None:
    out_dir = tmp_path / 'pub'
    writer = MarkdownPublicationReadmeWriter()
    path = await writer.write(_bundle(out_dir), out_dir=out_dir)
    assert path.name == 'README.md'
    assert path.parent == out_dir
