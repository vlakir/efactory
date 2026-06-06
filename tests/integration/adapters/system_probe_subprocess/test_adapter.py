"""Integration-тесты для `SystemProbeSubprocess` (T036).

Используют реально доступные probe-цели (`python --version`, `git
--version`) + tmp-paths. Probe тулчейна efactory:linux (kicad-cli,
ngspice, Elmer и т.д.) НЕ проверяем здесь — это работа смок-теста в
контейнере.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from adapters.outbound.system_probe_subprocess.adapter import (
    SystemProbeSubprocess,
)


def test_probe_command_python_version() -> None:
    probe = SystemProbeSubprocess()
    result = probe.probe_command(('python', '--version'))
    assert result.found
    assert result.exit_code == 0
    assert not result.timed_out
    assert 'Python' in result.stdout


def test_probe_command_git_version() -> None:
    probe = SystemProbeSubprocess()
    result = probe.probe_command(('git', '--version'))
    assert result.found
    assert result.exit_code == 0
    assert 'git version' in result.stdout


def test_probe_command_not_found_returns_found_false() -> None:
    probe = SystemProbeSubprocess()
    result = probe.probe_command(('this-binary-does-not-exist-12345',))
    assert not result.found
    assert result.exit_code is None
    assert result.stdout == ''


def test_probe_command_empty_argv_returns_found_false() -> None:
    probe = SystemProbeSubprocess()
    result = probe.probe_command(())
    assert not result.found


def test_probe_command_timeout(tmp_path: Path) -> None:
    """sleep 5 с timeout 0.5 → должен пометить timed_out."""
    probe = SystemProbeSubprocess()
    result = probe.probe_command(('sleep', '5'), timeout_s=0.5)
    assert result.found
    assert result.timed_out


def test_probe_path_existing_dir(tmp_path: Path) -> None:
    probe = SystemProbeSubprocess()
    result = probe.probe_path(tmp_path)
    assert result.exists
    assert result.is_dir
    assert not result.is_file
    assert result.writable


def test_probe_path_existing_file(tmp_path: Path) -> None:
    f = tmp_path / 'a.txt'
    f.write_text('x')
    probe = SystemProbeSubprocess()
    result = probe.probe_path(f)
    assert result.exists
    assert result.is_file
    assert not result.is_dir


def test_probe_path_missing(tmp_path: Path) -> None:
    probe = SystemProbeSubprocess()
    result = probe.probe_path(tmp_path / 'nope')
    assert not result.exists


def test_probe_env_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('EFACTORY_TEST_PROBE_VAR', 'hello')
    probe = SystemProbeSubprocess()
    assert probe.probe_env('EFACTORY_TEST_PROBE_VAR') == 'hello'


def test_probe_env_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('EFACTORY_TEST_PROBE_VAR_X', raising=False)
    probe = SystemProbeSubprocess()
    assert probe.probe_env('EFACTORY_TEST_PROBE_VAR_X') is None


def test_probe_env_empty_treated_as_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('EFACTORY_TEST_PROBE_VAR_EMPTY', '')
    probe = SystemProbeSubprocess()
    assert probe.probe_env('EFACTORY_TEST_PROBE_VAR_EMPTY') is None


def test_probe_python_package_version_installed() -> None:
    probe = SystemProbeSubprocess()
    # pydantic — точно установлен (dep efactory)
    v = probe.probe_python_package_version('pydantic')
    assert v is not None
    assert v[0].isdigit()


def test_probe_python_package_version_missing() -> None:
    probe = SystemProbeSubprocess()
    assert (
        probe.probe_python_package_version('this-pkg-does-not-exist-12345')
        is None
    )


def test_probe_disk_free_bytes_positive(tmp_path: Path) -> None:
    probe = SystemProbeSubprocess()
    free = probe.probe_disk_free_bytes(tmp_path)
    assert free is not None
    assert free > 0


def test_probe_ulimit_nofile_positive() -> None:
    probe = SystemProbeSubprocess()
    nofile = probe.probe_ulimit_nofile()
    assert nofile is not None
    assert nofile > 0


def test_probe_cgroup_memory_max_returns_int_or_none() -> None:
    probe = SystemProbeSubprocess()
    result = probe.probe_cgroup_memory_max_bytes()
    assert result is None or isinstance(result, int)


def test_probe_dri_devices_tuple_of_strings() -> None:
    probe = SystemProbeSubprocess()
    devices = probe.probe_dri_devices()
    assert isinstance(devices, tuple)
    for d in devices:
        assert d.startswith('/dev/dri/')
