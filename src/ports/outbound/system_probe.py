"""SystemProbe — outbound port для `efactory doctor` (T036).

Абстрагирует subprocess / FS / env probe-операции, чтобы use case
`run_doctor` оставался TDD-friendly (stub probe в тестах) и не зависел
от deployment контекста.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True, slots=True)
class CommandProbeResult:
    """Результат попытки запуска внешней команды (probe версии)."""

    found: bool
    stdout: str
    exit_code: int | None
    timed_out: bool


@dataclass(frozen=True, slots=True)
class PathProbeResult:
    """Результат проверки FS-пути (mount-точки или файла)."""

    exists: bool
    is_dir: bool
    is_file: bool
    writable: bool


class SystemProbe(Protocol):
    """Низкоуровневые probe-операции для диагностики окружения."""

    def probe_command(
        self,
        argv: tuple[str, ...],
        *,
        timeout_s: float = 5.0,
    ) -> CommandProbeResult: ...

    def probe_path(self, path: Path) -> PathProbeResult: ...

    def probe_env(self, name: str) -> str | None: ...

    def probe_python_package_version(self, package: str) -> str | None: ...

    def probe_disk_free_bytes(self, path: Path) -> int | None: ...

    def probe_ulimit_nofile(self) -> int | None: ...

    def probe_cgroup_memory_max_bytes(self) -> int | None: ...

    def probe_dri_devices(self) -> tuple[str, ...]: ...


__all__ = [
    'CommandProbeResult',
    'PathProbeResult',
    'SystemProbe',
]
