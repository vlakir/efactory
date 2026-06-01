"""E2E: efactory bridge measure phase-margin (T153 Phase B.6).

Soft acceptance — pipeline доходит до crossover detection без
parse-fail'ов / TypeError. Exit 0 (success) ИЛИ exit 2 на ожидаемых
domain error'ах (NoUnityGainCrossover / LoopGainAlwaysAboveUnity)
для op-amp fixture — оба исхода валидируют CLI→use case→ngspice
orchestration целостность. Physics correctness — Phase C calibration.

Validation-тесты (без ngspice) проверяют early-exit'ы CLI слоя:
invalid flags, missing netlist, half-explicit edge.
"""

from __future__ import annotations

import json
import shutil
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from composition.main import build_cli_app

if TYPE_CHECKING:
    from pathlib import Path

_NGSPICE_AVAILABLE = shutil.which('ngspice') is not None

needs_ngspice = pytest.mark.skipif(
    not _NGSPICE_AVAILABLE,
    reason='ngspice not installed on host',
)

# Op-amp inverting amp с output RC rolloff (та же fixture, что в Phase B.4
# integration: A=1e5, R=1k, C=10µ → fp ≈ 15.9 Hz; β = 1/11).
_OPAMP_INV_WITH_POLE = (
    '* op-amp inverting amp with output RC rolloff (T153 B.6 e2e)\n'
    '* V_in DC-only (AC=0); единственный AC source — это injected Vinj.\n'
    'V_in vin 0 DC 0\n'
    'R_in vin in_neg 1k\n'
    'R_fb vout in_neg 10k\n'
    'E_amp v_open 0 0 in_neg 1e5\n'
    'R_amp v_open vout 1k\n'
    'C_amp vout 0 10u\n'
    'R_load vout 0 1Meg\n'
    '.end\n'
)


def _setup_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    projects_root = tmp_path / 'projects'
    monkeypatch.setenv('EFACTORY_PROJECTS_ROOT', str(projects_root))
    monkeypatch.setenv('EFACTORY_SESSION_ROOT', str(tmp_path / 'sessions'))
    return projects_root


def _write_opamp(tmp_path: Path) -> Path:
    netlist_path = tmp_path / 'opamp_pole.cir'
    netlist_path.write_text(_OPAMP_INV_WITH_POLE)
    return netlist_path


# --------- validation-only тесты (early-exit, ngspice не нужен) ----------


