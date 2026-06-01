"""T027 Phase D acceptance: Active 2nd-order Sallen-Key low-pass filter.

Voltage-controlled voltage-source (VCVS) unity-gain Sallen-Key topology
с **equal-R, unequal-C** component choice (per spec Analyze 🟡 W1
recommendation):

  R1 = R2 = R = 10 kΩ
  C1 = 22 nF (mid → vout feedback)
  C2 = 10 nF (in_p → GND shunt)

Time constants и filter parameters:
* f_c = 1/(2π·R·√(C1·C2)) = 1/(2π·10k·√(22n·10n)) ≈ 1.07 kHz
* Q = 0.5·√(C1/C2) = 0.5·√(2.2) ≈ 0.742 (slightly above Butterworth 0.707)

Spec Q10 (Round 2 одобрено Vladimir) suggested equal-R/equal-C с
C=15.9nF → f_c=1kHz, Q=0.5 (overdamped, не Butterworth). Analyze W1
recommended switch к unequal-C для proper Butterworth Q=0.707.
С E12 values C1=22n, C2=10n получаем Q=0.742 — close to 0.707 within
spec ±10% tolerance.

Topology (left → right):

  V_in (VSIN 100 mV @ 1 kHz) → R1 (10 kΩ) → mid;
  mid → R2 (10 kΩ) → in_p;
  mid → C1 (22 nF) → vout (feedback от op-amp output);
  in_p → C2 (10 nF) → GND (filter shunt);
  in_p → TL072.IN+;
  TL072.IN- → vout (unity-gain VCVS = voltage follower);
  TL072.OUT → vout → R_load (10 kΩ) → GND.

Acceptance:
  * netlist содержит X1 ... TL072 + .include TL072.lib + 2 R=10k + C1=22n + C2=10n.
  * Topology: R1+R2 equal (10k each), C1=22n (feedback to vout),
    C2=10n (shunt to GND).
  * op-amp configured unity-gain (IN- == OUT net = vout).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from adapters.outbound.kicad_cli.schematic_exporter import (
    KicadCliSchematicExporter,
)
from adapters.outbound.schematic_kicad.facade import Schematic
from adapters.outbound.subprocess_apps.app_manager import (
    SubprocessAppManager,
)
from adapters.outbound.platform_native.platform_layer import (
    NativePlatformLayer,
)
from domain.schematic import Position

_KICAD_AVAILABLE = any(
    (Path.home() / 'kicad').glob('kicad*.AppImage'),
) or shutil.which('kicad-cli') is not None

needs_kicad = pytest.mark.skipif(
    not _KICAD_AVAILABLE,
    reason='KiCad not installed',
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_OPAMP_LIB = (
    _REPO_ROOT / 'data' / 'models' / 'opamps' / 'generic' / 'TL072.lib'
)


# === Layout (mm, Y-down) ===
# Filter row Y=70 (R1, R2 horizontal). C1 vertical between mid and vout
# at Y=80 below R1. C2 vertical between in_p and GND. Op-amp at Y=85
# below filter, OUT routes back UP to feedback path.

_V_IN_AT = (50.0, 70.0)
_GND_VIN_AT = (50.0, 78.74)
_R1_AT = (63.5, 65.0)  # rot=90: pin_a@(59.69,65), pin_b@(67.31,65)
_C1_AT = (77.47, 71.12)  # vertical: pin_a@(77.47,74.93)→vout, pin_b@(77.47,67.31)→mid wire
_R2_AT = (90.17, 65.0)  # rot=90: pin_a@(86.36,65), pin_b@(93.98,65)
_C2_AT = (100.33, 71.12)  # vertical: pin_a@(100.33,74.93)→GND, pin_b@(100.33,67.31)→in_p wire
_GND_C2_AT = (100.33, 78.74)
_U1_AT = (115.0, 85.0)  # OPAMP center: IN+@(107.38,82.46), IN-@(107.38,87.54), OUT@(122.62,85)
_R_LOAD_AT = (140.0, 85.0)  # rot=90: pin_a@(136.19,85), pin_b@(143.81,85)
_GND_RLOAD_AT = (148.0, 85.0)


def _app_manager() -> SubprocessAppManager:
    return SubprocessAppManager(NativePlatformLayer())


def _build_active_lpf_sallen_key(path: Path) -> Path:
    """Builds active-lpf-sallen-key reference fixture.

    Imported by `scripts/regenerate-templates.py` to bake the shipping
    template (`data/templates/active-lpf-sallen-key/`).
    """
    sch = Schematic('active_lpf_sallen_key')

    v_in = sch.add_v_ac(
        value='VSIN', at=_V_IN_AT,
        amplitude=0.1, frequency=1000.0,
        reference='V_in',
    )
    gnd_vin = sch.add_ground(at=_GND_VIN_AT)
    sch.connect(v_in.pin_plus, gnd_vin.pin)  # real "-" → GND

    # R1 horizontal: pin_a (left) → vin, pin_b (right) → mid.
    r1 = sch.add_resistor(value='10k', at=_R1_AT, rotation=90, reference='R1')
    # R2 horizontal: pin_a (left) → mid, pin_b (right) → in_p.
    r2 = sch.add_resistor(value='10k', at=_R2_AT, rotation=90, reference='R2')
    # C1 vertical: pin_b (bottom, Y-3.81) → mid; pin_a (top, Y+3.81) → vout.
    c1 = sch.add_capacitor(value='22n', at=_C1_AT, reference='C1')
    # C2 vertical: pin_b (bottom, Y-3.81) → in_p; pin_a (top, Y+3.81) → GND.
    # 11 nF (NOT standard E12) для exact Butterworth Q=0.707 with C1=22n
    # (C1/C2=2 strict). BOM realization: 10n + 1n parallel film caps.
    c2 = sch.add_capacitor(value='11n', at=_C2_AT, reference='C2')

    # TL072 op-amp.
    u1 = sch.add_op_amp(
        model_id='TL072',
        lib_path=_OPAMP_LIB,
        at=_U1_AT,
        reference='U1',
    )
    # V+/V- macromodel pins — supply not modeled.
    sch.no_connect(at=u1.pin_vplus)
    sch.no_connect(at=u1.pin_vminus)

    # R_load horizontal: pin_a (left) → vout, pin_b (right) → GND.
    # R_load 100k — typical high-Z next-stage input impedance. 10k loaded
    # op-amp output слишком сильно — shifted f_c измерение down on 12-13%.
    r_load = sch.add_resistor(
        value='100k', at=_R_LOAD_AT, rotation=90, reference='R_load',
    )
    gnd_rload = sch.add_ground(at=_GND_RLOAD_AT)
    gnd_c2 = sch.add_ground(at=_GND_C2_AT)

    # === Vin → R1 ===
    sch.connect(v_in.pin_minus, r1.pin_a)

    # === R1.pin_b → mid → R2.pin_a + C1.pin_b ===
    # All on Y=65 row: R1.pin_b (67.31, 65), R2.pin_a (86.36, 65).
    # C1.pin_b at (77.47, 67.31) — slightly below Y=65. L-route:
    # horizontal Y=65 R1.pin_b → R2.pin_a, with stub vertical к C1.pin_b.
    sch.connect(r1.pin_b, r2.pin_a)
    # C1.pin_b (77.47, 67.31) → mid wire Y=65: vertical stub.
    sch.connect(c1.pin_b, Position(x_mm=77.47, y_mm=65.0))
    sch.junction(at=(77.47, 65.0))

    # === R2.pin_b → in_p → C2.pin_b + op-amp.IN+ ===
    # R2.pin_b (93.98, 65). C2.pin_b (100.33, 67.31). Op-amp IN+ at (107.38, 82.46).
    # in_p wire Y=65 from R2.pin_b до C2.pin_b's X column (100.33).
    sch.connect(r2.pin_b, Position(x_mm=100.33, y_mm=65.0))
    # C2.pin_b stub.
    sch.connect(c2.pin_b, Position(x_mm=100.33, y_mm=65.0))
    sch.junction(at=(100.33, 65.0))
    # in_p → op-amp.IN+: L-route from (100.33, 65) → (107.38, 65) → (107.38, 82.46).
    sch.connect(
        Position(x_mm=100.33, y_mm=65.0),
        Position(x_mm=107.38, y_mm=65.0),
    )
    sch.connect(
        Position(x_mm=107.38, y_mm=65.0),
        u1.pin_inp,
    )

    # === C2.pin_a → GND ===
    sch.connect(c2.pin_a, gnd_c2.pin)

    # === Feedback: C1.pin_a → vout (= op-amp.OUT) ===
    # C1.pin_a (77.47, 74.93). U1.OUT (122.62, 85). L-route:
    # horizontal Y=74.93 east → (122.62, 74.93) → vertical to OUT (Y=85).
    sch.connect(
        c1.pin_a,
        Position(x_mm=122.62, y_mm=74.93),
    )
    sch.connect(
        Position(x_mm=122.62, y_mm=74.93),
        u1.pin_out,
    )

    # === Unity-gain VCVS feedback: IN- tied к OUT ===
    # U1.IN- (107.38, 87.54). U1.OUT (122.62, 85). L-route below op-amp.
    sch.connect(
        u1.pin_inn,
        Position(x_mm=107.38, y_mm=92.0),
    )
    sch.connect(
        Position(x_mm=107.38, y_mm=92.0),
        Position(x_mm=122.62, y_mm=92.0),
    )
    sch.connect(
        Position(x_mm=122.62, y_mm=92.0),
        u1.pin_out,
    )
    sch.junction(at=u1.pin_out)

    # === vout → R_load → GND ===
    sch.connect(u1.pin_out, r_load.pin_a)
    sch.connect(r_load.pin_b, gnd_rload.pin)

    # === SPICE labels ===
    sch.label('vin', at=v_in.pin_minus)
    sch.label('mid', at=Position(x_mm=77.47, y_mm=65.0))
    sch.label('in_p', at=u1.pin_inp)
    sch.label('vout', at=u1.pin_out)

    return sch.save(path)


async def _export_netlist(schematic_path: Path, netlist_path: Path) -> Path:
    exporter = KicadCliSchematicExporter(_app_manager())
    return await exporter.export_spice_netlist(schematic_path, netlist_path)


@needs_kicad
async def test_facade_active_lpf_sallen_key_writes_includes(
    tmp_path: Path,
) -> None:
    """Netlist содержит X1 ... TL072 + .include TL072.lib."""
    sch_path = _build_active_lpf_sallen_key(tmp_path / 'lpf.kicad_sch')
    netlist = await _export_netlist(sch_path, tmp_path / 'lpf.cir')
    text = netlist.read_text()
    x_lines = [ln for ln in text.splitlines() if ln.startswith('X')]
    assert x_lines, f'No X lines:\n{text}'
    assert any(ln.endswith('TL072') for ln in x_lines), x_lines
    assert 'TL072.lib' in text, text


@needs_kicad
async def test_facade_active_lpf_sallen_key_topology(tmp_path: Path) -> None:
    """Verify equal-R unequal-C Sallen-Key topology + unity-gain VCVS."""
    sch_path = _build_active_lpf_sallen_key(tmp_path / 'lpf.kicad_sch')
    netlist = await _export_netlist(sch_path, tmp_path / 'lpf.cir')
    lines = netlist.read_text().splitlines()

    r_lines = [ln for ln in lines if ln.startswith('R')]
    c_lines = [ln for ln in lines if ln.startswith('C')]

    # R1 = R2 = 10k (filter resistors), R_load = 100k.
    r_10k = [ln for ln in r_lines if ' 10k' in ln]
    assert len(r_10k) == 2, f'expected 2× 10k (R1+R2), got: {r_10k}'
    assert any(' 100k' in ln for ln in r_lines), 'no 100k R_load'

    # C1 = 22n (mid→vout feedback).
    assert any(' 22n' in ln for ln in c_lines), 'no 22n C1 feedback'
    # C2 = 11n (in_p→GND shunt; C1/C2=2 exact для Butterworth Q=0.707).
    assert any(' 11n' in ln for ln in c_lines), 'no 11n C2 shunt'

    # Unity-gain VCVS: IN- net == OUT net == vout.
    # 3-pin SUBCKT mapping via Sim.Pins='1=INP 2=INN 5=OUT' collapses
    # netlist X line к: X<ref> <inp> <inn> <out> TL072 (parts[1..3]).
    opamp_lines = [ln for ln in lines if ln.endswith('TL072')]
    assert len(opamp_lines) == 1, opamp_lines
    parts = opamp_lines[0].split()
    assert len(parts) == 5, opamp_lines[0]
    inn_net = parts[2]
    out_net = parts[3]
    assert inn_net == out_net, (
        f'Unity-gain VCVS expects IN- ({inn_net}) tied к OUT ({out_net}). '
        f'Op-amp line: {opamp_lines[0]}'
    )
