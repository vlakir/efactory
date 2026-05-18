"""E2E: bridge edit-value + design-to-sim (T004b) на RC-фильтре.

Acceptance: после изменения R1 с 1k на 10k через CLI `bridge edit`,
повторный `bridge design-to-sim op` показывает other V(/out) или
operating-point значения (sanity: R1 изменился, лампа netlist'а
содержит новый value).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from composition.main import build_cli_app

_KICAD_AVAILABLE = any(
    (Path.home() / 'kicad').glob('kicad*.AppImage'),
) or shutil.which('kicad-cli') is not None

needs_kicad = pytest.mark.skipif(
    not _KICAD_AVAILABLE,
    reason='KiCad not installed',
)


def _setup_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    projects_root = tmp_path / 'projects'
    monkeypatch.setenv('EFACTORY_PROJECTS_ROOT', str(projects_root))
    monkeypatch.setenv(
        'EFACTORY_DATABASE_URL',
        f'sqlite+aiosqlite:///{tmp_path / "efactory.sqlite"}',
    )
    monkeypatch.setenv('EFACTORY_SESSION_ROOT', str(tmp_path / 'sessions'))
    return projects_root


@needs_kicad
def test_bridge_edit_changes_value_in_schematic(
    rc_filter_schematic_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """bridge edit меняет value R1 в существующем .kicad_sch."""
    projects_root = _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()
    create_result = runner.invoke(
        build_cli_app(), ['project', 'create', '--name', 'editor_test'],
    )
    assert create_result.exit_code == 0, create_result.output

    project_path = projects_root / 'editor_test'
    schematic_dir = project_path / 'schematic'
    schematic_dir.mkdir(parents=True, exist_ok=True)
    target = schematic_dir / 'rc_filter.kicad_sch'
    shutil.copy(rc_filter_schematic_path, target)

    # Verify pre-edit value
    pre_text = target.read_text(encoding='utf-8')
    assert '(property "Value" "1k"' in pre_text

    result = runner.invoke(
        build_cli_app(),
        [
            'bridge', 'edit',
            'editor_test',
            '--schematic', 'schematic/rc_filter.kicad_sch',
            '--set', 'R1=10k',
        ],
    )
    assert result.exit_code == 0, result.output
    assert "R1: '1k' → '10k'" in result.output

    # File теперь содержит value="10k" для R1 (был "1k").
    post_text = target.read_text(encoding='utf-8')
    assert post_text.count('(property "Value" "10k"') == 1
    assert '(property "Value" "1k"' not in post_text


@needs_kicad
def test_bridge_edit_unknown_reference_exits_1(
    rc_filter_schematic_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """bridge edit падает с exit 1 если ref не найден."""
    projects_root = _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()
    runner.invoke(
        build_cli_app(), ['project', 'create', '--name', 'editor_test'],
    )
    project_path = projects_root / 'editor_test'
    schematic_dir = project_path / 'schematic'
    schematic_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(rc_filter_schematic_path, schematic_dir / 'rc_filter.kicad_sch')

    result = runner.invoke(
        build_cli_app(),
        [
            'bridge', 'edit',
            'editor_test',
            '--schematic', 'schematic/rc_filter.kicad_sch',
            '--set', 'R999=10k',
        ],
    )
    assert result.exit_code == 1
    assert 'R999' in result.output


@needs_kicad
def test_bridge_edit_invalid_set_format_exits_2(
    rc_filter_schematic_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projects_root = _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()
    runner.invoke(
        build_cli_app(), ['project', 'create', '--name', 'editor_test'],
    )
    project_path = projects_root / 'editor_test'
    schematic_dir = project_path / 'schematic'
    schematic_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(rc_filter_schematic_path, schematic_dir / 'rc_filter.kicad_sch')

    result = runner.invoke(
        build_cli_app(),
        [
            'bridge', 'edit',
            'editor_test',
            '--schematic', 'schematic/rc_filter.kicad_sch',
            '--set', 'no_equals_sign',
        ],
    )
    assert result.exit_code == 2
    assert 'REF=VALUE' in result.output
