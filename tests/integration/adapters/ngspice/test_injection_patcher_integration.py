"""
Integration: NgspiceInjectionNetlistPatcher + real ngspice (T153 Phase B.3).

Применяем 4 patch-операции к простой op-amp inverting-amp fixture
(VCVS-imitatation op-amp, чтобы не зависеть от subckt-include'ов),
вешаем `.ac dec ...` analysis card и прогоняем через `NgspiceSimulator`.
Проверяем: ngspice не падает на parse, AC-sweep успешен, probe-trace'и
из `ProbePair` присутствуют в результате.

Physical correctness конкретных topology'ей (DC op-point, loop-gain
sanity) валидируется в Phase C на calibration fixture'ах. Здесь —
syntactic + probe-name conformance contract.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest

from adapters.outbound.ngspice.injection_patcher import (
    NgspiceInjectionNetlistPatcher,
)
from adapters.outbound.ngspice.simulator import NgspiceSimulator
from adapters.outbound.platform_native.platform_layer import (
    NativePlatformLayer,
)
from adapters.outbound.subprocess_apps.app_manager import SubprocessAppManager
from domain.simulation import AcAnalysis

if TYPE_CHECKING:
    from pathlib import Path

_NGSPICE_AVAILABLE = shutil.which('ngspice') is not None
needs_ngspice = pytest.mark.skipif(
    not _NGSPICE_AVAILABLE,
    reason='ngspice not installed (apt install ngspice / brew install ngspice)',
)

# Op-amp inverting amp fixture без external subckt:
# VCVS E_amp реализует op-amp как gain=-1e5 (in_neg → vout, inverting).
# R_in задаёт inverting node, R_fb замыкает обратную связь.
_OPAMP_INV = (
    '* op-amp inverting amp fixture (T153 B.3 integration)\n'
    'V_in vin 0 AC 1 0\n'
    'R_in vin in_neg 1k\n'
    'R_fb vout in_neg 10k\n'
    'E_amp vout 0 0 in_neg 1e5\n'
    'R_load vout 0 100k\n'
    '.end\n'
)


def _append_ac_card(netlist_text: str) -> str:
    """Insert `.ac dec 10 1 1e6` before `.end`. Adds `.end` if missing."""
    ac_card = '.ac dec 10 1 1e6\n'
    if '.end' in netlist_text:
        return netlist_text.replace('.end', ac_card + '.end', 1)
    return netlist_text + ac_card + '.end\n'


def _make_simulator() -> NgspiceSimulator:
    return NgspiceSimulator(SubprocessAppManager(NativePlatformLayer()))


# ============================================== voltage injection ===========


@needs_ngspice
async def test_voltage_patched_netlist_runs_in_ngspice(tmp_path: Path) -> None:
    patcher = NgspiceInjectionNetlistPatcher()
    result = patcher.insert_voltage_source(
        _OPAMP_INV,
        break_node='in_neg',
        break_element_ref='R_fb',
        source_ref='Vinj',
        ac_magnitude=1.0,
    )
    netlist_path = tmp_path / 'voltage.cir'
    netlist_path.write_text(_append_ac_card(result.patched_netlist))

    simulator = _make_simulator()
    ac = await simulator.run(
        netlist_path,
        AcAnalysis(sweep='dec', n_points=10, f_start=1.0, f_stop=1e6),
    )

    assert ac.ac_sweep is not None
    sweep = ac.ac_sweep
    assert result.probe_pair.fwd in sweep.traces_real
    assert result.probe_pair.rev in sweep.traces_real


# ============================================== current injection ===========


@needs_ngspice
async def test_current_patched_netlist_runs_in_ngspice(tmp_path: Path) -> None:
    patcher = NgspiceInjectionNetlistPatcher()
    result = patcher.insert_current_source(
        _OPAMP_INV,
        break_node='in_neg',
        break_element_ref='R_fb',
        source_ref='Iinj',
        ac_magnitude=1.0,
    )
    netlist_path = tmp_path / 'current.cir'
    netlist_path.write_text(_append_ac_card(result.patched_netlist))

    simulator = _make_simulator()
    ac = await simulator.run(
        netlist_path,
        AcAnalysis(sweep='dec', n_points=10, f_start=1.0, f_stop=1e6),
    )

    assert ac.ac_sweep is not None
    sweep = ac.ac_sweep
    assert result.probe_pair.fwd in sweep.traces_real
    assert result.probe_pair.rev in sweep.traces_real


# ============================================== open break (Rosenstark) =====


@needs_ngspice
async def test_open_break_patched_netlist_runs_in_ngspice(
    tmp_path: Path,
) -> None:
    patcher = NgspiceInjectionNetlistPatcher()
    result = patcher.open_break(
        _OPAMP_INV,
        break_node='in_neg',
        break_element_ref='R_fb',
    )
    netlist_path = tmp_path / 'open.cir'
    netlist_path.write_text(_append_ac_card(result.patched_netlist))

    simulator = _make_simulator()
    ac = await simulator.run(
        netlist_path,
        AcAnalysis(sweep='dec', n_points=10, f_start=1.0, f_stop=1e6),
    )

    assert ac.ac_sweep is not None
    sweep = ac.ac_sweep
    assert result.probe_pair.fwd in sweep.traces_real
    assert result.probe_pair.rev in sweep.traces_real


# ============================================== short break (Rosenstark) ====


@needs_ngspice
async def test_short_break_patched_netlist_runs_in_ngspice(
    tmp_path: Path,
) -> None:
    patcher = NgspiceInjectionNetlistPatcher()
    result = patcher.short_break(
        _OPAMP_INV,
        break_node='in_neg',
        break_element_ref='R_fb',
    )
    netlist_path = tmp_path / 'short.cir'
    netlist_path.write_text(_append_ac_card(result.patched_netlist))

    simulator = _make_simulator()
    ac = await simulator.run(
        netlist_path,
        AcAnalysis(sweep='dec', n_points=10, f_start=1.0, f_stop=1e6),
    )

    assert ac.ac_sweep is not None
    sweep = ac.ac_sweep
    assert result.probe_pair.fwd in sweep.traces_real
    assert result.probe_pair.rev in sweep.traces_real
