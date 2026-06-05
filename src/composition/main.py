"""Composition root: сборка графа зависимостей и точка входа CLI (T157)."""

from __future__ import annotations

import logging
import os
import secrets
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING

from adapters.inbound.cli.app import build_app
from adapters.outbound.decision_markdown.decision_repository import (
    FilesystemDecisionRepository,
)
from adapters.outbound.erc_kicad_cli.runner import KicadCliErcRunner
from adapters.outbound.erc_report_markdown.writer import (
    MarkdownErcReportWriter,
)
from adapters.outbound.file_store.project_file_repository import (
    FilesystemProjectFileRepository,
)
from adapters.outbound.git_subprocess.git_repository import (
    SubprocessGitRepository,
)
from adapters.outbound.grid_report_markdown.writer import (
    MarkdownGridReportWriter,
)
from adapters.outbound.kicad_cli.schematic_exporter import (
    KicadCliSchematicExporter,
)
from adapters.outbound.kicad_cli.schematic_publication_renderer import (
    KicadCliSchematicPublicationRenderer,
)
from adapters.outbound.kicad_cli.schematic_renderer import (
    KicadCliSchematicRenderer,
)
from adapters.outbound.knowledge_base_filesystem.store import FileSystemKbStore
from adapters.outbound.magnetic_results_filesystem.adapter import (
    FileSystemMagneticResults,
)
from adapters.outbound.manifest_yaml.project_manifest_repository import (
    FilesystemProjectManifestRepository,
)
from adapters.outbound.ngspice.injection_patcher import (
    NgspiceInjectionNetlistPatcher,
)
from adapters.outbound.ngspice.netlist_substitution import NgspiceNetlistEditor
from adapters.outbound.ngspice.simulator import NgspiceSimulator
from adapters.outbound.platform_native.platform_layer import (
    NativePlatformLayer,
)
from adapters.outbound.publication_readme_markdown.writer import (
    MarkdownPublicationReadmeWriter,
)
from adapters.outbound.raw_waveforms_filesystem.adapter import (
    FileSystemRawWaveforms,
)
from adapters.outbound.schematic_kicad.lock_detector import KicadLockDetector
from adapters.outbound.schematic_kicad.scanner import KicadPendingStagedScanner
from adapters.outbound.session_jsonl.session_logger import (
    FilesystemJsonlSessionLogger,
)
from adapters.outbound.sim_report_markdown.writer import (
    MarkdownSimReportWriter,
)
from adapters.outbound.sim_results_filesystem.adapter import FileSystemSimResults
from adapters.outbound.spice_import_classify.classifier import (
    RegexSpiceModelClassifier,
)
from adapters.outbound.spice_import_http.downloader import (
    UrllibSpiceModelDownloader,
)
from adapters.outbound.spice_import_kb.writer import MarkdownSpiceKbWriter
from adapters.outbound.spice_import_smoke.runner import NgspiceSmokeRunner
from adapters.outbound.spice_models.spice_library import (
    FilesystemSpiceModelLibrary,
)
from adapters.outbound.spice_models.tube_json import FilesystemTubeIVRepository
from adapters.outbound.spice_models.tube_lib_writer import FilesystemTubeLibWriter
from adapters.outbound.subprocess_apps.app_manager import (
    SubprocessAppManager,
)
from composition.settings import Settings

if TYPE_CHECKING:
    import typer


def _ensure_storage_dirs(settings: Settings) -> None:
    """Создать projects_root + session_root (T157: SQL-БД больше не нужна)."""
    settings.projects_root.mkdir(parents=True, exist_ok=True)
    settings.session_root.mkdir(parents=True, exist_ok=True)


def _make_session_id() -> str:
    """`YYYYMMDD-HHMMSS-<rand6>` либо EFACTORY_SESSION_ID override (T010 N2)."""
    env_id = os.environ.get('EFACTORY_SESSION_ID')
    if env_id:
        return env_id
    timestamp = datetime.now(UTC).strftime('%Y%m%d-%H%M%S')
    return f'{timestamp}-{secrets.token_hex(3)}'


def _resolve_efactory_version() -> str:
    try:
        return version('efactory')
    except PackageNotFoundError:
        return 'unknown'


def build_cli_app() -> typer.Typer:
    logging.basicConfig(level=logging.INFO)

    settings = Settings()
    _ensure_storage_dirs(settings)

    session_id = _make_session_id()
    platform = NativePlatformLayer()
    app_manager = SubprocessAppManager(platform)
    simulator = NgspiceSimulator(app_manager)

    return build_app(
        projects_root=settings.projects_root,
        file_repository=FilesystemProjectFileRepository(),
        manifest_repository=FilesystemProjectManifestRepository(),
        decision_repository=FilesystemDecisionRepository(),
        git_repository=SubprocessGitRepository(),
        session_logger=FilesystemJsonlSessionLogger(
            settings.session_root,
            session_id,
        ),
        spice_library=FilesystemSpiceModelLibrary(
            settings.library_root,
            settings.user_library_root,
        ),
        app_manager=app_manager,
        schematic_exporter=KicadCliSchematicExporter(app_manager),
        schematic_renderer=KicadCliSchematicRenderer(app_manager),
        erc_runner=KicadCliErcRunner(),
        erc_report_writer=MarkdownErcReportWriter(),
        grid_report_writer=MarkdownGridReportWriter(),
        simulator=simulator,
        netlist_editor=NgspiceNetlistEditor(),
        injection_patcher=NgspiceInjectionNetlistPatcher(),
        kb_store=FileSystemKbStore(
            built_in_dir=settings.kb_built_in_dir,
            host_mutated_dir=settings.kb_host_mutated_dir,
        ),
        sim_results_repo=FileSystemSimResults(),
        raw_waveform_repo=FileSystemRawWaveforms(),
        magnetics_results_repo=FileSystemMagneticResults(),
        lock_detector=KicadLockDetector(),
        staged_scanner=KicadPendingStagedScanner(),
        tube_iv_repository=FilesystemTubeIVRepository(),
        tube_lib_writer=FilesystemTubeLibWriter(),
        user_templates_root=settings.user_templates_root,
        user_library_root=settings.user_library_root,
        kb_host_mutated_dir=settings.kb_host_mutated_dir,
        spice_downloader=UrllibSpiceModelDownloader(),
        spice_classifier=RegexSpiceModelClassifier(),
        spice_smoke=NgspiceSmokeRunner(simulator=simulator),
        spice_kb_writer=MarkdownSpiceKbWriter(),
        publication_renderer=KicadCliSchematicPublicationRenderer(app_manager),
        publication_readme_writer=MarkdownPublicationReadmeWriter(),
        sim_report_writer=MarkdownSimReportWriter(),
        efactory_version=_resolve_efactory_version(),
    )


def run() -> None:
    build_cli_app()()
