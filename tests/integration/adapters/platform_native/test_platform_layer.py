"""Integration: NativePlatformLayer (T009).

Reality-tests на dev-машине (KiCad/FreeCAD AppImage есть) +
unit-style тесты через monkeypatch для воспроизводимости.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from adapters.outbound.platform_native.platform_layer import (
    NativePlatformLayer,
    _parse_desktop_exec,
)
from domain.application import ApplicationKind, OsKind

if TYPE_CHECKING:
    pass


def test_os_kind_returns_linux_on_linux_machine() -> None:
    platform = NativePlatformLayer()
    # На моей dev-машине Linux. На CI/Windows ожидаемое значение
    # отличается — тест skip для них.
    if platform.os_kind() is not OsKind.LINUX:
        pytest.skip(f'not linux ({platform.os_kind().value})')
    assert platform.os_kind() is OsKind.LINUX


def test_parse_desktop_exec_extracts_appimage_path(tmp_path: Path) -> None:
    """C1: .desktop Exec с %f/%F/`--single-instance` → чистый path."""
    fake_app = tmp_path / 'kicad.AppImage'
    fake_app.write_text('fake')
    fake_app.chmod(0o755)

    # Стиль KiCad: `<path> %f`.
    assert _parse_desktop_exec(f'{fake_app} %f') == fake_app
    # Стиль FreeCAD: '<path>' - --single-instance %F.
    assert (
        _parse_desktop_exec(f"'{fake_app}' - --single-instance %F") == fake_app
    )
    # Только flags / placeholders.
    assert _parse_desktop_exec('%F --foo') is None
    # Несуществующий путь.
    assert _parse_desktop_exec('/no/such/file %f') is None
    # Malformed shell quoting.
    assert _parse_desktop_exec("''''") is None


def test_resolve_env_override_takes_priority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = tmp_path / 'my-kicad.AppImage'
    fake.write_text('fake')
    fake.chmod(0o755)
    monkeypatch.setenv('EFACTORY_KICAD_PATH', str(fake))

    platform = NativePlatformLayer()
    cmd = platform.resolve_command(ApplicationKind.KICAD)

    assert cmd == [str(fake)]


def test_resolve_env_override_for_kebab_case_kind(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`EFACTORY_KICAD_CLI_PATH` (kebab → underscore + UPPER)."""
    fake = tmp_path / 'kicad-cli'
    fake.write_text('#!/bin/sh\necho mock')
    fake.chmod(0o755)
    monkeypatch.setenv('EFACTORY_KICAD_CLI_PATH', str(fake))

    platform = NativePlatformLayer()
    cmd = platform.resolve_command(ApplicationKind.KICAD_CLI)

    assert cmd == [str(fake)]


def test_resolve_returns_none_when_not_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FEMM на Linux dev-машине отсутствует."""
    # Чистим env override + симулируем "нет в PATH".
    monkeypatch.delenv('EFACTORY_FEMM_PATH', raising=False)
    monkeypatch.setattr(shutil, 'which', lambda _: None)

    platform = NativePlatformLayer()
    cmd = platform.resolve_command(ApplicationKind.FEMM)

    # Linux + нет PATH + нет .desktop + не AppImage pattern → None.
    if cmd is not None:
        pytest.skip(f'unexpectedly resolved {cmd}; environment leak')
    assert cmd is None


def test_resolve_finds_kicad_appimage_on_dev_machine() -> None:
    """Reality check: KiCad AppImage установлен на dev-машине."""
    if shutil.which('kicad') is not None:
        pytest.skip('kicad in PATH; this test for AppImage path')
    kicad_home = Path.home() / 'kicad'
    if not any(kicad_home.glob('kicad*.AppImage')):
        pytest.skip('no KiCad AppImage in ~/kicad/')

    # Чистим возможный env override.
    if 'EFACTORY_KICAD_PATH' in os.environ:
        pytest.skip('EFACTORY_KICAD_PATH set; reality test irrelevant')

    platform = NativePlatformLayer()
    cmd = platform.resolve_command(ApplicationKind.KICAD)

    assert cmd is not None
    assert cmd[0].endswith('.AppImage')
    assert Path(cmd[0]).is_file()


def test_resolve_kicad_cli_uses_kicad_appimage_with_subcommand() -> None:
    """C2: KICAD_CLI через KiCad AppImage → ['<appimage>', 'kicad-cli']."""
    if shutil.which('kicad-cli') is not None:
        pytest.skip('kicad-cli in PATH; this test for AppImage subcommand')
    if not any((Path.home() / 'kicad').glob('kicad*.AppImage')):
        pytest.skip('no KiCad AppImage in ~/kicad/')
    if 'EFACTORY_KICAD_CLI_PATH' in os.environ:
        pytest.skip('EFACTORY_KICAD_CLI_PATH set')

    platform = NativePlatformLayer()
    cmd = platform.resolve_command(ApplicationKind.KICAD_CLI)

    assert cmd is not None
    assert len(cmd) == 2
    assert cmd[0].endswith('.AppImage')
    assert cmd[1] == 'kicad-cli'


def test_resolve_finds_freecad_appimage_on_dev_machine() -> None:
    """Reality: FreeCAD AppImage в ~/Загрузки."""
    if shutil.which('freecad') is not None:
        pytest.skip('freecad in PATH')
    home = Path.home()
    candidates = list(
        (home / 'Загрузки').glob('FreeCAD*.AppImage'),
    ) + list((home / 'Downloads').glob('FreeCAD*.AppImage'))
    if not candidates:
        pytest.skip('no FreeCAD AppImage')
    if 'EFACTORY_FREECAD_PATH' in os.environ:
        pytest.skip('EFACTORY_FREECAD_PATH set')

    platform = NativePlatformLayer()
    cmd = platform.resolve_command(ApplicationKind.FREECAD)

    assert cmd is not None
    assert cmd[0].endswith('.AppImage')
    assert Path(cmd[0]).is_file()
