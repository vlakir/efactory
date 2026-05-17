"""Маппинг domain.Project ↔ ProjectModel — единственное место связки."""

from __future__ import annotations

from pathlib import Path

from adapters.outbound.persistence_sql.models import PhaseModel, ProjectModel
from domain.phase import Phase, PhaseName, PhaseStatus
from domain.project import Project


def project_to_model(project: Project) -> ProjectModel:
    return ProjectModel(
        id=project.id,
        name=project.name,
        path=str(project.path),
        created_at=project.created_at,
        phases=[_phase_to_model(project.id, phase) for phase in project.phases],
    )


def model_to_project(model: ProjectModel) -> Project:
    phases_by_name = {p.name: p for p in model.phases}
    canonical = tuple(
        Phase(
            name=name,
            status=PhaseStatus(phases_by_name[name.value].status),
            started_at=phases_by_name[name.value].started_at,
            completed_at=phases_by_name[name.value].completed_at,
        )
        for name in PhaseName
    )
    return Project(
        id=model.id,
        name=model.name,
        path=Path(model.path),
        created_at=model.created_at,
        phases=canonical,
    )


def _phase_to_model(project_id: object, phase: Phase) -> PhaseModel:
    return PhaseModel(
        project_id=project_id,
        name=phase.name.value,
        status=phase.status.value,
        started_at=phase.started_at,
        completed_at=phase.completed_at,
    )
