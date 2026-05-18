"""
SubprocessAppManager — управление процессами через `subprocess` (T009).

Headless (`run`): blocking `subprocess.run(..., capture_output=True,
text=True, timeout=...)`, возвращает RunResult.

GUI (`launch`): `subprocess.Popen(..., start_new_session=True)` на
POSIX, `creationflags=DETACHED_PROCESS|CREATE_NEW_PROCESS_GROUP` на
Windows. PID хранится в in-memory registry per-process.

Stop semantics (N6): `process.terminate()` → wait 5s → `process.kill()`
если ещё жив.

Status (W1): `process.poll()` для проверки stale PID; если завершился
— чистим из registry, status = INSTALLED_STOPPED.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

from domain.application import (
    ApplicationInfo,
    ApplicationKind,
    ApplicationStatus,
)
from ports.outbound.app_manager import (
    ApplicationNotInstalledError,
    ApplicationStartError,
    ApplicationStopError,
    RunResult,
)

if TYPE_CHECKING:
    from ports.outbound.platform_layer import PlatformLayer

_STOP_GRACE_SECONDS: Final = 5.0


def _detach_kwargs() -> dict:
    """
    Platform-specific kwargs для detached background Popen (T009 C3).

    Windows: DETACHED_PROCESS (0x00000008) + CREATE_NEW_PROCESS_GROUP.
    POSIX: start_new_session=True (отвязка от tty).
    """
    if sys.platform.startswith('win'):
        creationflags = (
            subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
            | subprocess.CREATE_NEW_PROCESS_GROUP
        )
        return {'creationflags': creationflags}
    return {'start_new_session': True}


class SubprocessAppManager:
    def __init__(self, platform_layer: PlatformLayer) -> None:
        self._platform = platform_layer
        self._processes: dict[ApplicationKind, subprocess.Popen[bytes]] = {}

    async def status(self, kind: ApplicationKind) -> ApplicationInfo:
        return await asyncio.to_thread(self._status_sync, kind)

    def _status_sync(self, kind: ApplicationKind) -> ApplicationInfo:
        command = self._platform.resolve_command(kind)
        if command is None:
            return ApplicationInfo(
                kind=kind,
                status=ApplicationStatus.NOT_INSTALLED,
            )
        executable = Path(command[0])

        process = self._processes.get(kind)
        if process is None:
            return ApplicationInfo(
                kind=kind,
                status=ApplicationStatus.INSTALLED_STOPPED,
                executable_path=executable,
            )
        # W1: проверка stale PID.
        if process.poll() is not None:
            # Завершился сам — чистим registry.
            self._processes.pop(kind, None)
            return ApplicationInfo(
                kind=kind,
                status=ApplicationStatus.INSTALLED_STOPPED,
                executable_path=executable,
            )
        return ApplicationInfo(
            kind=kind,
            status=ApplicationStatus.RUNNING,
            executable_path=executable,
            pid=process.pid,
        )

    async def launch(
        self,
        kind: ApplicationKind,
        args: list[str] | None = None,
    ) -> ApplicationInfo:
        return await asyncio.to_thread(self._launch_sync, kind, args or [])

    def _launch_sync(
        self,
        kind: ApplicationKind,
        args: list[str],
    ) -> ApplicationInfo:
        command = self._platform.resolve_command(kind)
        if command is None:
            msg = f'Application {kind.value} not found on this system'
            raise ApplicationNotInstalledError(msg)
        argv = [*command, *args]
        try:
            process = subprocess.Popen(
                argv,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                **_detach_kwargs(),
            )
        except OSError as exc:
            msg = f'Failed to launch {kind.value}: {exc}'
            raise ApplicationStartError(msg) from exc
        self._processes[kind] = process
        return ApplicationInfo(
            kind=kind,
            status=ApplicationStatus.RUNNING,
            executable_path=Path(command[0]),
            pid=process.pid,
        )

    async def run(
        self,
        kind: ApplicationKind,
        args: list[str] | None = None,
        *,
        timeout_seconds: float | None = None,
    ) -> RunResult:
        return await asyncio.to_thread(
            self._run_sync,
            kind,
            args or [],
            timeout_seconds,
        )

    def _run_sync(
        self,
        kind: ApplicationKind,
        args: list[str],
        timeout_seconds: float | None,
    ) -> RunResult:
        command = self._platform.resolve_command(kind)
        if command is None:
            msg = f'Application {kind.value} not found on this system'
            raise ApplicationNotInstalledError(msg)
        argv = [*command, *args]
        try:
            completed = subprocess.run(
                argv,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            msg = f'Failed to run {kind.value}: {exc}'
            raise ApplicationStartError(msg) from exc
        return RunResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    async def stop(self, kind: ApplicationKind) -> None:
        return await asyncio.to_thread(self._stop_sync, kind)

    def _stop_sync(self, kind: ApplicationKind) -> None:
        process = self._processes.get(kind)
        if process is None:
            return  # nothing to stop
        if process.poll() is not None:
            # Уже завершился сам.
            self._processes.pop(kind, None)
            return
        try:
            process.terminate()
            try:
                process.wait(timeout=_STOP_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        except OSError as exc:
            msg = f'Failed to stop {kind.value}: {exc}'
            raise ApplicationStopError(msg) from exc
        finally:
            self._processes.pop(kind, None)

    async def restart(self, kind: ApplicationKind) -> ApplicationInfo:
        await self.stop(kind)
        return await self.launch(kind)


__all__ = ['SubprocessAppManager']
