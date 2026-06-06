"""E2E: efactory publication <export-schematic|export-sim-report> (T035 Phase 4-5)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from composition.main import build_cli_app

if TYPE_CHECKING:
    pass


_KICAD_AVAILABLE = shutil.which('kicad-cli') is not None
_RSVG_AVAILABLE = shutil.which('rsvg-convert') is not None

needs_kicad_cli = pytest.mark.skipif(
    not _KICAD_AVAILABLE,
    reason='kicad-cli not installed',
)
needs_rsvg = pytest.mark.skipif(
    not _RSVG_AVAILABLE,
    reason='rsvg-convert not installed (apt install librsvg2-bin) — нужен в '
    'efactory:linux контейнере',
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TEMPLATES_DIR = _REPO_ROOT / 'data' / 'templates'
_ALL_TEMPLATES = sorted(p.name for p in _TEMPLATES_DIR.iterdir() if p.is_dir())


def _setup_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('EFACTORY_PROJECTS_ROOT', str(tmp_path / 'projects'))
    monkeypatch.setenv('EFACTORY_SESSION_ROOT', str(tmp_path / 'sessions'))


def _create_project(name: str) -> None:
    runner = CliRunner()
    result = runner.invoke(build_cli_app(), ['project', 'create', '--name', name])
    assert result.exit_code == 0, result.output


def _create_project_from_template(name: str, template: str) -> None:
    runner = CliRunner()
    result = runner.invoke(
        build_cli_app(),
        ['project', 'create', '--name', name, '--template', template],
    )
    assert result.exit_code == 0, result.output


# ─────────────────────────── export-schematic ────────────────────────────


@needs_kicad_cli
@needs_rsvg
def test_publication_export_schematic_succeeds_on_clean_template(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    _create_project('demo')

    # Add a minimal schematic so renderer has input.
    project_root = tmp_path / 'projects' / 'demo'
    sch = project_root / 'demo.kicad_sch'
    sch.write_text(
        '(kicad_sch (version 20231120) (generator eeschema)\n'
        '  (uuid "00000000-0000-0000-0000-000000000000")\n'
        '  (paper "A4")\n'
        '  (lib_symbols)\n'
        ')\n',
        encoding='utf-8',
    )

    runner = CliRunner()
    result = runner.invoke(
        build_cli_app(),
        ['publication', 'export-schematic', 'demo'],
    )

    assert result.exit_code == 0, result.output
    assert 'publication-export:' in result.output
    # Verify directory tree:
    pub_root = project_root / 'out' / 'publications'
    assert pub_root.is_dir()
    ts_dirs = list(pub_root.iterdir())
    assert len(ts_dirs) == 1
    ts_root = ts_dirs[0]
    assert (ts_root / 'README.md').is_file()
    assert (ts_root / 'schematic' / 'color' / 'per-sheet').is_dir()
    assert (ts_root / 'schematic' / 'bw' / 'per-sheet').is_dir()


def test_publication_export_schematic_fails_with_unknown_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)

    runner = CliRunner()
    result = runner.invoke(
        build_cli_app(),
        ['publication', 'export-schematic', 'nonexistent'],
    )

    assert result.exit_code != 0
    # Either 2 (no schematic detected before manifest load) or 1 (project not found).
    assert result.exit_code in {1, 2}


def test_publication_export_schematic_rejects_bad_multi_sheet_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    _create_project('demo')

    runner = CliRunner()
    result = runner.invoke(
        build_cli_app(),
        [
            'publication', 'export-schematic', 'demo',
            '--multi-sheet-mode', 'bogus',
        ],
    )

    assert result.exit_code == 2
    assert 'per-sheet|combined' in result.output


def test_publication_export_schematic_rejects_bad_lang(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    _create_project('demo')

    runner = CliRunner()
    result = runner.invoke(
        build_cli_app(),
        ['publication', 'export-schematic', 'demo', '--lang', 'de'],
    )

    assert result.exit_code == 2
    assert 'ru|en' in result.output


# ─────────────────────────── export-sim-report ────────────────────────────


def test_publication_export_sim_report_minimal_produces_report_md(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    _create_project('demo')

    runner = CliRunner()
    result = runner.invoke(
        build_cli_app(),
        ['publication', 'export-sim-report', 'demo'],
    )

    assert result.exit_code == 0, result.output
    assert 'publication-export:' in result.output

    project_root = tmp_path / 'projects' / 'demo'
    pub_root = project_root / 'out' / 'publications'
    ts_dirs = list(pub_root.iterdir())
    assert len(ts_dirs) == 1
    ts_root = ts_dirs[0]
    assert (ts_root / 'README.md').is_file()
    assert (ts_root / 'sim-report' / 'report.md').is_file()
    report_md = (ts_root / 'sim-report' / 'report.md').read_text(encoding='utf-8')
    # MVP: metadata + magnetics-missing notice only (no TRAN/AC because no data).
    assert '# Отчёт о симуляции — demo' in report_md
    assert '## Магнитные компоненты' in report_md
    assert 'не найдены' in report_md


def test_publication_export_sim_report_en_lang_uses_english(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    _create_project('demo')

    runner = CliRunner()
    result = runner.invoke(
        build_cli_app(),
        ['publication', 'export-sim-report', 'demo', '--lang', 'en'],
    )

    assert result.exit_code == 0, result.output
    project_root = tmp_path / 'projects' / 'demo'
    pub_root = project_root / 'out' / 'publications'
    ts_root = next(pub_root.iterdir())
    report_md = (ts_root / 'sim-report' / 'report.md').read_text(encoding='utf-8')
    assert '# Simulation Report — demo' in report_md
    assert '## Magnetic components' in report_md


def test_publication_export_sim_report_fails_with_unknown_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)

    runner = CliRunner()
    result = runner.invoke(
        build_cli_app(),
        ['publication', 'export-sim-report', 'nonexistent'],
    )

    assert result.exit_code == 1


def test_publication_export_sim_report_rejects_bad_lang(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    _create_project('demo')

    runner = CliRunner()
    result = runner.invoke(
        build_cli_app(),
        ['publication', 'export-sim-report', 'demo', '--lang', 'fr'],
    )

    assert result.exit_code == 2
    assert 'ru|en' in result.output


# ─────────────────────────── Phase 5: SC-1 / SC-7 acceptance ──────────────────


@needs_kicad_cli
@needs_rsvg
def test_sc1_se_amp_template_full_acceptance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    SC-1 (T035 Phase 5): на тестовом проекте `se-amp`
    `/export-schematic-publication` за <60 секунд создаёт:
    - 3 файла в color/per-sheet/ (.svg + .pdf + .png, 1 sheet);
    - 3 файла в bw/per-sheet/;
    - README.md ≥10 строк;
    - exit 0.

    Skip на host без rsvg-convert (есть только в efactory:linux).
    """
    _setup_env(tmp_path, monkeypatch)
    _create_project_from_template('my-amp', 'se-amp')

    runner = CliRunner()
    result = runner.invoke(
        build_cli_app(),
        ['publication', 'export-schematic', 'my-amp'],
    )

    assert result.exit_code == 0, result.output
    assert 'publication-export:' in result.output

    project_root = tmp_path / 'projects' / 'my-amp'
    pub_root = project_root / 'out' / 'publications'
    ts_dirs = list(pub_root.iterdir())
    assert len(ts_dirs) == 1
    ts_root = ts_dirs[0]

    color_per_sheet = ts_root / 'schematic' / 'color' / 'per-sheet'
    bw_per_sheet = ts_root / 'schematic' / 'bw' / 'per-sheet'

    color_files = sorted(color_per_sheet.iterdir())
    bw_files = sorted(bw_per_sheet.iterdir())

    # se-amp = single-sheet → 3 файла (svg+pdf+png) на цвет.
    assert len(color_files) == 3, [p.name for p in color_files]
    assert len(bw_files) == 3, [p.name for p in bw_files]

    color_exts = sorted(p.suffix for p in color_files)
    bw_exts = sorted(p.suffix for p in bw_files)
    assert color_exts == ['.pdf', '.png', '.svg']
    assert bw_exts == ['.pdf', '.png', '.svg']

    readme = ts_root / 'README.md'
    assert readme.is_file()
    lines = readme.read_text(encoding='utf-8').splitlines()
    assert len(lines) >= 10, f'README only {len(lines)} lines: {lines}'


