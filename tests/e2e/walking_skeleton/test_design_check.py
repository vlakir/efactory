"""E2E: efactory design check — standalone ERC quality gate (T029)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from composition.main import build_cli_app

_KICAD_AVAILABLE = shutil.which('kicad-cli') is not None

needs_kicad_cli = pytest.mark.skipif(
    not _KICAD_AVAILABLE,
    reason='kicad-cli not installed',
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TEMPLATES = _REPO_ROOT / 'data' / 'templates'


def _setup_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('EFACTORY_PROJECTS_ROOT', str(tmp_path / 'projects'))
    monkeypatch.setenv('EFACTORY_SESSION_ROOT', str(tmp_path / 'sessions'))


def _stage(name: str, tmp_path: Path) -> Path:
    src = _TEMPLATES / name
    dst = tmp_path / name
    shutil.copytree(src, dst)
    return dst / '{{PROJECT_NAME}}.kicad_sch'


@needs_kicad_cli
def test_design_check_passes_on_clean_template(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    sch = _stage('se-amp', tmp_path)

    runner = CliRunner()
    result = runner.invoke(build_cli_app(), ['design', 'check', str(sch)])

    assert result.exit_code == 0, result.output
    assert 'ERC: 0 errors' in result.output


@needs_kicad_cli
def test_design_check_rejects_unknown_severity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    sch = _stage('se-amp', tmp_path)

    runner = CliRunner()
    result = runner.invoke(
        build_cli_app(),
        ['design', 'check', str(sch), '--severity', 'info'],
    )

    assert result.exit_code == 2
    assert '--severity must be one of' in result.output


@needs_kicad_cli
def test_design_check_infrastructure_failure_on_garbage_sch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    bad = tmp_path / 'bad.kicad_sch'
    bad.write_text('not a real kicad schematic\n', encoding='utf-8')

    runner = CliRunner()
    result = runner.invoke(build_cli_app(), ['design', 'check', str(bad)])

    assert result.exit_code == 2
    assert 'ERC infrastructure failure' in result.output


@needs_kicad_cli
def test_design_check_auto_detect_in_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    project_dir = tmp_path / 'demo'
    project_dir.mkdir()
    shutil.copy(
        _TEMPLATES / 'se-amp' / '{{PROJECT_NAME}}.kicad_sch',
        project_dir / 'demo.kicad_sch',
    )
    monkeypatch.chdir(tmp_path)

    runner = CliRunner()
    result = runner.invoke(build_cli_app(), ['design', 'check'])

    assert result.exit_code == 0, result.output
    assert 'ERC: 0 errors' in result.output


def test_design_check_directory_with_no_kicad_sch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    empty = tmp_path / 'empty'
    empty.mkdir()

    runner = CliRunner()
    result = runner.invoke(build_cli_app(), ['design', 'check', str(empty)])

    assert result.exit_code == 2
    assert 'expected exactly one .kicad_sch' in result.output


def test_design_check_no_arg_no_sch_in_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    empty = tmp_path / 'empty'
    empty.mkdir()
    monkeypatch.chdir(empty)

    runner = CliRunner()
    result = runner.invoke(build_cli_app(), ['design', 'check'])

    assert result.exit_code == 2
    assert 'No .kicad_sch found' in result.output
