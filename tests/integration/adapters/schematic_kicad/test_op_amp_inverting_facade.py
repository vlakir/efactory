"""T153 Phase C.1.2 acceptance: op-amp inverting reference fixture.

Inverting amp с two-pole macromodel (`GENERIC_OPAMP_2POLE`) для
calibration четырёх phase-margin injection methods. Closed-loop gain
−R_fb/R_in = −10 V/V. Analytical reference (см. macromodel header):

* `T_loop_DC = A0·β = 1e5·(1/11) ≈ 9091` (79.2 dB)
* `crossover ≈ 64 kHz`, **phase margin ≈ 45°**

Топология (Y-down, mm):

  V_in (DC 0 / AC 1) → R_in (1k) → in_neg ── OPAMP(IN-) ─→ OUT → vout
                                              OPAMP(IN+) → GND
  vout ── R_fb (10k) ── in_neg     (global voltage NFB)
  vout ── R_load (1Meg) ── GND
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
    _REPO_ROOT
    / 'data'
    / 'models'
    / 'opamps'
    / 'generic'
    / 'GENERIC_OPAMP_2POLE.lib'
)


# === Layout (mm, Y-down) ===
# Все резисторы — rotation=90 (горизонтально), это обходит документированный
# V_DC/R pin-position bug для rotation=0 (см. comment в facade.py выше
# `_RESISTOR_PINS`). V_DC vertical — применяется swap workaround
# (pin_plus connects to GND, pin_minus connects to vin), как в SE/CE amp.

_V_IN_AT = (50.0, 80.0)
_GND_VIN_AT = (50.0, 88.9)
_R_IN_AT = (65.0, 75.0)  # rotation 90: pin_a@(61.19,75.0), pin_b@(68.81,75.0)
_U1_AT = (90.0, 75.0)  # OPAMP: pin_inp@(82.38, 72.46), pin_inn@(82.38, 77.54), pin_out@(97.62, 75.0)
_GND_OPAMP_AT = (82.38, 67.31)  # для opamp.pin_inp
_R_FB_AT = (90.0, 60.0)  # rotation 90: pin_a@(86.19, 60), pin_b@(93.81, 60)
_R_LOAD_AT = (115.0, 75.0)  # rotation 90: pin_a@(111.19, 75), pin_b@(118.81, 75)
_GND_RLOAD_AT = (123.0, 75.0)


def _app_manager() -> SubprocessAppManager:
    return SubprocessAppManager(NativePlatformLayer())


def _build_op_amp_inverting(path: Path) -> Path:
    """Builds op-amp-inverting reference fixture.

    Imported by `scripts/regenerate-templates.py` to bake the shipping
    template (`data/templates/op-amp-inverting/`).
    """
    sch = Schematic('op_amp_inverting')

    # Source: DC=0 + AC=1, vertical (rotation 0). Bug-swap: real "+"
    # pin (1) — это `pin_minus` атрибут facade'а, real "-" pin (2) —
    # `pin_plus`. Поэтому к vin (signal net) подключаем pin_minus, к
    # GND — pin_plus.
    v_in = sch.add_v_dc(value='0', at=_V_IN_AT, reference='V_in')
    gnd_vin = sch.add_ground(at=_GND_VIN_AT)
    sch.connect(v_in.pin_plus, gnd_vin.pin)  # real pin 2 ("-") → GND

    # R_in horizontal: pin_a (left) → vin, pin_b (right) → in_neg.
    r_in = sch.add_resistor(value='1k', at=_R_IN_AT, rotation=90, reference='R_in')

    # Wire: v_in real "+" pin (= pin_minus после swap) → r_in.pin_a.
    # v_in.pin_minus @ (50.0, 74.92). r_in.pin_a @ (61.19, 75.0).
    # Manhattan: vertical to y=75.0 then horizontal to 61.19.
    sch.connect(v_in.pin_minus, r_in.pin_a)

    # OPAMP: 5-pin. IN+ (1) → GND; IN- (2) → in_neg; OUT (5) → vout.
    # V+, V- (3, 4) — floating (macromodel ignores; ERC warning).
    u1 = sch.add_op_amp(
        model_id='GENERIC_OPAMP_2POLE',
        lib_path=_OPAMP_LIB,
        at=_U1_AT,
        reference='U1',
    )
    gnd_opamp = sch.add_ground(at=_GND_OPAMP_AT)
    sch.connect(u1.pin_inp, gnd_opamp.pin)
    # V+/V- (pins 3/4) — supply pins macromodel'и не используются. Маркер
    # `no_connect` гасит KiCad ERC warning «Pin not connected».
    sch.no_connect(at=u1.pin_vplus)
    sch.no_connect(at=u1.pin_vminus)

    # r_in.pin_b → u1.pin_inn. r_in.pin_b @ (68.81, 75.0). u1.pin_inn @
    # (82.38, 77.54). Manhattan corner (68.81, 77.54) → (82.38, 77.54).
    sch.connect(r_in.pin_b, u1.pin_inn)

    # R_fb horizontal: pin_a (left) → in_neg, pin_b (right) → vout.
    r_fb = sch.add_resistor(value='10k', at=_R_FB_AT, rotation=90, reference='R_fb')
    # r_fb.pin_a (86.19, 60) → u1.pin_inn (82.38, 77.54).
    sch.connect(r_fb.pin_a, u1.pin_inn)
    sch.junction(at=u1.pin_inn)

    # R_load horizontal: pin_a (left) → vout, pin_b (right) → GND.
    r_load = sch.add_resistor(value='1Meg', at=_R_LOAD_AT, rotation=90, reference='R_load')
    # r_load.pin_a (111.19, 75) → u1.pin_out (97.62, 75).
    sch.connect(r_load.pin_a, u1.pin_out)
    # r_fb.pin_b (93.81, 60) → u1.pin_out (97.62, 75).
    sch.connect(r_fb.pin_b, u1.pin_out)
    sch.junction(at=u1.pin_out)

    gnd_rload = sch.add_ground(at=_GND_RLOAD_AT)
    sch.connect(r_load.pin_b, gnd_rload.pin)

    # SPICE-trace labels — основные nets для phase-margin tools.
    sch.label('vin', at=r_in.pin_a)
    sch.label('in_neg', at=u1.pin_inn)
    sch.label('vout', at=u1.pin_out)

    return sch.save(path)


async def _export_netlist(schematic_path: Path, netlist_path: Path) -> Path:
    exporter = KicadCliSchematicExporter(_app_manager())
    return await exporter.export_spice_netlist(schematic_path, netlist_path)


@needs_kicad
async def test_facade_op_amp_inverting_writes_subckt_include(
    tmp_path: Path,
) -> None:
    """Netlist содержит X1 (GENERIC_OPAMP_2POLE) и .include на .lib."""
    sch_path = _build_op_amp_inverting(tmp_path / 'op_amp_inverting.kicad_sch')
    netlist = await _export_netlist(sch_path, tmp_path / 'op_amp_inverting.cir')
    text = netlist.read_text()

    assert 'GENERIC_OPAMP_2POLE' in text, text
    assert 'GENERIC_OPAMP_2POLE.lib' in text, text
    x_lines = [ln for ln in text.splitlines() if ln.startswith('X')]
    assert len(x_lines) == 1, (
        f'expected exactly one X (op-amp subckt), got {len(x_lines)}: {x_lines}'
    )
    assert x_lines[0].endswith('GENERIC_OPAMP_2POLE'), x_lines[0]


@needs_kicad
async def test_facade_op_amp_inverting_topology(tmp_path: Path) -> None:
    """Verify inverting topology: R_in vin↔in_neg, R_fb vout↔in_neg, OPAMP IN+=GND, IN-=in_neg, OUT=vout."""
    sch_path = _build_op_amp_inverting(tmp_path / 'op_amp_inverting.kicad_sch')
    netlist = await _export_netlist(sch_path, tmp_path / 'op_amp_inverting.cir')
    text = netlist.read_text()

    # R_in между vin и in_neg (порядок может варьироваться).
    assert any(
        ln.startswith('R_in ') and 'vin' in ln and 'in_neg' in ln and ' 1k' in ln
        for ln in text.splitlines()
    ), text

    # R_fb между vout и in_neg.
    assert any(
        ln.startswith('R_fb ') and 'vout' in ln and 'in_neg' in ln and ' 10k' in ln
        for ln in text.splitlines()
    ), text

    # R_load между vout и GND.
    assert any(
        ln.startswith('R_load ')
        and 'vout' in ln
        and 'GND' in ln
        and ' 1Meg' in ln
        for ln in text.splitlines()
    ), text

    # OPAMP subckt-call: pin 1 (IN+) → GND, pin 2 (IN-) → in_neg,
    # pin 5 (OUT) → vout. KiCad emits `X<ref> <node-INP> <node-INN>
    # <node-OUT> GENERIC_OPAMP_2POLE`. Local labels приходят как `/<name>`.
    opamp_line = next(
        ln for ln in text.splitlines() if ln.startswith('XU1 ')
    )
    parts = opamp_line.split()
    # XU1 INP_net INN_net OUT_net GENERIC_OPAMP_2POLE
    assert parts[1] == 'GND', f'IN+ should be GND, got: {parts!r}'
    assert parts[2] == '/in_neg', f'IN- should be /in_neg, got: {parts!r}'
    assert parts[3] == '/vout', f'OUT should be /vout, got: {parts!r}'
