"""AddDecision — use case добавления решения (T099 Phase 2 + T157)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from application.errors import DecisionPersistenceError
from application.get_project import get_project
from domain.decision import Decision, DecisionRef, DecisionStatus

if TYPE_CHECKING:
    from datetime import date
    from pathlib import Path

    from ports.outbound.decision_repository import DecisionRepository
    from ports.outbound.project_manifest_repository import (
        ProjectManifestRepository,
    )


async def add_decision(
    *,
    project_name: str,
    title: str,
    decision_date: date,
    status: DecisionStatus,
    summary: str,
    rationale: str,
    evidence: Path | None = None,
    session: Path | None = None,
    projects_root: Path,
    manifest_repo: ProjectManifestRepository,
    decision_repo: DecisionRepository,
) -> Decision:
    """
    T157: markdown first → manifest reference. SQL slice удалён.

    Markdown = truth: при partial failure manifest sync — markdown
    остаётся, `validate_manifests` диагностирует desync.
    """
    project = await get_project(
        name=project_name,
        projects_root=projects_root,
        manifest_repo=manifest_repo,
    )

    next_id = await decision_repo.next_id(project.path)
    decision = Decision(
        id=next_id,
        title=title,
        date=decision_date,
        status=status,
        summary=summary,
        rationale=rationale,
        evidence=evidence,
        session=session,
    )

    await decision_repo.save(project.path, decision)

    new_decisions = (*project.decisions, DecisionRef.from_decision(decision))
    project.decisions = new_decisions
    project.updated_at = datetime.now(UTC)

    try:
        await manifest_repo.save(project)
    except OSError as exc:
        raise DecisionPersistenceError(project_name, decision.id, exc) from exc

    return decision


__all__ = ['add_decision']
