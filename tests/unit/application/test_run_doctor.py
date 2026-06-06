"""Unit-тесты для `run_doctor` use case (T036)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from application.run_doctor import (
    CGROUP_MEMORY_UNLIMITED_BYTES,
    CREDENTIAL_FILE,
    DISK_FREE_FAIL_BYTES,
    DISK_FREE_WARN_BYTES,
    IMAGE_VERSION_ENV,
    MOUNT_POINTS,
    TOOLCHAIN_COMMANDS,
    TOOLCHAIN_PYTHON_LIBS,
    ULIMIT_NOFILE_WARN_THRESHOLD,
    run_doctor,
)
from domain.doctor import (
    CATEGORY_GUI,
    CATEGORY_MOUNTS,
    CATEGORY_RUNTIME,
    CATEGORY_TOOLCHAIN,
    CheckStatus,
)
from ports.outbound.system_probe import (
    CommandProbeResult,
    PathProbeResult,
)


@dataclass(slots=True)
class StubProbe:
    """Stub `SystemProbe` с canned responses для unit-тестов."""

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


def _happy_probe() -> StubProbe:
    """Probe, где все required-проверки зелёные."""
    probe = StubProbe()
    probe.envs[IMAGE_VERSION_ENV] = 'linux-dev'
    probe.envs['DISPLAY'] = ':0'
    for spec in TOOLCHAIN_COMMANDS:
        probe.commands[tuple(spec.argv)] = CommandProbeResult(
            found=True,
            stdout=f'{spec.name} 9.9.9',
            exit_code=0,
            timed_out=False,
        )
    probe.commands[('xset', 'q')] = CommandProbeResult(
        found=True,
        stdout='Keyboard Control: ...',
        exit_code=0,
        timed_out=False,
    )
    for spec in TOOLCHAIN_PYTHON_LIBS:
        probe.py_versions[spec.package] = '1.2.3'
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
    probe.dri_devices = ('/dev/dri/card0', '/dev/dri/renderD128')
    return probe


def test_happy_path_all_ok() -> None:
    report = run_doctor(_happy_probe())
    assert report.worst_status == CheckStatus.OK


def test_required_command_missing_fails() -> None:
    probe = _happy_probe()
    probe.commands[('kicad-cli', '--version')] = CommandProbeResult(
        found=False,
        stdout='',
        exit_code=None,
        timed_out=False,
    )
    report = run_doctor(probe)
    assert report.worst_status == CheckStatus.FAIL
    fails = [c for c in report.checks if c.status == CheckStatus.FAIL]
    assert any(c.name == 'kicad-cli' for c in fails)


def test_optional_command_missing_warns_not_fails() -> None:
    probe = _happy_probe()
    # freecad помечен как required=False в TOOLCHAIN_COMMANDS
    probe.commands[('freecad', '--version')] = CommandProbeResult(
        found=False,
        stdout='',
        exit_code=None,
        timed_out=False,
    )
    report = run_doctor(probe)
    assert report.worst_status == CheckStatus.WARN
    freecad = next(c for c in report.checks if c.name == 'freecad')
    assert freecad.status == CheckStatus.WARN


def test_command_no_output_warns() -> None:
    probe = _happy_probe()
    probe.commands[('ngspice', '-v')] = CommandProbeResult(
        found=True,
        stdout='',
        exit_code=2,
        timed_out=False,
    )
    report = run_doctor(probe)
    ngspice = next(c for c in report.checks if c.name == 'ngspice')
    assert ngspice.status == CheckStatus.WARN
    assert 'exit=2' in ngspice.detail


def test_command_timed_out_warns() -> None:
    probe = _happy_probe()
    probe.commands[('uv', '--version')] = CommandProbeResult(
        found=True,
        stdout='',
        exit_code=None,
        timed_out=True,
    )
    report = run_doctor(probe)
    uv = next(c for c in report.checks if c.name == 'uv')
    assert uv.status == CheckStatus.WARN
    assert 'timed out' in uv.detail


def test_required_python_lib_missing_fails() -> None:
    probe = _happy_probe()
    probe.py_versions['pyopenmagnetics'] = None
    report = run_doctor(probe)
    assert report.worst_status == CheckStatus.FAIL


def test_optional_python_lib_missing_warns() -> None:
    probe = _happy_probe()
    probe.py_versions['femmt'] = None
    report = run_doctor(probe)
    assert report.worst_status == CheckStatus.WARN


def test_efactory_version_env_missing_warns() -> None:
    probe = _happy_probe()
    probe.envs[IMAGE_VERSION_ENV] = None
    report = run_doctor(probe)
    img = next(c for c in report.checks if c.name == 'efactory image')
    assert img.status == CheckStatus.WARN


def test_include_gui_false_skips_gui_checks() -> None:
    probe = _happy_probe()
    report = run_doctor(probe, include_gui=False)
    gui_checks = [c for c in report.checks if c.category == CATEGORY_GUI]
    assert gui_checks == []


def test_display_unset_warns() -> None:
    probe = _happy_probe()
    probe.envs['DISPLAY'] = None
    report = run_doctor(probe)
    display = next(c for c in report.checks if c.name == '$DISPLAY')
    assert display.status == CheckStatus.WARN


def test_xset_x11_unreachable_warns() -> None:
    probe = _happy_probe()
    probe.commands[('xset', 'q')] = CommandProbeResult(
        found=True,
        stdout='unable to open display',
        exit_code=1,
        timed_out=False,
    )
    report = run_doctor(probe)
    xset = next(c for c in report.checks if c.name == 'xset q')
    assert xset.status == CheckStatus.WARN


def test_no_dri_devices_warns() -> None:
    probe = _happy_probe()
    probe.dri_devices = ()
    report = run_doctor(probe)
    dri = next(c for c in report.checks if c.name == '/dev/dri')
    assert dri.status == CheckStatus.WARN


def test_workspace_missing_fails() -> None:
    probe = _happy_probe()
    probe.paths[Path('/workspace')] = PathProbeResult(
        exists=False,
        is_dir=False,
        is_file=False,
        writable=False,
    )
    report = run_doctor(probe)
    workspace = next(c for c in report.checks if c.name == '/workspace')
    assert workspace.status == CheckStatus.FAIL


def test_workspace_unwritable_fails() -> None:
    probe = _happy_probe()
    probe.paths[Path('/workspace')] = PathProbeResult(
        exists=True,
        is_dir=True,
        is_file=False,
        writable=False,
    )
    report = run_doctor(probe)
    workspace = next(c for c in report.checks if c.name == '/workspace')
    assert workspace.status == CheckStatus.FAIL


def test_libs_unwritable_ok() -> None:
    """libs montируется ro — writable=False НЕ должно валить FAIL."""
    probe = _happy_probe()
    probe.paths[Path('/libs/symbols')] = PathProbeResult(
        exists=True,
        is_dir=True,
        is_file=False,
        writable=False,
    )
    report = run_doctor(probe)
    symbols = next(c for c in report.checks if c.name == '/libs/symbols')
    assert symbols.status == CheckStatus.OK


def test_credentials_missing_warns() -> None:
    probe = _happy_probe()
    probe.paths[CREDENTIAL_FILE] = PathProbeResult(
        exists=False,
        is_dir=False,
        is_file=False,
        writable=False,
    )
    report = run_doctor(probe)
    cred = next(c for c in report.checks if c.name == str(CREDENTIAL_FILE))
    assert cred.status == CheckStatus.WARN


def test_disk_free_below_fail_threshold_fails() -> None:
    probe = _happy_probe()
    probe.disk_free[Path('/workspace')] = DISK_FREE_FAIL_BYTES - 1
    report = run_doctor(probe)
    disk = next(
        c for c in report.checks if c.name == '/workspace free space'
    )
    assert disk.status == CheckStatus.FAIL


def test_disk_free_below_warn_threshold_warns() -> None:
    probe = _happy_probe()
    probe.disk_free[Path('/workspace')] = DISK_FREE_WARN_BYTES - 1
    report = run_doctor(probe)
    disk = next(
        c for c in report.checks if c.name == '/workspace free space'
    )
    assert disk.status == CheckStatus.WARN


def test_ulimit_low_warns() -> None:
    probe = _happy_probe()
    probe.ulimit_nofile = ULIMIT_NOFILE_WARN_THRESHOLD - 1
    report = run_doctor(probe)
    ulimit = next(c for c in report.checks if c.name == 'ulimit -n')
    assert ulimit.status == CheckStatus.WARN


def test_cgroup_memory_unlimited_reports_ok_with_unlimited_detail() -> None:
    probe = _happy_probe()
    probe.cgroup_memory_max = CGROUP_MEMORY_UNLIMITED_BYTES + 1
    report = run_doctor(probe)
    mem = next(c for c in report.checks if c.name == 'cgroup memory.max')
    assert mem.status == CheckStatus.OK
    assert 'unlimited' in mem.detail


def test_cgroup_memory_finite_reports_gib() -> None:
    probe = _happy_probe()
    probe.cgroup_memory_max = 8 * 1024**3
    report = run_doctor(probe)
    mem = next(c for c in report.checks if c.name == 'cgroup memory.max')
    assert mem.status == CheckStatus.OK
    assert 'GiB' in mem.detail


def test_report_contains_all_canonical_categories_in_happy_path() -> None:
    report = run_doctor(_happy_probe())
    cats = {check.category for check in report.checks}
    assert CATEGORY_TOOLCHAIN in cats
    assert CATEGORY_GUI in cats
    assert CATEGORY_MOUNTS in cats
    assert CATEGORY_RUNTIME in cats
