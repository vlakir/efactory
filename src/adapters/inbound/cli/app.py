"""Typer CLI inbound-adapter: команды efactory."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
from pydantic import ValidationError

from application.add_decision import add_decision as add_decision_use_case
from application.create_project import create_project as create_project_use_case
from application.delete_project import delete_project as delete_project_use_case
from application.errors import (
    DecisionPersistenceError,
    IndexPersistenceError,
    ProjectManifestMissingError,
)
from application.get_decision import get_decision as get_decision_use_case
from application.get_project import (
    ProjectNotFoundError,
)
from application.get_project import (
    get_project as get_project_use_case,
)
from application.list_decisions import list_decisions as list_decisions_use_case
from application.list_projects import list_projects as list_projects_use_case
from application.reindex_projects import (
    reindex_projects as reindex_projects_use_case,
)
from application.update_project import (
    PhaseUpdate,
    UpdateProjectCommand,
)
from application.update_project import (
    update_project as update_project_use_case,
)
from domain.decision import DecisionStatus
from domain.phase import PhaseName, PhaseStatus
from ports.outbound.decision_repository import DecisionNotFoundError

if TYPE_CHECKING:
    from domain.project import Project
    from ports.outbound.decision_repository import DecisionRepository
    from ports.outbound.metadata_repository import MetadataRepository
    from ports.outbound.project_file_repository import ProjectFileRepository
    from ports.outbound.project_manifest_repository import (
        ProjectManifestRepository,
    )


def build_app(
    *,
    projects_root: Path,
    metadata_repository: MetadataRepository,
    file_repository: ProjectFileRepository,
    manifest_repository: ProjectManifestRepository,
    decision_repository: DecisionRepository,
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
                    manifest_repo=manifest_repository,
                ),
            )
        except ValidationError as exc:
            messages = '; '.join(error['msg'] for error in exc.errors())
            typer.echo(f'Invalid project name: {messages}', err=True)
            raise typer.Exit(code=2) from exc
        except IndexPersistenceError as exc:
            typer.echo(str(exc), err=True)
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
                get_project_use_case(
                    name=name,
                    repo=metadata_repository,
                    manifest_repo=manifest_repository,
                ),
            )
        except ProjectNotFoundError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        except ProjectManifestMissingError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
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
                    manifest_repo=manifest_repository,
                ),
            )
        except ProjectNotFoundError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        except ProjectManifestMissingError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        except IndexPersistenceError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
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

    @project_app.command('reindex')
    def reindex(
        *,
        storage_root: Annotated[
            str | None,
            typer.Option(
                '--storage-root',
                help=(
                    'Каталог со всеми проектами для сканирования. '
                    'По умолчанию — projects_root из Settings.'
                ),
            ),
        ] = None,
        remove_orphans: Annotated[
            bool,
            typer.Option(
                '--remove-orphans',
                help=(
                    'Удалить из SQL индекса записи без manifest на диске. '
                    'По умолчанию — оставить и попытаться bootstrap из SQL.'
                ),
            ),
        ] = False,
    ) -> None:
        """Пересобрать SQL индекс по manifest'ам (T098); sync decisions (T099)."""
        root: Path = Path(storage_root) if storage_root is not None else projects_root
        summary = asyncio.run(
            reindex_projects_use_case(
                storage_root=root,
                repo=metadata_repository,
                manifest_repo=manifest_repository,
                decision_repo=decision_repository,
                remove_orphans=remove_orphans,
            ),
        )
        typer.echo(f'Reindexed {summary.indexed} projects.')
        if summary.bootstrapped:
            typer.echo(
                f'Bootstrapped {summary.bootstrapped} manifests for pre-T098 projects.',
            )
        if summary.orphans:
            action = 'removed' if remove_orphans else 'kept'
            typer.echo(
                f'Orphans ({len(summary.orphans)}, {action}): '
                f'{", ".join(summary.orphans)}',
            )
            if not remove_orphans:
                typer.echo('  (Use --remove-orphans to clean.)')
        if summary.failed:
            typer.echo(f'Failed ({len(summary.failed)}):', err=True)
            for failed_path, message in summary.failed:
                typer.echo(f'  {failed_path}: {message}', err=True)
            raise typer.Exit(code=1)

    decision_app = typer.Typer(no_args_is_help=True, add_completion=False)
    app.add_typer(decision_app, name='decision')

    @decision_app.command('add')
    def decision_add(
        *,
        project: Annotated[
            str,
            typer.Option('--project', help='Имя проекта'),
        ],
        title: Annotated[
            str,
            typer.Option('--title', help='Заголовок решения'),
        ],
        summary: Annotated[
            str,
            typer.Option('--summary', help='Краткое описание (1-2 строки)'),
        ],
        rationale: Annotated[
            str,
            typer.Option('--rationale', help='Обоснование выбора'),
        ],
        status: Annotated[
            DecisionStatus,
            typer.Option('--status', help='proposed | accepted | rejected'),
        ] = DecisionStatus.ACCEPTED,
        decision_date: Annotated[
            datetime | None,
            typer.Option(
                '--date',
                help='Дата решения (YYYY-MM-DD); по умолчанию сегодня UTC',
                formats=['%Y-%m-%d'],
            ),
        ] = None,
        evidence: Annotated[
            str | None,
            typer.Option(
                '--evidence',
                help='Путь к данным-подтверждению, относительный к проекту',
            ),
        ] = None,
        session: Annotated[
            str | None,
            typer.Option(
                '--session',
                help='Путь к файлу сессии, относительный к проекту',
            ),
        ] = None,
    ) -> None:
        date_value = (
            decision_date.date()
            if decision_date is not None
            else datetime.now(UTC).date()
        )
        try:
            decision = asyncio.run(
                add_decision_use_case(
                    project_name=project,
                    title=title,
                    decision_date=date_value,
                    status=status,
                    summary=summary,
                    rationale=rationale,
                    evidence=Path(evidence) if evidence is not None else None,
                    session=Path(session) if session is not None else None,
                    repo=metadata_repository,
                    manifest_repo=manifest_repository,
                    decision_repo=decision_repository,
                ),
            )
        except ProjectNotFoundError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        except ProjectManifestMissingError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        except DecisionPersistenceError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        except IndexPersistenceError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        except ValidationError as exc:
            messages = '; '.join(error['msg'] for error in exc.errors())
            typer.echo(f'Invalid decision: {messages}', err=True)
            raise typer.Exit(code=2) from exc
        typer.echo(f'Added {decision.id}: {decision.title}')

    @decision_app.command('list')
    def decision_list(
        *,
        project: Annotated[
            str,
            typer.Option('--project', help='Имя проекта'),
        ],
    ) -> None:
        try:
            decisions = asyncio.run(
                list_decisions_use_case(
                    project_name=project,
                    repo=metadata_repository,
                    manifest_repo=manifest_repository,
                    decision_repo=decision_repository,
                ),
            )
        except ProjectNotFoundError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        except ProjectManifestMissingError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        if not decisions:
            typer.echo('No decisions found.')
            return
        for d in decisions:
            typer.echo(
                f'{d.id}\t{d.date.isoformat()}\t{d.status.value}\t{d.summary}',
            )

    @decision_app.command('show')
    def decision_show(
        *,
        project: Annotated[
            str,
            typer.Option('--project', help='Имя проекта'),
        ],
        decision_id: Annotated[
            str,
            typer.Option('--id', help='ID решения (D001)'),
        ],
    ) -> None:
        try:
            decision = asyncio.run(
                get_decision_use_case(
                    project_name=project,
                    decision_id=decision_id,
                    repo=metadata_repository,
                    manifest_repo=manifest_repository,
                    decision_repo=decision_repository,
                ),
            )
        except ProjectNotFoundError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        except ProjectManifestMissingError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        except DecisionNotFoundError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(f'# {decision.id}: {decision.title}')
        typer.echo(f'Дата: {decision.date.isoformat()}')
        typer.echo(f'Статус: {decision.status.value}')
        if decision.session is not None:
            typer.echo(f'Сессия: {decision.session}')
        typer.echo(f'\nSummary:\n{decision.summary}')
        typer.echo(f'\nRationale:\n{decision.rationale}')
        if decision.evidence is not None:
            typer.echo(f'\nEvidence: {decision.evidence}')

    return app