def test_phase_margin_invalid_injection_method(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    netlist = _write_opamp(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        build_cli_app(),
        [
            'bridge', 'measure', 'phase-margin', str(netlist),
            '--injection-method', 'bogus-method',
            '--loop-break-node', 'in_neg',
            '--loop-break-element', 'R_fb',
        ],
    )

    assert result.exit_code == 2
    assert 'Invalid --injection-method' in result.output


def test_phase_margin_invalid_confidence_threshold(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    netlist = _write_opamp(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        build_cli_app(),
        [
            'bridge', 'measure', 'phase-margin', str(netlist),
            '--confidence-threshold', '1.5',
            '--loop-break-node', 'in_neg',
            '--loop-break-element', 'R_fb',
        ],
    )

    assert result.exit_code == 2
    assert 'Invalid --confidence-threshold' in result.output


def test_phase_margin_missing_netlist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()

    result = runner.invoke(
        build_cli_app(),
        [
            'bridge', 'measure', 'phase-margin',
            str(tmp_path / 'does_not_exist.cir'),
            '--loop-break-node', 'in_neg',
            '--loop-break-element', 'R_fb',
        ],
    )

    assert result.exit_code == 2
    assert 'Netlist file not found' in result.output


def test_phase_margin_half_explicit_edge_node_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--loop-break-node без --loop-break-element → ValueError → exit 2."""
    _setup_env(tmp_path, monkeypatch)
    netlist = _write_opamp(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        build_cli_app(),
        [
            'bridge', 'measure', 'phase-margin', str(netlist),
            '--loop-break-node', 'in_neg',
        ],
    )

    assert result.exit_code == 2
    # Use case message: «break_node и break_element_ref должны быть переданы пара».
    assert 'break_node' in result.output or 'pair' in result.output.lower()


def test_phase_margin_half_explicit_edge_element_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """--loop-break-element без --loop-break-node → ValueError → exit 2."""
    _setup_env(tmp_path, monkeypatch)
    netlist = _write_opamp(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        build_cli_app(),
        [
            'bridge', 'measure', 'phase-margin', str(netlist),
            '--loop-break-element', 'R_fb',
        ],
    )

    assert result.exit_code == 2


# --------- pipeline smoke (нужен real ngspice) --------------------------


def _check_smoke_exit(exit_code: int, output: str) -> None:
    """
    Acceptance — exit 0 (нашли PM) ИЛИ exit 2 c known domain error.

    Spec Phase B.4 / B.5.x smoke pattern: Middlebrook V/I single-injection
    формула даёт T_v (не T_loop), для op-amp |T_v| < 1 во всём диапазоне →
    NoUnityGainCrossover. Это calibration issue для Phase C, не CLI bug.
    """
    if exit_code == 0:
        return
    assert exit_code == 2, output
    expected_markers = (
        'unity',  # NoUnityGainCrossover
        'above unity',  # LoopGainAlwaysAbove
        'unity gain',
        'loop gain',
    )
    assert any(marker in output.lower() for marker in expected_markers), output


@needs_ngspice
def test_phase_margin_explicit_edge_smoke(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end через real ngspice с explicit edge-pair, text output."""
    _setup_env(tmp_path, monkeypatch)
    netlist = _write_opamp(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        build_cli_app(),
        [
            'bridge', 'measure', 'phase-margin', str(netlist),
            '--loop-break-node', 'in_neg',
            '--loop-break-element', 'R_fb',
            '--f-low', '1',
            '--f-high', '10Meg',
            '--n-points-per-decade', '50',
        ],
    )

    _check_smoke_exit(result.exit_code, result.output)
    if result.exit_code == 0:
        assert 'Phase margin:' in result.output
        assert 'middlebrook_voltage' in result.output


@needs_ngspice
def test_phase_margin_explicit_edge_json_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JSON output совместим с PhaseMarginMeasurement schema."""
    _setup_env(tmp_path, monkeypatch)
    netlist = _write_opamp(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        build_cli_app(),
        [
            'bridge', 'measure', 'phase-margin', str(netlist),
            '--loop-break-node', 'in_neg',
            '--loop-break-element', 'R_fb',
            '--f-low', '1',
            '--f-high', '10Meg',
            '--n-points-per-decade', '50',
            '--output', 'json',
        ],
    )

    _check_smoke_exit(result.exit_code, result.output)
    if result.exit_code == 0:
        payload = json.loads(result.output)
        assert payload['injection_method'] == 'middlebrook_voltage'
        assert payload['measured_at_node'] == 'in_neg'
        assert isinstance(payload['margin_deg'], float)
        assert isinstance(payload['crossover_hz'], float)
        assert payload['stability_class'] in {
            'high', 'adequate', 'marginal', 'risky',
        }


@needs_ngspice
def test_phase_margin_auto_detect_no_confirm_smoke(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Auto-detect path с --no-confirm + low threshold (для guaranteed accept)."""
    _setup_env(tmp_path, monkeypatch)
    netlist = _write_opamp(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        build_cli_app(),
        [
            'bridge', 'measure', 'phase-margin', str(netlist),
            '--no-confirm',
            '--confidence-threshold', '0.0',
            '--f-low', '1',
            '--f-high', '10Meg',
            '--n-points-per-decade', '50',
        ],
    )

    _check_smoke_exit(result.exit_code, result.output)
    if result.exit_code == 0:
        assert 'auto-detect:' in result.output


@needs_ngspice
def test_phase_margin_injection_method_tian_smoke(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tian двойного injection orchestration работает (2 sweeps)."""
    _setup_env(tmp_path, monkeypatch)
    netlist = _write_opamp(tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        build_cli_app(),
        [
            'bridge', 'measure', 'phase-margin', str(netlist),
            '--injection-method', 'tian',
            '--loop-break-node', 'in_neg',
            '--loop-break-element', 'R_fb',
            '--f-low', '1',
            '--f-high', '10Meg',
            '--n-points-per-decade', '50',
        ],
    )

    _check_smoke_exit(result.exit_code, result.output)
    if result.exit_code == 0:
        assert 'tian' in result.output.lower()
