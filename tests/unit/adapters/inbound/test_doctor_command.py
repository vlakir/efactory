"""Unit-тесты для `efactory doctor` CLI команды (T036)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import typer
from typer.testing import CliRunner

from adapters.inbound.cli.doctor_command import register_doctor_command
from application.run_doctor import (
    CREDENTIAL_FILE,
    IMAGE_VERSION_ENV,
    MOUNT_POINTS,
    TOOLCHAIN_COMMANDS,
    TOOLCHAIN_PYTHON_LIBS,
)
from ports.outbound.system_probe import (
    CommandProbeResult,
    PathProbeResult,
)


@dataclass(slots=True)
class _Probe:
    commands: dict[tuple[str, ...], CommandProbeResult] = field(
        default_factory=dict,
    )
    paths: dict[Path, PathProbeResult] = field(default_factory=dict)
    envs: dict[str, str | None] = field(default_factory=dict)
    py_versions: dict[str, str | None] = field(default_factory=dict)
    disk_free: dict[Path, int | None] = field(default_factory=dict)
    ulimit_nofile: int | None = 65535
    cgroup_memory_max: int | None = 8 * 1024**3
    dri_devices: tuple[str, ...] = ()
    last_include_gui_seen: bool = True

    def probe_command(
        self,
        argv: tuple[str, ...],
        *,
        timeout_s: float = 5.0,
    ) -> CommandProbeResult:
        del timeout_s
        return self.commands.get(
            tuple(argv),
            CommandProbeResult(
                found=False,
                stdout='',
                exit_code=None,
                timed_out=False,
            ),
        )

    def probe_path(self, path: Path) -> PathProbeResult:
        return self.paths.get(
            path,
            PathProbeResult(
                exists=False,
                is_dir=False,
                is_file=False,
                writable=False,
            ),
        )

    def probe_env(self, name: str) -> str | None:
        return self.envs.get(name)

    def probe_python_package_version(self, package: str) -> str | None:
        return self.py_versions.get(package)

    def probe_disk_free_bytes(self, path: Path) -> int | None:
        return self.disk_free.get(path)

    def probe_ulimit_nofile(self) -> int | None:
        return self.ulimit_nofile

    def probe_cgroup_memory_max_bytes(self) -> int | None:
        return self.cgroup_memory_max

    def probe_dri_devices(self) -> tuple[str, ...]:
        return self.dri_devices


def _populate_happy(probe: _Probe) -> None:
    probe.envs[IMAGE_VERSION_ENV] = 'linux-dev'
    probe.envs['DISPLAY'] = ':0'
    for spec in TOOLCHAIN_COMMANDS:
        probe.commands[tuple(spec.argv)] = CommandProbeResult(
            found=True,
            stdout='9.9.9',
            exit_code=0,
            timed_out=False,
        )
    probe.commands[('xset', 'q')] = CommandProbeResult(
        found=True,
        stdout='Keyboard',
        exit_code=0,
        timed_out=False,
    )
    for spec in TOOLCHAIN_PYTHON_LIBS:
        probe.py_versions[spec.package] = '1.0.0'
    for mount in MOUNT_POINTS:
        probe.paths[mount.path] = PathProbeResult(
            exists=True,
            is_dir=True,
            is_file=False,
            writable=True,
        )
    probe.paths[CREDENTIAL_FILE] = PathProbeResult(
        exists=True,
        is_dir=False,
        is_file=True,
        writable=True,
    )
    probe.disk_free[Path('/workspace')] = 20 * 1024**3
    probe.dri_devices = ('/dev/dri/card0',)


def _build_cli(probe: _Probe) -> typer.Typer:
    app = typer.Typer()
    register_doctor_command(app, system_probe=probe)

    # typer.Typer схлопывает single-command app в root-callable: чтобы
    # invoke ['doctor', ...] работал как subcommand (как в реальном
    # `efactory doctor`), регистрируем dummy второй command.
    @app.command('_noop')
    def _noop() -> None:
        pass

    return app


def test_doctor_exits_0_on_happy_path() -> None:
    probe = _Probe()
    _populate_happy(probe)
    result = CliRunner().invoke(_build_cli(probe), ['doctor'])
    assert result.exit_code == 0, result.output
    assert 'worst=OK' in result.output


def test_doctor_exits_0_on_warn_only() -> None:
    probe = _Probe()
    _populate_happy(probe)
    probe.envs['DISPLAY'] = None  # WARN, not FAIL
    result = CliRunner().invoke(_build_cli(probe), ['doctor'])
    assert result.exit_code == 0
    assert 'worst=WARN' in result.output


def test_doctor_exits_1_on_fail() -> None:
    probe = _Probe()
    _populate_happy(probe)
    probe.commands[('kicad-cli', '--version')] = CommandProbeResult(
        found=False,
        stdout='',
        exit_code=None,
        timed_out=False,
    )
    result = CliRunner().invoke(_build_cli(probe), ['doctor'])
    assert result.exit_code == 1
    assert 'worst=FAIL' in result.output


def test_doctor_no_gui_flag_skips_gui_block() -> None:
    probe = _Probe()
    _populate_happy(probe)
    result = CliRunner().invoke(_build_cli(probe), ['doctor', '--no-gui'])
    assert result.exit_code == 0
    assert 'GUI passthrough' not in result.output


def test_doctor_default_includes_gui_block() -> None:
    probe = _Probe()
    _populate_happy(probe)
    result = CliRunner().invoke(_build_cli(probe), ['doctor'])
    assert result.exit_code == 0
    assert 'GUI passthrough' in result.output