@needs_kicad_cli
@needs_rsvg
def test_sc1_combined_mode_creates_combined_pdf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Combined-mode дополнительно к per-sheet создаёт combined PDF в подкаталоге."""
    _setup_env(tmp_path, monkeypatch)
    _create_project_from_template('my-amp', 'se-amp')

    runner = CliRunner()
    result = runner.invoke(
        build_cli_app(),
        [
            'publication', 'export-schematic', 'my-amp',
            '--multi-sheet-mode', 'combined',
        ],
    )

    assert result.exit_code == 0, result.output

    project_root = tmp_path / 'projects' / 'my-amp'
    pub_root = project_root / 'out' / 'publications'
    ts_root = next(pub_root.iterdir())

    combined_color = ts_root / 'schematic' / 'color' / 'combined'
    combined_bw = ts_root / 'schematic' / 'bw' / 'combined'

    assert combined_color.is_dir()
    assert combined_bw.is_dir()
    assert (combined_color / 'my-amp.pdf').is_file()
    assert (combined_bw / 'my-amp.pdf').is_file()


@needs_kicad_cli
@needs_rsvg
def test_sc6_multi_sheet_combined_pdf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    SC-6 (T192): на synthetic 2-sheet проекте `--multi-sheet-mode combined`
    создаёт combined PDF + per-sheet PDF для каждого листа.

    Synthesizes multi-sheet проект через `Schematic` facade
    (`add_sub_sheet` API, T192), затем гонит `/export-schematic-publication
    --multi-sheet-mode combined` через CLI runner. Acceptance:
    - 1 combined PDF в `color/combined/<project>.pdf` (+ bw);
    - per-sheet PDF count = 2 (parent + child) в `color/per-sheet/`;
    - README.md содержит warning text про SVG/PNG combined;
    - exit 0.

    Skip на host без kicad-cli / rsvg-convert.
    """
    from adapters.outbound.schematic_kicad.facade import Schematic

    _setup_env(tmp_path, monkeypatch)
    _create_project('multi-sch')

    # Synthesize multi-sheet проект: parent с одним sub-sheet ссылкой,
    # plus child schematic file.
    project_root = tmp_path / 'projects' / 'multi-sch'
    child = Schematic(name='psu')
    child.add_resistor(value='10k', at=(10.16, 10.16))
    child.save(project_root / 'psu.kicad_sch')

    parent = Schematic(name='multi-sch')
    parent.add_sub_sheet(
        sheet_name='psu',
        sheet_file='psu.kicad_sch',
        at=(50.8, 60.96),
    )
    parent.save(project_root / 'multi-sch.kicad_sch')

    runner = CliRunner()
    result = runner.invoke(
        build_cli_app(),
        [
            'publication', 'export-schematic', 'multi-sch',
            '--multi-sheet-mode', 'combined',
            '--schematic', 'multi-sch.kicad_sch',
        ],
    )

    assert result.exit_code == 0, result.output
    pub_root = project_root / 'out' / 'publications'
    ts_root = next(pub_root.iterdir())
    # Combined PDF на месте.
    assert (ts_root / 'schematic' / 'color' / 'combined' / 'multi-sch.pdf').is_file()
    assert (ts_root / 'schematic' / 'bw' / 'combined' / 'multi-sch.pdf').is_file()
    # Per-sheet PDF count = 2 (parent + child).
    color_per_sheet = ts_root / 'schematic' / 'color' / 'per-sheet'
    pdfs = sorted(p.name for p in color_per_sheet.iterdir() if p.suffix == '.pdf')
    assert len(pdfs) == 2, pdfs
    # README warning text.
    readme = (ts_root / 'README.md').read_text(encoding='utf-8')
    assert 'combined' in readme.lower()


