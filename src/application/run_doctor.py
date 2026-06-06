"""
`run_doctor` use case — сборка `DoctorReport` через `SystemProbe` (T036).

Data-driven: списки `TOOLCHAIN_COMMANDS` / `TOOLCHAIN_PYTHON_LIBS` /
`MOUNT_POINTS` — единственная точка правки для добавления / удаления
проверок. Тесты используют stub probe с canned-ответами.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from domain.doctor import (
    CATEGORY_GUI,
    CATEGORY_MOUNTS,
    CATEGORY_RUNTIME,
    CATEGORY_TOOLCHAIN,
    CheckStatus,
    DoctorCheck,
    DoctorReport,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from ports.outbound.system_probe import (
        CommandProbeResult,
        PathProbeResult,
        SystemProbe,
    )


@dataclass(frozen=True, slots=True)
class CommandProbeSpec:
    """Описание одной команды-probe."""

    name: str
    argv: tuple[str, ...]
    required: bool = True


@dataclass(frozen=True, slots=True)
class PythonLibSpec:
    """Описание одной python-библиотеки-probe."""

    name: str
    package: str
    required: bool = True


@dataclass(frozen=True, slots=True)
class MountSpec:
    """Описание mount-точки."""

    name: str
    path: Path
    must_be_writable: bool


TOOLCHAIN_COMMANDS: tuple[CommandProbeSpec, ...] = (
    CommandProbeSpec('kicad-cli', ('kicad-cli', '--version')),
    CommandProbeSpec('ngspice', ('ngspice', '-v')),
    CommandProbeSpec('ElmerSolver', ('ElmerSolver',)),
    CommandProbeSpec('getdp', ('getdp', '--version')),
    CommandProbeSpec('gmsh', ('gmsh', '--version')),
    CommandProbeSpec('freecad', ('freecad', '--version'), required=False),
    CommandProbeSpec('freecadcmd', ('freecadcmd', '--version')),
    CommandProbeSpec('rsvg-convert', ('rsvg-convert', '--version')),
    CommandProbeSpec('python', ('python', '--version')),
    CommandProbeSpec('uv', ('uv', '--version')),
    CommandProbeSpec('git', ('git', '--version')),
)

TOOLCHAIN_PYTHON_LIBS: tuple[PythonLibSpec, ...] = (
    PythonLibSpec(name='PyOpenMagnetics', package='pyopenmagnetics'),
    PythonLibSpec(name='femmt', package='femmt', required=False),
    PythonLibSpec(name='scipy', package='scipy'),
)

MOUNT_POINTS: tuple[MountSpec, ...] = (
    MountSpec('/workspace', Path('/workspace'), must_be_writable=True),
    MountSpec(
        '/efactory/.claude',
        Path('/efactory/.claude'),
        must_be_writable=True,
    ),
    MountSpec('/libs/symbols', Path('/libs/symbols'), must_be_writable=False),
    MountSpec(
        '/libs/footprints',
        Path('/libs/footprints'),
        must_be_writable=False,
    ),
)

CREDENTIAL_FILE = Path('/efactory/.claude/.credentials.json')

IMAGE_VERSION_ENV = 'EFACTORY_VERSION'

DISK_FREE_WARN_BYTES = 1 * 1024**3
DISK_FREE_FAIL_BYTES = 100 * 1024**2
ULIMIT_NOFILE_WARN_THRESHOLD = 1024
# Heuristic: cgroup memory.max выше этого порога трактуется как «без лимита»
# (host без cgroup-ограничения возвращает огромные числа вплоть до int64 max).
CGROUP_MEMORY_UNLIMITED_BYTES = 2**62


def run_doctor(
    probe: SystemProbe,
    *,
    include_gui: bool = True,
) -> DoctorReport:
    """
    Собрать `DoctorReport` через `SystemProbe`. `include_gui=False`
    пропускает GUI-блок (для `--no-gui` / headless контекста).
    """
    checks: list[DoctorCheck] = []
    checks.extend(_toolchain_checks(probe))
    if include_gui:
        checks.extend(_gui_checks(probe))
    checks.extend(_mount_checks(probe))
    checks.extend(_runtime_checks(probe))
    return DoctorReport(checks=tuple(checks))


def _toolchain_checks(probe: SystemProbe) -> Iterable[DoctorCheck]:
    yield _efactory_version_check(probe)
    for cmd_spec in TOOLCHAIN_COMMANDS:
        yield _command_check(cmd_spec, probe.probe_command(cmd_spec.argv))
    for lib_spec in TOOLCHAIN_PYTHON_LIBS:
        yield _python_lib_check(
            lib_spec,
            probe.probe_python_package_version(lib_spec.package),
        )


def _efactory_version_check(probe: SystemProbe) -> DoctorCheck:
    raw = probe.probe_env(IMAGE_VERSION_ENV)
    if raw:
        return DoctorCheck(
            name='efactory image',
            status=CheckStatus.OK,
            detail=raw,
            category=CATEGORY_TOOLCHAIN,
        )
    return DoctorCheck(
        name='efactory image',
        status=CheckStatus.WARN,
        detail=f'${IMAGE_VERSION_ENV} not set',
        category=CATEGORY_TOOLCHAIN,
    )


def _command_check(
    spec: CommandProbeSpec,
    result: CommandProbeResult,
) -> DoctorCheck:
    if not result.found:
        return DoctorCheck(
            name=spec.name,
            status=CheckStatus.FAIL if spec.required else CheckStatus.WARN,
            detail='command not found',
            category=CATEGORY_TOOLCHAIN,
        )
    if result.timed_out:
        return DoctorCheck(
            name=spec.name,
            status=CheckStatus.WARN,
            detail='probe timed out',
            category=CATEGORY_TOOLCHAIN,
        )
    if not result.stdout:
        return DoctorCheck(
            name=spec.name,
            status=CheckStatus.WARN,
            detail=f'no output (exit={result.exit_code})',
            category=CATEGORY_TOOLCHAIN,
        )
    return DoctorCheck(
        name=spec.name,
        status=CheckStatus.OK,
        detail=result.stdout,
        category=CATEGORY_TOOLCHAIN,
    )


def _python_lib_check(
    spec: PythonLibSpec,
    version: str | None,
) -> DoctorCheck:
    if version is None:
        return DoctorCheck(
            name=spec.name,
            status=CheckStatus.FAIL if spec.required else CheckStatus.WARN,
            detail='package not installed',
            category=CATEGORY_TOOLCHAIN,
        )
    return DoctorCheck(
        name=spec.name,
        status=CheckStatus.OK,
        detail=version,
        category=CATEGORY_TOOLCHAIN,
    )


def _gui_checks(probe: SystemProbe) -> Iterable[DoctorCheck]:
    display = probe.probe_env('DISPLAY')
    yield (
        DoctorCheck(
            name='$DISPLAY',
            status=CheckStatus.OK,
            detail=display,
            category=CATEGORY_GUI,
        )
        if display
        else DoctorCheck(
            name='$DISPLAY',
            status=CheckStatus.WARN,
            detail='not set',
            category=CATEGORY_GUI,
        )
    )

    xset = probe.probe_command(('xset', 'q'), timeout_s=3.0)
    yield _xset_check(xset)

    dri = probe.probe_dri_devices()
    if dri:
        yield DoctorCheck(
            name='/dev/dri',
            status=CheckStatus.OK,
            detail=', '.join(dri),
            category=CATEGORY_GUI,
        )
    else:
        yield DoctorCheck(
            name='/dev/dri',
            status=CheckStatus.WARN,
            detail='no DRI devices (no GPU passthrough)',
            category=CATEGORY_GUI,
        )


def _xset_check(result: CommandProbeResult) -> DoctorCheck:
    if not result.found:
        return DoctorCheck(
            name='xset q',
            status=CheckStatus.WARN,
            detail='xset binary not found in image',
            category=CATEGORY_GUI,
        )
    if result.timed_out or (result.exit_code is not None and result.exit_code != 0):
        return DoctorCheck(
            name='xset q',
            status=CheckStatus.WARN,
            detail=f'X11 unreachable (exit={result.exit_code})',
            category=CATEGORY_GUI,
        )
    return DoctorCheck(
        name='xset q',
        status=CheckStatus.OK,
        detail='X11 reachable',
        category=CATEGORY_GUI,
    )


def _mount_checks(probe: SystemProbe) -> Iterable[DoctorCheck]:
    for spec in MOUNT_POINTS:
        yield _mount_check(spec, probe.probe_path(spec.path))
    yield _credentials_check(probe.probe_path(CREDENTIAL_FILE))


def _mount_check(spec: MountSpec, result: PathProbeResult) -> DoctorCheck:
    if not result.exists:
        return DoctorCheck(
            name=spec.name,
            status=CheckStatus.FAIL,
            detail='does not exist',
            category=CATEGORY_MOUNTS,
        )
    if not result.is_dir:
        return DoctorCheck(
            name=spec.name,
            status=CheckStatus.FAIL,
            detail='exists but is not a directory',
            category=CATEGORY_MOUNTS,
        )
    if spec.must_be_writable and not result.writable:
        return DoctorCheck(
            name=spec.name,
            status=CheckStatus.FAIL,
            detail='directory not writable',
            category=CATEGORY_MOUNTS,
        )
    return DoctorCheck(
        name=spec.name,
        status=CheckStatus.OK,
        detail='dir, writable' if spec.must_be_writable else 'dir',
        category=CATEGORY_MOUNTS,
    )


def _credentials_check(result: PathProbeResult) -> DoctorCheck:
    if result.exists and result.is_file:
        return DoctorCheck(
            name=str(CREDENTIAL_FILE),
            status=CheckStatus.OK,
            detail='Claude Code auth state present',
            category=CATEGORY_MOUNTS,
        )
    return DoctorCheck(
        name=str(CREDENTIAL_FILE),
        status=CheckStatus.WARN,
        detail='absent — agent will require login on first run',
        category=CATEGORY_MOUNTS,
    )


def _runtime_checks(probe: SystemProbe) -> Iterable[DoctorCheck]:
    yield _disk_free_check(probe.probe_disk_free_bytes(Path('/workspace')))
    yield _ulimit_check(probe.probe_ulimit_nofile())
    yield _cgroup_memory_check(probe.probe_cgroup_memory_max_bytes())


def _disk_free_check(free_bytes: int | None) -> DoctorCheck:
    if free_bytes is None:
        return DoctorCheck(
            name='/workspace free space',
            status=CheckStatus.WARN,
            detail='cannot determine',
            category=CATEGORY_RUNTIME,
        )
    detail = f'{free_bytes / 1024**3:.1f} GiB free'
    if free_bytes < DISK_FREE_FAIL_BYTES:
        return DoctorCheck(
            name='/workspace free space',
            status=CheckStatus.FAIL,
            detail=detail,
            category=CATEGORY_RUNTIME,
        )
    if free_bytes < DISK_FREE_WARN_BYTES:
        return DoctorCheck(
            name='/workspace free space',
            status=CheckStatus.WARN,
            detail=detail,
            category=CATEGORY_RUNTIME,
        )
    return DoctorCheck(
        name='/workspace free space',
        status=CheckStatus.OK,
        detail=detail,
        category=CATEGORY_RUNTIME,
    )


def _ulimit_check(nofile: int | None) -> DoctorCheck:
    if nofile is None:
        return DoctorCheck(
            name='ulimit -n',
            status=CheckStatus.WARN,
            detail='cannot determine',
            category=CATEGORY_RUNTIME,
        )
    if nofile < ULIMIT_NOFILE_WARN_THRESHOLD:
        return DoctorCheck(
            name='ulimit -n',
            status=CheckStatus.WARN,
            detail=f'{nofile} (< {ULIMIT_NOFILE_WARN_THRESHOLD})',
            category=CATEGORY_RUNTIME,
        )
    return DoctorCheck(
        name='ulimit -n',
        status=CheckStatus.OK,
        detail=str(nofile),
        category=CATEGORY_RUNTIME,
    )


def _cgroup_memory_check(limit_bytes: int | None) -> DoctorCheck:
    if limit_bytes is None:
        return DoctorCheck(
            name='cgroup memory.max',
            status=CheckStatus.WARN,
            detail='cannot determine',
            category=CATEGORY_RUNTIME,
        )
    if limit_bytes > CGROUP_MEMORY_UNLIMITED_BYTES:
        return DoctorCheck(
            name='cgroup memory.max',
            status=CheckStatus.OK,
            detail='unlimited (no cgroup limit)',
            category=CATEGORY_RUNTIME,
        )
    return DoctorCheck(
        name='cgroup memory.max',
        status=CheckStatus.OK,
        detail=f'{limit_bytes / 1024**3:.1f} GiB',
        category=CATEGORY_RUNTIME,
    )


__all__ = [
    'CGROUP_MEMORY_UNLIMITED_BYTES',
    'CREDENTIAL_FILE',
    'DISK_FREE_FAIL_BYTES',
    'DISK_FREE_WARN_BYTES',
    'IMAGE_VERSION_ENV',
    'MOUNT_POINTS',
    'TOOLCHAIN_COMMANDS',
    'TOOLCHAIN_PYTHON_LIBS',
    'ULIMIT_NOFILE_WARN_THRESHOLD',
    'CommandProbeSpec',
    'MountSpec',
    'PythonLibSpec',
    'run_doctor',
]
