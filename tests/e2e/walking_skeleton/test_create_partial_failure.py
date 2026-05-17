"""E2E: partial-failure scenario для CreateProject (T098 § 4 / Analyze C2).

Manifest записан (truth на диске), SQL upsert упал → CLI exit_code=2,
stderr содержит подсказку `efactory project reindex`. Последующий
reindex восстанавливает индекс из manifest'а.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.exc import SQLAlchemyError
from typer.testing import CliRunner

from adapters.outbound.persistence_sql.repository import (
    SqlAlchemyMetadataRepository,
)
from composition.main import build_cli_app

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from domain.project import Project


def test_create_partial_failure_keeps_manifest_and_recovers_via_reindex(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage_root = tmp_path / 'storage'
    db_file = tmp_path / 'efactory.sqlite'
    monkeypatch.setenv('EFACTORY_PROJECTS_ROOT', str(storage_root))
    monkeypatch.setenv(
        'EFACTORY_DATABASE_URL',
        f'sqlite+aiosqlite:///{db_file}',
    )
    runner = CliRunner()

    async def failing_save(
        self: SqlAlchemyMetadataRepository,  # noqa: ARG001
        project: Project,  # noqa: ARG001
    ) -> None:
        msg = 'simulated SQL outage'
        raise SQLAlchemyError(msg)

    with monkeypatch.context() as patched:
        patched.setattr(SqlAlchemyMetadataRepository, 'save', failing_save)
        result = runner.invoke(
            build_cli_app(), ['project', 'create', '--name', 'half-done'],
        )

    assert result.exit_code == 2, result.output
    assert 'reindex' in result.output.lower()
    manifest_path = storage_root / 'half-done' / 'project.yaml'
    assert manifest_path.is_file(), 'manifest должен сохраниться (truth)'

    reindex_result = runner.invoke(build_cli_app(), ['project', 'reindex'])
    assert reindex_result.exit_code == 0, reindex_result.output
    assert 'Reindexed 1 projects.' in reindex_result.output

    show_result = runner.invoke(
        build_cli_app(), ['project', 'show', '--name', 'half-done'],
    )
    assert show_result.exit_code == 0, show_result.output
    assert 'half-done' in show_result.output
