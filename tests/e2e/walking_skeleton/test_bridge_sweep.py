"""E2E: bridge sweep + edit-model (T004b/T005 Phase 1)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from composition.main import build_cli_app

_KICAD_AVAILABLE = any(
    (Path.home() / 'kicad').glob('kicad*.AppImage'),
) or shutil.which('kicad-cli') is not None
_NGSPICE_AVAILABLE = shutil.which('ngspice') is not None

needs_kicad = pytest.mark.skipif(
    not _KICAD_AVAILABLE, reason='KiCad not installed',
)
needs_ngspice = pytest.mark.skipif(
    not _NGSPICE_AVAILABLE, reason='ngspice not installed',
)


def _setup_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    projects_root = tmp_path / 'projects'
    monkeypatch.setenv('EFACTORY_PROJECTS_ROOT', str(projects_root))
    monkeypatch.setenv(
        'EFACTORY_DATABASE_URL',
        f'sqlite+aiosqlite:///{tmp_path / "efactory.sqlite"}',
    )
    monkeypatch.setenv('EFACTORY_SESSION_ROOT', str(tmp_path / 'sessions'))
    return projects_root


def _seed_rc_project(
    rc_filter_schematic_path: Path,
    projects_root: Path,
    runner: CliRunner,
    project_name: str = 'sweep_test',
) -> Path:
    create_result = runner.invoke(
        build_cli_app(), ['project', 'create', '--name', project_name],
    )
    assert create_result.exit_code == 0, create_result.output
    project_path = projects_root / project_name
    schematic_dir = project_path / 'schematic'
    schematic_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(rc_filter_schematic_path, schematic_dir / 'rc_filter.kicad_sch')
    return project_path


@needs_kicad
@needs_ngspice
def test_bridge_sweep_two_param_combinations(
    rc_filter_schematic_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """bridge sweep --param R1=1k,10k --param C1=100n,1u → 4 combinations."""
    projects_root = _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()
    _seed_rc_project(rc_filter_schematic_path, projects_root, runner)

    result = runner.invoke(
        build_cli_app(),
        [
            'bridge', 'sweep',
            'sweep_test',
            '--schematic', 'schematic/rc_filter.kicad_sch',
            '--param', 'R1=1k,10k',
            '--param', 'C1=1u,10u',
        ],
    )

    assert result.exit_code == 0, result.output
    assert 'Sweep complete: 4 combinations' in result.output
    # Каждая combination печатается как [R1=X C1=Y] op_voltages
    assert '[R1=1k C1=1u]' in result.output
    assert '[R1=1k C1=10u]' in result.output
    assert '[R1=10k C1=1u]' in result.output
    assert '[R1=10k C1=10u]' in result.output


@needs_kicad
def test_bridge_sweep_invalid_param_format_exits_2(
    rc_filter_schematic_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projects_root = _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()
    _seed_rc_project(rc_filter_schematic_path, projects_root, runner)

    result = runner.invoke(
        build_cli_app(),
        [
            'bridge', 'sweep',
            'sweep_test',
            '--schematic', 'schematic/rc_filter.kicad_sch',
            '--param', 'no_equals',
        ],
    )
    assert result.exit_code == 2
    assert 'REF=v1' in result.output


@needs_kicad
def test_bridge_edit_atomic_rollback_on_failure(
    rc_filter_schematic_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T004b P1: multi-edit с failure посередине → весь batch откатывается."""
    projects_root = _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()
    _seed_rc_project(rc_filter_schematic_path, projects_root, runner)
    target = projects_root / 'sweep_test' / 'schematic' / 'rc_filter.kicad_sch'

    pre_text = target.read_text(encoding='utf-8')

    # R1 success, R999 missing → весь batch откатывается
    result = runner.invoke(
        build_cli_app(),
        [
            'bridge', 'edit',
            'sweep_test',
            '--schematic', 'schematic/rc_filter.kicad_sch',
            '--set', 'R1=42k',          # valid
            '--set', 'R999=100',        # missing → fail
        ],
    )
    assert result.exit_code == 1
    assert 'Rollback' in result.output

    # Файл должен совпадать с pre_text — R1 НЕ изменён, потому что rollback
    post_text = target.read_text(encoding='utf-8')
    assert post_text == pre_text
