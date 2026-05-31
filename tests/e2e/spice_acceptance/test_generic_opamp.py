"""T153 Phase A.1 acceptance: open-loop AC response GENERIC_OPAMP.

Cross-validation reference для 4 phase-margin injection methods в
Phase B-C. Здесь же проверяем, что macromodel параметры — A0=100 dB,
fp=10 Hz, GBW=1 MHz — действительно выдаются ngspice'ом без сюрпризов.
"""

from __future__ import annotations

import math
import shutil
from pathlib import Path

import pytest

from adapters.outbound.ngspice.simulator import NgspiceSimulator
from adapters.outbound.platform_native.platform_layer import (
    NativePlatformLayer,
)
from adapters.outbound.subprocess_apps.app_manager import (
    SubprocessAppManager,
)
from domain.simulation import AcAnalysis

_NGSPICE_AVAILABLE = shutil.which('ngspice') is not None
_REPO_ROOT = Path(__file__).resolve().parents[3]
_OPAMP_LIB = _REPO_ROOT / 'data' / 'models' / 'opamps' / 'generic' / 'GENERIC_OPAMP.lib'

needs_ngspice = pytest.mark.skipif(
    not _NGSPICE_AVAILABLE,
    reason='ngspice not installed (apt install ngspice / brew install ngspice)',
)

_A0 = 1e5  # design DC gain
_GBW = 1e6  # design gain-bandwidth product


def _open_loop_netlist(opamp_lib: Path) -> str:
    """Minimal open-loop AC test bench: V(out) = T(s)·V(inp)."""
    return f"""* Open-loop AC test for GENERIC_OPAMP (T153)
.include {opamp_lib}
Vinp inp 0 dc 0 ac 1
Rinn inn 0 1
X1 inp inn out GENERIC_OPAMP
Rload out 0 1Meg
"""


def _magnitude_at(ac, target_hz: float) -> tuple[float, float]:
    """Return (|V(out)|, frequency_actual) closest to target_hz."""
    idx = min(
        range(len(ac.frequency)),
        key=lambda i: abs(math.log10(ac.frequency[i]) - math.log10(target_hz)),
    )
    re = ac.traces_real['v(out)'][idx]
    im = ac.traces_imag['v(out)'][idx]
    return math.hypot(re, im), ac.frequency[idx]


def _app_manager() -> SubprocessAppManager:
    return SubprocessAppManager(NativePlatformLayer())


@needs_ngspice
async def test_generic_opamp_dc_gain_matches_design(tmp_path: Path) -> None:
    """На f << fp (1 Hz) |V(out)| ≈ A0 = 1e5 (100 dB)."""
    netlist = tmp_path / 'opamp_ol.cir'
    netlist.write_text(_open_loop_netlist(_OPAMP_LIB))
    simulator = NgspiceSimulator(_app_manager())

    result = await simulator.run(
        netlist,
        AcAnalysis(sweep='dec', n_points=10, f_start=1.0, f_stop=1e7),
    )

    assert result.ac_sweep is not None
    magnitude, _ = _magnitude_at(result.ac_sweep, 1.0)
    assert magnitude == pytest.approx(_A0, rel=0.05)


@needs_ngspice
async def test_generic_opamp_unity_gain_crossover_at_gbw(tmp_path: Path) -> None:
    """На f = GBW = 1 MHz |V(out)| ≈ 1 (unity gain crossover)."""
    netlist = tmp_path / 'opamp_ol.cir'
    netlist.write_text(_open_loop_netlist(_OPAMP_LIB))
    simulator = NgspiceSimulator(_app_manager())

    result = await simulator.run(
        netlist,
        AcAnalysis(sweep='dec', n_points=20, f_start=1.0, f_stop=1e7),
    )

    assert result.ac_sweep is not None
    magnitude, freq = _magnitude_at(result.ac_sweep, _GBW)
    assert freq == pytest.approx(_GBW, rel=0.2)
    assert magnitude == pytest.approx(1.0, rel=0.15)


@needs_ngspice
async def test_generic_opamp_phase_at_gbw_is_minus_90deg(tmp_path: Path) -> None:
    """Single-pole rolloff → phase at GBW ≈ -90° (well past fp=10 Hz)."""
    netlist = tmp_path / 'opamp_ol.cir'
    netlist.write_text(_open_loop_netlist(_OPAMP_LIB))
    simulator = NgspiceSimulator(_app_manager())

    result = await simulator.run(
        netlist,
        AcAnalysis(sweep='dec', n_points=20, f_start=1.0, f_stop=1e7),
    )

    assert result.ac_sweep is not None
    ac = result.ac_sweep
    idx = min(
        range(len(ac.frequency)),
        key=lambda i: abs(math.log10(ac.frequency[i]) - math.log10(_GBW)),
    )
    re = ac.traces_real['v(out)'][idx]
    im = ac.traces_imag['v(out)'][idx]
    phase_deg = math.degrees(math.atan2(im, re))
    assert phase_deg == pytest.approx(-90.0, abs=5.0)


@needs_ngspice
async def test_generic_opamp_output_resistance(tmp_path: Path) -> None:
    """Rload = Rout = 50 Ω → divider /2 в far passband."""
    netlist_text = f"""* Output-resistance probe
.include {_OPAMP_LIB}
Vinp inp 0 dc 0 ac 1
Rinn inn 0 1
X1 inp inn out GENERIC_OPAMP
Rload out 0 50
"""
    netlist = tmp_path / 'opamp_rout.cir'
    netlist.write_text(netlist_text)
    simulator = NgspiceSimulator(_app_manager())

    result = await simulator.run(
        netlist,
        AcAnalysis(sweep='dec', n_points=10, f_start=1.0, f_stop=10.0),
    )

    assert result.ac_sweep is not None
    magnitude, _ = _magnitude_at(result.ac_sweep, 1.0)
    # Half voltage divider: 50 / (50+50) = 0.5 → |V(out)| ≈ A0 / 2
    assert magnitude == pytest.approx(_A0 / 2, rel=0.05)
