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

if TYPE_CHECKING:
    from pathlib import Path

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

    return app
