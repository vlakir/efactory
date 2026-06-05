"""T187 Phase 4: pentode SE-resistive parametric builder + 3 wrappers.

Восстанавливает builders для 3 шаблонов T031 (6p13s-se-resistive,
6zh32p-mic-preamp, 6zh38p-if-amp), которые исторически builded one-shot
скриптом `/tmp/build_t031_templates.py` (не committed). T187 Plan B
(Q1 resolved): пишем proper Python builders с тем же layout +
snap-on-write из facade → автоматически фиксит R3/C2 cathode pair,
которые в baked версиях стояли на y=103.81 (off-grid, Δ=0.33 mm).

Топология (single-stage class-A pentode common-cathode SE с
резистивной нагрузкой Ra вместо OPT):

  V_BB (B+ DC)   ──── B+ rail ──── R_a (plate load) ──── X1.P
  V_G2 (G2 DC)   ──── G2 rail ──── X1.G2
  V_in (VSIN)    → C_in → R_g ‖ X1.G                    (Stage 1)
  X1.K → R_k ‖ C_k → GND                                (auto-bias)

Visual symbol — `Valve:EL84` (canonical 4-pin pentode shape из KiCad
Valve.kicad_sym, P/G2/G/K). SPICE — custom subckt per tube_type
(6P13S/6ZH32P/6ZH38P). Symbol-vs-numerics decoupling — стандартный
T104 паттерн.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import NamedTuple

import pytest

from adapters.outbound.kicad_cli.schematic_exporter import (
    KicadCliSchematicExporter,
)
from adapters.outbound.platform_native.platform_layer import (
    NativePlatformLayer,
)
from adapters.outbound.schematic_kicad.facade import Schematic
from adapters.outbound.subprocess_apps.app_manager import (
    SubprocessAppManager,
)
from domain.schematic import Position
from domain.spice_model import (
    ComponentCategory,
    ModelSource,
    SpiceModel,
)

_KICAD_AVAILABLE = shutil.which('kicad-cli') is not None

needs_kicad = pytest.mark.skipif(
    not _KICAD_AVAILABLE, reason='kicad-cli not in PATH',
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_TUBES_CUSTOM = _REPO_ROOT / 'data' / 'models' / 'tubes' / 'custom'


# === Layout (mm, Y-down, KiCad grid 1.27 mm) ===
# Single-stage pentode SE-resistive layout. T187 facade snap'ит off-grid
# auto-magically — R_k / C_k cathode pair (y=103.81 → 104.14, Δ+0.33).

_V_BB_AT = (50.8, 55.88)  # B+ DC source
_V_G2_AT = (76.2, 55.88)  # G2 DC source
_V_IN_AT = (50.8, 90.17)  # VSIN signal source

_C_IN_AT = (63.5, 85.09)  # input coupling cap (rot=90)
_R_G_AT = (81.28, 95.25)  # grid leak resistor
_R_A_AT = (101.6, 64.77)  # plate load resistor
# R_K / C_K — cathode pair (исторически off-grid в baked). Snap → 104.14.
_R_K_AT = (99.06, 103.81)
_C_K_AT = (109.22, 103.81)

_TUBE_AT = (101.6, 85.09)  # Valve:EL84 symbol pos (P top, G left, K bottom)

# Grounds.
_GND_VBB_AT = (50.8, 64.77)
_GND_VG2_AT = (76.2, 64.77)
_GND_VIN_AT = (50.8, 99.06)
_GND_RG_AT = (81.28, 101.6)
_GND_RK_AT = (99.06, 111.76)
_GND_CK_AT = (109.22, 111.76)

# PWR_FLAG (B+ rail driver для ERC).
_FLG_AT = (45.72, 99.06)

# Net-labels.
_LABEL_INPUT_AT = (50.8, 85.09)
_LABEL_PLATE_AT = (101.6, 73.66)
_LABEL_CATHODE_AT = (99.06, 93.98)

# SPICE directive (`.op` annotation).
_SPICE_OP_AT = (135.0, 50.0)


class _PentodeParams(NamedTuple):
    """Параметры single-stage pentode SE-resistive amp.

    `tube_id` соответствует имени .lib (CUSTOM SpiceModel) и `Sim.Name`.
    """

    schematic_name: str
    tube_id: str
    tube_lib_filename: str  # e.g. '6P13S.lib'
    v_bb: str  # B+ DC value
    v_g2: str  # G2 DC value
    c_in: str  # input coupling cap
    r_g: str  # grid leak
    r_a: str  # plate load resistor
    r_k: str  # cathode resistor (auto-bias)
    c_k: str  # cathode bypass cap


_PARAMS_6P13S = _PentodeParams(
    schematic_name='pentode_se_resistive_6p13s',
    tube_id='6P13S',
    tube_lib_filename='6P13S.lib',
    v_bb='250', v_g2='200',
    c_in='470n', r_g='470k', r_a='5k', r_k='470', c_k='220u',
)
_PARAMS_6ZH32P = _PentodeParams(
    schematic_name='pentode_se_resistive_6zh32p',
    tube_id='6ZH32P',
    tube_lib_filename='6ZH32P.lib',
    v_bb='250', v_g2='140',
    c_in='100n', r_g='1Meg', r_a='100k', r_k='2.7k', c_k='100u',
)
_PARAMS_6ZH38P = _PentodeParams(
    schematic_name='pentode_se_resistive_6zh38p',
    tube_id='6ZH38P',
    tube_lib_filename='6ZH38P.lib',
    v_bb='150', v_g2='150',
    c_in='100n', r_g='1Meg', r_a='10k', r_k='1k', c_k='10u',
)


def _tube_model(p: _PentodeParams) -> SpiceModel:
    return SpiceModel(
        id=p.tube_id,
        name=p.tube_id,
        category=ComponentCategory.TUBE,
        subcategory='pentode',
        source=ModelSource.CUSTOM,
        file_path=_TUBES_CUSTOM / p.tube_lib_filename,
        subckt_pins=('P', 'G2', 'G', 'K'),
    )


def _build_pentode_se_resistive(
    path: Path,
    params: _PentodeParams,
) -> Path:
    """Parametric builder. Topology identical across 3 templates,
    параметры — R/C/V values + tube SpiceModel.

    Imported by `scripts/regenerate-templates.py` via thin wrappers
    `_build_6p13s_se_resistive` / `_build_6zh32p_mic_preamp` /
    `_build_6zh38p_if_amp` ниже.
    """
    sch = Schematic(params.schematic_name)

    # === Supplies & input ===
    v_bb = sch.add_v_dc(value=params.v_bb, at=_V_BB_AT)
    v_g2 = sch.add_v_dc(value=params.v_g2, at=_V_G2_AT)
    v_in = sch.add_v_ac(
        value='VSIN', at=_V_IN_AT,
        amplitude=0.001, frequency=1000.0,
    )

    flg = sch.add_pwr_flag(at=_FLG_AT, rotation=180)

    # === Passives ===
    c_in = sch.add_capacitor(value=params.c_in, at=_C_IN_AT, rotation=90)
    r_g = sch.add_resistor(value=params.r_g, at=_R_G_AT)
    r_a = sch.add_resistor(value=params.r_a, at=_R_A_AT)
    r_k = sch.add_resistor(value=params.r_k, at=_R_K_AT)
    c_k = sch.add_capacitor(value=params.c_k, at=_C_K_AT)

    # === Tube (pentode subckt via Valve:EL84 4-pin symbol) ===
    x1 = sch.add_tube(
        spice_model=_tube_model(params),
        at=_TUBE_AT,
        symbol='Valve:EL84',
    )

    # === Grounds ===
    gnd_vbb = sch.add_ground(at=_GND_VBB_AT)
    gnd_vg2 = sch.add_ground(at=_GND_VG2_AT)
    gnd_vin = sch.add_ground(at=_GND_VIN_AT)
    gnd_rg = sch.add_ground(at=_GND_RG_AT)
    gnd_rk = sch.add_ground(at=_GND_RK_AT)
    gnd_ck = sch.add_ground(at=_GND_CK_AT)

    # === V_BB → B+ rail → R_a.pin_b ===
    # V_DC swap: pin_minus = real "+", pin_plus = real "-" (facade quirk
    # документирован в se-amp builder). Connect pin_plus to GND.
    # Route pin_minus horizontal-first (через (R_a.x, V_BB.pin_minus.y))
    # чтобы wire НЕ проходил через pin_plus position (вертикальная
    # Manhattan default корнером (V_BB.x, R_a.y) = (50.8, 60.96)
    # совпадает с pin_plus → 3-wire endpoint coincidence → short).
    sch.connect(v_bb.pin_plus, gnd_vbb.pin)
    _b_plus_rail_y = 50.8  # V_BB.pin_minus Y
    sch.connect(
        v_bb.pin_minus,
        Position(x_mm=_R_A_AT[0], y_mm=_b_plus_rail_y),
    )
    sch.connect(
        Position(x_mm=_R_A_AT[0], y_mm=_b_plus_rail_y), r_a.pin_b,
    )

    # === V_G2 → G2 rail → X1.G2 ===
    # Аналогично: route horizontal-first чтобы избежать pin_plus
    # midpoint collision.
    sch.connect(v_g2.pin_plus, gnd_vg2.pin)
    _g2_rail_y = 50.8  # V_G2.pin_minus Y
    sch.connect(
        v_g2.pin_minus,
        Position(x_mm=109.22, y_mm=_g2_rail_y),
    )
    sch.connect(
        Position(x_mm=109.22, y_mm=_g2_rail_y),
        x1.pin('G2'),
    )

    # === V_in → C_in → R_g + X1.G ===
    sch.connect(flg.pin, v_in.pin_plus)  # ERC needs PWR_FLAG on driven net
    sch.connect(v_in.pin_plus, gnd_vin.pin)  # V_in cold side to GND
    sch.connect(v_in.pin_minus, c_in.pin_a)
    sch.connect(c_in.pin_b, x1.pin('G'))
    sch.connect(c_in.pin_b, r_g.pin_a)
    sch.connect(r_g.pin_b, gnd_rg.pin)
    sch.junction(at=x1.pin('G'))  # T-junction: C_in.pin_b + R_g.pin_a + X1.G

    # === Plate ===
    sch.connect(r_a.pin_a, x1.pin('P'))

    # === Cathode: R_k ‖ C_k → GND ===
    sch.connect(x1.pin('K'), r_k.pin_a)
    # C_k.pin_a (left side, rot=0) connects to cathode rail at R_k.pin_a Y.
    # Pin layout: capacitor rot=0 → pin_a at (0, +3.81), pin_b at (0, -3.81)
    # relative. C_K placed at (109.22, 104.14 after snap), pin_a at
    # (109.22, 108.0) — но это снизу tube. Нужно cross-snap:
    # cathode rail Y = X1.K Y = 93.98 (X1 at (101.6, 85.09), K offset
    # (-2.54, 8.89) → (99.06, 93.98)). Connect через два сегмента.
    sch.connect(x1.pin('K'), Position(x_mm=_R_K_AT[0], y_mm=93.98))
    sch.connect(
        Position(x_mm=_R_K_AT[0], y_mm=93.98),
        Position(x_mm=_C_K_AT[0], y_mm=93.98),
    )
    sch.connect(Position(x_mm=_C_K_AT[0], y_mm=93.98), c_k.pin_a)
    sch.junction(at=(_R_K_AT[0], 93.98))
    sch.connect(r_k.pin_b, gnd_rk.pin)
    sch.connect(c_k.pin_b, gnd_ck.pin)

    # === Net labels (SPICE trace names) ===
    sch.label('input', at=_LABEL_INPUT_AT)
    sch.label('plate', at=_LABEL_PLATE_AT)
    sch.label('cathode', at=_LABEL_CATHODE_AT)

    # === SPICE directive — .op для default analysis ===
    sch.spice_directive('.op', at=_SPICE_OP_AT)

    return sch.save(path)


# === 3 thin wrappers — imported by regenerate-templates.py ===


def _build_6p13s_se_resistive(path: Path) -> Path:
    """Builds 6p13s-se-resistive reference fixture (T187 Phase 4)."""
    return _build_pentode_se_resistive(path, _PARAMS_6P13S)


def _build_6zh32p_mic_preamp(path: Path) -> Path:
    """Builds 6zh32p-mic-preamp reference fixture (T187 Phase 4)."""
    return _build_pentode_se_resistive(path, _PARAMS_6ZH32P)


def _build_6zh38p_if_amp(path: Path) -> Path:
    """Builds 6zh38p-if-amp reference fixture (T187 Phase 4)."""
    return _build_pentode_se_resistive(path, _PARAMS_6ZH38P)


# === Tests: smoke-build + netlist export ===


def _app_manager() -> SubprocessAppManager:
    return SubprocessAppManager(NativePlatformLayer())


@pytest.mark.parametrize(
    ('builder', 'tube_id', 'r_a_value'),
    [
        pytest.param(_build_6p13s_se_resistive, '6P13S', '5k', id='6p13s'),
        pytest.param(
            _build_6zh32p_mic_preamp, '6ZH32P', '100k', id='6zh32p',
        ),
        pytest.param(_build_6zh38p_if_amp, '6ZH38P', '10k', id='6zh38p'),
    ],
)
def test_pentode_se_resistive_builder_emits_expected_components(
    tmp_path: Path,
    builder: object,  # callable, but Protocol noise not worth it
    tube_id: str,
    r_a_value: str,
) -> None:
    sch_path = builder(tmp_path / f'{tube_id.lower()}.kicad_sch')  # type: ignore[operator]
    text = sch_path.read_text(encoding='utf-8')
    # 1 tube subckt + 5 passives + 6 GND + 1 PWR_FLAG + 3 voltage sources.
    assert f'"Sim.Name" "{tube_id}"' in text
    assert tube_id in text  # tube lib reference somewhere
    # R_a value drives plate-load semantic per template family.
    assert f'"Value" "{r_a_value}"' in text


@needs_kicad
@pytest.mark.parametrize(
    ('builder', 'tube_id'),
    [
        pytest.param(_build_6p13s_se_resistive, '6P13S', id='6p13s'),
        pytest.param(_build_6zh32p_mic_preamp, '6ZH32P', id='6zh32p'),
        pytest.param(_build_6zh38p_if_amp, '6ZH38P', id='6zh38p'),
    ],
)
async def test_pentode_se_resistive_kicad_cli_netlist_succeeds(
    tmp_path: Path,
    builder: object,
    tube_id: str,
) -> None:
    """kicad-cli sch export netlist must succeed on each builder output."""
    sch_path = builder(tmp_path / f'{tube_id.lower()}.kicad_sch')  # type: ignore[operator]
    exporter = KicadCliSchematicExporter(_app_manager())
    netlist = await exporter.export_spice_netlist(
        sch_path, tmp_path / f'{tube_id.lower()}.cir',
    )
    netlist_text = netlist.read_text(encoding='utf-8')
    assert f'X1 ' in netlist_text or f'XX1 ' in netlist_text
    assert '.include' in netlist_text
