"""
NativePlatformLayer — resolve внешних приложений на текущей платформе (T009).

Strategy (от specific к generic):
1. Env override `EFACTORY_<KIND>_PATH=/path/to/binary`.
2. `shutil.which(binary_name)` — apt/snap/Homebrew installs в PATH.
3. `.desktop` файл `~/.local/share/applications/<kind>.desktop`,
   парсинг `Exec=` → первый non-flag path.
4. Known install paths (level-1 в `~/Applications/`, `~/Downloads/`,
   `~/Загрузки/`, `~/AppImages/`, `~/<app>/`).

Multi-call AppImage (T009 C2):
- KICAD GUI → `[<kicad.AppImage>]`.
- KICAD_CLI (внутри KiCad AppImage через sharun wrapper) →
  `[<kicad.AppImage>, 'kicad-cli']`.

`.desktop` parsing (C1): `shlex.split(Exec)`, отфильтровать
`%[fFuU]` placeholders и `--flag` arguments, взять первый
существующий absolute path.
"""

from __future__ import annotations

import os
import platform
import re
import shlex
import shutil
from pathlib import Path
from typing import Final

from domain.application import ApplicationKind, OsKind

# Имя binary в PATH для шага shutil.which.
_BINARY_NAMES: Final[dict[ApplicationKind, str]] = {
    ApplicationKind.KICAD: 'kicad',
    ApplicationKind.KICAD_CLI: 'kicad-cli',
    ApplicationKind.FREECAD: 'freecad',
    ApplicationKind.FEMM: 'femm',
    ApplicationKind.NGSPICE: 'ngspice',
}

# .desktop файл по соглашению (`~/.local/share/applications/`).
_DESKTOP_NAMES: Final[dict[ApplicationKind, str]] = {
    ApplicationKind.KICAD: 'kicad.desktop',
    ApplicationKind.FREECAD: 'freecad.desktop',
    ApplicationKind.FEMM: 'femm.desktop',
}

# Расширение AppImage glob: `<app>*.AppImage`.
_APPIMAGE_PATTERNS: Final[dict[ApplicationKind, list[str]]] = {
    ApplicationKind.KICAD: ['kicad*.AppImage', 'KiCad*.AppImage'],
    ApplicationKind.FREECAD: ['freecad*.AppImage', 'FreeCAD*.AppImage'],
}

# Каталоги где обычно лежат AppImage на Linux (level-1 scan).
_LINUX_APPIMAGE_DIRS: Final = (
    Path.home() / 'Applications',
    Path.home() / 'AppImages',
    Path.home() / 'Downloads',
    Path.home() / 'Загрузки',
    Path.home() / 'kicad',
    Path.home() / 'freecad',
)

# Windows known install paths.
_WINDOWS_PATHS: Final[dict[ApplicationKind, list[str]]] = {
    ApplicationKind.KICAD: [
        r'C:\Program Files\KiCad\10.0\bin\kicad.exe',
        r'C:\Program Files\KiCad\9.0\bin\kicad.exe',
    ],
    ApplicationKind.KICAD_CLI: [
        r'C:\Program Files\KiCad\10.0\bin\kicad-cli.exe',
        r'C:\Program Files\KiCad\9.0\bin\kicad-cli.exe',
    ],
    ApplicationKind.FREECAD: [
        r'C:\Program Files\FreeCAD 1.1\bin\freecad.exe',
        r'C:\Program Files\FreeCAD 1.0\bin\freecad.exe',
    ],
    ApplicationKind.FEMM: [r'C:\femm42\bin\femm.exe'],
    ApplicationKind.NGSPICE: [r'C:\Program Files\ngspice\bin\ngspice.exe'],
}

_DESKTOP_PLACEHOLDER_RE = re.compile(r'^%[fFuU]$')
_DESKTOP_EXEC_RE = re.compile(r'^Exec=(.+)$', re.MULTILINE)


def _env_var_for(kind: ApplicationKind) -> str:
    return f'EFACTORY_{kind.value.upper().replace("-", "_")}_PATH'


def _parse_desktop_exec(exec_line: str) -> Path | None:
    """Извлечь executable из Exec= строки .desktop файла (T009 C1)."""
    try:
        tokens = shlex.split(exec_line)
    except ValueError:
        return None
    for token in tokens:
        if token.startswith('-'):  # --flag, -short
            continue
        if _DESKTOP_PLACEHOLDER_RE.match(token):  # %f / %F / %u / %U
            continue
        # Берём первый кандидат, который выглядит как путь.
        candidate = Path(token)
        if candidate.is_absolute() and candidate.is_file():
            return candidate
        # Может быть относительный (редко в .desktop, но поддержим).
        resolved = shutil.which(token)
        if resolved:
            return Path(resolved)
    return None


