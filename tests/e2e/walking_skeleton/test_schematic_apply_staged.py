"""E2E: `efactory schematic apply-staged <project>` (T026).

Покрывает full happy path: create project → manually drop staged + meta
sidecar → apply-staged → active обновлён, staged + meta удалены, stdout
содержит `schematic-applied: <abs>` строку.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from adapters.outbound.schematic_kicad.staged_metadata import (
    StagedMetadata,
    write_staged_metadata,
)
from adapters.outbound.schematic_kicad.staged_paths import (
    lock_path,
    meta_path,
    staged_path,
)
from composition.main import build_cli_app

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _set_env(
    monkeypatch: 'pytest.MonkeyPatch',
    tmp_path: 'Path',
) -> None:
    monkeypatch.setenv('EFACTORY_PROJECTS_ROOT', str(tmp_path / 'projects'))


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _drop_staged(
    project_dir: 'Path',
    *,
    active_name: str = 'foo.kicad_sch',
    active_bytes: bytes = b'ACTIVE',
    staged_text: str = 'STAGED',
) -> tuple['Path', 'Path']:
    active = project_dir / active_name
    active.write_bytes(active_bytes)
    sp = staged_path(active)
    sp.write_text(staged_text, encoding='utf-8')
    meta = StagedMetadata(
        parent_hash=_sha256_hex(active_bytes),
        staged_at='2026-06-03T01:00:00Z',
        staged_by='efactory-test',
        trigger='/sim-run',
    )
    write_staged_metadata(meta_path(sp), meta)
    return active, sp


def test_schematic_apply_staged_happy_path(
    tmp_path: 'Path',
    monkeypatch: 'pytest.MonkeyPatch',
) -> None:
    _set_env(monkeypatch, tmp_path)
    runner = CliRunner()
    app = build_cli_app()

    created = runner.invoke(app, ['project', 'create', '--name', 'demo'])
    assert created.exit_code == 0, created.output
    project_dir = tmp_path / 'projects' / 'demo'
    active, sp = _drop_staged(project_dir)

    result = runner.invoke(app, ['schematic', 'apply-staged', 'demo'])
    assert result.exit_code == 0, result.output
    assert f'schematic-applied: {active}' in result.output
    assert active.read_text() == 'STAGED'
    assert not sp.exists()
    assert not meta_path(sp).exists()


def test_schematic_apply_staged_no_pending(
    tmp_path: 'Path',
    monkeypatch: 'pytest.MonkeyPatch',
) -> None:
    _set_env(monkeypatch, tmp_path)
    runner = CliRunner()
    app = build_cli_app()

    runner.invoke(app, ['project', 'create', '--name', 'empty'])
    result = runner.invoke(app, ['schematic', 'apply-staged', 'empty'])
    assert result.exit_code == 0
    assert 'no pending staged to apply' in result.output


def test_schematic_apply_staged_unknown_project_exit_1(
    tmp_path: 'Path',
    monkeypatch: 'pytest.MonkeyPatch',
) -> None:
    _set_env(monkeypatch, tmp_path)
    runner = CliRunner()
    app = build_cli_app()
    result = runner.invoke(app, ['schematic', 'apply-staged', 'ghost'])
    assert result.exit_code == 1
    assert 'ghost' in result.output


def test_schematic_apply_staged_lock_blocks_without_force(
    tmp_path: 'Path',
    monkeypatch: 'pytest.MonkeyPatch',
) -> None:
    _set_env(monkeypatch, tmp_path)
    runner = CliRunner()
    app = build_cli_app()

    runner.invoke(app, ['project', 'create', '--name', 'locked'])
    project_dir = tmp_path / 'projects' / 'locked'
    active, _sp = _drop_staged(project_dir)
    lock_path(active).write_text('{"hostname":"h","username":"u"}', encoding='utf-8')

    result = runner.invoke(app, ['schematic', 'apply-staged', 'locked'])
    assert result.exit_code == 1
    assert 'reason=lock' in result.output
    assert active.read_text() == 'ACTIVE'  # untouched


def test_schematic_apply_staged_force_bypasses_lock(
    tmp_path: 'Path',
    monkeypatch: 'pytest.MonkeyPatch',
) -> None:
    _set_env(monkeypatch, tmp_path)
    runner = CliRunner()
    app = build_cli_app()

    runner.invoke(app, ['project', 'create', '--name', 'forced'])
    project_dir = tmp_path / 'projects' / 'forced'
    active, _sp = _drop_staged(project_dir)
    lock_path(active).write_text('{"hostname":"h","username":"u"}', encoding='utf-8')

    result = runner.invoke(app, ['schematic', 'apply-staged', 'forced', '--force'])
    assert result.exit_code == 0, result.output
    assert f'schematic-applied: {active}' in result.output
    assert active.read_text() == 'STAGED'


def test_schematic_apply_staged_parent_hash_mismatch_blocks(
    tmp_path: 'Path',
    monkeypatch: 'pytest.MonkeyPatch',
) -> None:
    _set_env(monkeypatch, tmp_path)
    runner = CliRunner()
    app = build_cli_app()

    runner.invoke(app, ['project', 'create', '--name', 'diverged'])
    project_dir = tmp_path / 'projects' / 'diverged'
    active, _sp = _drop_staged(project_dir)
    active.write_bytes(b'USER_EDIT')  # divergence

    result = runner.invoke(app, ['schematic', 'apply-staged', 'diverged'])
    assert result.exit_code == 1
    assert 'reason=parent-hash-mismatch' in result.output
    assert active.read_bytes() == b'USER_EDIT'


def test_schematic_apply_staged_accept_overwrite_proceeds(
    tmp_path: 'Path',
    monkeypatch: 'pytest.MonkeyPatch',
) -> None:
    _set_env(monkeypatch, tmp_path)
    runner = CliRunner()
    app = build_cli_app()

    runner.invoke(app, ['project', 'create', '--name', 'accepted'])
    project_dir = tmp_path / 'projects' / 'accepted'
    active, _sp = _drop_staged(project_dir)
    active.write_bytes(b'USER_EDIT')

    result = runner.invoke(
        app,
        ['schematic', 'apply-staged', 'accepted', '--accept-overwrite'],
    )
    assert result.exit_code == 0, result.output
    assert active.read_text() == 'STAGED'