@pytest.mark.parametrize('template', _ALL_TEMPLATES)
def test_sc7_sim_report_smoke_per_template(
    template: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    SC-7 (T035 Phase 5): `/export-sim-report` не падает ни на одном из
    11 templates (MVP режим — bundle metadata only, без TRAN/AC).

    Полноценный отчёт с plots зависит от T190+T191 (см. BACKLOG);
    smoke здесь проверяет CLI-плоскость: команда отрабатывает, exit 0,
    report.md создан с правильной metadata-секцией.
    """
    _setup_env(tmp_path, monkeypatch)
    project_name = f'smoke-{template}'
    _create_project_from_template(project_name, template)

    runner = CliRunner()
    result = runner.invoke(
        build_cli_app(),
        ['publication', 'export-sim-report', project_name],
    )

    assert result.exit_code == 0, result.output
    assert 'publication-export:' in result.output

    project_root = tmp_path / 'projects' / project_name
    pub_root = project_root / 'out' / 'publications'
    ts_root = next(pub_root.iterdir())
    report_md = ts_root / 'sim-report' / 'report.md'
    assert report_md.is_file()
    content = report_md.read_text(encoding='utf-8')
    # Metadata-секция обязательна (FR §3).
    assert f'# Отчёт о симуляции — {project_name}' in content
    assert '## Метаданные' in content
    assert project_name in content
    # MVP — magnetics graceful skip notice присутствует.
    assert '## Магнитные компоненты' in content