def _read_desktop_executable(kind: ApplicationKind) -> Path | None:
    """Найти executable через `~/.local/share/applications/<kind>.desktop`."""
    desktop_name = _DESKTOP_NAMES.get(kind)
    if desktop_name is None:
        return None
    desktop_path = Path.home() / '.local' / 'share' / 'applications' / desktop_name
    if not desktop_path.is_file():
        return None
    try:
        content = desktop_path.read_text(encoding='utf-8', errors='ignore')
    except OSError:
        return None
    match = _DESKTOP_EXEC_RE.search(content)
    if match is None:
        return None
    return _parse_desktop_exec(match.group(1))


def _scan_appimage_locations(kind: ApplicationKind) -> Path | None:
    """Level-1 scan known dirs для AppImage с patterns (T009 N7)."""
    patterns = _APPIMAGE_PATTERNS.get(kind)
    if patterns is None:
        return None
    for directory in _LINUX_APPIMAGE_DIRS:
        if not directory.is_dir():
            continue
        for pattern in patterns:
            for candidate in sorted(directory.glob(pattern)):
                if candidate.is_file():
                    return candidate
    return None


def _command_prefix(kind: ApplicationKind, executable: Path) -> list[str]:
    """KICAD_CLI через KiCad AppImage = sharun wrapper (T009 C2)."""
    if kind is ApplicationKind.KICAD_CLI and executable.suffix == '.AppImage':
        # `kicad.AppImage kicad-cli <args>` — sharun multi-call.
        return [str(executable), 'kicad-cli']
    return [str(executable)]


def _detect_kicad_cli_via_kicad_appimage() -> Path | None:
    """KICAD_CLI fallback: если KiCad AppImage есть, он содержит kicad-cli."""
    for getter in (
        _env_kicad,
        lambda: _which(ApplicationKind.KICAD),
        lambda: _read_desktop_executable(ApplicationKind.KICAD),
        lambda: _scan_appimage_locations(ApplicationKind.KICAD),
    ):
        result = getter()
        if result is not None and result.suffix == '.AppImage':
            return result
    return None


def _env_kicad() -> Path | None:
    env_val = os.environ.get(_env_var_for(ApplicationKind.KICAD))
    if env_val:
        path = Path(env_val)
        if path.is_file():
            return path
    return None


def _which(kind: ApplicationKind) -> Path | None:
    binary = _BINARY_NAMES.get(kind)
    if binary is None:
        return None
    found = shutil.which(binary)
    return Path(found) if found else None


def _scan_windows_paths(kind: ApplicationKind) -> Path | None:
    for raw in _WINDOWS_PATHS.get(kind, []):
        path = Path(raw)
        if path.is_file():
            return path
    return None


def _detect_os_kind() -> OsKind:
    name = platform.system().lower()
    if name == 'linux':
        return OsKind.LINUX
    if name == 'windows':
        return OsKind.WINDOWS
    if name == 'darwin':
        return OsKind.MACOS
    msg = f'Unsupported platform: {name}'
    raise NotImplementedError(msg)


class NativePlatformLayer:
    def __init__(self) -> None:
        self._os_kind = _detect_os_kind()

    def os_kind(self) -> OsKind:
        return self._os_kind

    def resolve_command(self, kind: ApplicationKind) -> list[str] | None:
        executable = self._resolve_executable(kind)
        if executable is None:
            return None
        return _command_prefix(kind, executable)

    def _resolve_executable(self, kind: ApplicationKind) -> Path | None:
        """Цепочка resolvers; первый non-None выигрывает."""
        for resolver in self._resolvers_for(kind):
            result = resolver(kind)
            if result is not None:
                return result
        return None

    def _resolvers_for(
        self,
        kind: ApplicationKind,
    ) -> list:
        common = [_resolve_env, _which, _read_desktop_executable]
        if self._os_kind is OsKind.WINDOWS:
            return [*common, _scan_windows_paths]
        if self._os_kind is OsKind.LINUX:
            linux = [*common, _scan_appimage_locations]
            if kind is ApplicationKind.KICAD_CLI:
                linux.append(_resolve_kicad_cli_via_kicad_appimage)
            return linux
        return common  # macOS: только PATH + .desktop


def _resolve_env(kind: ApplicationKind) -> Path | None:
    env_val = os.environ.get(_env_var_for(kind))
    if env_val:
        path = Path(env_val)
        if path.is_file():
            return path
    return None


def _resolve_kicad_cli_via_kicad_appimage(
    kind: ApplicationKind,
) -> Path | None:
    if kind is not ApplicationKind.KICAD_CLI:
        return None
    return _detect_kicad_cli_via_kicad_appimage()


__all__ = ['NativePlatformLayer']
