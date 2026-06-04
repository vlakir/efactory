"""Typer CLI inbound-adapter: команды efactory."""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
from pydantic import ValidationError

from adapters.inbound.cli.edit_and_resim_renderer import (
    render_edit_and_resim_json,
    render_edit_and_resim_text,
)
from adapters.inbound.cli.plot_renderer import (
    render_ac_sweep,
    render_ac_sweep_png,
    render_sweep_plot,
    render_time_series,
    render_time_series_png,
)
from adapters.inbound.cli.spice_units import (
    SpiceNumberFormatError,
    parse_spice_number,
)
from adapters.inbound.cli.sweep_table_renderer import (
    render_sweep_csv,
    render_sweep_json,
    render_sweep_text,
)
from adapters.inbound.cli.template_materializer import (
    TemplateConflictError,
    TemplateNotFoundError,
    describe_templates,
    list_templates,
    materialize_template,
)
from application.add_decision import add_decision as add_decision_use_case
from application.apply_staged_schematic import (
    ApplyStagedOutcome,
    SkippedStagedEntry,
)
from application.apply_staged_schematic import (
    apply_staged_schematic as apply_staged_schematic_use_case,
)
from application.bridge_sweep import (
    MAX_COMBINATIONS_DEFAULT,
    SOFT_WARN_COMBINATIONS,
    SweepConfig,
    SweepRun,
    bridge_sweep,
)
from application.create_project import create_project as create_project_use_case
from application.create_template_from_project import (
    CreateTemplateError,
    CreateTemplateRequest,
    create_template_from_project,
)
from application.delete_project import delete_project as delete_project_use_case
from application.design_to_netlist import (
    design_to_netlist as design_to_netlist_use_case,
)
from application.design_to_sim import design_to_sim as design_to_sim_use_case
from application.edit_and_resim_with_delta import (
    SOFT_WARN_EDITS,
    BaselineFailedError,
    EditAndResimConfig,
    EditAndResimReport,
    edit_and_resim_with_delta,
)
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
from application.fit_tube_from_points import (
    FitTubeFromPointsRequest,
    FitTubeFromPointsResult,
    FitTubeUseCaseError,
    fit_tube_from_points,
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
from application.measure_phase_margin import (
    measure_phase_margin as measure_phase_margin_use_case,
)
from application.measure_thd import measure_thd as measure_thd_use_case
from application.prune_sim_results import (
    PruneOptionsInvalidError,
)
from application.prune_sim_results import (
    prune_sim_results as prune_sim_results_use_case,
)
from application.reindex_projects import (
    reindex_projects as reindex_projects_use_case,
)
from application.run_erc_check import run_erc_check
from application.schematic_snapshot import SchematicSnapshot
from application.sim_run import sim_run as sim_run_use_case
from application.update_project import (
    PhaseUpdate,
    UpdateProjectCommand,
)
from application.update_project import (
    update_project as update_project_use_case,
)
from application.validate_lib import validate_lib
from domain.application import ApplicationKind
from domain.decision import DecisionStatus
from domain.erc import (
    ErcErrorsFoundError,
    ErcParseError,
    ErcTimeoutError,
    KiCadCliUnavailableError,
    SchematicParseError,
)
from domain.knowledge_base import KbConflictError, KbEntry, KbParseError
from domain.phase import PhaseName, PhaseStatus
from domain.phase_margin import (
    AutoDetectConfidenceTooLowError,
    AutoDetectInfo,
    AutoDetectRejectedError,
    LoopBreakNodeNotFoundError,
    LoopGainAlwaysAboveUnityError,
    NoFeedbackLoopDetectedError,
    NoUnityGainCrossoverError,
)
from domain.phase_margin_injection import (
    InjectionStrategy,
    MiddlebrookCurrentStrategy,
    MiddlebrookVoltageStrategy,
    RosenstarkReturnRatioStrategy,
    TianStrategy,
)
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
from ports.outbound.schematic_renderer import SchematicRenderError
from ports.outbound.session_logger import SessionEventStatus
from ports.outbound.simulator import (
    SimulationFailedError,
    SimulatorUnavailableError,
)
from ports.outbound.spice_model_library import SpiceModelNotFoundError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Generator

    from application.create_project import CreateProjectResult
    from application.reindex_projects import ReindexSummary
    from domain.decision import Decision
    from domain.erc import ErcReport
    from domain.injection_patcher import InjectionNetlistPatcher
    from domain.measurement import (
        BandwidthMeasurement,
        GainMeasurement,
        ThdMeasurement,
    )
    from domain.phase_margin import (
        ConfirmationCallback,
        PhaseMarginMeasurement,
    )
    from domain.project import Project
    from domain.simulation import AnalysisSpec, Simulation, SimulationResult
    from domain.spice_model import SpiceModel
    from ports.outbound.app_manager import AppManager, RunResult
    from ports.outbound.decision_repository import DecisionRepository
    from ports.outbound.erc import ErcReportWriter, ErcRunner
    from ports.outbound.git_repository import GitRepository
    from ports.outbound.knowledge_base import KbStore
    from ports.outbound.netlist_editor import NetlistEditor
    from ports.outbound.project_file_repository import ProjectFileRepository
    from ports.outbound.project_manifest_repository import (
        ProjectManifestRepository,
    )
    from ports.outbound.schematic_exporter import SchematicExporter
    from ports.outbound.schematic_renderer import SchematicRender, SchematicRenderer
    from ports.outbound.session_logger import SessionLogger
    from ports.outbound.sim_results import SimResultsRepository
    from ports.outbound.simulator import Simulator
    from ports.outbound.spice_model_library import SpiceModelLibrary
    from ports.outbound.staged_schematics import (
        LockDetector,
        PendingStagedScanner,
    )
    from ports.outbound.tube_iv_repository import TubeIVRepository
    from ports.outbound.tube_lib_writer import TubeLibWriter


# Per-metric Y-field default для --plot (sweep): какую колонку
# строим по умолчанию. `op` → None (требует явный --plot-y).
_DEFAULT_PLOT_Y: dict[str, str] = {
    'gain': 'gain_db',
    'bandwidth': 'bandwidth_hz',
    'thd': 'thd_percent',
}

# Max params для sweep plot (1 → single line, 2 → multi-line group_by,
# >2 → plot disabled).
_PLOT_MAX_PARAMS = 2


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


@contextlib.contextmanager
def _prepare_ac_netlist(
    *,
    netlist_path: Path,
    netlist_editor: NetlistEditor,
    explicit_source: str | None,
) -> Generator[Path]:
    """
    Inject `AC 1` modifier на V-source перед AC analysis (context manager).

    Yields путь к prepared netlist: либо original (если V-source нет —
    injection не требуется), либо tmp file в `TemporaryDirectory`,
    который cleanup-ится на выходе из `with` (T165).

    Если netlist уже содержит `AC <mag>` — ensure_ac_modifier no-op'нет.
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
        yield netlist_path
        return
    prepared = netlist_editor.ensure_ac_modifier(
        base_text,
        source_ref=source_ref,
        ac_magnitude=1.0,
    )
    with tempfile.TemporaryDirectory(prefix='efactory-plot-') as tmp_dir:
        tmp_netlist = Path(tmp_dir) / f'{netlist_path.stem}.tmp_plot.cir'
        tmp_netlist.write_text(prepared)
        yield tmp_netlist


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


def _emit_phase_margin(
    result: PhaseMarginMeasurement,
    *,
    output_fmt: str,
) -> None:
    if output_fmt == 'json':
        typer.echo(result.model_dump_json(indent=2))
        return
    typer.echo(
        f'Phase margin: {result.margin_deg:.2f}° @ '
        f'{result.crossover_hz:.2f} Hz '
        f'[{result.stability_class}, method={result.injection_method}, '
        f'node={result.measured_at_node}]',
    )
    if result.auto_detect_info is not None:
        info = result.auto_detect_info
        typer.echo(
            f'  auto-detect: node={info.chosen_node!r}, '
            f'element={info.chosen_element_ref!r}, '
            f'confidence={info.confidence * 100:.1f}%',
        )
    if result.extra_crossovers_hz:
        extras = ', '.join(f'{f:.2f}' for f in result.extra_crossovers_hz)
        typer.echo(f'  extra crossovers (Hz): {extras}', err=True)


# Spec §3 «Loop break»: CLI string ↔ InjectionMethod Literal в domain.
_INJECTION_STRATEGY_BUILDERS: dict[
    str,
    Callable[[InjectionNetlistPatcher], InjectionStrategy],
] = {
    'middlebrook-voltage': MiddlebrookVoltageStrategy,
    'middlebrook-current': MiddlebrookCurrentStrategy,
    'tian': TianStrategy,
    'rosenstark-return-ratio': RosenstarkReturnRatioStrategy,
}


def _make_confirmation_callback(
    *,
    no_confirm: bool,
    confidence_threshold: float,
) -> ConfirmationCallback:
    """
    Собрать callback для `measure_phase_margin` auto-detect path.

    Policy (Spec §3 «Loop break» C4):
    * confidence < threshold → reject (AutoDetectRejectedError).
    * non-TTY ИЛИ --no-confirm → accept выше threshold.
    * interactive TTY → typer.confirm prompt с default=True.
    """

    def callback(info: AutoDetectInfo) -> bool:
        if info.confidence < confidence_threshold:
            return False
        if no_confirm or not sys.stdin.isatty():
            return True
        typer.echo(
            f'Auto-detected feedback break: '
            f'node={info.chosen_node!r}, '
            f'element={info.chosen_element_ref!r} '
            f'(confidence {info.confidence * 100:.1f}%).',
        )
        return typer.confirm('Continue with this break edge?', default=True)

    return callback


async def render_and_announce_schematic(
    renderer: SchematicRenderer,
    schematic: Path,
    project_root: Path,
) -> SchematicRender | None:
    """
    T025: render `<schematic>` → PNG/SVG в `<project>/.efactory/renders/<TS>/`.

    Печатает строку `schematic-render: <abs path>` в stdout по одной на
    каждый PNG (multi-sheet → несколько строк). Fail-soft: при
    `SchematicRenderError` пишет warning в stderr и возвращает None —
    основной pipeline (`project create` / `bridge design-to-sim`)
    продолжается.
    """
    out_root = project_root / '.efactory' / 'renders'
    try:
        render = await renderer.render(schematic, out_root)
    except SchematicRenderError as exc:
        typer.echo(f'Warning: schematic render failed: {exc}', err=True)
        return None
    for png in render.png_paths:
        typer.echo(f'schematic-render: {png}')
    return render


def build_app(
    *,
    projects_root: Path,
    file_repository: ProjectFileRepository,
    manifest_repository: ProjectManifestRepository,
    decision_repository: DecisionRepository,
    git_repository: GitRepository,
    session_logger: SessionLogger,
    spice_library: SpiceModelLibrary,
    app_manager: AppManager,
    schematic_exporter: SchematicExporter,
    schematic_renderer: SchematicRenderer,
    erc_runner: ErcRunner,
    erc_report_writer: ErcReportWriter,
    simulator: Simulator,
    netlist_editor: NetlistEditor,
    injection_patcher: InjectionNetlistPatcher,
    kb_store: KbStore,
    sim_results_repo: SimResultsRepository,
    lock_detector: LockDetector,
    staged_scanner: PendingStagedScanner,
    tube_iv_repository: TubeIVRepository,
    tube_lib_writer: TubeLibWriter,
    user_templates_root: Path,
) -> typer.Typer:
    app = typer.Typer(no_args_is_help=True, add_completion=False)
    project_app = typer.Typer(no_args_is_help=True, add_completion=False)
    app.add_typer(project_app, name='project')
    schematic_app = typer.Typer(no_args_is_help=True, add_completion=False)
    app.add_typer(schematic_app, name='schematic')

    async def _render_and_announce_schematic(
        schematic: Path,
        project_root: Path,
    ) -> SchematicRender | None:
        return await render_and_announce_schematic(
            schematic_renderer,
            schematic,
            project_root,
        )

    def _emit_pending_staged_warning(project_root: Path) -> None:
        """T026: предупредить о pending `.kicad_sch.staged` без блокировки."""
        if not project_root.is_dir():
            return
        entries = staged_scanner.scan(project_root)
        if not entries:
            return
        typer.echo(
            f'schematic-staged-pending: {len(entries)} file(s) in '
            f'{project_root} — apply via `efactory schematic apply-staged '
            f'<project>` or `/schematic-apply`.',
            err=True,
        )
        for entry in entries:
            typer.echo(f'  staged: {entry.staged_path}', err=True)

    def _count_pending_staged(project_root: Path) -> int:
        if not project_root.is_dir():
            return 0
        return len(staged_scanner.scan(project_root))

    @project_app.command('create')
    def create(
        name: str = typer.Option(..., '--name', help='Имя нового проекта'),
        template: str | None = typer.Option(
            None,
            '--template',
            help=(
                'Шаблон проекта. Доступно: '
                f'{", ".join(list_templates(user_templates_root)) or "(none)"}.'
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
                    user_overlay_root=user_templates_root,
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
        if template is not None:
            schematic_files = sorted(project.path.glob('*.kicad_sch'))
            if schematic_files:
                asyncio.run(
                    _render_and_announce_schematic(
                        schematic_files[0],
                        project.path,
                    ),
                )

    @project_app.command('list-templates')
    def list_templates_command(
        *,
        as_json: Annotated[
            bool,
            typer.Option('--json', help='Output as JSON array.'),
        ] = False,
    ) -> None:
        """
        Список доступных project templates.

        Data-driven из ``data/templates/*/template.yaml`` (T027 Phase E).
        """
        templates = describe_templates(user_templates_root)
        if as_json:
            typer.echo(json.dumps(templates, indent=2, ensure_ascii=False))
            return
        if not templates:
            typer.echo('No templates found.')
            return
        # Human-readable table: name + summary, aligned.
        max_name_len = max(len(t['name']) for t in templates)
        for tpl in templates:
            name = tpl['name'].ljust(max_name_len)
            summary = tpl['summary'] or '(no summary)'
            typer.echo(f'{name}  {summary}')

    @project_app.command('list')
    def list_() -> None:
        async def _run() -> list:
            return await list_projects_use_case(
                projects_root=projects_root,
                manifest_repo=manifest_repository,
            )

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
            pending = _count_pending_staged(project.path)
            pending_marker = f'\t[{pending} pending staged]' if pending else ''
            typer.echo(
                f'{project.name}\t{project.created_at.isoformat()}'
                f'\t{project.path}{pending_marker}',
            )

    @project_app.command('show')
    def show(
        name: str = typer.Option(..., '--name', help='Имя искомого проекта'),
    ) -> None:
        async def _run() -> Project:
            return await get_project_use_case(
                name=name,
                projects_root=projects_root,
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
        _emit_pending_staged_warning(project.path)

    @project_app.command('delete')
    def delete(
        name: str = typer.Option(..., '--name', help='Имя удаляемого проекта'),
    ) -> None:
        async def _run() -> None:
            await delete_project_use_case(
                name=name,
                projects_root=projects_root,
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
                projects_root=projects_root,
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
    ) -> None:
        """Валидировать manifest'ы проектов (T157: filesystem = source of truth)."""
        root: Path = Path(storage_root) if storage_root is not None else projects_root

        async def _run() -> ReindexSummary:
            return await reindex_projects_use_case(
                storage_root=root,
                manifest_repo=manifest_repository,
                decision_repo=decision_repository,
            )

        summary = asyncio.run(
            _log_command(
                session_logger,
                'project.reindex',
                project=None,
                payload={'storage_root': str(root)},
                fn=_run,
            ),
        )
        typer.echo(f'Validated {summary.valid} projects.')
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
                projects_root=projects_root,
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
                projects_root=projects_root,
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
                projects_root=projects_root,
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
    ) -> typer.Typer:
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

        return sub

    tube_app = _register_model_subapp(
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
    _register_model_subapp(
        'opamp',
        ComponentCategory.OPAMP,
        'No opamp models found.',
    )

    # T146: SPICE-models static validator (`efactory lib validate <file>`).
    lib_app = typer.Typer(no_args_is_help=True, add_completion=False)
    app.add_typer(lib_app, name='lib')

    @lib_app.command('validate')
    def lib_validate(
        lib_file: Annotated[
            str,
            typer.Argument(help='Путь к SPICE `.lib` / `.cir` / `.net` файлу'),
        ],
    ) -> None:
        """
        T146: static validator — floating-node detection в `.SUBCKT`-блоках.

        Каждая нода subckt должна встречаться ≥ 2 раз (external pin счёт
        + internal touches). Ноды с count == 1 — floating (как `P3`/`S3`
        в pre-T147 `OPT_SE_5K_8.lib`).

        Exit codes:
        - 0: no floating nodes.
        - 1: floating nodes detected (printed details to stdout).
        - 2: file not found / parse error.
        """
        path = Path(lib_file).resolve()
        if not path.is_file():
            typer.echo(f'lib file not found: {path}', err=True)
            raise typer.Exit(code=2)
        try:
            report = validate_lib(path)
        except OSError as exc:
            typer.echo(f'read error: {exc}', err=True)
            raise typer.Exit(code=2) from exc

        typer.echo(f'lib: {report.lib_path}')
        typer.echo(f'subckts validated: {report.subckts_validated}')
        if report.skipped_subckts:
            typer.echo(
                f'skipped (X-subckt refs): {", ".join(report.skipped_subckts)}',
            )
        if not report.floating_nodes:
            typer.echo('result: OK (no floating nodes)')
            return
        typer.echo(f'result: FLOATING ({len(report.floating_nodes)} node(s))')
        for f in report.floating_nodes:
            typer.echo(
                f'  - {f.subckt}: node {f.node!r} '
                f'occurs {f.occurrences} time(s) (expected ≥ 2)',
            )
        raise typer.Exit(code=1)

    # T142: sim-results retention policy (`efactory sim-results prune ...`).
    sim_results_app = typer.Typer(no_args_is_help=True, add_completion=False)
    app.add_typer(sim_results_app, name='sim-results')

    @sim_results_app.command('prune')
    def sim_results_prune(
        project: Annotated[str, typer.Argument(help='Имя проекта')],
        *,
        keep_last: Annotated[
            int | None,
            typer.Option(
                '--keep-last',
                help='Оставить N последних sim-results файлов (default 100)',
            ),
        ] = None,
        keep_days: Annotated[
            int | None,
            typer.Option(
                '--keep-days',
                help='Удалить файлы старше D дней (mutually exclusive с --keep-last)',
            ),
        ] = None,
    ) -> None:
        """
        T142: retention policy для `.efactory/sim-results/`.

        Default (без options): `--keep-last 100`.
        """

        async def _resolve_path() -> Path:
            project_obj = await get_project_use_case(
                name=project,
                projects_root=projects_root,
                manifest_repo=manifest_repository,
            )
            return project_obj.path

        try:
            project_root = asyncio.run(_resolve_path())
        except ProjectNotFoundError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc

        try:
            deleted = asyncio.run(
                prune_sim_results_use_case(
                    project_root=project_root,
                    repo=sim_results_repo,
                    keep_last=keep_last,
                    keep_days=keep_days,
                ),
            )
        except PruneOptionsInvalidError as exc:
            typer.echo(f'invalid options: {exc}', err=True)
            raise typer.Exit(code=2) from exc

        typer.echo(
            f'Pruned {deleted} file(s) from {project_root}/.efactory/sim-results/',
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

    design_app = typer.Typer(no_args_is_help=True, add_completion=False)
    app.add_typer(design_app, name='design')

    def _resolve_design_check_target(arg: str | None) -> Path:
        """
        `efactory design check [<arg>]` target resolution (spec F11/F12/R7).

        - `arg` is a `.kicad_sch` → returned as-is.
        - `arg` is a directory → first `.kicad_sch` inside, fail on
          ambiguity.
        - `arg` is None → auto-detect in cwd (top-level + 1 subdir,
          excluding dot-dirs), exactly one match required.
        """
        if arg is not None:
            target = Path(arg)
            if target.is_file() and target.suffix == '.kicad_sch':
                return target
            if target.is_dir():
                matches = sorted(target.glob('*.kicad_sch'))
                if len(matches) == 1:
                    return matches[0]
                msg = f'{target}: expected exactly one .kicad_sch, got {len(matches)}'
                typer.echo(msg, err=True)
                raise typer.Exit(2)
            msg = f'{target}: not a .kicad_sch file or project directory'
            typer.echo(msg, err=True)
            raise typer.Exit(2)

        cwd = Path.cwd()
        max_depth = 2  # top-level + 1 subdir, как у /sim-run (spec R7)
        matches = [
            p
            for p in cwd.rglob('*.kicad_sch')
            if not any(part.startswith('.') for part in p.relative_to(cwd).parts)
            and len(p.relative_to(cwd).parts) <= max_depth
        ]
        if len(matches) == 1:
            return matches[0]
        if not matches:
            typer.echo(
                'No .kicad_sch found in cwd (top-level + 1 subdir). '
                'Pass a path: `efactory design check path/to/sch.kicad_sch`.',
                err=True,
            )
            raise typer.Exit(2)
        typer.echo(
            f'Multiple .kicad_sch found ({len(matches)}); pick one:',
            err=True,
        )
        for p in matches:
            typer.echo(f'  {p}', err=True)
        raise typer.Exit(2)

    async def _execute_design_check(schematic: Path) -> ErcReport:
        project_root = schematic.parent
        return await run_erc_check(
            schematic=schematic,
            project_root=project_root,
            erc_runner=erc_runner,
            report_writer=erc_report_writer,
        )

    @design_app.command('check')
    def design_check(
        project: Annotated[
            str | None,
            typer.Argument(
                help='Путь к .kicad_sch или к директории проекта '
                '(default: auto-detect в cwd).',
            ),
        ] = None,
        *,
        severity: Annotated[
            str,
            typer.Option(
                '--severity',
                help='Фильтр отчёта (error|warning|all); exit-code не зависит '
                'от фильтра. Default — all.',
            ),
        ] = 'all',
    ) -> None:
        """ERC-проверка schematic'а (standalone, без SPICE-симуляции, T029)."""
        if severity not in {'error', 'warning', 'all'}:
            typer.echo(
                f'--severity must be one of error|warning|all, got {severity!r}',
                err=True,
            )
            raise typer.Exit(2)

        schematic = _resolve_design_check_target(project)
        try:
            report = asyncio.run(_execute_design_check(schematic))
        except ErcErrorsFoundError as exc:
            r = exc.report
            typer.echo(
                f'ERC errors: {r.error_count} (see out/erc/<ts>/report.md)',
                err=True,
            )
            raise typer.Exit(1) from exc
        except (
            KiCadCliUnavailableError,
            ErcParseError,
            ErcTimeoutError,
            SchematicParseError,
        ) as exc:
            typer.echo(f'ERC infrastructure failure: {exc}', err=True)
            raise typer.Exit(2) from exc

        typer.echo(
            f'ERC: {report.error_count} errors, '
            f'{report.warning_count} warnings → out/erc/<ts>/report.md',
        )

    def _exit_on_bridge_error(exc: Exception) -> typer.Exit:
        """Унифицированный маппинг bridge-ошибок в exit-коды."""
        typer.echo(str(exc), err=True)
        if isinstance(exc, ProjectNotFoundError):
            return typer.Exit(code=1)
        return typer.Exit(code=2)

    def _resolve_netlist_path(netlist: str) -> Path:
        # T161: guard для CLI netlist argument. Без него пустая
        # строка резолвится в Path('.') → IsADirectoryError, а
        # nonexistent path → FileNotFoundError — оба cryptic, exit=1.
        if not netlist or not Path(netlist).is_file():
            typer.echo(f'Netlist file not found: {netlist!r}', err=True)
            raise typer.Exit(code=2)
        return Path(netlist)

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
                projects_root=projects_root,
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
        *,
        enable_op_fallback: bool = False,
    ) -> SimulationResult:
        async def _run() -> SimulationResult:
            return await sim_run_use_case(
                netlist=netlist,
                analysis=analysis,
                simulator=simulator,
                timeout_seconds=timeout_seconds,
                enable_op_fallback=enable_op_fallback,
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
        *,
        enable_op_fallback: bool = False,
    ) -> None:
        netlist_path = _resolve_netlist_path(netlist)
        # T029 F16: `sim-run` operates on a pre-built netlist — no schematic
        # means ERC is physically impossible. We surface this so agents can
        # see the gate was skipped intentionally, not silently bypassed.
        typer.echo('ERC: skipped (pre-built netlist mode)')
        try:
            asyncio.run(
                _execute_sim_run(
                    netlist_path,
                    analysis,
                    timeout_seconds,
                    event,
                    enable_op_fallback=enable_op_fallback,
                ),
            )
        except (
            SimulationFailedError,
            SimulatorUnavailableError,
            SpiceNumberFormatError,
            ValidationError,
        ) as exc:
            raise _exit_on_bridge_error(exc) from exc

        if enable_op_fallback:
            typer.echo(
                f'Simulation: completed (analysis={analysis.type}, '
                'fallback=transient-to-op)',
            )
        else:
            typer.echo(f'Simulation: completed (analysis={analysis.type})')

    @sim_run_app.command('op')
    def sim_run_op(
        netlist: Annotated[str, typer.Argument(help='Путь к SPICE netlist')],
        *,
        timeout: Annotated[
            float,
            typer.Option('--timeout', help='Таймаут в секундах (default 60.0)'),
        ] = 60.0,
        with_op_fallback: Annotated[
            bool,
            typer.Option(
                '--with-op-fallback',
                help='T145: подменить `.OP` на `.TRAN ... uic=True` и '
                'собрать synthetic operating-point из settled tail. '
                'Полезно для tube/saturable circuits где `.OP` solver '
                'сходится к trivial idle solution.',
            ),
        ] = False,
    ) -> None:
        _run_sim_and_report(
            netlist,
            OpAnalysis(),
            timeout,
            'bridge.sim_run.op',
            enable_op_fallback=with_op_fallback,
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
        project_root = projects_root / project
        _emit_pending_staged_warning(project_root)
        schematic_path = Path(schematic)
        if not schematic_path.is_absolute():
            schematic_path = (project_root / schematic_path).resolve()
        if schematic_path.is_file():
            await _render_and_announce_schematic(schematic_path, project_root)

        async def _run() -> Simulation:
            return await design_to_sim_use_case(
                project_name=project,
                schematic=Path(schematic),
                analysis=analysis,
                netlist_output=(
                    Path(netlist_output) if netlist_output is not None else None
                ),
                timeout_seconds=timeout_seconds,
                projects_root=projects_root,
                manifest_repo=manifest_repository,
                exporter=schematic_exporter,
                simulator=simulator,
                erc_runner=erc_runner,
                erc_report_writer=erc_report_writer,
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
        except ErcErrorsFoundError as exc:
            report = exc.report
            typer.echo(
                f'ERC errors: {report.error_count} '
                f'(out/erc/<ts>/report.md) — sim skipped',
                err=True,
            )
            raise typer.Exit(1) from exc
        except (
            KiCadCliUnavailableError,
            ErcParseError,
            ErcTimeoutError,
            SchematicParseError,
        ) as exc:
            typer.echo(f'ERC infrastructure failure: {exc}', err=True)
            raise typer.Exit(2) from exc
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
                projects_root=projects_root,
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
                projects_root=projects_root,
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

    @bridge_app.command('edit-and-resim')
    def bridge_edit_and_resim_cmd(
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
                help='REF=VALUE (повторяемый) — изменение component value. '
                'Пример: --set R1=10k --set C3=470n',
            ),
        ],
        measure: Annotated[
            list[str],
            typer.Option(
                '--measure',
                help='gain | bandwidth | thd | phase-margin (повторяемый). '
                'Можно несколько метрик одной командой.',
            ),
        ],
        freq: Annotated[
            str | None,
            typer.Option(
                '--freq',
                help='Частота для gain/thd (SPICE notation: 1k, 100, 10Meg)',
            ),
        ] = None,
        v_in_peak: Annotated[
            float | None,
            typer.Option(
                '--v-in-peak',
                help='Peak amplitude (V) — для gain-large и thd',
            ),
        ] = None,
        f_low: Annotated[
            str,
            typer.Option('--f-low', help='Bandwidth нижняя граница (default 1)'),
        ] = '1',
        f_high: Annotated[
            str,
            typer.Option(
                '--f-high',
                help='Bandwidth верхняя граница (default 1Meg)',
            ),
        ] = '1Meg',
        mode: Annotated[
            str,
            typer.Option(
                '--mode',
                help='small (AC) | large (TRAN RMS) — только для gain',
            ),
        ] = 'small',
        output_signal: Annotated[
            str,
            typer.Option(
                '--output-signal',
                help='Trace name для measure_* (default v(load))',
            ),
        ] = 'v(load)',
        input_signal: Annotated[
            str | None,
            typer.Option(
                '--input-signal',
                help='Input trace name (нужен для --mode large)',
            ),
        ] = None,
        input_source: Annotated[
            str | None,
            typer.Option(
                '--input-source',
                help='V-source ref для injection (multi-V netlist'
                'ах вроде se-amp). Без него — auto-detect single V-source.',
            ),
        ] = None,
        loop_break_node: Annotated[
            str | None,
            typer.Option(
                '--loop-break-node',
                help=(
                    'Phase-margin: net разрыва петли. Пара с '
                    '--loop-break-element. Оба не заданы → auto-detect.'
                ),
            ),
        ] = None,
        loop_break_element: Annotated[
            str | None,
            typer.Option(
                '--loop-break-element',
                help=(
                    'Phase-margin: ref элемента edge-pair (ADR-T153d). '
                    'Пара с --loop-break-node.'
                ),
            ),
        ] = None,
        injection_method: Annotated[
            str,
            typer.Option(
                '--injection-method',
                help=(
                    'Phase-margin injection: middlebrook-voltage | '
                    'middlebrook-current | tian | rosenstark-return-ratio'
                ),
            ),
        ] = 'middlebrook-voltage',
        confidence_threshold: Annotated[
            float,
            typer.Option(
                '--confidence-threshold',
                help='Phase-margin auto-detect threshold (0..1, default 0.8)',
            ),
        ] = 0.8,
        no_confirm: Annotated[
            bool,
            typer.Option(
                '--no-confirm',
                help='Phase-margin: не спрашивать confirmation auto-detect в TTY',
            ),
        ] = False,
        pm_n_points_per_decade: Annotated[
            int,
            typer.Option(
                '--pm-n-points-per-decade',
                help='Phase-margin AC sweep разрешение (default 100)',
            ),
        ] = 100,
        output_format: Annotated[
            str,
            typer.Option(
                '--output',
                '--output-format',
                help='text | json (default text)',
            ),
        ] = 'text',
        output_file: Annotated[
            str | None,
            typer.Option(
                '--output-file',
                help='Записать output в файл вместо stdout',
            ),
        ] = None,
        netlist_dir: Annotated[
            str | None,
            typer.Option(
                '--netlist-dir',
                help='Папка для debug-копий baseline.cir / after.cir',
            ),
        ] = None,
        timeout: Annotated[
            float,
            typer.Option('--timeout', help='Per-run timeout (default 60s)'),
        ] = 60.0,
    ) -> None:
        """
        T021: применить edits к schematic, сравнить выбранные метрики до/после.

        Sequence: baseline measure × N → batch edit (SchematicSnapshot
        rollback на failure) → after measure × N → таблица «до / после /
        Δ / Δ%». Edit'ы остаются применёнными на failure after-measure
        (per-metric `failed_reason` в output). Exit-код = 1 если есть
        failed-метрика.
        """
        # Parse --set REF=VALUE list.
        edits: list[tuple[str, str]] = []
        for spec_str in set_:
            if '=' not in spec_str:
                typer.echo(
                    f'--set требует формат REF=VALUE, получено {spec_str!r}',
                    err=True,
                )
                raise typer.Exit(code=2)
            r, _, v = spec_str.partition('=')
            edits.append((r.strip(), v.strip()))
        if not edits:
            typer.echo(
                '--set обязателен (хотя бы один REF=VALUE).',
                err=True,
            )
            raise typer.Exit(code=2)

        # Validate --measure values up-front (Pydantic Literal даёт
        # cryptic ValidationError; явное сообщение полезнее).
        allowed_metrics = ('gain', 'bandwidth', 'thd', 'phase-margin')
        for m in measure:
            if m not in allowed_metrics:
                typer.echo(
                    f'--measure: {m!r}; ожидалось одно из {", ".join(allowed_metrics)}',
                    err=True,
                )
                raise typer.Exit(code=2)
        if not measure:
            typer.echo(
                '--measure обязателен (хотя бы одна метрика: '
                f'{", ".join(allowed_metrics)}).',
                err=True,
            )
            raise typer.Exit(code=2)
        if mode not in ('small', 'large'):
            typer.echo(
                f'--mode: {mode!r}; ожидалось small | large',
                err=True,
            )
            raise typer.Exit(code=2)
        if output_format not in ('text', 'json'):
            typer.echo(
                f'--output: {output_format!r}; ожидалось text | json',
                err=True,
            )
            raise typer.Exit(code=2)

        # Phase-margin specific guards (только если запрошен).
        wants_pm = 'phase-margin' in measure
        if wants_pm:
            if injection_method not in _INJECTION_STRATEGY_BUILDERS:
                typer.echo(
                    f'--injection-method: {injection_method!r}; expected '
                    f'one of {sorted(_INJECTION_STRATEGY_BUILDERS)}',
                    err=True,
                )
                raise typer.Exit(code=2)
            if not (0.0 <= confidence_threshold <= 1.0):
                typer.echo(
                    f'--confidence-threshold: {confidence_threshold!r}; '
                    f'expected float in [0, 1]',
                    err=True,
                )
                raise typer.Exit(code=2)

        # Build EditAndResimConfig (Pydantic валидирует required-fields
        # per metric; cryptic ValidationError превращается в человеко-
        # читаемое сообщение). CLI принимает hyphenated 'phase-margin',
        # domain Literal — underscore'd 'phase_margin'.
        try:
            normalised_metrics = [
                'phase_margin' if m == 'phase-margin' else m for m in measure
            ]
            cfg_kwargs: dict[str, object] = {
                'metrics': normalised_metrics,
                'mode': mode,
                'output_signal': output_signal,
                'f_low_hz': parse_spice_number(f_low),
                'f_high_hz': parse_spice_number(f_high),
                'pm_n_points_per_decade': pm_n_points_per_decade,
            }
            if freq is not None:
                cfg_kwargs['frequency_hz'] = parse_spice_number(freq)
            if v_in_peak is not None:
                cfg_kwargs['v_in_peak'] = v_in_peak
            if input_signal is not None:
                cfg_kwargs['input_signal'] = input_signal
            if input_source is not None:
                cfg_kwargs['input_source'] = input_source
            if loop_break_node is not None:
                cfg_kwargs['loop_break_node'] = loop_break_node
            if loop_break_element is not None:
                cfg_kwargs['break_element_ref'] = loop_break_element
            config = EditAndResimConfig(**cfg_kwargs)  # type: ignore[arg-type]
        except (ValueError, ValidationError, SpiceNumberFormatError) as exc:
            typer.echo(f'EditAndResimConfig: {exc}', err=True)
            raise typer.Exit(code=2) from exc

        # Phase-margin DI: собираем strategy + callback только если нужно.
        strategy: InjectionStrategy | None = None
        confirmation: ConfirmationCallback | None = None
        if wants_pm:
            strategy = _INJECTION_STRATEGY_BUILDERS[injection_method](
                injection_patcher,
            )
            confirmation = _make_confirmation_callback(
                no_confirm=no_confirm,
                confidence_threshold=confidence_threshold,
            )

        # Soft warn для больших batch'ей (T022 паттерн).
        if len(edits) > SOFT_WARN_EDITS:
            typer.echo(
                f'Warning: {len(edits)} edits in single command — '
                f'consider splitting; complex what-if often easier to '
                f'debug step by step. Continuing.',
                err=True,
            )

        async def _resolve_path() -> Path:
            project_obj = await get_project_use_case(
                name=project,
                projects_root=projects_root,
                manifest_repo=manifest_repository,
            )
            return (project_obj.path / schematic).resolve()

        try:
            schematic_path = asyncio.run(_resolve_path())
        except ProjectNotFoundError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc

        nd = Path(netlist_dir).resolve() if netlist_dir else None

        async def _run() -> EditAndResimReport:
            return await edit_and_resim_with_delta(
                schematic=schematic_path,
                edits=edits,
                config=config,
                exporter=schematic_exporter,
                simulator=simulator,
                netlist_editor=netlist_editor,
                netlist_dir=nd,
                timeout_seconds=timeout,
                project=project,
                injection_strategy=strategy,
                auto_detect_confirmation=confirmation,
            )

        try:
            report = asyncio.run(
                _log_command(
                    session_logger,
                    'bridge.edit_and_resim',
                    project=project,
                    payload={
                        'schematic': schematic,
                        'set': set_,
                        'measure': list(measure),
                        'output': output_format,
                    },
                    fn=_run,
                ),
            )
        except BaselineFailedError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        except (ComponentNotFoundError, MultipleMatchesError) as exc:
            typer.echo(str(exc), err=True)
            typer.echo(
                "Rollback: edit'ы откачены SchematicSnapshot'ом.",
                err=True,
            )
            raise typer.Exit(code=1) from exc
        except (
            AutoDetectConfidenceTooLowError,
            AutoDetectRejectedError,
            LoopBreakNodeNotFoundError,
            LoopGainAlwaysAboveUnityError,
            NoFeedbackLoopDetectedError,
            NoUnityGainCrossoverError,
        ) as exc:
            # Phase-margin baseline errors уже завернуты BaselineFailedError;
            # сюда попадают only direct re-raises (например edge issue в config).
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc

        # Render output.
        if output_format == 'json':
            content = render_edit_and_resim_json(report)
        else:
            content = render_edit_and_resim_text(report)

        if output_file is not None:
            out_path = Path(output_file).resolve()
            out_path.write_text(content, encoding='utf-8')
            typer.echo(f'edit-and-resim complete → {out_path}')
        else:
            typer.echo(content)

        # Exit=1 если есть failed-метрика (Q-E → a / CI-friendly signal).
        has_failure = any(d.after is None for d in report.deltas)
        if has_failure:
            raise typer.Exit(code=1)

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
                '--param C1=100n,1u → 4 запуска',
            ),
        ],
        metric: Annotated[
            str,
            typer.Option(
                '--metric',
                help='op | gain | bandwidth | thd (default op)',
            ),
        ] = 'op',
        analysis: Annotated[
            str | None,
            typer.Option(
                '--analysis',
                help='op | tran | ac — overrides auto-mapping из --metric',
            ),
        ] = None,
        mode: Annotated[
            str | None,
            typer.Option(
                '--mode',
                help='small | large (только для --metric=gain, default small)',
            ),
        ] = None,
        freq: Annotated[
            str | None,
            typer.Option(
                '--freq',
                help='Частота для gain/thd (SPICE notation: 1k, 1Meg)',
            ),
        ] = None,
        f_low: Annotated[
            str,
            typer.Option(
                '--f-low',
                help='--metric=bandwidth lower bound (default 1)',
            ),
        ] = '1',
        f_high: Annotated[
            str,
            typer.Option(
                '--f-high',
                help='--metric=bandwidth upper bound (default 1Meg)',
            ),
        ] = '1Meg',
        v_in_peak: Annotated[
            float | None,
            typer.Option(
                '--v-in-peak',
                help='Input amplitude V (gain-large, thd)',
            ),
        ] = None,
        output_signal: Annotated[
            str,
            typer.Option(
                '--output-signal',
                help='Trace name для measure_* (default v(load))',
            ),
        ] = 'v(load)',
        input_signal: Annotated[
            str | None,
            typer.Option(
                '--input-signal',
                help='Input trace для --metric=gain --mode=large',
            ),
        ] = None,
        input_source: Annotated[
            str | None,
            typer.Option(
                '--input-source',
                help='V-source ref для injection (multi-V netlist'
                'ах: se-amp с B+/input). Без него — auto-detect '
                'single V-source, ambiguity → error.',
            ),
        ] = None,
        output_format: Annotated[
            str,
            typer.Option(
                '--output',
                '--output-format',
                help='text | csv | json (default text)',
            ),
        ] = 'text',
        output_file: Annotated[
            str | None,
            typer.Option(
                '--output-file',
                help='Записать output в файл (вместо stdout); '
                'stdout печатает 1-line summary',
            ),
        ] = None,
        plot: Annotated[
            bool,
            typer.Option('--plot', help='ASCII plot после таблицы'),
        ] = False,
        plot_y: Annotated[
            str | None,
            typer.Option(
                '--plot-y',
                help='Y-колонка plot (default: gain_db / bandwidth_hz / '
                'thd_percent в зависимости от --metric; обязателен для op)',
            ),
        ] = None,
        plot_x_scale: Annotated[
            str,
            typer.Option(
                '--plot-x-scale',
                help='auto | linear | log (default auto)',
            ),
        ] = 'auto',
        max_combinations: Annotated[
            int,
            typer.Option(
                '--max-combinations',
                help=f'Hard cap для N (default {MAX_COMBINATIONS_DEFAULT})',
            ),
        ] = MAX_COMBINATIONS_DEFAULT,
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
        T022: параметрический sweep с tabular output + ASCII plot.

        Metric dispatch: op (operating_points), gain (gain_db /
        gain_linear), bandwidth (f_low_hz / f_high_hz / bandwidth_hz),
        thd (thd_percent / dominant_harmonic_n / dominant_harmonic_percent).
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

        # Build SweepConfig (validation в Pydantic raises ValueError →
        # typer.Exit(2) с понятным сообщением).
        try:
            cfg_kwargs: dict[str, object] = {
                'metric': metric,
                'output_signal': output_signal,
            }
            if analysis is not None:
                cfg_kwargs['analysis'] = analysis
            if mode is not None:
                cfg_kwargs['mode'] = mode
            if freq is not None:
                cfg_kwargs['frequency_hz'] = parse_spice_number(freq)
            cfg_kwargs['f_low_hz'] = parse_spice_number(f_low)
            cfg_kwargs['f_high_hz'] = parse_spice_number(f_high)
            if v_in_peak is not None:
                cfg_kwargs['v_in_peak'] = v_in_peak
            if input_signal is not None:
                cfg_kwargs['input_signal'] = input_signal
            if input_source is not None:
                cfg_kwargs['input_source'] = input_source
            config = SweepConfig(**cfg_kwargs)  # type: ignore[arg-type]
        except (ValueError, ValidationError) as exc:
            typer.echo(f'SweepConfig: {exc}', err=True)
            raise typer.Exit(code=2) from exc

        if output_format not in ('text', 'csv', 'json'):
            typer.echo(
                f'--output: {output_format!r}; ожидалось text | csv | json',
                err=True,
            )
            raise typer.Exit(code=2)
        if plot_x_scale not in ('auto', 'linear', 'log'):
            typer.echo(
                f'--plot-x-scale: {plot_x_scale!r}; ожидалось auto | linear | log',
                err=True,
            )
            raise typer.Exit(code=2)

        # N pre-check (soft warn).
        n_combos = 1
        for vlist in params_dict.values():
            n_combos *= len(vlist)
        if n_combos > SOFT_WARN_COMBINATIONS:
            est_min = max(1, (n_combos * int(timeout)) // 60)
            typer.echo(
                f'Warning: {n_combos} combinations '
                f'(estimated ~{est_min} min upper-bound runtime). Continuing.',
                err=True,
            )

        async def _resolve_path() -> Path:
            project_obj = await get_project_use_case(
                name=project,
                projects_root=projects_root,
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
                config=config,
                exporter=schematic_exporter,
                simulator=simulator,
                netlist_editor=netlist_editor,
                netlist_dir=nd,
                timeout_seconds=timeout,
                max_combinations=max_combinations,
            )

        try:
            runs = asyncio.run(
                _log_command(
                    session_logger,
                    'bridge.sweep',
                    project=project,
                    payload={
                        'schematic': schematic,
                        'param': param,
                        'metric': metric,
                        'output': output_format,
                    },
                    fn=_run,
                ),
            )
        except ValueError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=2) from exc

        # Render tabular output.
        if output_format == 'csv':
            content = render_sweep_csv(runs, metric=metric)  # type: ignore[arg-type]
        elif output_format == 'json':
            content = render_sweep_json(runs, metric=metric)  # type: ignore[arg-type]
        else:
            content = render_sweep_text(runs, metric=metric)  # type: ignore[arg-type]

        if output_file is not None:
            out_path = Path(output_file).resolve()
            out_path.write_text(content, encoding='utf-8')
            typer.echo(f'Sweep complete: {len(runs)} rows → {out_path}')
        else:
            typer.echo(f'Sweep complete: {len(runs)} combinations.')
            typer.echo(content)

        # Plot (опционально).
        if plot:
            y_field = plot_y or _DEFAULT_PLOT_Y.get(metric)
            if y_field is None:
                typer.echo(
                    '--plot для --metric=op требует --plot-y <signal-name>; '
                    'plot отключён.',
                    err=True,
                )
            else:
                refs = list(params_dict)
                if len(refs) > _PLOT_MAX_PARAMS:
                    typer.echo(
                        f'--plot не поддерживает >{_PLOT_MAX_PARAMS} параметров '
                        f'(got {len(refs)}); таблица выведена, plot отключён.',
                        err=True,
                    )
                else:
                    try:
                        plot_str = render_sweep_plot(
                            runs,
                            x_param=refs[0],
                            y_field=y_field,
                            group_by=refs[1] if len(refs) == _PLOT_MAX_PARAMS else None,
                            x_scale=plot_x_scale,  # type: ignore[arg-type]
                        )
                        typer.echo(plot_str)
                    except ValueError as exc:
                        typer.echo(
                            f'Plot disabled: {exc}',
                            err=True,
                        )

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
        netlist_path = _resolve_netlist_path(netlist)
        try:
            freq_hz = parse_spice_number(freq)
        except SpiceNumberFormatError as exc:
            raise _exit_on_bridge_error(exc) from exc

        async def _run() -> GainMeasurement:
            return await measure_gain_use_case(
                netlist=netlist_path,
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
        netlist_path = _resolve_netlist_path(netlist)
        try:
            f_low_hz = parse_spice_number(f_low)
            f_high_hz = parse_spice_number(f_high)
            ref_freq_hz = parse_spice_number(ref_freq) if ref_freq else None
        except SpiceNumberFormatError as exc:
            raise _exit_on_bridge_error(exc) from exc

        async def _run() -> BandwidthMeasurement:
            return await measure_bandwidth_use_case(
                netlist=netlist_path,
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
        netlist_path = _resolve_netlist_path(netlist)
        try:
            freq_hz = parse_spice_number(freq)
        except SpiceNumberFormatError as exc:
            raise _exit_on_bridge_error(exc) from exc

        async def _run() -> ThdMeasurement:
            return await measure_thd_use_case(
                netlist=netlist_path,
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

    @measure_app.command('phase-margin')
    def measure_phase_margin_cmd(
        netlist: Annotated[str, typer.Argument(help='Путь к SPICE netlist (.cir)')],
        *,
        loop_break_node: Annotated[
            str | None,
            typer.Option(
                '--loop-break-node',
                help=(
                    'Net, в котором режется петля. Обязательно вместе с '
                    '--loop-break-element. Если оба не заданы — auto-detect.'
                ),
            ),
        ] = None,
        loop_break_element: Annotated[
            str | None,
            typer.Option(
                '--loop-break-element',
                help=(
                    'Ref элемента, чья ссылка на --loop-break-node '
                    'переименовывается (edge-pair, ADR-T153d).'
                ),
            ),
        ] = None,
        injection_method: Annotated[
            str,
            typer.Option(
                '--injection-method',
                help=(
                    'middlebrook-voltage | middlebrook-current | tian | '
                    'rosenstark-return-ratio'
                ),
            ),
        ] = 'middlebrook-voltage',
        confidence_threshold: Annotated[
            float,
            typer.Option(
                '--confidence-threshold',
                help='Порог auto-detect confidence (0..1, default 0.8)',
            ),
        ] = 0.8,
        no_confirm: Annotated[
            bool,
            typer.Option(
                '--no-confirm',
                help='Не спрашивать confirmation в TTY (batch-friendly)',
            ),
        ] = False,
        f_low: Annotated[
            str,
            typer.Option('--f-low', help='Нижняя граница AC sweep (default 1)'),
        ] = '1',
        f_high: Annotated[
            str,
            typer.Option('--f-high', help='Верхняя граница AC sweep (default 1Meg)'),
        ] = '1Meg',
        n_points_per_decade: Annotated[
            int,
            typer.Option('--n-points-per-decade', help='Разрешение (default 100)'),
        ] = 100,
        output: Annotated[
            str,
            typer.Option('--output', help='Формат: text (default) | json'),
        ] = 'text',
        timeout: Annotated[
            float,
            typer.Option('--timeout', help='Таймаут на каждый AC sweep (default 60.0)'),
        ] = 60.0,
    ) -> None:
        if injection_method not in _INJECTION_STRATEGY_BUILDERS:
            typer.echo(
                f'Invalid --injection-method: {injection_method!r}; expected '
                f'one of {sorted(_INJECTION_STRATEGY_BUILDERS)}',
                err=True,
            )
            raise typer.Exit(code=2)
        if not (0.0 <= confidence_threshold <= 1.0):
            typer.echo(
                f'Invalid --confidence-threshold: {confidence_threshold!r}; '
                f'expected float in [0, 1]',
                err=True,
            )
            raise typer.Exit(code=2)
        netlist_path = _resolve_netlist_path(netlist)
        try:
            f_low_hz = parse_spice_number(f_low)
            f_high_hz = parse_spice_number(f_high)
        except SpiceNumberFormatError as exc:
            raise _exit_on_bridge_error(exc) from exc

        strategy = _INJECTION_STRATEGY_BUILDERS[injection_method](injection_patcher)
        confirmation = _make_confirmation_callback(
            no_confirm=no_confirm,
            confidence_threshold=confidence_threshold,
        )

        async def _run() -> PhaseMarginMeasurement:
            return await measure_phase_margin_use_case(
                netlist=netlist_path,
                injection_strategy=strategy,
                break_node=loop_break_node,
                break_element_ref=loop_break_element,
                auto_detect_confirmation=confirmation,
                simulator=simulator,
                f_low=f_low_hz,
                f_high=f_high_hz,
                n_points_per_decade=n_points_per_decade,
                timeout_seconds=timeout,
            )

        try:
            result = asyncio.run(
                _log_command(
                    session_logger,
                    'bridge.measure.phase_margin',
                    project=None,
                    payload={
                        'netlist': netlist,
                        'injection_method': injection_method,
                        'loop_break_node': loop_break_node,
                        'loop_break_element': loop_break_element,
                        'f_low_hz': f_low_hz,
                        'f_high_hz': f_high_hz,
                    },
                    fn=_run,
                ),
            )
        except (
            AutoDetectConfidenceTooLowError,
            AutoDetectRejectedError,
            LoopBreakNodeNotFoundError,
            LoopGainAlwaysAboveUnityError,
            NoFeedbackLoopDetectedError,
            NoUnityGainCrossoverError,
            SimulationFailedError,
            SimulatorUnavailableError,
            SpiceNumberFormatError,
            ValidationError,
            ValueError,
        ) as exc:
            raise _exit_on_bridge_error(exc) from exc

        _emit_phase_margin(result, output_fmt=output)

    # === efactory kb {list,show,add,search} (Agent Knowledge Base, T134) ===

    kb_app = typer.Typer(no_args_is_help=True, add_completion=False)
    app.add_typer(kb_app, name='kb')

    @kb_app.command('list')
    def kb_list_cmd() -> None:
        """Список всех KB entries (built-in + host-mutated, host wins)."""
        try:
            entries = kb_store.list_all()
        except KbParseError as exc:
            typer.echo(f'KB scan failed: {exc}', err=True)
            raise typer.Exit(code=2) from exc
        if not entries:
            typer.echo('Knowledge Base пуста (no entries).')
            return
        for entry in entries:
            typer.echo(f'{entry.topic}\t[{entry.source}]\t{entry.description}')

    @kb_app.command('show')
    def kb_show_cmd(
        topic: Annotated[
            str,
            typer.Argument(help='Namespaced slug (например spice.saturable)'),
        ],
    ) -> None:
        """Полный markdown entry по topic."""
        try:
            entry = kb_store.get(topic)
        except KbParseError as exc:
            typer.echo(f'KB scan failed: {exc}', err=True)
            raise typer.Exit(code=2) from exc
        if entry is None:
            typer.echo(f'Topic {topic!r} not found.', err=True)
            raise typer.Exit(code=1)
        typer.echo(f'# {entry.topic}')
        typer.echo(f'> {entry.description}')
        tags_str = ', '.join(entry.tags) if entry.tags else '(none)'
        typer.echo(f'> tags: {tags_str}')
        typer.echo(f'> source: {entry.source}')
        typer.echo('')
        typer.echo(entry.body)

    @kb_app.command('add')
    def kb_add_cmd(
        topic: Annotated[str, typer.Argument(help='Namespaced slug')],
        description: Annotated[
            str,
            typer.Option('--description', help='One-liner для TOC (≤200 chars)'),
        ],
        body: Annotated[
            str | None,
            typer.Option(
                '--body',
                help=(
                    'Inline markdown body (для коротких entries / автономного '
                    'agent-use). Mutually exclusive с --body-file.'
                ),
            ),
        ] = None,
        body_file: Annotated[
            Path | None,
            typer.Option(
                '--body-file',
                help='Файл с markdown body (либо `-` для stdin).',
            ),
        ] = None,
        tags: Annotated[
            str,
            typer.Option('--tags', help='CSV (например spice,magnetics)'),
        ] = '',
        *,
        force: Annotated[
            bool,
            typer.Option('--force', help='Overwrite existing topic'),
        ] = False,
    ) -> None:
        """
        Добавить entry в host-mutated KB.

        Body source priority: --body (inline) > --body-file > stdin (default).
        """
        if body is not None and body_file is not None:
            typer.echo('--body and --body-file are mutually exclusive.', err=True)
            raise typer.Exit(code=2)
        if body is not None:
            body_text = body
        elif body_file is None or str(body_file) == '-':
            body_text = sys.stdin.read()
        else:
            try:
                body_text = body_file.read_text(encoding='utf-8')
            except OSError as exc:
                typer.echo(f'cannot read --body-file: {exc}', err=True)
                raise typer.Exit(code=2) from exc
        if not body_text.strip():
            typer.echo(
                'Body is empty; provide content via --body, --body-file, or stdin.',
                err=True,
            )
            raise typer.Exit(code=2)
        tag_tuple: tuple[str, ...] = tuple(
            t.strip() for t in tags.split(',') if t.strip()
        )
        try:
            entry = KbEntry(
                topic=topic,
                description=description,
                tags=tag_tuple,
                source='host-mutated',
                body=body_text,
            )
        except ValidationError as exc:
            typer.echo(f'invalid KB entry: {exc}', err=True)
            raise typer.Exit(code=2) from exc
        try:
            kb_store.add(entry, force=force)
        except KbConflictError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(f'KB entry {topic!r} added (source=host-mutated).')

    @kb_app.command('search')
    def kb_search_cmd(
        query: Annotated[str, typer.Argument(help='Token-AND query')],
    ) -> None:
        """Token-AND поиск по KB (topic + description + tags + body)."""
        try:
            results = kb_store.search(query)
        except KbParseError as exc:
            typer.echo(f'KB scan failed: {exc}', err=True)
            raise typer.Exit(code=2) from exc
        if not results:
            typer.echo(f'No KB entries match {query!r}.')
            return
        typer.echo(f'{len(results)} match(es) for {query!r}:')
        for entry in results:
            typer.echo(f'  {entry.topic}\t[{entry.source}]\t{entry.description}')

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
        output: Annotated[
            str | None,
            typer.Option(
                '--output',
                help='Сохранить график как PNG (T025; abs path; agent открывает eog).',
            ),
        ] = None,
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
        netlist_path = _resolve_netlist_path(netlist)
        with contextlib.ExitStack() as stack:
            try:
                prepared_netlist_path = stack.enter_context(
                    _prepare_ac_netlist(
                        netlist_path=netlist_path,
                        netlist_editor=netlist_editor,
                        explicit_source=input_source,
                    ),
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
        if output is not None:
            try:
                png_path = render_ac_sweep_png(
                    result.ac_sweep,
                    signal=signal,
                    output=Path(output),
                )
            except ValueError as exc:
                typer.echo(str(exc), err=True)
                raise typer.Exit(code=2) from exc
            typer.echo(f'plot-render: {png_path}')

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
        output: Annotated[
            str | None,
            typer.Option(
                '--output',
                help='Сохранить график как PNG (T025; abs path; agent открывает eog).',
            ),
        ] = None,
        timeout: Annotated[
            float,
            typer.Option('--timeout', help='Таймаут в секундах (default 60.0)'),
        ] = 60.0,
    ) -> None:
        netlist_path = _resolve_netlist_path(netlist)
        try:
            analysis = _make_tran(t_step, t_stop, t_start, uic=uic)
        except (SpiceNumberFormatError, ValidationError) as exc:
            raise _exit_on_bridge_error(exc) from exc

        async def _run() -> SimulationResult:
            return await sim_run_use_case(
                netlist=netlist_path,
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
        if output is not None:
            try:
                png_path = render_time_series_png(
                    result.time_series,
                    signal=signal,
                    output=Path(output),
                )
            except ValueError as exc:
                typer.echo(str(exc), err=True)
                raise typer.Exit(code=2) from exc
            typer.echo(f'plot-render: {png_path}')

    @schematic_app.command('apply-staged')
    def schematic_apply_staged(
        name: Annotated[
            str,
            typer.Argument(help='Имя проекта (директория в projects_root).'),
        ],
        *,
        force: Annotated[
            bool,
            typer.Option(
                '--force',
                help=(
                    'Bypass lock-check (KiCad GUI ещё держит файл, '
                    'stale-lock после crash и т.п.). НЕ обходит '
                    'parent-hash divergence — для этого --accept-overwrite.'
                ),
            ),
        ] = False,
        accept_overwrite: Annotated[
            bool,
            typer.Option(
                '--accept-overwrite',
                help=(
                    'Bypass parent-hash check: согласиться потерять '
                    'изменения, сделанные в KiCad GUI после staged-write.'
                ),
            ),
        ] = False,
    ) -> None:
        """Apply pending `.kicad_sch.staged` → active для всех файлов проекта."""

        async def _run() -> ApplyStagedOutcome:
            return await apply_staged_schematic_use_case(
                name=name,
                projects_root=projects_root,
                lock_detector=lock_detector,
                scanner=staged_scanner,
                force=force,
                accept_overwrite=accept_overwrite,
            )

        try:
            outcome = asyncio.run(
                _log_command(
                    session_logger,
                    'schematic.apply-staged',
                    project=name,
                    payload={
                        'name': name,
                        'force': force,
                        'accept_overwrite': accept_overwrite,
                    },
                    fn=_run,
                ),
            )
        except ProjectNotFoundError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        _emit_apply_staged_outcome(outcome)
        if outcome.skipped:
            raise typer.Exit(code=1)

    # T177: `efactory template create-from-project` — promote проект
    # в user-overlay template (persistent persistent).
    template_app = typer.Typer(no_args_is_help=True, add_completion=False)
    app.add_typer(template_app, name='template')

    @template_app.command('create-from-project')
    def template_create_from_project(
        project_name: Annotated[
            str,
            typer.Argument(help='Имя существующего project (в projects_root).'),
        ],
        *,
        name: Annotated[
            str,
            typer.Option(
                '--name',
                help='Имя нового template (slug, latin lowercase + dashes).',
            ),
        ],
        description: Annotated[
            str,
            typer.Option(
                '--description',
                help='Многострочное описание для template.yaml.',
            ),
        ] = '',
        summary: Annotated[
            str,
            typer.Option(
                '--summary',
                help='Однострочное краткое description для list-templates.',
            ),
        ] = '',
        force: Annotated[
            bool,
            typer.Option('--force', help='Перезаписать existing template.'),
        ] = False,
    ) -> None:
        """T177: promote проект в user-overlay template (persistent)."""
        request = CreateTemplateRequest(
            project_dir=projects_root / project_name,
            template_name=name,
            target_root=user_templates_root,
            description=description,
            summary=summary,
            force=force,
        )
        try:
            result = create_template_from_project(request)
        except CreateTemplateError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        typer.echo(f'template: {result.template_dir}')
        typer.echo(f'files: {result.files_copied}')
        typer.echo(f'usage: efactory project create --name <new> --template {name}')

    # T031: `efactory tube fit-from-points` — fit Koren triode / Ayumi
    # pentode params из JSON IV-точек, пишет `.lib` в user overlay.
    # tube_app — это existing sub-app (T006: list/show), reuse'им.

    @tube_app.command('fit-from-points')
    def tube_fit_from_points(
        spice_name: Annotated[
            str,
            typer.Argument(help='SPICE id для .SUBCKT (e.g., 6ZH38P).'),
        ],
        tube_type: Annotated[
            str,
            typer.Option(
                '--type',
                help='Тип лампы для fit (`triode` или `pentode`).',
            ),
        ],
        points: Annotated[
            Path,
            typer.Option(
                '--points',
                help='Path к JSON с IVDataset.',
            ),
        ],
        *,
        out: Annotated[
            Path | None,
            typer.Option(
                '--out',
                help='Куда положить .lib (default: $XDG_DATA_HOME/efactory'
                '/models/tubes/custom/).',
            ),
        ] = None,
        include_vct: Annotated[
            bool,
            typer.Option(
                '--include-vct',
                help='Fit Vct (cathode contact potential) — только для triode.',
            ),
        ] = False,
        header_type: Annotated[
            str,
            typer.Option(
                '--header-type',
                help='tube_type header в .lib (pentode | tetrode); для triode '
                'игнорируется.',
            ),
        ] = 'pentode',
        seed_from: Annotated[
            Path | None,
            typer.Option(
                '--seed-from',
                help='JSON с params существующей лампы — multi-start hint (S3).',
            ),
        ] = None,
        kg2_ratio: Annotated[
            float,
            typer.Option(
                '--kg2-ratio',
                help='Typical KG2/KG1 ratio fallback при отсутствии '
                'screen_curves в JSON (default 5.0).',
            ),
        ] = 5.0,
        force: Annotated[
            bool,
            typer.Option('--force', help='Перезаписать existing .lib.'),
        ] = False,
        formula_variant: Annotated[
            str,
            typer.Option(
                '--formula-variant',
                help='Forward-formula variant: auto (default, per tube_type — '
                'pentode → koren-modified-knee, triode → koren-canonical) | '
                'koren-canonical (T031 backwards-compat) | koren-modified-knee '
                '(pentode, T182 sharper knee) | koren-modified-cutoff (triode, '
                'T182 sharper cutoff — для 300B-style power triodes).',
            ),
        ] = 'auto',
    ) -> None:
        """T031/T182: fit Koren triode / Ayumi pentode → `.lib` в user overlay."""
        if tube_type not in ('triode', 'pentode'):
            typer.echo(
                f"--type must be 'triode' or 'pentode', got '{tube_type}'",
                err=True,
            )
            raise typer.Exit(code=2)
        if header_type not in ('pentode', 'tetrode'):
            typer.echo(
                f"--header-type must be 'pentode' or 'tetrode', got '{header_type}'",
                err=True,
            )
            raise typer.Exit(code=2)
        if include_vct and tube_type != 'triode':
            typer.echo(
                '--include-vct valid only with --type triode',
                err=True,
            )
            raise typer.Exit(code=2)
        if formula_variant not in (
            'auto',
            'koren-canonical',
            'koren-modified-knee',
            'koren-modified-cutoff',
        ):
            typer.echo(
                f'--formula-variant must be one of: auto (default), '
                f'koren-canonical, koren-modified-knee, '
                f"koren-modified-cutoff (got '{formula_variant}')",
                err=True,
            )
            raise typer.Exit(code=2)
        # Auto-default per tube_type (T134 cleanup 2026-06-04):
        # pentode → modified-knee (Phase 4 best 36% on EL34 vs canonical 286%);
        # triode → canonical (small-signal default; power triodes opt-in
        # modified-cutoff manually). См. KB topic tubes.formula-variant-choice.
        if formula_variant == 'auto':
            formula_variant = (
                'koren-modified-knee' if tube_type == 'pentode' else 'koren-canonical'
            )
        if out is None:
            out = projects_root.parent / 'models' / 'tubes' / 'custom'
        request = FitTubeFromPointsRequest(
            spice_name=spice_name,
            tube_type=tube_type,  # type: ignore[arg-type]
            points_json=points,
            out_dir=out,
            include_vct=include_vct,
            header_type=header_type,  # type: ignore[arg-type]
            seed_from=seed_from,
            kg2_ratio=kg2_ratio,
            force=force,
            formula_variant=formula_variant,  # type: ignore[arg-type]
        )
        try:
            result = fit_tube_from_points(
                request,
                iv_repository=tube_iv_repository,
                lib_writer=tube_lib_writer,
            )
        except FitTubeUseCaseError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        _emit_tube_fit_summary(result)

    return app


def _emit_tube_fit_summary(
    result: FitTubeFromPointsResult,
) -> None:
    """T031 CLI stdout summary (SC#3)."""
    fr = result.fit_result
    p = fr.params
    typer.echo(f'lib: {result.lib_path}')
    typer.echo(f'fit: n_points={fr.n_points} rms={fr.rms_residual_ma:.3f} mA')
    typer.echo(f'starts: tried={fr.n_starts_tried} best={fr.best_start_index}')
    if result.used_joint_ig2_fit:
        typer.echo('mode: joint Ia+Ig2 (KG2 identifiable)')
    if result.kg2_was_overridden:
        typer.echo(f'kg2: overridden = ratio * kg1 = {p.kg2:.2f}')  # type: ignore[union-attr]
    typer.echo(f'params: {p.model_dump()}')


def _emit_apply_staged_outcome(outcome: ApplyStagedOutcome) -> None:
    if not outcome.applied and not outcome.skipped:
        typer.echo('schematic-apply-staged: no pending staged to apply')
        return
    for path in outcome.applied:
        typer.echo(f'schematic-applied: {path}')
    for entry in outcome.skipped:
        typer.echo(_format_skipped(entry), err=True)


def _format_skipped(entry: SkippedStagedEntry) -> str:
    if entry.reason == 'lock':
        return (
            f'schematic-apply-skipped: {entry.active_path} '
            f'reason=lock (KiCad держит файл; закрой GUI или используй --force)'
        )
    current = (entry.current_hash or 'absent')[:16]
    expected = (entry.expected_hash or 'absent')[:16]
    return (
        f'schematic-apply-skipped: {entry.active_path} '
        f'reason=parent-hash-mismatch current={current} expected={expected} '
        f'(active изменён после staged-write; --accept-overwrite чтобы перезаписать)'
    )
