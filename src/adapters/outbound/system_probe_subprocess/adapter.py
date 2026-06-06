"""
SystemProbeSubprocess — реальная имплементация SystemProbe (T036).

Использует subprocess / stdlib (os, shutil, resource, importlib.metadata,
pathlib) — никакой обёртки над AppManager: probe-операции должны
работать даже когда тулчейн поломан.
"""

from __future__ import annotations

import os
import resource
import shutil
import subprocess
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from ports.outbound.system_probe import (
    CommandProbeResult,
    PathProbeResult,
)

_CGROUP_V2_MEMORY_MAX = Path('/sys/fs/cgroup/memory.max')
_CGROUP_V1_MEMORY_LIMIT = Path('/sys/fs/cgroup/memory/memory.limit_in_bytes')
_DRI_ROOT = Path('/dev/dri')
_MAX_STDOUT_LINE_LEN = 200


class SystemProbeSubprocess:
    """Реальный SystemProbe — subprocess + stdlib FS / env / pkg-version."""

    def probe_command(
        self,
        argv: tuple[str, ...],
        *,
        timeout_s: float = 5.0,
    ) -> CommandProbeResult:
        if not argv:
            return CommandProbeResult(
                found=False,
                stdout='',
                exit_code=None,
                timed_out=False,
            )
        if shutil.which(argv[0]) is None:
            return CommandProbeResult(
                found=False,
                stdout='',
                exit_code=None,
                timed_out=False,
            )
        try:
            result = subprocess.run(
                list(argv),
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            return CommandProbeResult(
                found=True,
                stdout='',
                exit_code=None,
                timed_out=True,
            )
        except OSError:
            return CommandProbeResult(
                found=False,
                stdout='',
                exit_code=None,
                timed_out=False,
            )
        return CommandProbeResult(
            found=True,
            stdout=_first_non_empty_line(result.stdout, result.stderr),
            exit_code=result.returncode,
            timed_out=False,
        )

    def probe_path(self, path: Path) -> PathProbeResult:
        exists = path.exists()
        if not exists:
            return PathProbeResult(
                exists=False,
                is_dir=False,
                is_file=False,
                writable=False,
            )
        is_dir = path.is_dir()
        is_file = path.is_file()
        writable = os.access(path, os.W_OK)
        return PathProbeResult(
            exists=True,
            is_dir=is_dir,
            is_file=is_file,
            writable=writable,
        )

    def probe_env(self, name: str) -> str | None:
        raw = os.environ.get(name)
        if raw is None or raw == '':
            return None
        return raw

    def probe_python_package_version(self, package: str) -> str | None:
        try:
            return version(package)
        except PackageNotFoundError:
            return None

    def probe_disk_free_bytes(self, path: Path) -> int | None:
        try:
            return shutil.disk_usage(path).free
        except OSError:
            return None

    def probe_ulimit_nofile(self) -> int | None:
        try:
            soft, _hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        except (OSError, ValueError):
            return None
        return soft

    def probe_cgroup_memory_max_bytes(self) -> int | None:
        if _CGROUP_V2_MEMORY_MAX.is_file():
            return _read_cgroup_v2_memory_max()
        if _CGROUP_V1_MEMORY_LIMIT.is_file():
            return _read_cgroup_v1_memory_limit()
        return None

    def probe_dri_devices(self) -> tuple[str, ...]:
        if not _DRI_ROOT.is_dir():
            return ()
        try:
            return tuple(sorted(str(p) for p in _DRI_ROOT.iterdir()))
        except OSError:
            return ()


def _read_cgroup_v2_memory_max() -> int | None:
    try:
        raw = _CGROUP_V2_MEMORY_MAX.read_text().strip()
    except OSError:
        return None
    if raw == 'max':
        return 2**63 - 1
    try:
        return int(raw)
    except ValueError:
        return None


def _read_cgroup_v1_memory_limit() -> int | None:
    try:
        return int(_CGROUP_V1_MEMORY_LIMIT.read_text().strip())
    except (OSError, ValueError):
        return None


def _first_non_empty_line(stdout: str, stderr: str) -> str:
    for blob in (stdout, stderr):
        for line in blob.splitlines():
            stripped = line.strip()
            if stripped:
                return stripped[:_MAX_STDOUT_LINE_LEN]
    return ''


__all__ = ['SystemProbeSubprocess']
