"""GetDecision — use case получения одного решения (T099 Phase 2)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from application.get_project import get_project

if TYPE_CHECKING:
    from domain.decision import Decision
    from ports.outbound.decision_repository import DecisionRepository
    from ports.outbound.metadata_repository import MetadataRepository
    from ports.outbound.project_manifest_repository import (
        ProjectManifestRepository,
    )


async def get_decision(
    *,
    project_name: str,
    decision_id: str,
    repo: MetadataRepository,
    manifest_repo: ProjectManifestRepository,
    decision_repo: DecisionRepository,
) -> Decision:
    """`DecisionNotFoundError` если markdown файл отсутствует."""
    project = await get_project(
        name=project_name, repo=repo, manifest_repo=manifest_repo
    )
    return await decision_repo.load(project.path, decision_id)


__all__ = ['get_decision']
