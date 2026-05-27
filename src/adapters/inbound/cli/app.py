"""Typer CLI inbound-adapter: команды efactory."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
from pydantic import ValidationError

from adapters.inbound.cli.plot_renderer import (
    render_ac_sweep,
    render_time_series,
)
from adapters.inbound.cli.spice_units import (
    SpiceNumberFormatError,
    parse_spice_number,
)
from adapters.inbound.cli.template_materializer import (
    TemplateConflictError,
    TemplateNotFoundError,
    list_templates,
    materialize_template,
)
from application.add_decision import add_decision as add_decision_use_case
from application.bridge_sweep import SweepRun, bridge_sweep
from application.create_project import create_project as create_project_use_case
from application.delete_project import delete_project as delete_project_use_case
from application.design_to_netlist import (
    design_to_netlist as design_to_netlist_use_case,
)
from application.design_to_sim import design_to_sim as design_to_sim_use_case
from application.edit_component_model import edit_component_model
from application.edit_component_value import (
    ComponentNotFoundError,
    MultipleMatchesError,
    edit_component_value,
)
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
from application.measure_bandwidth import (
    measure_bandwidth as measure_bandwidth_use_case,
)
from application.measure_gain import measure_gain as measure_gain_use_case
from application.measure_thd import measure_thd as measure_thd_use_case
from application.reindex_projects import (
    reindex_projects as reindex_projects_use_case,
)
from application.schematic_snapshot import SchematicSnapshot
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
    from domain.measurement import (
        BandwidthMeasurement,
        GainMeasurement,
        ThdMeasurement,
    )
    from domain.project import Project
    from domain.simulation import AnalysisSpec, Simulation, SimulationResult
    from domain.spice_model import SpiceModel
    from ports.outbound.app_manager import AppManager, RunResult
    from ports.outbound.decision_repository import DecisionRepository
    from ports.outbound.git_repository import GitRepository
    from ports.outbound.metadata_repository import MetadataRepository
    from ports.outbound.netlist_editor import NetlistEditor
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


def _emit_gain(result: GainMeasurement, *, output_fmt: str) -> None:
    if output_fmt == 'json':
        typer.echo(result.model_dump_json(indent=2))
        return
    typer.echo(
        f'Gain: {result.value_db:.2f} dB '
        f'(x{result.value_linear:.4g}) @ {result.frequency_hz:.0f} Hz '
        f'[mode={result.mode}, in={result.input_signal}, out={result.output_signal}]',
    )


def _emit_bandwidth(result: BandwidthMeasurement, *, output_fmt: str) -> None:
    if output_fmt == 'json':
        typer.echo(result.model_dump_json(indent=2))
        return
    typer.echo(
        f'Bandwidth: {result.f_low_hz:.1f} Hz … {result.f_high_hz:.1f} Hz '
        f'({result.bandwidth_hz:.1f} Hz @ {result.ref_db:+.1f} dB, '
        f'midpoint={result.midpoint_db:.2f} dB '
        f'[{result.midpoint_source}])',
    )


def _prepare_ac_netlist(
    *,
    netlist_path: Path,
    netlist_editor: NetlistEditor,
    explicit_source: str | None,
) -> Path:
    """
    Inject `AC 1` modifier на V-source перед AC analysis.

    Если netlist уже содержит `AC <mag>` — ensure_ac_modifier no-op'нет.
    Возвращает путь к prepared netlist (либо tmp, либо original если
    в netlist'е нет V-source — без injection).
    """
    base_text = netlist_path.read_text()
    if explicit_source is not None:
        source_ref: str | None = explicit_source
    else:
        sources = netlist_editor.find_top_level_v_sources(base_text)
        if len(sources) == 1:
            source_ref = sources[0]
        elif len(sources) == 0:
            source_ref = None
        else:
            candidates = ', '.join(sources)
            msg = (
                f'multiple V-sources in netlist ({candidates}); '
                f'pass --input-source explicitly.'
            )
            raise ValueError(msg)
    if source_ref is None:
        return netlist_path
    prepared = netlist_editor.ensure_ac_modifier(
        base_text,
        source_ref=source_ref,
        ac_magnitude=1.0,
    )
    tmp_netlist = netlist_path.with_suffix('.tmp_plot.cir')
    tmp_netlist.write_text(prepared)
    return tmp_netlist


def _emit_thd(result: ThdMeasurement, *, output_fmt: str) -> None:
    if output_fmt == 'json':
        typer.echo(result.model_dump_json(indent=2))
        return
    typer.echo(
        f'THD: {result.thd_percent:.3f}% @ {result.fundamental_hz:.0f} Hz '
        f'(v_in_peak={result.v_in_peak:.4g} V, '
        f'P_out={result.measured_power_w * 1000:.2f} mW, '
        f'dominant n={result.dominant_harmonic_n} '
        f'@ {result.dominant_harmonic_percent:.3f}%)',
    )


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
    netlist_editor: NetlistEditor,
) -> typer.Typer:
    app = typer.Typer(no_args_is_help=True, add_completion=False)
    project_app = typer.Typer(no_args_is_help=True, add_completion=False)
    app.add_typer(project_app, name='project')

    @project_app.command('create')
    def create(
        name: str = typer.Option(..., '--name', help='Имя нового проекта'),
        template: str | None = typer.Option(
            None,
            '--template',
            help=(
                f'Шаблон проекта. Доступно: {", ".join(list_templates()) or "(none)"}.'
            ),
        ),
        target_dir: Path | None = typer.Option(
            None,
            '--target-dir',
            help=(
                'Override корневого каталога для этой инвокации '
                '(по умолчанию — settings.projects_root '
                'из EFACTORY_PROJECTS_ROOT).'
            ),
        ),
    ) -> None:
        effective_root = target_dir if target_dir is not None else projects_root

        async def _run() -> CreateProjectResult:
            return await create_project_use_case(
                name=name,
                projects_root=effective_root,
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
                    payload={'name': name, 'template': template},
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
        if template is not None:
            try:
                materialize_template(
                    template_name=template,
                    target_dir=project.path,
                    project_name=name,
                )
            except TemplateNotFoundError as exc:
                typer.echo(str(exc), err=True)
                raise typer.Exit(code=2) from exc
            except TemplateConflictError as exc:
                typer.echo(str(exc), err=True)
                raise typer.Exit(code=2) from exc

        if not result.git_initialized:
            asyncio.run(
                session_logger.log_event(
                    'git.init',
                    status=SessionEventStatus.ERROR,
                    project=name,
                    error='git not found on PATH (skipped)',
                ),
            )
        suffix = f' (template: {template})' if template else ''
        typer.echo(
            f'Created project {project.name} at {project.path} '
            f'(id={project.id}){suffix}',
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
        def list_models(
            *,
            source: Annotated[
                str | None,
                typer.Option(
                    '--source',
                    help='Фильтр по ModelSource: koren/ayumi/duncan/custom/generic',
                ),
            ] = None,
            subcategory: Annotated[
                str | None,
                typer.Option(
                    '--subcategory',
                    help='Фильтр по subcategory (T005): triode/pentode/'
                    'rectifier/signal/schottky/opt/speaker/...',
                ),
            ] = None,
        ) -> None:
            async def _run() -> list[SpiceModel]:
                models = await spice_library.list_all()
                filtered = [m for m in models if m.category is category]
                if source is not None:
                    filtered = [m for m in filtered if m.source.value == source]
                if subcategory is not None:
                    filtered = [m for m in filtered if m.subcategory == subcategory]
                return filtered

            models = asyncio.run(
                _log_command(
                    session_logger,
                    f'{name}.list',
                    project=None,
                    payload={'source': source, 'subcategory': subcategory},
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

    @bridge_app.command('edit')
    def bridge_edit(
        project: Annotated[str, typer.Argument(help='Имя проекта')],
        *,
        schematic: Annotated[
            str,
            typer.Option('--schematic', help='Путь к .kicad_sch'),
        ],
        set_: Annotated[
            list[str],
            typer.Option(
                '--set',
                help='REF=VALUE (можно несколько раз) — изменить value '
                'компонента в schematic. Пример: --set R1=10k --set C1=100n',
            ),
        ],
    ) -> None:
        """
        T004b: изменить value-properties компонентов в `.kicad_sch`.

        Использует `application.edit_component_value` (text-based atomic
        replace). T004b Phase 1: multi-edit обёрнут в `SchematicSnapshot`
        — на failure любого edit'а откатывается весь batch. Combined
        edit+resim в Python — через `application.edit_and_resim`.
        """

        async def _resolve_schematic_path() -> Path:
            project_obj = await get_project_use_case(
                name=project,
                repo=metadata_repository,
                manifest_repo=manifest_repository,
            )
            return (project_obj.path / schematic).resolve()

        try:
            schematic_path = asyncio.run(
                _log_command(
                    session_logger,
                    'bridge.edit',
                    project=project,
                    payload={'schematic': schematic, 'set': set_},
                    fn=_resolve_schematic_path,
                ),
            )
        except ProjectNotFoundError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc

        edits: list[tuple[str, str]] = []
        for spec_str in set_:
            if '=' not in spec_str:
                typer.echo(
                    f'--set требует формат REF=VALUE, получено {spec_str!r}',
                    err=True,
                )
                raise typer.Exit(code=2)
            ref, _, val = spec_str.partition('=')
            edits.append((ref.strip(), val.strip()))

        with SchematicSnapshot(schematic_path) as snap:
            for ref, new_value in edits:
                try:
                    old_value = edit_component_value(
                        schematic_path,
                        ref,
                        new_value,
                    )
                except (ComponentNotFoundError, MultipleMatchesError) as exc:
                    typer.echo(str(exc), err=True)
                    typer.echo(
                        "Rollback: предыдущие edit'ы отменены, schematic восстановлен.",
                        err=True,
                    )
                    raise typer.Exit(code=1) from exc
                typer.echo(f'{ref}: {old_value!r} → {new_value!r}')
            snap.commit()

    @bridge_app.command('edit-model')
    def bridge_edit_model(
        project: Annotated[str, typer.Argument(help='Имя проекта')],
        *,
        schematic: Annotated[
            str,
            typer.Option('--schematic', help='Путь к .kicad_sch'),
        ],
        ref: Annotated[
            str,
            typer.Option('--ref', help='Reference компонента (X1, D1, ...)'),
        ],
        model: Annotated[
            str,
            typer.Option('--model', help='ID SPICE-модели (6P14P, 1N4007, ...)'),
        ],
    ) -> None:
        """
        T005 Phase 1: swap SPICE-модели для существующего subckt-компонента.

        Resolve `--model` через SpiceModelLibrary (любая категория —
        tube/diode/transformer/load), затем edit_component_model обновит
        `Value`, `Sim.Library`, `Sim.Name` properties атомарно.
        """

        async def _resolve() -> tuple[Path, SpiceModel]:
            project_obj = await get_project_use_case(
                name=project,
                repo=metadata_repository,
                manifest_repo=manifest_repository,
            )
            sch_path = (project_obj.path / schematic).resolve()
            spice_model = await spice_library.get_by_id(model)
            return sch_path, spice_model

        try:
            schematic_path, spice_model = asyncio.run(
                _log_command(
                    session_logger,
                    'bridge.edit_model',
                    project=project,
                    payload={
                        'schematic': schematic,
                        'ref': ref,
                        'model': model,
                    },
                    fn=_resolve,
                ),
            )
        except ProjectNotFoundError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        except SpiceModelNotFoundError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc

        try:
            old_values = edit_component_model(
                schematic_path,
                ref,
                spice_model,
            )
        except (ComponentNotFoundError, MultipleMatchesError) as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        for prop_name, old_value in old_values.items():
            typer.echo(f'  {prop_name}: {old_value!r} → ...')
        typer.echo(f'{ref}: model swap → {spice_model.id}')

    @bridge_app.command('sweep')
    def bridge_sweep_cli(
        project: Annotated[str, typer.Argument(help='Имя проекта')],
        *,
        schematic: Annotated[
            str,
            typer.Option('--schematic', help='Путь к .kicad_sch'),
        ],
        param: Annotated[
            list[str],
            typer.Option(
                '--param',
                help='REF=v1,v2,v3 (можно несколько раз). Cartesian '
                'product даёт N комбинаций. Пример: --param R1=1k,10k '
                '--param C1=100n,1u → 4 запуска OP',
            ),
        ],
        netlist_dir: Annotated[
            str | None,
            typer.Option(
                '--netlist-dir',
                help='Папка для netlist debug-файлов (per combination)',
            ),
        ] = None,
        timeout: Annotated[
            float,
            typer.Option('--timeout', help='Per-run timeout (default 60s)'),
        ] = 60.0,
    ) -> None:
        """
        T004b Phase 1: параметрический OP sweep.

        Для каждой combination параметров: копия schematic → apply
        value edits → kicad-cli netlist → ngspice OP. Failure на
        конкретной combination не аборт sweep'а — записывается с
        `error=...`. Output: tabular print parameters + key voltages
        per run. TRAN/AC sweep'ы — Phase 2 backlog T021/T022.
        """
        params_dict: dict[str, list[str]] = {}
        for spec_str in param:
            if '=' not in spec_str:
                typer.echo(
                    f'--param требует REF=v1,v2,..., получено {spec_str!r}',
                    err=True,
                )
                raise typer.Exit(code=2)
            r, _, vals_str = spec_str.partition('=')
            params_dict[r.strip()] = [
                v.strip() for v in vals_str.split(',') if v.strip()
            ]

        async def _resolve_path() -> Path:
            project_obj = await get_project_use_case(
                name=project,
                repo=metadata_repository,
                manifest_repo=manifest_repository,
            )
            return (project_obj.path / schematic).resolve()

        try:
            schematic_path = asyncio.run(_resolve_path())
        except ProjectNotFoundError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc

        nd = Path(netlist_dir).resolve() if netlist_dir else None

        async def _run() -> list[SweepRun]:
            return await bridge_sweep(
                schematic=schematic_path,
                parameters=params_dict,
                analysis=OpAnalysis(),
                exporter=schematic_exporter,
                simulator=simulator,
                netlist_dir=nd,
                timeout_seconds=timeout,
            )

        runs = asyncio.run(
            _log_command(
                session_logger,
                'bridge.sweep',
                project=project,
                payload={'schematic': schematic, 'param': param},
                fn=_run,
            ),
        )
        typer.echo(f'Sweep complete: {len(runs)} combinations.')
        for run in runs:
            params_repr = ' '.join(f'{k}={v}' for k, v in run.parameters.items())
            if run.result is None:
                typer.echo(f'  [{params_repr}]  FAILED: {run.error}')
                continue
            op = run.result.operating_points or {}
            op_repr = ' '.join(f'{k}={v:.4g}' for k, v in sorted(op.items()))
            typer.echo(f'  [{params_repr}]  {op_repr}')

    # === bridge measure <gain|bandwidth|thd> (T023 Phase C) ===

    measure_app = typer.Typer(no_args_is_help=True, add_completion=False)
    bridge_app.add_typer(measure_app, name='measure')

    @measure_app.command('gain')
    def measure_gain_cmd(
        netlist: Annotated[str, typer.Argument(help='Путь к SPICE netlist (.cir)')],
        *,
        freq: Annotated[
            str,
            typer.Option('--freq', help='Частота измерения (1k, 100, 10Meg)'),
        ],
        mode: Annotated[
            str,
            typer.Option('--mode', help='small (AC analysis) | large (TRAN RMS)'),
        ] = 'small',
        v_in_peak: Annotated[
            float | None,
            typer.Option(
                '--v-in-peak',
                help='Peak amplitude входа (V), обязательно для --mode large',
            ),
        ] = None,
        input_source: Annotated[
            str | None,
            typer.Option(
                '--input-source',
                help='V-source ref (auto-detect, если ровно один в netlist)',
            ),
        ] = None,
        input_signal: Annotated[
            str | None,
            typer.Option(
                '--input-signal',
                help='Trace name для VO/RMS (обязательно для --mode large)',
            ),
        ] = None,
        output_signal: Annotated[
            str,
            typer.Option('--output-signal', help='Trace для измерения'),
        ] = 'v(load)',
        output: Annotated[
            str,
            typer.Option('--output', help='Формат: text (default) | json'),
        ] = 'text',
        timeout: Annotated[
            float,
            typer.Option('--timeout', help='Таймаут в секундах (default 60.0)'),
        ] = 60.0,
    ) -> None:
        if mode not in ('small', 'large'):
            typer.echo(f'Invalid --mode: {mode!r}; expected small|large', err=True)
            raise typer.Exit(code=2)
        try:
            freq_hz = parse_spice_number(freq)
        except SpiceNumberFormatError as exc:
            raise _exit_on_bridge_error(exc) from exc

        async def _run() -> GainMeasurement:
            return await measure_gain_use_case(
                netlist=Path(netlist),
                frequency_hz=freq_hz,
                mode=mode,  # type: ignore[arg-type]
                simulator=simulator,
                netlist_editor=netlist_editor,
                output_signal=output_signal,
                input_source=input_source,
                input_signal=input_signal,
                v_in_peak=v_in_peak,
                timeout_seconds=timeout,
            )

        try:
            result = asyncio.run(
                _log_command(
                    session_logger,
                    'bridge.measure.gain',
                    project=None,
                    payload={
                        'netlist': netlist,
                        'freq_hz': freq_hz,
                        'mode': mode,
                    },
                    fn=_run,
                ),
            )
        except (
            SimulationFailedError,
            SimulatorUnavailableError,
            SpiceNumberFormatError,
            ValidationError,
            ValueError,
        ) as exc:
            raise _exit_on_bridge_error(exc) from exc

        _emit_gain(result, output_fmt=output)

    @measure_app.command('bandwidth')
    def measure_bandwidth_cmd(
        netlist: Annotated[str, typer.Argument(help='Путь к SPICE netlist (.cir)')],
        *,
        f_low: Annotated[
            str,
            typer.Option('--f-low', help='Нижняя граница sweep (default 1)'),
        ] = '1',
        f_high: Annotated[
            str,
            typer.Option('--f-high', help='Верхняя граница sweep (default 1Meg)'),
        ] = '1Meg',
        n_points_per_decade: Annotated[
            int,
            typer.Option('--n-points-per-decade', help='Разрешение (default 10)'),
        ] = 10,
        ref_db: Annotated[
            float,
            typer.Option('--ref-db', help='Reference dB (default -3)'),
        ] = -3.0,
        midpoint_source: Annotated[
            str,
            typer.Option(
                '--midpoint-source',
                help='auto (max|H|) | ref_freq (|H(ref_freq)|)',
            ),
        ] = 'auto',
        ref_freq: Annotated[
            str | None,
            typer.Option(
                '--ref-freq',
                help='Опорная частота для midpoint_source=ref_freq',
            ),
        ] = None,
        input_source: Annotated[
            str | None,
            typer.Option('--input-source', help='V-source ref (auto-detect)'),
        ] = None,
        output_signal: Annotated[
            str,
            typer.Option('--output-signal', help='Trace для измерения'),
        ] = 'v(load)',
        output: Annotated[
            str,
            typer.Option('--output', help='Формат: text (default) | json'),
        ] = 'text',
        timeout: Annotated[
            float,
            typer.Option('--timeout', help='Таймаут в секундах (default 60.0)'),
        ] = 60.0,
    ) -> None:
        if midpoint_source not in ('auto', 'ref_freq'):
            typer.echo(
                f'Invalid --midpoint-source: {midpoint_source!r}; '
                f'expected auto|ref_freq',
                err=True,
            )
            raise typer.Exit(code=2)
        try:
            f_low_hz = parse_spice_number(f_low)
            f_high_hz = parse_spice_number(f_high)
            ref_freq_hz = parse_spice_number(ref_freq) if ref_freq else None
        except SpiceNumberFormatError as exc:
            raise _exit_on_bridge_error(exc) from exc

        async def _run() -> BandwidthMeasurement:
            return await measure_bandwidth_use_case(
                netlist=Path(netlist),
                simulator=simulator,
                netlist_editor=netlist_editor,
                f_low=f_low_hz,
                f_high=f_high_hz,
                n_points_per_decade=n_points_per_decade,
                output_signal=output_signal,
                input_source=input_source,
                ref_db=ref_db,
                midpoint_source=midpoint_source,  # type: ignore[arg-type]
                ref_freq_hz=ref_freq_hz,
                timeout_seconds=timeout,
            )

        try:
            result = asyncio.run(
                _log_command(
                    session_logger,
                    'bridge.measure.bandwidth',
                    project=None,
                    payload={
                        'netlist': netlist,
                        'f_low_hz': f_low_hz,
                        'f_high_hz': f_high_hz,
                        'ref_db': ref_db,
                    },
                    fn=_run,
                ),
            )
        except (
            SimulationFailedError,
            SimulatorUnavailableError,
            SpiceNumberFormatError,
            ValidationError,
            ValueError,
        ) as exc:
            raise _exit_on_bridge_error(exc) from exc

        _emit_bandwidth(result, output_fmt=output)

    @measure_app.command('thd')
    def measure_thd_cmd(
        netlist: Annotated[str, typer.Argument(help='Путь к SPICE netlist (.cir)')],
        *,
        freq: Annotated[
            str,
            typer.Option('--freq', help='Fundamental частота (1k, 100)'),
        ],
        v_in_peak: Annotated[
            float,
            typer.Option('--v-in-peak', help='Peak amplitude входа (V)'),
        ],
        input_source: Annotated[
            str | None,
            typer.Option('--input-source', help='V-source ref (auto-detect)'),
        ] = None,
        signal: Annotated[
            str,
            typer.Option('--signal', help='Trace для Fourier (default v(load))'),
        ] = 'v(load)',
        load_ohm: Annotated[
            float,
            typer.Option('--load-ohm', help='Нагрузка для measured_power'),
        ] = 8.0,
        n_harmonics: Annotated[
            int,
            typer.Option('--n-harmonics', help='Число гармоник (3..20)'),
        ] = 10,
        output: Annotated[
            str,
            typer.Option('--output', help='Формат: text (default) | json'),
        ] = 'text',
        timeout: Annotated[
            float,
            typer.Option('--timeout', help='Таймаут в секундах (default 60.0)'),
        ] = 60.0,
    ) -> None:
        try:
            freq_hz = parse_spice_number(freq)
        except SpiceNumberFormatError as exc:
            raise _exit_on_bridge_error(exc) from exc

        async def _run() -> ThdMeasurement:
            return await measure_thd_use_case(
                netlist=Path(netlist),
                frequency_hz=freq_hz,
                v_in_peak=v_in_peak,
                simulator=simulator,
                netlist_editor=netlist_editor,
                signal=signal,
                input_source=input_source,
                load_ohm=load_ohm,
                n_harmonics=n_harmonics,
                timeout_seconds=timeout,
            )

        try:
            result = asyncio.run(
                _log_command(
                    session_logger,
                    'bridge.measure.thd',
                    project=None,
                    payload={
                        'netlist': netlist,
                        'freq_hz': freq_hz,
                        'v_in_peak': v_in_peak,
                    },
                    fn=_run,
                ),
            )
        except (
            SimulationFailedError,
            SimulatorUnavailableError,
            SpiceNumberFormatError,
            ValidationError,
            ValueError,
        ) as exc:
            raise _exit_on_bridge_error(exc) from exc

        _emit_thd(result, output_fmt=output)

    # === bridge plot <ac|tran> (ASCII chart, T024) ===

    plot_app = typer.Typer(no_args_is_help=True, add_completion=False)
    bridge_app.add_typer(plot_app, name='plot')

    @plot_app.command('ac')
    def plot_ac_cmd(
        netlist: Annotated[str, typer.Argument(help='Путь к SPICE netlist (.cir)')],
        *,
        signal: Annotated[
            str,
            typer.Option('--signal', help='Trace для отрисовки (default v(load))'),
        ] = 'v(load)',
        input_source: Annotated[
            str | None,
            typer.Option('--input-source', help='V-source ref (auto-detect)'),
        ] = None,
        f_start: Annotated[
            str,
            typer.Option('--f-start', help='Начальная частота (default 1)'),
        ] = '1',
        f_stop: Annotated[
            str,
            typer.Option('--f-stop', help='Конечная частота (default 1Meg)'),
        ] = '1Meg',
        n_points: Annotated[
            int,
            typer.Option('--n-points', help='Точек на декаду (default 10)'),
        ] = 10,
        sweep: Annotated[
            str,
            typer.Option('--sweep', help='dec | lin | oct (default dec)'),
        ] = 'dec',
        width: Annotated[
            int,
            typer.Option('--width', help='Ширина графика в символах'),
        ] = 80,
        height: Annotated[
            int,
            typer.Option('--height', help='Высота графика в строках'),
        ] = 20,
        timeout: Annotated[
            float,
            typer.Option('--timeout', help='Таймаут в секундах (default 60.0)'),
        ] = 60.0,
    ) -> None:
        try:
            analysis = _make_ac(sweep, n_points, f_start, f_stop)
        except (SpiceNumberFormatError, ValidationError) as exc:
            raise _exit_on_bridge_error(exc) from exc

        # AC analysis требует AC modifier на V-source'е, иначе ngspice
        # видит AC=0 и магнитуда везде 0 → -inf dB (T024 follow-up fix).
        netlist_path = Path(netlist)
        try:
            prepared_netlist_path = _prepare_ac_netlist(
                netlist_path=netlist_path,
                netlist_editor=netlist_editor,
                explicit_source=input_source,
            )
        except ValueError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc

        async def _run() -> SimulationResult:
            return await sim_run_use_case(
                netlist=prepared_netlist_path,
                analysis=analysis,
                simulator=simulator,
                timeout_seconds=timeout,
            )

        try:
            result = asyncio.run(
                _log_command(
                    session_logger,
                    'bridge.plot.ac',
                    project=None,
                    payload={'netlist': netlist, 'signal': signal},
                    fn=_run,
                ),
            )
        except (
            SimulationFailedError,
            SimulatorUnavailableError,
            SpiceNumberFormatError,
            ValidationError,
        ) as exc:
            raise _exit_on_bridge_error(exc) from exc

        if result.ac_sweep is None:
            typer.echo('Simulator returned no ac_sweep result.', err=True)
            raise typer.Exit(code=2)
        try:
            chart = render_ac_sweep(
                result.ac_sweep,
                signal=signal,
                width=width,
                height=height,
            )
        except ValueError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        typer.echo(chart)

    @plot_app.command('tran')
    def plot_tran_cmd(
        netlist: Annotated[str, typer.Argument(help='Путь к SPICE netlist (.cir)')],
        *,
        signal: Annotated[
            str,
            typer.Option('--signal', help='Trace для отрисовки (default v(load))'),
        ] = 'v(load)',
        t_step: Annotated[
            str,
            typer.Option('--t-step', help='Шаг по времени (1u, 10n)'),
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
        width: Annotated[
            int,
            typer.Option('--width', help='Ширина графика в символах'),
        ] = 80,
        height: Annotated[
            int,
            typer.Option('--height', help='Высота графика в строках'),
        ] = 20,
        timeout: Annotated[
            float,
            typer.Option('--timeout', help='Таймаут в секундах (default 60.0)'),
        ] = 60.0,
    ) -> None:
        try:
            analysis = _make_tran(t_step, t_stop, t_start, uic=uic)
        except (SpiceNumberFormatError, ValidationError) as exc:
            raise _exit_on_bridge_error(exc) from exc

        async def _run() -> SimulationResult:
            return await sim_run_use_case(
                netlist=Path(netlist),
                analysis=analysis,
                simulator=simulator,
                timeout_seconds=timeout,
            )

        try:
            result = asyncio.run(
                _log_command(
                    session_logger,
                    'bridge.plot.tran',
                    project=None,
                    payload={'netlist': netlist, 'signal': signal},
                    fn=_run,
                ),
            )
        except (
            SimulationFailedError,
            SimulatorUnavailableError,
            SpiceNumberFormatError,
            ValidationError,
        ) as exc:
            raise _exit_on_bridge_error(exc) from exc

        if result.time_series is None:
            typer.echo('Simulator returned no time_series result.', err=True)
            raise typer.Exit(code=2)
        try:
            chart = render_time_series(
                result.time_series,
                signal=signal,
                width=width,
                height=height,
            )
        except ValueError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc
        typer.echo(chart)

    return app
