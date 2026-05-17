"""
ReindexProjects — пересборка SQL индекса по manifest'ам + sync decisions (T098, T099).

Работает в две стороны (Resolved #3 (B)):
- **Primary mode** (manifest → SQL): сканирует `storage_root`,
  upsert'ит каждый найденный manifest в SQL. Это штатный путь после
  переноса проектов или потери `index.db`.
- **Bootstrap mode** (SQL → manifest): для SQL-строк, у которых нет
  manifest на диске (pre-T098 проекты), генерирует `project.yaml`
  из SQL-данных. `updated_at = created_at` (Clarify #10).

`remove_orphans=True` отменяет bootstrap: SQL-only записи удаляются
из индекса и попадают в `orphans` summary как «удалённые».

T099 расширение: если передан `decision_repo`, для каждого
индексируемого/bootstrapped проекта `Project.decisions` пересобирается
из реальных markdown файлов в `<path>/decisions/` (markdown = truth,
manifest reference — index). Без `decision_repo` поведение идентично
T098 phase 2.

Best-effort (Resolved #6): первая ошибка не блокирует остальные.
Любые errors собираются в `failed: [(path, message)]` — CLI Phase 3
читает их и выставляет exit_code = 1 при non-empty failed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sqlalchemy.exc import SQLAlchemyError

from domain.decision import DecisionRef
from ports.outbound.project_manifest_repository import (
    ManifestInvalidError,
    ManifestNotFoundError,
)

if TYPE_CHECKING:
    from pathlib import Path

    from domain.project import Project
    from ports.outbound.decision_repository import DecisionRepository
    from ports.outbound.metadata_repository import MetadataRepository
    from ports.outbound.project_manifest_repository import (
        ProjectManifestRepository,
    )


@dataclass(frozen=True)
class ReindexSummary:
    indexed: int = 0
    bootstrapped: int = 0
    orphans: list[str] = field(default_factory=list)
    failed: list[tuple[Path, str]] = field(default_factory=list)


async def _sync_decisions(
    project: Project,
    decision_repo: DecisionRepository | None,
) -> Project:
    """Подтянуть `project.decisions` из markdown файлов (T099). No-op без repo."""
    if decision_repo is None:
        return project
    decisions = await decision_repo.list_all(project.path)
    refs = tuple(DecisionRef.from_decision(d) for d in decisions)
    return project.model_copy(update={'decisions': refs})


async def reindex_projects(
    *,
    storage_root: Path,
    repo: MetadataRepository,
    manifest_repo: ProjectManifestRepository,
    decision_repo: DecisionRepository | None = None,
    remove_orphans: bool = False,
) -> ReindexSummary:
    indexed = 0
    bootstrapped = 0
    orphans: list[str] = []
    failed: list[tuple[Path, str]] = []

    discovered = await manifest_repo.discover_all(storage_root)
    discovered_set = set(discovered)

    for manifest_path in discovered:
        try:
            project = await manifest_repo.load(manifest_path)
        except (ManifestNotFoundError, ManifestInvalidError) as exc:
            failed.append((manifest_path, str(exc)))
            continue
        project = await _sync_decisions(project, decision_repo)
        # Если decisions поменялись — пере-сохранить manifest до SQL upsert.
        if decision_repo is not None:
            try:
                await manifest_repo.save(project)
            except OSError as exc:
                failed.append((manifest_path, str(exc)))
                continue
        try:
            await repo.save(project)
        except SQLAlchemyError as exc:
            failed.append((manifest_path, str(exc)))
            continue
        indexed += 1

    sql_rows = await repo.list_all()
    for sql_row in sql_rows:
        if sql_row.path in discovered_set:
            continue
        if remove_orphans:
            try:
                await repo.delete_by_name(sql_row.name)
            except SQLAlchemyError as exc:
                failed.append((sql_row.path, str(exc)))
                continue
            orphans.append(sql_row.name)
            continue
        bootstrap_project = sql_row.model_copy(
            update={'updated_at': sql_row.created_at},
        )
        bootstrap_project = await _sync_decisions(bootstrap_project, decision_repo)
        try:
            await manifest_repo.save(bootstrap_project)
        except OSError as exc:
            orphans.append(sql_row.name)
            failed.append((sql_row.path, str(exc)))
            continue
        bootstrapped += 1

    return ReindexSummary(
        indexed=indexed,
        bootstrapped=bootstrapped,
        orphans=orphans,
        failed=failed,
    )


__all__ = ['ReindexSummary', 'reindex_projects']
