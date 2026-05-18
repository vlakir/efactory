"""E2E: efactory bridge design-to-sim — kicad-cli export RC-фильтр (T004)."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from composition.main import build_cli_app

if TYPE_CHECKING:
    pass


_RC_FIXTURE = Path(__file__).resolve().parents[2] / 'fixtures' / 'rc_filter.kicad_sch'
_KICAD_AVAILABLE = any(
    (Path.home() / 'kicad').glob('kicad*.AppImage'),
) or shutil.which('kicad-cli') is not None

needs_kicad = pytest.mark.skipif(
    not _KICAD_AVAILABLE,
    reason='KiCad not installed (AppImage in ~/kicad/ или kicad-cli в PATH)',
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
def test_design_to_sim_rc_filter_produces_spice_netlist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T004 acceptance: RC-фильтр → SPICE netlist через kicad-cli."""
    projects_root = _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()

    create_result = runner.invoke(
        build_cli_app(), ['project', 'create', '--name', 'rc_test'],
    )
    assert create_result.exit_code == 0, create_result.output

    project_path = projects_root / 'rc_test'
    schematic_dir = project_path / 'schematic'
    schematic_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(_RC_FIXTURE, schematic_dir / 'rc_filter.kicad_sch')

    bridge_result = runner.invoke(
        build_cli_app(),
        [
            'bridge',
            'design-to-sim',
            'rc_test',
            '--schematic',
            'schematic/rc_filter.kicad_sch',
        ],
    )
    assert bridge_result.exit_code == 0, bridge_result.output

    netlist_path = project_path / 'sim' / 'rc_filter.cir'
    assert netlist_path.is_file()
    content = netlist_path.read_text(encoding='utf-8')
    # Acceptance: содержит R1, C1, V1 (имена из fixture).
    assert 'R1' in content
    assert 'C1' in content
    assert 'V1' in content
    # T004 split-scope: simulation pending (T008 message).
    assert 'not yet implemented' in bridge_result.output
    assert 'T008' in bridge_result.output


@needs_kicad
def test_design_to_sim_unknown_project_exits_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()

    result = runner.invoke(
        build_cli_app(),
        [
            'bridge',
            'design-to-sim',
            'ghost',
            '--schematic',
            'schematic/x.kicad_sch',
        ],
    )

    assert result.exit_code == 1
    assert 'ghost' in result.output


@needs_kicad
def test_design_to_sim_invalid_schematic_returns_export_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projects_root = _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()
    runner.invoke(build_cli_app(), ['project', 'create', '--name', 'bad'])

    schematic = projects_root / 'bad' / 'schematic' / 'broken.kicad_sch'
    schematic.parent.mkdir(parents=True, exist_ok=True)
    schematic.write_text('not a valid kicad schematic at all')

    result = runner.invoke(
        build_cli_app(),
        [
            'bridge',
            'design-to-sim',
            'bad',
            '--schematic',
            'schematic/broken.kicad_sch',
        ],
    )

    assert result.exit_code == 2
    assert 'kicad-cli exit' in result.output
