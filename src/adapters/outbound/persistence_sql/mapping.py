"""Маппинг domain.Project ↔ ProjectModel — единственное место связки."""

from __future__ import annotations

from pathlib import Path

from adapters.outbound.persistence_sql.models import ProjectModel
from domain.project import Project


def project_to_model(project: Project) -> ProjectModel:
    return ProjectModel(
        id=project.id,
        name=project.name,
        path=str(project.path),
        created_at=project.created_at,
        status=project.status.value,
    )


def model_to_project(model: ProjectModel) -> Project:
    """
    Phases пока не загружаются из SQL — default all-pending.

    Stored `model.status` игнорируется: после T097 фаза 1 status
    стал computed property, его в input конструктора Project
    передать нельзя. Колонка SQL остаётся как stale-cache; в фазе
    2 миграция дропнет её и заведёт таблицу `phases`, тогда
    phases начнут восстанавливаться при load.
    """
    return Project(
        id=model.id,
        name=model.name,
        path=Path(model.path),
        created_at=model.created_at,
    )
