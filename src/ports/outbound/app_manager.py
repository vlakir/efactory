"""AppManager — outbound port для управления процессами внешних apps (T009)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain.application import ApplicationInfo, ApplicationKind


@dataclass(frozen=True)
class RunResult:
    """Результат blocking-вызова `run()` (T009 N3)."""

    returncode: int
    stdout: str
    stderr: str


class ApplicationNotInstalledError(Exception):
    """`resolve_command(kind)` вернул None — app не найден."""


class ApplicationStartError(Exception):
    """`launch` / `run` не смогли запустить subprocess."""


class ApplicationStopError(Exception):
    """`stop` не смог завершить процесс."""


class AppManager(Protocol):
    """
    Управление жизненным циклом внешних приложений (T009).

    Headless (`run`) и GUI (`launch`) — единый interface, разные
    semantics:
      - `run`: blocking subprocess.run, возвращает RunResult.
      - `launch`: detach background (Popen + start_new_session),
        возвращает ApplicationInfo с PID.

    PID registry — in-memory per-CLI-process (Resolved #2). Между
    CLI вызовами state не сохраняется.
    """

    async def status(self, kind: ApplicationKind) -> ApplicationInfo: ...

    async def launch(
        self,
        kind: ApplicationKind,
        args: list[str] | None = None,
    ) -> ApplicationInfo: ...

    async def run(
        self,
        kind: ApplicationKind,
        args: list[str] | None = None,
        *,
        timeout_seconds: float | None = None,
    ) -> RunResult: ...

    async def stop(self, kind: ApplicationKind) -> None: ...

    async def restart(self, kind: ApplicationKind) -> ApplicationInfo: ...
