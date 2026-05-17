"""Typer CLI inbound-adapter: команды efactory."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import typer
from pydantic import ValidationError

from application.create_project import create_project as create_project_use_case
from application.delete_project import delete_project as delete_project_use_case
from application.get_project import (
    ProjectNotFoundError,
)
from application.get_project import (
    get_project as get_project_use_case,
)
from application.list_projects import list_projects as list_projects_use_case
from application.update_project import (
    PhaseUpdate,
    UpdateProjectCommand,
)
from application.update_project import (
    update_project as update_project_use_case,
)
from domain.phase import PhaseName, PhaseStatus

if TYPE_CHECKING:
    from pathlib import Path

    from domain.project import Project
    from ports.outbound.metadata_repository import MetadataRepository
    from ports.outbound.project_file_repository import ProjectFileRepository


def build_app(
    *,
    projects_root: Path,
    metadata_repository: MetadataRepository,
    file_repository: ProjectFileRepository,
) -> typer.Typer:
    app = typer.Typer(no_args_is_help=True, add_completion=False)
    project_app = typer.Typer(no_args_is_help=True, add_completion=False)
    app.add_typer(project_app, name='project')

    @project_app.command('create')
    def create(
        name: str = typer.Option(..., '--name', help='Имя нового проекта'),
    ) -> None:
        try:
            project = asyncio.run(
                create_project_use_case(
                    name=name,
                    projects_root=projects_root,
                    repo=metadata_repository,
                    file_repo=file_repository,
                ),
            )
        except ValidationError as exc:
            messages = '; '.join(error['msg'] for error in exc.errors())
            typer.echo(f'Invalid project name: {messages}', err=True)
            raise typer.Exit(code=2) from exc
        typer.echo(
            f'Created project {project.name} at {project.path} (id={project.id})',
        )

    @project_app.command('list')
    def list_() -> None:
        projects = asyncio.run(
            list_projects_use_case(repo=metadata_repository),
        )
        if not projects:
            typer.echo('No projects found.')
            return
        for project in projects:
            typer.echo(
                f'{project.name}\t{project.created_at.isoformat()}\t{project.path}',
            )

    @project_app.command('show')
    def show(
        name: str = typer.Option(..., '--name', help='Имя искомого проекта'),
    ) -> None:
        try:
            project = asyncio.run(
                get_project_use_case(name=name, repo=metadata_repository),
            )
        except ProjectNotFoundError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(f'name: {project.name}')
        typer.echo(f'id: {project.id}')
        typer.echo(f'status: {project.status.value}')
        typer.echo(f'created_at: {project.created_at.isoformat()}')
        typer.echo(f'path: {project.path}')
        typer.echo('phases:')
        for phase in project.phases:
            started = phase.started_at.isoformat() if phase.started_at else '-'
            completed = phase.completed_at.isoformat() if phase.completed_at else '-'
            typer.echo(
                f'  {phase.name.value}\t{phase.status.value}\t{started}\t{completed}',
            )

    @project_app.command('delete')
    def delete(
        name: str = typer.Option(..., '--name', help='Имя удаляемого проекта'),
    ) -> None:
        try:
            asyncio.run(
                delete_project_use_case(
                    name=name,
                    repo=metadata_repository,
                    file_repo=file_repository,
                ),
            )
        except ProjectNotFoundError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(f'Deleted project {name}')

    def _run_update(
        *,
        current_name: str,
        new_name: str | None,
        phase_update: PhaseUpdate | None,
    ) -> Project:
        try:
            return asyncio.run(
                update_project_use_case(
                    command=UpdateProjectCommand(
                        name=current_name,
                        new_name=new_name,
                        phase_update=phase_update,
                    ),
                    repo=metadata_repository,
                ),
            )
        except ProjectNotFoundError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        except ValidationError as exc:
            messages = '; '.join(error['msg'] for error in exc.errors())
            typer.echo(f'Invalid project name: {messages}', err=True)
            raise typer.Exit(code=2) from exc
        except ValueError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc

    @project_app.command('update')
    def update(
        name: str = typer.Argument(..., help='Текущее имя проекта'),
        new_name: str | None = typer.Option(
            None,
            '--new-name',
            help='Новое имя проекта (для переименования)',
        ),
        phase: PhaseName | None = typer.Option(
            None,
            '--phase',
            help='Имя фазы для смены статуса',
        ),
        status: PhaseStatus | None = typer.Option(
            None,
            '--status',
            help='Целевой статус фазы',
        ),
    ) -> None:
        has_rename = new_name is not None
        has_phase_op = phase is not None or status is not None
        if has_rename and has_phase_op:
            typer.echo(
                '--new-name and --phase/--status are mutually exclusive: '
                'one update per command',
                err=True,
            )
            raise typer.Exit(code=2)
        if not has_rename and not has_phase_op:
            typer.echo(
                'Specify either --new-name or both --phase and --status',
                err=True,
            )
            raise typer.Exit(code=2)
        if has_phase_op and (phase is None or status is None):
            typer.echo('--phase and --status must be used together', err=True)
            raise typer.Exit(code=2)

        phase_update = (
            PhaseUpdate(name=phase, target_status=status)
            if phase is not None and status is not None
            else None
        )
        project = _run_update(
            current_name=name,
            new_name=new_name,
            phase_update=phase_update,
        )
        typer.echo(f'Updated project {project.name} (id={project.id})')

    @project_app.command('add-phase')
    def add_phase(
        name: str = typer.Argument(..., help='Имя проекта'),
        phase: PhaseName = typer.Argument(
            ...,
            help='Фаза для возврата в pending (unskip)',
        ),
    ) -> None:
        """Shortcut: вернуть фазу из skipped обратно в pending."""
        project = _run_update(
            current_name=name,
            new_name=None,
            phase_update=PhaseUpdate(
                name=phase,
                target_status=PhaseStatus.PENDING,
            ),
        )
        typer.echo(
            f'Phase {phase.value} -> pending in project {project.name}',
        )

    @project_app.command('skip-phase')
    def skip_phase(
        name: str = typer.Argument(..., help='Имя проекта'),
        phase: PhaseName = typer.Argument(
            ...,
            help='Фаза для пометки как пропущенной',
        ),
    ) -> None:
        """Shortcut: пометить фазу как skipped (гибкий скоуп §4.1)."""
        project = _run_update(
            current_name=name,
            new_name=None,
            phase_update=PhaseUpdate(
                name=phase,
                target_status=PhaseStatus.SKIPPED,
            ),
        )
        typer.echo(
            f'Phase {phase.value} -> skipped in project {project.name}',
        )

    return app
