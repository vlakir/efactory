"""Typer CLI inbound-adapter: команды efactory."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
from pydantic import ValidationError

from adapters.inbound.cli.spice_units import (
    SpiceNumberFormatError,
    parse_spice_number,
)
from application.add_decision import add_decision as add_decision_use_case
from application.create_project import create_project as create_project_use_case
from application.delete_project import delete_project as delete_project_use_case
from application.design_to_netlist import (
    design_to_netlist as design_to_netlist_use_case,
)
from application.design_to_sim import design_to_sim as design_to_sim_use_case
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
from application.sim_run import sim_run as sim_run_use_case
from application.update_project import (
    PhaseUpdate,
    UpdateProjectCommand,
)
from application.update_project import (
    update_project as update_project_use_case,
)
from domain.application import ApplicationKind
from domain.decision import DecisionStatus
from domain.phase import PhaseName, PhaseStatus
from domain.simulation import (
    AcAnalysis,
    OpAnalysis,
    TranAnalysis,
)
from domain.spice_model import ComponentCategory
from ports.outbound.app_manager import (
    ApplicationNotInstalledError,
    ApplicationStartError,
    ApplicationStopError,
)
from ports.outbound.decision_repository import DecisionNotFoundError
from ports.outbound.git_repository import GitOperationError
from ports.outbound.schematic_exporter import SchematicExportError
from ports.outbound.session_logger import SessionEventStatus
from ports.outbound.simulator import (
    SimulationFailedError,
    SimulatorUnavailableError,
)
from ports.outbound.spice_model_library import SpiceModelNotFoundError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from application.create_project import CreateProjectResult
    from application.reindex_projects import ReindexSummary
    from domain.decision import Decision
    from domain.project import Project
    from domain.simulation import AnalysisSpec, Simulation, SimulationResult
    from domain.spice_model import SpiceModel
    from ports.outbound.app_manager import AppManager, RunResult
    from ports.outbound.decision_repository import DecisionRepository
    from ports.outbound.git_repository import GitRepository
    from ports.outbound.metadata_repository import MetadataRepository
    from ports.outbound.project_file_repository import ProjectFileRepository
    from ports.outbound.project_manifest_repository import (
        ProjectManifestRepository,
    )
    from ports.outbound.schematic_exporter import SchematicExporter
    from ports.outbound.session_logger import SessionLogger
    from ports.outbound.simulator import Simulator
    from ports.outbound.spice_model_library import SpiceModelLibrary


async def _log_command[T](
    logger: SessionLogger,
    event: str,
    *,
    project: str | None,
    payload: dict | None,
    fn: Callable[[], Awaitable[T]],
) -> T:
    """Wrapper: log_event(ok) on success / log_event(error) on exception."""
    try:
        result = await fn()
    except Exception as exc:
        await logger.log_event(
            event,
            status=SessionEventStatus.ERROR,
            project=project,
            payload=payload,
            error=f'{type(exc).__name__}: {exc}',
        )
        raise
    await logger.log_event(
        event,
        status=SessionEventStatus.OK,
        project=project,
        payload=payload,
    )
    return result


def build_app(
    *,
    projects_root: Path,
    metadata_repository: MetadataRepository,
    file_repository: ProjectFileRepository,
    manifest_repository: ProjectManifestRepository,
    decision_repository: DecisionRepository,
    git_repository: GitRepository,
    session_logger: SessionLogger,
    spice_library: SpiceModelLibrary,
    app_manager: AppManager,
    schematic_exporter: SchematicExporter,
    simulator: Simulator,
) -> typer.Typer:
    app = typer.Typer(no_args_is_help=True, add_completion=False)
    project_app = typer.Typer(no_args_is_help=True, add_completion=False)
    app.add_typer(project_app, name='project')

    @project_app.command('create')
    def create(
        name: str = typer.Option(..., '--name', help='Имя нового проекта'),
    ) -> None:
        async def _run() -> CreateProjectResult:
            return await create_project_use_case(
                name=name,
                projects_root=projects_root,
                repo=metadata_repository,
                file_repo=file_repository,
                manifest_repo=manifest_repository,
                git_repo=git_repository,
            )

        try:
            result = asyncio.run(
                _log_command(
                    session_logger,
                    'project.create',
                    project=name,
                    payload={'name': name},
                    fn=_run,
                ),
            )
        except ValidationError as exc:
            messages = '; '.join(error['msg'] for error in exc.errors())
            typer.echo(f'Invalid project name: {messages}', err=True)
            raise typer.Exit(code=2) from exc
        except IndexPersistenceError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        except GitOperationError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        project = result.project
        if not result.git_initialized:
            asyncio.run(
                session_logger.log_event(
                    'git.init',
                    status=SessionEventStatus.ERROR,
                    project=name,
                    error='git not found on PATH (skipped)',
                ),
            )
        typer.echo(
            f'Created project {project.name} at {project.path} (id={project.id})',
        )

    @project_app.command('list')
    def list_() -> None:
        async def _run() -> list:
            return await list_projects_use_case(repo=metadata_repository)

        projects = asyncio.run(
            _log_command(
                session_logger,
                'project.list',
                project=None,
                payload=None,
                fn=_run,
            ),
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
        async def _run() -> Project:
            return await get_project_use_case(
                name=name,
                repo=metadata_repository,
                manifest_repo=manifest_repository,
            )

        try:
            project = asyncio.run(
                _log_command(
                    session_logger,
                    'project.show',
                    project=name,
                    payload={'name': name},
                    fn=_run,
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
        async def _run() -> None:
            await delete_project_use_case(
                name=name,
                repo=metadata_repository,
                file_repo=file_repository,
            )

        try:
            asyncio.run(
                _log_command(
                    session_logger,
                    'project.delete',
                    project=name,
                    payload={'name': name},
                    fn=_run,
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
        async def _run() -> Project:
            return await update_project_use_case(
                command=UpdateProjectCommand(
                    name=current_name,
                    new_name=new_name,
                    phase_update=phase_update,
                ),
                repo=metadata_repository,
                manifest_repo=manifest_repository,
            )

        payload: dict = {'name': current_name}
        if new_name is not None:
            payload['new_name'] = new_name
        if phase_update is not None:
            payload['phase'] = phase_update.name.value
            payload['status'] = phase_update.target_status.value

        try:
            return asyncio.run(
                _log_command(
                    session_logger,
                    'project.update',
                    project=current_name,
                    payload=payload,
                    fn=_run,
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

        async def _run() -> ReindexSummary:
            return await reindex_projects_use_case(
                storage_root=root,
                repo=metadata_repository,
                manifest_repo=manifest_repository,
                decision_repo=decision_repository,
                remove_orphans=remove_orphans,
            )

        summary = asyncio.run(
            _log_command(
                session_logger,
                'project.reindex',
                project=None,
                payload={'storage_root': str(root), 'remove_orphans': remove_orphans},
                fn=_run,
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

        async def _run() -> Decision:
            return await add_decision_use_case(
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
            )

        try:
            decision = asyncio.run(
                _log_command(
                    session_logger,
                    'decision.add',
                    project=project,
                    payload={
                        'project': project,
                        'title': title,
                        'status': status.value,
                    },
                    fn=_run,
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
        async def _run() -> list:
            return await list_decisions_use_case(
                project_name=project,
                repo=metadata_repository,
                manifest_repo=manifest_repository,
                decision_repo=decision_repository,
            )

        try:
            decisions = asyncio.run(
                _log_command(
                    session_logger,
                    'decision.list',
                    project=project,
                    payload={'project': project},
                    fn=_run,
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
        async def _run() -> Decision:
            return await get_decision_use_case(
                project_name=project,
                decision_id=decision_id,
                repo=metadata_repository,
                manifest_repo=manifest_repository,
                decision_repo=decision_repository,
            )

        try:
            decision = asyncio.run(
                _log_command(
                    session_logger,
                    'decision.show',
                    project=project,
                    payload={'project': project, 'id': decision_id},
                    fn=_run,
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

    def _register_model_subapp(
        name: str,
        category: ComponentCategory,
        empty_message: str,
    ) -> None:
        sub = typer.Typer(no_args_is_help=True, add_completion=False)
        app.add_typer(sub, name=name)

        @sub.command('list')
        def list_models() -> None:
            async def _run() -> list[SpiceModel]:
                models = await spice_library.list_all()
                return [m for m in models if m.category is category]

            models = asyncio.run(
                _log_command(
                    session_logger,
                    f'{name}.list',
                    project=None,
                    payload=None,
                    fn=_run,
                ),
            )
            if not models:
                typer.echo(empty_message)
                return
            for m in models:
                library = 'user' if m.is_user else 'built-in'
                typer.echo(
                    f'{m.id}\t{library}\t{m.source.value}\t'
                    f'{m.subcategory}\t{m.file_path}',
                )

        @sub.command('show')
        def show_model(
            *,
            model_id: Annotated[
                str,
                typer.Option('--id', help='ID модели (uppercase filename stem)'),
            ],
        ) -> None:
            async def _run_model() -> SpiceModel:
                model = await spice_library.get_by_id(model_id)
                if model.category is not category:
                    msg = (
                        f"Model '{model_id}' has category={model.category.value}, "
                        f'not {category.value}. Try `efactory '
                        f'{model.category.value} show --id {model_id}`.'
                    )
                    raise SpiceModelNotFoundError(msg)
                return model

            async def _run_subckt() -> str:
                return await spice_library.read_subckt(model_id)

            try:
                model = asyncio.run(
                    _log_command(
                        session_logger,
                        f'{name}.show',
                        project=None,
                        payload={'id': model_id},
                        fn=_run_model,
                    ),
                )
                subckt = asyncio.run(_run_subckt())
            except SpiceModelNotFoundError as exc:
                typer.echo(str(exc), err=True)
                raise typer.Exit(code=1) from exc

            typer.echo(f'id: {model.id}')
            typer.echo(f'name: {model.name}')
            typer.echo(f'library: {"user" if model.is_user else "built-in"}')
            typer.echo(f'category: {model.category.value}')
            typer.echo(f'source: {model.source.value}')
            typer.echo(f'type: {model.subcategory}')
            typer.echo(f'pins: {" ".join(model.subckt_pins)}')
            typer.echo(f'file_path: {model.file_path}')
            typer.echo('')
            typer.echo(subckt)

    _register_model_subapp(
        'tube',
        ComponentCategory.TUBE,
        'No tube models found.',
    )
    _register_model_subapp(
        'transformer',
        ComponentCategory.TRANSFORMER,
        'No transformer models found.',
    )
    _register_model_subapp(
        'load',
        ComponentCategory.LOAD,
        'No load models found.',
    )
    _register_model_subapp(
        'diode',
        ComponentCategory.DIODE,
        'No diode models found.',
    )

    app_subapp = typer.Typer(no_args_is_help=True, add_completion=False)
    app.add_typer(app_subapp, name='app')

    @app_subapp.command('status')
    def app_status(
        *,
        kind: Annotated[
            ApplicationKind | None,
            typer.Option('--kind', help='Конкретное приложение; иначе — все'),
        ] = None,
    ) -> None:
        kinds = [kind] if kind is not None else list(ApplicationKind)

        async def _run() -> list:
            return [await app_manager.status(k) for k in kinds]

        infos = asyncio.run(
            _log_command(
                session_logger,
                'app.status',
                project=None,
                payload={'kind': kind.value if kind else 'all'},
                fn=_run,
            ),
        )
        for info in infos:
            path = str(info.executable_path) if info.executable_path else '—'
            pid = str(info.pid) if info.pid else '—'
            typer.echo(
                f'{info.kind.value}\t{info.status.value}\t{pid}\t{path}',
            )

    @app_subapp.command('launch')
    def app_launch(
        kind: Annotated[
            ApplicationKind,
            typer.Argument(help='Приложение (kicad / freecad / ...)'),
        ],
    ) -> None:
        async def _run() -> object:
            return await app_manager.launch(kind)

        try:
            info = asyncio.run(
                _log_command(
                    session_logger,
                    'app.launch',
                    project=None,
                    payload={'kind': kind.value},
                    fn=_run,
                ),
            )
        except ApplicationNotInstalledError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        except ApplicationStartError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        typer.echo(f'Launched {kind.value} (pid={info.pid})')  # type: ignore[attr-defined]

    @app_subapp.command('run')
    def app_run(
        kind: Annotated[
            ApplicationKind,
            typer.Argument(help='Приложение'),
        ],
        *,
        timeout_seconds: Annotated[
            float | None,
            typer.Option('--timeout', help='Таймаут (сек)'),
        ] = None,
        cli_args: Annotated[
            list[str] | None,
            typer.Argument(
                help='Аргументы для приложения (после --)',
            ),
        ] = None,
    ) -> None:
        async def _run() -> RunResult:
            return await app_manager.run(
                kind,
                list(cli_args or []),
                timeout_seconds=timeout_seconds,
            )

        try:
            result = asyncio.run(
                _log_command(
                    session_logger,
                    'app.run',
                    project=None,
                    payload={'kind': kind.value, 'args': cli_args or []},
                    fn=_run,
                ),
            )
        except ApplicationNotInstalledError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        except ApplicationStartError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        if result.stdout:
            typer.echo(result.stdout, nl=False)
        if result.stderr:
            typer.echo(result.stderr, err=True, nl=False)
        if result.returncode != 0:
            raise typer.Exit(code=result.returncode)

    @app_subapp.command('stop')
    def app_stop(
        kind: Annotated[
            ApplicationKind,
            typer.Argument(help='Приложение'),
        ],
    ) -> None:
        async def _run() -> None:
            await app_manager.stop(kind)

        try:
            asyncio.run(
                _log_command(
                    session_logger,
                    'app.stop',
                    project=None,
                    payload={'kind': kind.value},
                    fn=_run,
                ),
            )
        except ApplicationStopError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        typer.echo(f'Stopped {kind.value}')

    @app_subapp.command('restart')
    def app_restart(
        kind: Annotated[
            ApplicationKind,
            typer.Argument(help='Приложение'),
        ],
    ) -> None:
        async def _run() -> object:
            return await app_manager.restart(kind)

        try:
            info = asyncio.run(
                _log_command(
                    session_logger,
                    'app.restart',
                    project=None,
                    payload={'kind': kind.value},
                    fn=_run,
                ),
            )
        except ApplicationNotInstalledError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        except (ApplicationStartError, ApplicationStopError) as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        typer.echo(f'Restarted {kind.value} (pid={info.pid})')  # type: ignore[attr-defined]

    bridge_app = typer.Typer(no_args_is_help=True, add_completion=False)
    app.add_typer(bridge_app, name='bridge')

    def _exit_on_bridge_error(exc: Exception) -> typer.Exit:
        """Унифицированный маппинг bridge-ошибок в exit-коды."""
        typer.echo(str(exc), err=True)
        if isinstance(exc, ProjectNotFoundError):
            return typer.Exit(code=1)
        return typer.Exit(code=2)

    def _make_tran(
        t_step: str,
        t_stop: str,
        t_start: str,
        *,
        uic: bool,
    ) -> TranAnalysis:
        return TranAnalysis(
            t_step=parse_spice_number(t_step),
            t_stop=parse_spice_number(t_stop),
            t_start=parse_spice_number(t_start),
            uic=uic,
        )

    def _make_ac(
        sweep: str,
        n_points: int,
        f_start: str,
        f_stop: str,
    ) -> AcAnalysis:
        return AcAnalysis(
            sweep=sweep,  # type: ignore[arg-type]
            n_points=n_points,
            f_start=parse_spice_number(f_start),
            f_stop=parse_spice_number(f_stop),
        )

    def _echo_sim_status(sim: Simulation) -> None:
        typer.echo(f'Exported netlist: {sim.netlist_path}')
        if sim.status.value == 'simulated':
            typer.echo('Simulation: completed')
        else:
            typer.echo(
                'Simulation: skipped (ngspice not available — install via '
                '`apt install ngspice` / `brew install ngspice`)',
            )

    # === bridge design-to-netlist (без симуляции) ===

    @bridge_app.command('design-to-netlist')
    def bridge_design_to_netlist(
        project: Annotated[str, typer.Argument(help='Имя проекта')],
        *,
        schematic: Annotated[
            str,
            typer.Option(
                '--schematic',
                help='Путь к .kicad_sch (относительный к проекту либо абсолютный)',
            ),
        ],
        netlist_output: Annotated[
            str | None,
            typer.Option(
                '--netlist-output',
                help='Путь для SPICE netlist (default: <project>/sim/<name>.cir)',
            ),
        ] = None,
    ) -> None:
        async def _run() -> Simulation:
            return await design_to_netlist_use_case(
                project_name=project,
                schematic=Path(schematic),
                netlist_output=(
                    Path(netlist_output) if netlist_output is not None else None
                ),
                repo=metadata_repository,
                manifest_repo=manifest_repository,
                exporter=schematic_exporter,
            )

        try:
            sim = asyncio.run(
                _log_command(
                    session_logger,
                    'bridge.design_to_netlist',
                    project=project,
                    payload={
                        'project': project,
                        'schematic': schematic,
                        'netlist_output': netlist_output,
                    },
                    fn=_run,
                ),
            )
        except (
            ProjectNotFoundError,
            ProjectManifestMissingError,
            SchematicExportError,
        ) as exc:
            raise _exit_on_bridge_error(exc) from exc

        typer.echo(f'Exported netlist: {sim.netlist_path}')

    # === bridge sim-run <op|tran|ac> (только симуляция готового netlist'а) ===

    sim_run_app = typer.Typer(no_args_is_help=True, add_completion=False)
    bridge_app.add_typer(sim_run_app, name='sim-run')

    async def _execute_sim_run(
        netlist: Path,
        analysis: AnalysisSpec,
        timeout_seconds: float,
        event: str,
    ) -> SimulationResult:
        async def _run() -> SimulationResult:
            return await sim_run_use_case(
                netlist=netlist,
                analysis=analysis,
                simulator=simulator,
                timeout_seconds=timeout_seconds,
            )

        return await _log_command(
            session_logger,
            event,
            project=None,
            payload={
                'netlist': str(netlist),
                'analysis': analysis.type,
                'timeout_seconds': timeout_seconds,
            },
            fn=_run,
        )

    def _run_sim_and_report(
        netlist: str,
        analysis: AnalysisSpec,
        timeout_seconds: float,
        event: str,
    ) -> None:
        try:
            asyncio.run(
                _execute_sim_run(
                    Path(netlist),
                    analysis,
                    timeout_seconds,
                    event,
                ),
            )
        except (
            SimulationFailedError,
            SimulatorUnavailableError,
            SpiceNumberFormatError,
            ValidationError,
        ) as exc:
            raise _exit_on_bridge_error(exc) from exc

        typer.echo(f'Simulation: completed (analysis={analysis.type})')

    @sim_run_app.command('op')
    def sim_run_op(
        netlist: Annotated[str, typer.Argument(help='Путь к SPICE netlist')],
        *,
        timeout: Annotated[
            float,
            typer.Option('--timeout', help='Таймаут в секундах (default 60.0)'),
        ] = 60.0,
    ) -> None:
        _run_sim_and_report(
            netlist,
            OpAnalysis(),
            timeout,
            'bridge.sim_run.op',
        )

    @sim_run_app.command('tran')
    def sim_run_tran(
        netlist: Annotated[str, typer.Argument(help='Путь к SPICE netlist')],
        *,
        t_step: Annotated[
            str,
            typer.Option('--t-step', help='Шаг по времени (SPICE-нотация: 1u, 10n)'),
        ],
        t_stop: Annotated[
            str,
            typer.Option('--t-stop', help='Длительность (1m, 20m)'),
        ],
        t_start: Annotated[
            str,
            typer.Option('--t-start', help='Начало записи (default 0)'),
        ] = '0',
        uic: Annotated[
            bool,
            typer.Option('--uic', help='Use Initial Conditions'),
        ] = False,
        timeout: Annotated[
            float,
            typer.Option('--timeout', help='Таймаут в секундах (default 60.0)'),
        ] = 60.0,
    ) -> None:
        try:
            analysis = _make_tran(t_step, t_stop, t_start, uic=uic)
        except (SpiceNumberFormatError, ValidationError) as exc:
            raise _exit_on_bridge_error(exc) from exc
        _run_sim_and_report(
            netlist,
            analysis,
            timeout,
            'bridge.sim_run.tran',
        )

    @sim_run_app.command('ac')
    def sim_run_ac(
        netlist: Annotated[str, typer.Argument(help='Путь к SPICE netlist')],
        *,
        n_points: Annotated[
            int,
            typer.Option(
                '--n-points', help='Число точек на октаву / декаду / на интервале'
            ),
        ],
        f_start: Annotated[
            str,
            typer.Option('--f-start', help='Начальная частота (1, 10, 100)'),
        ],
        f_stop: Annotated[
            str,
            typer.Option('--f-stop', help='Конечная частота (1Meg, 100k)'),
        ],
        sweep: Annotated[
            str,
            typer.Option(
                '--sweep',
                help='Тип развёртки: dec / lin / oct (default dec)',
            ),
        ] = 'dec',
        timeout: Annotated[
            float,
            typer.Option('--timeout', help='Таймаут в секундах (default 60.0)'),
        ] = 60.0,
    ) -> None:
        try:
            analysis = _make_ac(sweep, n_points, f_start, f_stop)
        except (SpiceNumberFormatError, ValidationError) as exc:
            raise _exit_on_bridge_error(exc) from exc
        _run_sim_and_report(
            netlist,
            analysis,
            timeout,
            'bridge.sim_run.ac',
        )

    # === bridge design-to-sim <op|tran|ac> (композиция export + sim) ===

    design_to_sim_app = typer.Typer(no_args_is_help=True, add_completion=False)
    bridge_app.add_typer(design_to_sim_app, name='design-to-sim')

    async def _execute_design_to_sim(
        project: str,
        schematic: str,
        netlist_output: str | None,
        analysis: AnalysisSpec,
        timeout_seconds: float,
        event: str,
    ) -> Simulation:
        async def _run() -> Simulation:
            return await design_to_sim_use_case(
                project_name=project,
                schematic=Path(schematic),
                analysis=analysis,
                netlist_output=(
                    Path(netlist_output) if netlist_output is not None else None
                ),
                timeout_seconds=timeout_seconds,
                repo=metadata_repository,
                manifest_repo=manifest_repository,
                exporter=schematic_exporter,
                simulator=simulator,
            )

        return await _log_command(
            session_logger,
            event,
            project=project,
            payload={
                'project': project,
                'schematic': schematic,
                'netlist_output': netlist_output,
                'analysis': analysis.type,
                'timeout_seconds': timeout_seconds,
            },
            fn=_run,
        )

    def _run_dts_and_report(
        project: str,
        schematic: str,
        netlist_output: str | None,
        analysis: AnalysisSpec,
        timeout_seconds: float,
        event: str,
    ) -> None:
        try:
            sim = asyncio.run(
                _execute_design_to_sim(
                    project,
                    schematic,
                    netlist_output,
                    analysis,
                    timeout_seconds,
                    event,
                ),
            )
        except (
            ProjectNotFoundError,
            ProjectManifestMissingError,
            SchematicExportError,
            SimulationFailedError,
            SpiceNumberFormatError,
            ValidationError,
        ) as exc:
            raise _exit_on_bridge_error(exc) from exc

        _echo_sim_status(sim)

    @design_to_sim_app.command('op')
    def dts_op(
        project: Annotated[str, typer.Argument(help='Имя проекта')],
        *,
        schematic: Annotated[
            str,
            typer.Option('--schematic', help='Путь к .kicad_sch'),
        ],
        netlist_output: Annotated[
            str | None,
            typer.Option('--netlist-output', help='Путь для SPICE netlist'),
        ] = None,
        timeout: Annotated[
            float,
            typer.Option('--timeout', help='Таймаут в секундах (default 60.0)'),
        ] = 60.0,
    ) -> None:
        _run_dts_and_report(
            project,
            schematic,
            netlist_output,
            OpAnalysis(),
            timeout,
            'bridge.design_to_sim.op',
        )

    @design_to_sim_app.command('tran')
    def dts_tran(
        project: Annotated[str, typer.Argument(help='Имя проекта')],
        *,
        schematic: Annotated[
            str,
            typer.Option('--schematic', help='Путь к .kicad_sch'),
        ],
        t_step: Annotated[str, typer.Option('--t-step')],
        t_stop: Annotated[str, typer.Option('--t-stop')],
        t_start: Annotated[str, typer.Option('--t-start')] = '0',
        uic: Annotated[bool, typer.Option('--uic')] = False,
        netlist_output: Annotated[
            str | None,
            typer.Option('--netlist-output'),
        ] = None,
        timeout: Annotated[
            float,
            typer.Option('--timeout'),
        ] = 60.0,
    ) -> None:
        try:
            analysis = _make_tran(t_step, t_stop, t_start, uic=uic)
        except (SpiceNumberFormatError, ValidationError) as exc:
            raise _exit_on_bridge_error(exc) from exc
        _run_dts_and_report(
            project,
            schematic,
            netlist_output,
            analysis,
            timeout,
            'bridge.design_to_sim.tran',
        )

    @design_to_sim_app.command('ac')
    def dts_ac(
        project: Annotated[str, typer.Argument(help='Имя проекта')],
        *,
        schematic: Annotated[
            str,
            typer.Option('--schematic', help='Путь к .kicad_sch'),
        ],
        n_points: Annotated[int, typer.Option('--n-points')],
        f_start: Annotated[str, typer.Option('--f-start')],
        f_stop: Annotated[str, typer.Option('--f-stop')],
        sweep: Annotated[str, typer.Option('--sweep')] = 'dec',
        netlist_output: Annotated[
            str | None,
            typer.Option('--netlist-output'),
        ] = None,
        timeout: Annotated[
            float,
            typer.Option('--timeout'),
        ] = 60.0,
    ) -> None:
        try:
            analysis = _make_ac(sweep, n_points, f_start, f_stop)
        except (SpiceNumberFormatError, ValidationError) as exc:
            raise _exit_on_bridge_error(exc) from exc
        _run_dts_and_report(
            project,
            schematic,
            netlist_output,
            analysis,
            timeout,
            'bridge.design_to_sim.ac',
        )

    return app
