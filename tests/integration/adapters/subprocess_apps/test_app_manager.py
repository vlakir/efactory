"""Integration: SubprocessAppManager (T009).

Через stub PlatformLayer возвращающий `/bin/sleep` / `/bin/echo` —
не зависим от KiCad/FreeCAD. Покрывает full lifecycle:
status / launch / run / stop / restart.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from adapters.outbound.subprocess_apps.app_manager import (
    SubprocessAppManager,
)
from domain.application import (
    ApplicationKind,
    ApplicationStatus,
    OsKind,
)
from ports.outbound.app_manager import (
    ApplicationNotInstalledError,
    ApplicationStartError,
)

if TYPE_CHECKING:
    pass


class StubPlatformLayer:
    """Тестовый stub — возвращает заданный command per kind."""

    def __init__(self, commands: dict[ApplicationKind, list[str]]) -> None:
        self._commands = commands

    def os_kind(self) -> OsKind:
        return OsKind.LINUX

    def resolve_command(self, kind: ApplicationKind) -> list[str] | None:
        return self._commands.get(kind)


needs_sleep = pytest.mark.skipif(
    shutil.which('sleep') is None,
    reason='/bin/sleep required for launch lifecycle test',
)
needs_echo = pytest.mark.skipif(
    shutil.which('echo') is None,
    reason='/bin/echo required for run test',
)


async def test_status_not_installed_when_resolve_returns_none() -> None:
    manager = SubprocessAppManager(StubPlatformLayer({}))

    info = await manager.status(ApplicationKind.FEMM)

    assert info.status is ApplicationStatus.NOT_INSTALLED
    assert info.executable_path is None
    assert info.pid is None


async def test_status_installed_stopped_when_resolved_but_not_launched() -> None:
    sleep_path = shutil.which('sleep')
    manager = SubprocessAppManager(
        StubPlatformLayer({ApplicationKind.KICAD: [sleep_path, '10']}),
    )

    info = await manager.status(ApplicationKind.KICAD)

    assert info.status is ApplicationStatus.INSTALLED_STOPPED
    assert info.executable_path == Path(sleep_path)
    assert info.pid is None


@needs_sleep
async def test_launch_returns_running_with_pid() -> None:
    sleep_path = shutil.which('sleep')
    manager = SubprocessAppManager(
        StubPlatformLayer({ApplicationKind.KICAD: [sleep_path]}),
    )

    info = await manager.launch(ApplicationKind.KICAD, ['10'])

    try:
        assert info.status is ApplicationStatus.RUNNING
        assert info.pid is not None
        assert info.executable_path == Path(sleep_path)

        # status повторно возвращает RUNNING.
        again = await manager.status(ApplicationKind.KICAD)
        assert again.status is ApplicationStatus.RUNNING
        assert again.pid == info.pid
    finally:
        await manager.stop(ApplicationKind.KICAD)


@needs_sleep
async def test_launch_raises_for_not_installed() -> None:
    manager = SubprocessAppManager(StubPlatformLayer({}))

    with pytest.raises(ApplicationNotInstalledError):
        await manager.launch(ApplicationKind.FEMM)


@needs_sleep
async def test_stop_terminates_running_process() -> None:
    sleep_path = shutil.which('sleep')
    manager = SubprocessAppManager(
        StubPlatformLayer({ApplicationKind.KICAD: [sleep_path]}),
    )

    info = await manager.launch(ApplicationKind.KICAD, ['10'])
    pid = info.pid
    assert pid is not None

    await manager.stop(ApplicationKind.KICAD)

    final = await manager.status(ApplicationKind.KICAD)
    assert final.status is ApplicationStatus.INSTALLED_STOPPED
    assert final.pid is None


@needs_sleep
async def test_stop_is_noop_when_not_running() -> None:
    sleep_path = shutil.which('sleep')
    manager = SubprocessAppManager(
        StubPlatformLayer({ApplicationKind.KICAD: [sleep_path]}),
    )

    # Не падает.
    await manager.stop(ApplicationKind.KICAD)


@needs_sleep
async def test_status_detects_stale_pid_after_process_exits() -> None:
    """W1: процесс завершился сам → status переходит в INSTALLED_STOPPED."""
    sleep_path = shutil.which('sleep')
    manager = SubprocessAppManager(
        StubPlatformLayer({ApplicationKind.KICAD: [sleep_path]}),
    )

    await manager.launch(ApplicationKind.KICAD, ['0.1'])  # умрёт через 0.1s
    time.sleep(0.3)

    info = await manager.status(ApplicationKind.KICAD)
    assert info.status is ApplicationStatus.INSTALLED_STOPPED
    assert info.pid is None


@needs_sleep
async def test_restart_replaces_pid() -> None:
    sleep_path = shutil.which('sleep')
    manager = SubprocessAppManager(
        StubPlatformLayer({ApplicationKind.KICAD: [sleep_path]}),
    )

    first = await manager.launch(ApplicationKind.KICAD, ['10'])
    try:
        second = await manager.restart(ApplicationKind.KICAD)
        try:
            assert second.status is ApplicationStatus.RUNNING
            assert second.pid != first.pid
        finally:
            await manager.stop(ApplicationKind.KICAD)
    except Exception:
        await manager.stop(ApplicationKind.KICAD)
        raise


@needs_echo
async def test_run_captures_stdout_and_returncode() -> None:
    echo_path = shutil.which('echo')
    manager = SubprocessAppManager(
        StubPlatformLayer({ApplicationKind.NGSPICE: [echo_path]}),
    )

    result = await manager.run(ApplicationKind.NGSPICE, ['hello'])

    assert result.returncode == 0
    assert result.stdout.strip() == 'hello'
    assert result.stderr == ''


@needs_sleep
async def test_run_timeout_raises_application_start_error() -> None:
    sleep_path = shutil.which('sleep')
    manager = SubprocessAppManager(
        StubPlatformLayer({ApplicationKind.NGSPICE: [sleep_path]}),
    )

    with pytest.raises(ApplicationStartError):
        await manager.run(
            ApplicationKind.NGSPICE, ['5'], timeout_seconds=0.5,
        )


async def test_run_raises_for_not_installed() -> None:
    manager = SubprocessAppManager(StubPlatformLayer({}))

    with pytest.raises(ApplicationNotInstalledError):
        await manager.run(ApplicationKind.NGSPICE, ['--version'])
