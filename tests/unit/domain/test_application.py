"""Domain: ApplicationKind / Status / Info / OsKind (T009)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from domain.application import (
    ApplicationInfo,
    ApplicationKind,
    ApplicationStatus,
    OsKind,
)


def test_application_kind_enum() -> None:
    assert set(ApplicationKind) == {
        ApplicationKind.KICAD,
        ApplicationKind.KICAD_CLI,
        ApplicationKind.FREECAD,
        ApplicationKind.FEMM,
        ApplicationKind.NGSPICE,
    }
    assert ApplicationKind.KICAD_CLI.value == 'kicad-cli'


def test_application_status_enum() -> None:
    assert ApplicationStatus.NOT_INSTALLED.value == 'not_installed'
    assert ApplicationStatus.INSTALLED_STOPPED.value == 'installed_stopped'
    assert ApplicationStatus.RUNNING.value == 'running'


def test_os_kind_enum() -> None:
    assert set(OsKind) == {OsKind.LINUX, OsKind.WINDOWS, OsKind.MACOS}


def test_application_info_running_with_pid() -> None:
    info = ApplicationInfo(
        kind=ApplicationKind.KICAD,
        status=ApplicationStatus.RUNNING,
        executable_path=Path('/home/u/kicad.AppImage'),
        pid=12345,
        version='10.0.2',
    )
    assert info.pid == 12345
    assert info.status is ApplicationStatus.RUNNING


def test_application_info_not_installed_defaults() -> None:
    info = ApplicationInfo(
        kind=ApplicationKind.FEMM,
        status=ApplicationStatus.NOT_INSTALLED,
    )
    assert info.executable_path is None
    assert info.pid is None
    assert info.version is None


def test_application_info_is_frozen() -> None:
    info = ApplicationInfo(
        kind=ApplicationKind.KICAD,
        status=ApplicationStatus.NOT_INSTALLED,
    )
    with pytest.raises(ValidationError):
        info.pid = 999  # type: ignore[misc]
