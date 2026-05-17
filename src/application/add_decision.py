"""AddDecision — use case добавления решения (T099 Phase 2)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy.exc import SQLAlchemyError

from application.errors import (
    DecisionPersistenceError,
    IndexPersistenceError,
)
from application.get_project import get_project
from domain.decision import Decision, DecisionRef, DecisionStatus

if TYPE_CHECKING:
    from datetime import date
    from pathlib import Path

    from ports.outbound.decision_repository import DecisionRepository
    from ports.outbound.metadata_repository import MetadataRepository
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
    repo: MetadataRepository,
    manifest_repo: ProjectManifestRepository,
    decision_repo: DecisionRepository,
) -> Decision:
    """
    Markdown first → manifest reference → SQL index.

    Markdown = truth: при partial failure manifest sync (или SQL) —
    markdown остаётся, `reindex` восстановит manifest и SQL.
    """
    project = await get_project(
        name=project_name, repo=repo, manifest_repo=manifest_repo
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

    try:
        await repo.update(project)
    except SQLAlchemyError as exc:
        raise IndexPersistenceError(project_name, exc) from exc

    return decision


__all__ = ['add_decision']
