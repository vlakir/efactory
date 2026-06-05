"""E2E: efactory publication <export-schematic|export-sim-report> (T035 Phase 4)."""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from composition.main import build_cli_app

if TYPE_CHECKING:
    from pathlib import Path


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


def _setup_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('EFACTORY_PROJECTS_ROOT', str(tmp_path / 'projects'))
    monkeypatch.setenv('EFACTORY_SESSION_ROOT', str(tmp_path / 'sessions'))


def _create_project(name: str) -> None:
    runner = CliRunner()
    result = runner.invoke(build_cli_app(), ['project', 'create', '--name', name])
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
