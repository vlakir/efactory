"""E2E: efactory bridge plot ac|tran — ASCII chart на real ngspice (T024)."""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from composition.main import build_cli_app

_NGSPICE_AVAILABLE = shutil.which('ngspice') is not None
needs_ngspice = pytest.mark.skipif(
    not _NGSPICE_AVAILABLE,
    reason='ngspice not installed on host',
)

_RC_LOWPASS_NETLIST = """\
* RC low-pass filter: R=1k, C=160n → f_c ≈ 1 kHz
V_in in 0 SIN(0 0.1 1000)
R1 in load 1k
C1 load 0 160n
.end
"""

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')


def _strip_ansi(s: str) -> str:
    return _ANSI_RE.sub('', s)


def _setup_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('EFACTORY_PROJECTS_ROOT', str(tmp_path / 'projects'))
    monkeypatch.setenv(
        'EFACTORY_DATABASE_URL',
        f'sqlite+aiosqlite:///{tmp_path / "efactory.sqlite"}',
    )
    monkeypatch.setenv('EFACTORY_SESSION_ROOT', str(tmp_path / 'sessions'))


def _write_netlist(tmp_path: Path) -> Path:
    netlist = tmp_path / 'rc.cir'
    netlist.write_text(_RC_LOWPASS_NETLIST)
    return netlist


@needs_ngspice
def test_bridge_plot_ac_rc_lowpass_renders_chart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    netlist = _write_netlist(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        build_cli_app(),
        [
            'bridge', 'plot', 'ac', str(netlist),
            '--f-start', '1', '--f-stop', '1Meg',
            '--n-points', '10', '--width', '80', '--height', '20',
        ],
    )

    assert result.exit_code == 0, result.output
    visible = _strip_ansi(result.output)
    # Title contains signal name (default v(load))
    assert 'v(load)' in visible.lower()
    # Axis labels rendered
    assert 'frequency' in visible.lower()
    assert 'magnitude' in visible.lower()
    # Chart spans roughly width х height (allow generous tolerance for axes).
    lines = visible.splitlines()
    assert len(lines) >= 15  # height=20 + axes


@needs_ngspice
def test_bridge_plot_tran_rc_lowpass_renders_waveform(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    netlist = _write_netlist(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        build_cli_app(),
        [
            'bridge', 'plot', 'tran', str(netlist),
            '--t-step', '10u', '--t-stop', '10m',
            '--width', '80', '--height', '15',
        ],
    )

    assert result.exit_code == 0, result.output
    visible = _strip_ansi(result.output)
    assert 'v(load)' in visible.lower()
    assert 'time' in visible.lower()


@needs_ngspice
def test_bridge_plot_ac_missing_signal_exits_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    netlist = _write_netlist(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        build_cli_app(),
        [
            'bridge', 'plot', 'ac', str(netlist),
            '--signal', 'v(nonexistent)',
            '--f-start', '1', '--f-stop', '1k',
        ],
    )

    assert result.exit_code == 2
    assert 'v(nonexistent)' in result.output
