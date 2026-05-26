"""E2E: efactory bridge measure <gain|bandwidth|thd> (T023 Phase C).

Use voltage divider netlist (R1=R2=1k, V_in=SIN) для воспроизводимости:
- gain (small AC) = 0.5 = -6.02 dB.
- bandwidth = flat → endpoints = sweep edges.
- thd на linear divider'е = 0% (никакой нелинейности).

Реальный ngspice через NgspiceSimulator (SubprocessAppManager). Skipif при
отсутствии ngspice на хосте.
"""

from __future__ import annotations

import json
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


_VOLTAGE_DIVIDER_NETLIST = """\
* Voltage divider: R1=R2=1k → gain = 0.5 (-6 dB)
V_in in 0 SIN(0 0.1 1000)
R1 in load 1k
R_load load 0 1k
.end
"""


def _setup_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    projects_root = tmp_path / 'projects'
    monkeypatch.setenv('EFACTORY_PROJECTS_ROOT', str(projects_root))
    monkeypatch.setenv(
        'EFACTORY_DATABASE_URL',
        f'sqlite+aiosqlite:///{tmp_path / "efactory.sqlite"}',
    )
    monkeypatch.setenv('EFACTORY_SESSION_ROOT', str(tmp_path / 'sessions'))
    return projects_root


def _write_divider(tmp_path: Path) -> Path:
    netlist_path = tmp_path / 'divider.cir'
    netlist_path.write_text(_VOLTAGE_DIVIDER_NETLIST)
    return netlist_path


@needs_ngspice
def test_bridge_measure_gain_small_voltage_divider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    netlist = _write_divider(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        build_cli_app(),
        [
            'bridge', 'measure', 'gain', str(netlist),
            '--freq', '1k', '--mode', 'small',
        ],
    )

    assert result.exit_code == 0, result.output
    assert 'Gain:' in result.output
    # Divider 1:2 → -6.02 dB (small-signal AC)
    assert '-6.0' in result.output or '-6.02' in result.output


@needs_ngspice
def test_bridge_measure_gain_json_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    netlist = _write_divider(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        build_cli_app(),
        [
            'bridge', 'measure', 'gain', str(netlist),
            '--freq', '1k', '--mode', 'small',
            '--output', 'json',
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload['mode'] == 'small'
    assert payload['frequency_hz'] == pytest.approx(1000.0)
    assert payload['value_linear'] == pytest.approx(0.5, abs=0.01)
    assert payload['value_db'] == pytest.approx(-6.02, abs=0.1)
    assert payload['input_signal'] == 'V_in'
    assert payload['output_signal'] == 'v(load)'


@needs_ngspice
def test_bridge_measure_gain_large_mode_voltage_divider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Large mode = TRAN RMS Vout/Vin. Linear divider — gain тот же 0.5."""
    _setup_env(tmp_path, monkeypatch)
    netlist = _write_divider(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        build_cli_app(),
        [
            'bridge', 'measure', 'gain', str(netlist),
            '--freq', '1k', '--mode', 'large',
            '--v-in-peak', '0.1',
            '--input-signal', 'v(in)',
            '--output', 'json',
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload['mode'] == 'large'
    assert payload['value_linear'] == pytest.approx(0.5, abs=0.01)
    assert payload['v_in_peak'] == pytest.approx(0.1)


@needs_ngspice
def test_bridge_measure_bandwidth_flat_voltage_divider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Чисто resistive divider → flat АЧХ → endpoints = sweep edges."""
    _setup_env(tmp_path, monkeypatch)
    netlist = _write_divider(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        build_cli_app(),
        [
            'bridge', 'measure', 'bandwidth', str(netlist),
            '--f-low', '1', '--f-high', '1Meg',
            '--output', 'json',
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload['f_low_hz'] == pytest.approx(1.0)
    assert payload['f_high_hz'] == pytest.approx(1e6)
    assert payload['midpoint_db'] == pytest.approx(-6.02, abs=0.1)
    assert payload['ref_db'] == -3.0
    assert payload['midpoint_source'] == 'auto'


@needs_ngspice
def test_bridge_measure_thd_linear_divider_below_one_percent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pure linear (R-only) → THD близко к 0 (numerical noise only)."""
    _setup_env(tmp_path, monkeypatch)
    netlist = _write_divider(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        build_cli_app(),
        [
            'bridge', 'measure', 'thd', str(netlist),
            '--freq', '1k', '--v-in-peak', '0.1',
            '--load-ohm', '1000',
            '--output', 'json',
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload['thd_percent'] == pytest.approx(0.0, abs=1.0)
    assert payload['fundamental_hz'] == pytest.approx(1000.0)
    assert payload['v_in_peak'] == pytest.approx(0.1)
    # V_in_peak=0.1 → V_out_peak=0.05 (divider /2) → V_out_rms=0.0354 →
    # P = V_rms² / R_load = (0.0354)² / 1000 ≈ 1.25 µW
    assert payload['measured_power_w'] == pytest.approx(1.25e-6, rel=0.1)


@needs_ngspice
def test_bridge_measure_gain_large_requires_v_in_peak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    netlist = _write_divider(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        build_cli_app(),
        [
            'bridge', 'measure', 'gain', str(netlist),
            '--freq', '1k', '--mode', 'large',
        ],
    )

    assert result.exit_code != 0
    assert 'v_in_peak' in result.output.lower()


@needs_ngspice
def test_bridge_measure_invalid_mode_exits_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    netlist = _write_divider(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        build_cli_app(),
        [
            'bridge', 'measure', 'gain', str(netlist),
            '--freq', '1k', '--mode', 'medium',
        ],
    )

    assert result.exit_code == 2
    assert 'mode' in result.output.lower()
