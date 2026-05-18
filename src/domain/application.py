"""Application domain — known external apps + status (T009)."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class OsKind(StrEnum):
    LINUX = 'linux'
    WINDOWS = 'windows'
    MACOS = 'macos'


class ApplicationKind(StrEnum):
    KICAD = 'kicad'
    KICAD_CLI = 'kicad-cli'
    FREECAD = 'freecad'
    FEMM = 'femm'
    NGSPICE = 'ngspice'


class ApplicationStatus(StrEnum):
    NOT_INSTALLED = 'not_installed'
    INSTALLED_STOPPED = 'installed_stopped'
    RUNNING = 'running'


class ApplicationInfo(BaseModel):
    """Снимок состояния приложения на момент запроса (T009)."""

    model_config = ConfigDict(frozen=True)

    kind: ApplicationKind
    status: ApplicationStatus
    executable_path: Path | None = None
    pid: int | None = None
    version: str | None = None
