"""Маппинг domain.Project ↔ ProjectModel — единственное место связки."""

from __future__ import annotations

from pathlib import Path

from adapters.outbound.persistence_sql.models import ProjectModel
from domain.project import Project, ProjectStatus


def project_to_model(project: Project) -> ProjectModel:
    return ProjectModel(
        id=project.id,
        name=project.name,
        path=str(project.path),
        created_at=project.created_at,
        status=project.status.value,
    )


def model_to_project(model: ProjectModel) -> Project:
    return Project(
        id=model.id,
        name=model.name,
        path=Path(model.path),
        created_at=model.created_at,
        status=ProjectStatus(model.status),
    )
