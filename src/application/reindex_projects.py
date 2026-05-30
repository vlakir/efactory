"""
validate_manifests — T157 replaces SQL-based reindex.

Diagnostic-only: scan `storage_root` для каждого подкаталога проверить
наличие и валидность `project.yaml`. SQL индекс удалён в T157 —
filesystem единственный источник истины, синхронизировать нечего.

Use case также экспортируется под старым именем `reindex_projects`
для backward-compat callers — но семантика теперь `validate_manifests`.
CLI rename выполнен в build_app (Q-A → b).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from domain.decision import DecisionRef
from ports.outbound.project_manifest_repository import (
    ManifestInvalidError,
    ManifestNotFoundError,
)

if TYPE_CHECKING:
    from pathlib import Path

    from domain.project import Project
    from ports.outbound.decision_repository import DecisionRepository
    from ports.outbound.project_manifest_repository import (
        ProjectManifestRepository,
    )


@dataclass(frozen=True)
class ValidateManifestsSummary:
    """T157: diagnostic отчёт о validate_manifests scan."""

    valid: int = 0
    failed: list[tuple[Path, str]] = field(default_factory=list)


# Backward-compat alias для callers (use case в CLI).
ReindexSummary = ValidateManifestsSummary


async def _sync_decisions(
    project: Project,
    decision_repo: DecisionRepository | None,
) -> Project:
    """Rebuild project.decisions из markdown файлов (T099). No-op без repo."""
    if decision_repo is None:
        return project
    decisions = await decision_repo.list_all(project.path)
    refs = tuple(DecisionRef.from_decision(d) for d in decisions)
    return project.model_copy(update={'decisions': refs})


async def validate_manifests(
    *,
    storage_root: Path,
    manifest_repo: ProjectManifestRepository,
    decision_repo: DecisionRepository | None = None,
) -> ValidateManifestsSummary:
    """
    T157: validate manifest YAML файлы в `storage_root`.

    Для каждого discovered project path: попытка load + (опц.)
    sync decisions. Errors собираются в `failed: [(path, message)]`.
    Best-effort — первая ошибка не блокирует остальные.
    """
    valid = 0
    failed: list[tuple[Path, str]] = []

    discovered = await manifest_repo.discover_all(storage_root)
    for manifest_path in discovered:
        try:
            project = await manifest_repo.load(manifest_path)
        except (ManifestNotFoundError, ManifestInvalidError) as exc:
            failed.append((manifest_path, str(exc)))
            continue
        if decision_repo is not None:
            project = await _sync_decisions(project, decision_repo)
            try:
                await manifest_repo.save(project)
            except OSError as exc:
                failed.append((manifest_path, str(exc)))
                continue
        valid += 1

    return ValidateManifestsSummary(valid=valid, failed=failed)


# Backward-compat alias для CLI callers.
reindex_projects = validate_manifests


__all__ = [
    'ReindexSummary',
    'ValidateManifestsSummary',
    'reindex_projects',
    'validate_manifests',
]
