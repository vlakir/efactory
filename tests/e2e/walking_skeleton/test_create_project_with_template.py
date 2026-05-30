"""E2E: CLI `efactory project create --template se-amp` (T014 Phase A)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from composition.main import build_cli_app

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _setup_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> Path:
    projects_root = tmp_path / 'projects'
    monkeypatch.setenv('EFACTORY_PROJECTS_ROOT', str(projects_root))
    return projects_root


def test_without_template_creates_empty_project_as_before(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Backward-compat: invocation без --template — поведение прежнее."""
    projects_root = _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()

    result = runner.invoke(
        build_cli_app(), ['project', 'create', '--name', 'demo-empty']
    )

    assert result.exit_code == 0, result.output
    project_dir = projects_root / 'demo-empty'
    assert project_dir.is_dir()
    assert (project_dir / 'project.yaml').is_file()
    # Без --template — кроме project.yaml + .git ничего не появилось
    assert not (project_dir / 'demo-empty.kicad_sch').exists()
    assert not (project_dir / 'models').exists()


def test_with_se_amp_template_materializes_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projects_root = _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()

    result = runner.invoke(
        build_cli_app(),
        [
            'project', 'create',
            '--name', 'my-amp-v2',
            '--template', 'se-amp',
        ],
    )

    assert result.exit_code == 0, result.output
    assert 'template: se-amp' in result.output

    project_dir = projects_root / 'my-amp-v2'
    assert (project_dir / 'project.yaml').is_file()
    assert (project_dir / 'my-amp-v2.kicad_sch').is_file()
    assert (project_dir / 'my-amp-v2.kicad_pro').is_file()
    assert (project_dir / 'models' / '6P14P.lib').is_file()
    assert (project_dir / 'models' / 'OPT_SE_5K_8.lib').is_file()
    # Метаданные шаблона не копируются в проект
    assert not (project_dir / 'template.yaml').exists()
    assert not (project_dir / 'README.md').exists()
    # `.kicad_pro` содержит подставленное имя
    pro_text = (project_dir / 'my-amp-v2.kicad_pro').read_text()
    assert 'my-amp-v2.kicad_pro' in pro_text


def test_unknown_template_exits_with_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()

    result = runner.invoke(
        build_cli_app(),
        ['project', 'create', '--name', 'foo', '--template', 'nope'],
    )

    assert result.exit_code == 2
    assert "Template 'nope' not found" in result.output


def test_target_dir_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--target-dir перекрывает settings.projects_root для этой инвокации."""
    _setup_env(tmp_path, monkeypatch)
    override_root = tmp_path / 'override'
    override_root.mkdir()
    runner = CliRunner()

    result = runner.invoke(
        build_cli_app(),
        [
            'project', 'create',
            '--name', 'foo',
            '--template', 'se-amp',
            '--target-dir', str(override_root),
        ],
    )

    assert result.exit_code == 0, result.output
    assert (override_root / 'foo').is_dir()
    assert (override_root / 'foo' / 'foo.kicad_sch').is_file()
