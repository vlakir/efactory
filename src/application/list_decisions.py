"""ListDecisions — use case списка решений (T099 Phase 2)."""

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


async def list_decisions(
    *,
    project_name: str,
    repo: MetadataRepository,
    manifest_repo: ProjectManifestRepository,
    decision_repo: DecisionRepository,
) -> list[Decision]:
    """Markdown = truth (Spec § 3): читаем напрямую из `decisions/*.md`."""
    project = await get_project(
        name=project_name, repo=repo, manifest_repo=manifest_repo
    )
    return await decision_repo.list_all(project.path)


__all__ = ['list_decisions']
