"""E2E: T026 Phase 3 — entry-point warnings о pending staged.

Project show / list / bridge design-to-sim печатают warning о
pending `.kicad_sch.staged`, не блокируя операцию.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from adapters.outbound.schematic_kicad.staged_metadata import (
    StagedMetadata,
    write_staged_metadata,
)
from adapters.outbound.schematic_kicad.staged_paths import meta_path, staged_path
from composition.main import build_cli_app

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _set_env(monkeypatch: 'pytest.MonkeyPatch', tmp_path: 'Path') -> None:
    monkeypatch.setenv('EFACTORY_PROJECTS_ROOT', str(tmp_path / 'projects'))


def _drop_staged(project_dir: 'Path', name: str = 'foo.kicad_sch') -> 'Path':
    active = project_dir / name
    active.write_bytes(b'ACTIVE')
    sp = staged_path(active)
    sp.write_text('STAGED', encoding='utf-8')
    parent_hash = hashlib.sha256(b'ACTIVE').hexdigest()
    write_staged_metadata(
        meta_path(sp),
        StagedMetadata(
            parent_hash=parent_hash,
            staged_at='2026-06-03T01:00:00Z',
            staged_by='efactory-test',
            trigger='/sim-run',
        ),
    )
    return active


def test_project_show_emits_warning_when_pending(
    tmp_path: 'Path',
    monkeypatch: 'pytest.MonkeyPatch',
) -> None:
    _set_env(monkeypatch, tmp_path)
    runner = CliRunner()
    app = build_cli_app()

    created = runner.invoke(app, ['project', 'create', '--name', 'demo'])
    assert created.exit_code == 0, created.output
    _drop_staged(tmp_path / 'projects' / 'demo')

    result = runner.invoke(app, ['project', 'show', '--name', 'demo'])
    assert result.exit_code == 0
    assert 'schematic-staged-pending: 1 file' in result.stderr


def test_project_show_no_warning_when_clean(
    tmp_path: 'Path',
    monkeypatch: 'pytest.MonkeyPatch',
) -> None:
    _set_env(monkeypatch, tmp_path)
    runner = CliRunner()
    app = build_cli_app()

    runner.invoke(app, ['project', 'create', '--name', 'clean'])
    result = runner.invoke(app, ['project', 'show', '--name', 'clean'])
    assert result.exit_code == 0
    assert 'schematic-staged-pending' not in result.stderr


def test_project_list_marks_projects_with_pending(
    tmp_path: 'Path',
    monkeypatch: 'pytest.MonkeyPatch',
) -> None:
    _set_env(monkeypatch, tmp_path)
    runner = CliRunner()
    app = build_cli_app()

    runner.invoke(app, ['project', 'create', '--name', 'dirty'])
    runner.invoke(app, ['project', 'create', '--name', 'pristine'])
    _drop_staged(tmp_path / 'projects' / 'dirty')

    result = runner.invoke(app, ['project', 'list'])
    assert result.exit_code == 0
    # Dirty помечен, pristine — нет.
    dirty_line = next(
        line for line in result.output.splitlines() if line.startswith('dirty')
    )
    pristine_line = next(
        line for line in result.output.splitlines() if line.startswith('pristine')
    )
    assert '[1 pending staged]' in dirty_line
    assert 'pending staged' not in pristine_line


def test_warnings_do_not_block_show(
    tmp_path: 'Path',
    monkeypatch: 'pytest.MonkeyPatch',
) -> None:
    """Pending staged не должны менять exit code show (0)."""
    _set_env(monkeypatch, tmp_path)
    runner = CliRunner()
    app = build_cli_app()

    runner.invoke(app, ['project', 'create', '--name', 'demo'])
    _drop_staged(tmp_path / 'projects' / 'demo')
    result = runner.invoke(app, ['project', 'show', '--name', 'demo'])
    assert result.exit_code == 0


def test_multiple_staged_summary_includes_count(
    tmp_path: 'Path',
    monkeypatch: 'pytest.MonkeyPatch',
) -> None:
    _set_env(monkeypatch, tmp_path)
    runner = CliRunner()
    app = build_cli_app()

    runner.invoke(app, ['project', 'create', '--name', 'multi'])
    project_dir = tmp_path / 'projects' / 'multi'
    _drop_staged(project_dir, 'one.kicad_sch')
    _drop_staged(project_dir, 'two.kicad_sch')

    result = runner.invoke(app, ['project', 'show', '--name', 'multi'])
    assert result.exit_code == 0
    assert 'schematic-staged-pending: 2 file' in result.stderr
