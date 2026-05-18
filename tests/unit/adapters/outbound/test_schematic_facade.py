"""Unit-тесты `Schematic` facade — без I/O (через `to_spec()`)."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from adapters.outbound.schematic_kicad.facade import Schematic
from domain.schematic import Position
from domain.spice_model import (
    ComponentCategory,
    ModelSource,
    SpiceModel,
)


def test_resistor_pins_at_rotation_zero() -> None:
    sch = Schematic('t')
    r = sch.add_resistor(reference='R1', value='1k', at=(0.0, 0.0))
    # Локальные пины R: (0, +3.81) и (0, -3.81); ротация 0 — без изменений.
    assert r.pin_a == Position(x_mm=0.0, y_mm=3.81)
    assert r.pin_b == Position(x_mm=0.0, y_mm=-3.81)


def test_resistor_pins_at_rotation_90_ccw() -> None:
    """CCW 90°: локальный (0, 3.81) → глобальный (-3.81, 0)."""
    sch = Schematic('t')
    r = sch.add_resistor(
        reference='R1', value='1k', at=(100.0, 50.0), rotation=90.0,
    )
    assert r.pin_a == Position(x_mm=100.0 - 3.81, y_mm=50.0)
    assert r.pin_b == Position(x_mm=100.0 + 3.81, y_mm=50.0)


def test_vdc_pins_at_rotation_180() -> None:
    """180° инвертирует Y: (0, +5.08) → (0, -5.08) (KiCad 9 VDC layout)."""
    sch = Schematic('t')
    v = sch.add_v_dc(
        reference='V1', value='1', at=(50.8, 62.23), rotation=180.0,
    )
    assert v.pin_plus.x_mm == pytest.approx(50.8)
    assert v.pin_plus.y_mm == pytest.approx(62.23 - 5.08)
    assert v.pin_minus.y_mm == pytest.approx(62.23 + 5.08)


def test_vdc_default_sim_properties_include_value_in_params() -> None:
    sch = Schematic('t')
    sch.add_v_dc(reference='V1', value='5', at=(0.0, 0.0))
    spec = sch.to_spec()
    props = spec.components[0].properties
    # Sim.Device='V' (built-in voltage source), Sim.Type='DC' — без Sim.Library
    # чтобы не триггерить «Не найдено определение модели симуляции» в KiCad GUI.
    assert props['Sim.Device'] == 'V'
    assert props['Sim.Type'] == 'DC'
    assert 'dc=5' in props['Sim.Params']
    assert 'Sim.Library' not in props


def test_ground_auto_increments_reference() -> None:
    sch = Schematic('t')
    g1 = sch.add_ground(at=(0.0, 0.0))
    g2 = sch.add_ground(at=(0.0, 10.0))
    g3 = sch.add_ground(at=(0.0, 20.0), reference='#PWR_CUSTOM')
    assert g1.reference == '#PWR01'
    assert g2.reference == '#PWR02'
    assert g3.reference == '#PWR_CUSTOM'


def test_connect_collinear_y_emits_single_wire() -> None:
    sch = Schematic('t')
    sch.connect(
        Position(x_mm=0.0, y_mm=5.0),
        Position(x_mm=10.0, y_mm=5.0),
    )
    assert len(sch.to_spec().wires) == 1


def test_connect_diagonal_emits_two_wires_with_corner() -> None:
    sch = Schematic('t')
    sch.connect(
        Position(x_mm=0.0, y_mm=0.0),
        Position(x_mm=10.0, y_mm=20.0),
    )
    wires = sch.to_spec().wires
    assert len(wires) == 2
    # Corner — (start.x, end.y) = (0, 20).
    assert wires[0].end == Position(x_mm=0.0, y_mm=20.0)
    assert wires[1].start == Position(x_mm=0.0, y_mm=20.0)
    assert wires[1].end == Position(x_mm=10.0, y_mm=20.0)


def test_connect_same_point_is_noop() -> None:
    sch = Schematic('t')
    p = Position(x_mm=1.0, y_mm=1.0)
    sch.connect(p, p)
    assert sch.to_spec().wires == ()


def test_label_records_position() -> None:
    sch = Schematic('t')
    sch.label('in', at=(5.0, 6.0))
    labels = sch.to_spec().labels
    assert labels[0].text == 'in'
    assert labels[0].position == Position(x_mm=5.0, y_mm=6.0)


def test_spice_directive_recorded_as_text_node() -> None:
    sch = Schematic('t')
    sch.spice_directive('.tran 100u 80m', at=(50.8, 80.0))
    texts = sch.to_spec().texts
    assert len(texts) == 1
    assert texts[0].text == '.tran 100u 80m'
    assert texts[0].position == Position(x_mm=50.8, y_mm=80.0)


def test_to_spec_carries_name_and_all_components() -> None:
    sch = Schematic('rc')
    sch.add_v_dc(reference='V1', value='1', at=(0.0, 0.0))
    sch.add_resistor(reference='R1', value='1k', at=(10.0, 0.0))
    sch.add_capacitor(reference='C1', value='1u', at=(20.0, 0.0))
    sch.add_ground(at=(0.0, 10.0))
    spec = sch.to_spec()
    assert spec.name == 'rc'
    assert [c.reference for c in spec.components] == ['V1', 'R1', 'C1', '#PWR01']


def test_junction_at_recorded() -> None:
    sch = Schematic('t')
    sch.junction(at=(5.0, 5.0))
    assert sch.to_spec().junctions[0].at == Position(x_mm=5.0, y_mm=5.0)


def test_handle_pin_by_number_unknown_raises() -> None:
    sch = Schematic('t')
    r = sch.add_resistor(reference='R1', value='1k', at=(0.0, 0.0))
    with pytest.raises(KeyError, match='no pin'):
        r.pin_by_number('99')


def test_pin_transform_pin_b_position_match_manual_calculation() -> None:
    """Проверка ротации совпадает с расчётом для R1 в RC-фикстуре T008."""
    sch = Schematic('t')
    r = sch.add_resistor(
        reference='R1', value='1k', at=(88.9, 55.88), rotation=90.0,
    )
    # Локальный pin "2" = (0, -3.81); rotate 90 CCW → (3.81, 0).
    # Global = (88.9 + 3.81, 55.88) = (92.71, 55.88).
    assert r.pin_b.x_mm == pytest.approx(92.71)
    assert r.pin_b.y_mm == pytest.approx(55.88)


def test_add_accepts_position_object_directly() -> None:
    """`at=` принимает не только tuple, но и готовый Position."""
    sch = Schematic('t')
    r = sch.add_resistor(
        reference='R1', value='1k', at=Position(x_mm=5.0, y_mm=6.0),
    )
    assert r.pin_a == Position(x_mm=5.0, y_mm=9.81)


def test_round_grid_eliminates_float_jitter() -> None:
    """Проверка что rotation 90 даёт ровный 3.81, не 3.8099999."""
    sch = Schematic('t')
    r = sch.add_resistor(
        reference='R1', value='1k', at=(0.0, 0.0), rotation=90.0,
    )
    # math.cos(90°) ≈ 6.12e-17 (не ровно 0). _round_grid должен это убрать.
    assert not math.isnan(r.pin_a.x_mm)
    assert r.pin_a.x_mm == -3.81  # без jitter
    assert r.pin_a.y_mm == 0.0


# === Phase 2: BJT / MOSFET / subckt / tube / transformer ===


def test_add_bjt_npn_sim_properties_and_pin_handles() -> None:
    sch = Schematic('t')
    q = sch.add_bjt(
        reference='Q1', value='2N3904',
        polarity='NPN', model_name='2N3904',
        at=(100.0, 50.0),
    )
    spec = sch.to_spec()
    c = spec.components[0]
    assert c.lib_id == 'Device:Q_NPN'
    assert c.properties['Sim.Device'] == 'NPN'
    assert c.properties['Sim.Model'] == '2N3904'
    assert c.properties['Sim.Pins'] == 'C=1 B=2 E=3'
    # pin handles по semantic именам
    assert q.pin_b == Position(x_mm=94.92, y_mm=50.0)
    assert q.pin_c == Position(x_mm=102.54, y_mm=50.0 - 5.08)
    assert q.pin_e == Position(x_mm=102.54, y_mm=50.0 + 5.08)


def test_add_bjt_pnp_uses_pnp_symbol_and_sim_device() -> None:
    sch = Schematic('t')
    sch.add_bjt(
        reference='Q2', value='2N3906',
        polarity='PNP', model_name='2N3906',
        at=(0.0, 0.0),
    )
    c = sch.to_spec().components[0]
    assert c.lib_id == 'Device:Q_PNP'
    assert c.properties['Sim.Device'] == 'PNP'


def test_add_bjt_invalid_polarity_raises() -> None:
    sch = Schematic('t')
    with pytest.raises(ValueError, match='NPN.*PNP'):
        sch.add_bjt(
            reference='Q1', value='?',
            polarity='JFET',  # invalid
            model_name='?', at=(0.0, 0.0),
        )


def test_add_mosfet_nmos_sim_properties_and_pins() -> None:
    sch = Schematic('t')
    m = sch.add_mosfet(
        reference='M1', value='IRF540',
        polarity='NMOS', model_name='IRF540',
        at=(50.0, 50.0),
    )
    c = sch.to_spec().components[0]
    assert c.lib_id == 'Device:Q_NMOS'
    assert c.properties['Sim.Device'] == 'NMOS'
    assert c.properties['Sim.Pins'] == 'D=1 G=2 S=3'
    assert m.pin_g.x_mm == pytest.approx(50.0 - 5.08)
    assert m.pin_d.y_mm == pytest.approx(50.0 - 5.08)
    assert m.pin_s.y_mm == pytest.approx(50.0 + 5.08)


def test_add_mosfet_invalid_polarity_raises() -> None:
    sch = Schematic('t')
    with pytest.raises(ValueError, match='NMOS.*PMOS'):
        sch.add_mosfet(
            reference='M1', value='?', polarity='JFET',
            model_name='?', at=(0.0, 0.0),
        )


def test_add_subckt_writes_sim_library_and_pin_mapping() -> None:
    sch = Schematic('t')
    sub = sch.add_subckt(
        reference='XV1', model_id='6P14P',
        lib_path=Path('/some/where/6P14P.lib'),
        pin_names=('P', 'G2', 'G', 'K'),
        at=(50.0, 50.0),
    )
    c = sch.to_spec().components[0]
    assert c.lib_id == 'Connector_Generic:Conn_01x04'
    assert c.properties['Sim.Device'] == 'subckt'
    assert c.properties['Sim.Name'] == '6P14P'
    assert c.properties['Sim.Library'] == '/some/where/6P14P.lib'
    assert c.properties['Sim.Pins'] == '1=P 2=G2 3=G 4=K'
    # pin('P') — semantic access
    assert sub.pin('P') == Position(x_mm=50.0 - 5.08, y_mm=50.0 - 2.54)
    assert sub.pin('K') == Position(x_mm=50.0 - 5.08, y_mm=50.0 + 5.08)


def test_add_subckt_wrong_pin_count_raises() -> None:
    sch = Schematic('t')
    with pytest.raises(ValueError, match='4 entries'):
        sch.add_subckt(
            reference='XV1', model_id='?',
            lib_path=Path('/x.lib'),
            pin_names=('A', 'B'),  # 2 pins, expected 4
            at=(0.0, 0.0),
        )


def test_subcircuit_pin_unknown_name_raises() -> None:
    sch = Schematic('t')
    sub = sch.add_subckt(
        reference='X', model_id='?',
        lib_path=Path('/x.lib'),
        pin_names=('A', 'B', 'C', 'D'),
        at=(0.0, 0.0),
    )
    with pytest.raises(KeyError, match="no pin 'Z'"):
        sub.pin('Z')


def test_add_tube_uses_spice_model_metadata() -> None:
    sch = Schematic('t')
    model = SpiceModel(
        id='6P14P', name='6П14П',
        category=ComponentCategory.TUBE, subcategory='pentode',
        source=ModelSource.CUSTOM,
        file_path=Path('/data/tubes/6P14P.lib'),
        subckt_pins=('P', 'G2', 'G', 'K'),
    )
    sch.add_tube(spice_model=model, reference='XV1', at=(0.0, 0.0))
    c = sch.to_spec().components[0]
    assert c.value == '6P14P'
    assert c.properties['Sim.Name'] == '6P14P'
    assert c.properties['Sim.Library'] == '/data/tubes/6P14P.lib'
    assert c.properties['Sim.Pins'] == '1=P 2=G2 3=G 4=K'


def test_add_transformer_uses_spice_model_metadata() -> None:
    sch = Schematic('t')
    model = SpiceModel(
        id='OPT_SE_5K_8', name='OPT_SE_5K_8',
        category=ComponentCategory.TRANSFORMER, subcategory='opt',
        source=ModelSource.GENERIC,
        file_path=Path('/data/trafo/OPT_SE_5K_8.lib'),
        subckt_pins=('P1', 'P2', 'S1', 'S2'),
    )
    sch.add_transformer(spice_model=model, reference='XT1', at=(10.0, 10.0))
    c = sch.to_spec().components[0]
    assert c.properties['Sim.Name'] == 'OPT_SE_5K_8'
    assert c.properties['Sim.Pins'] == '1=P1 2=P2 3=S1 4=S2'


# ---------- T104: auto-numbering refs ----------


def test_auto_ref_resistor_sequence() -> None:
    """Без explicit reference: R1, R2, R3 в порядке add'а."""
    sch = Schematic('t')
    r1 = sch.add_resistor(value='1k', at=(0.0, 0.0))
    r2 = sch.add_resistor(value='2k', at=(10.0, 0.0))
    r3 = sch.add_resistor(value='3k', at=(20.0, 0.0))
    assert (r1.reference, r2.reference, r3.reference) == ('R1', 'R2', 'R3')


def test_auto_ref_per_kind_independent() -> None:
    """Каждый kind — свой счётчик: R1/C1/L1/D1/V1/Q1/M1/X1."""
    sch = Schematic('t')
    r = sch.add_resistor(value='1k', at=(0.0, 0.0))
    c = sch.add_capacitor(value='1u', at=(10.0, 0.0))
    li = sch.add_inductor(value='1m', at=(20.0, 0.0))
    d = sch.add_diode(value='D', spice_params='Is=1n', at=(30.0, 0.0))
    v = sch.add_v_dc(value='5', at=(40.0, 0.0))
    q = sch.add_bjt(
        value='2N3904', polarity='NPN', model_name='2N3904',
        at=(50.0, 0.0),
    )
    m = sch.add_mosfet(
        value='IRF540', polarity='NMOS', model_name='IRF540',
        at=(60.0, 0.0),
    )
    assert r.reference == 'R1'
    assert c.reference == 'C1'
    assert li.reference == 'L1'
    assert d.reference == 'D1'
    assert v.reference == 'V1'
    assert q.reference == 'Q1'
    assert m.reference == 'M1'


def test_auto_ref_skips_explicit() -> None:
    """Explicit R5 → следующий auto = R1 (не R6); затем R2, R3, R4 (R5 занят)."""
    sch = Schematic('t')
    r5 = sch.add_resistor(reference='R5', value='5k', at=(0.0, 0.0))
    r1 = sch.add_resistor(value='1k', at=(10.0, 0.0))
    r2 = sch.add_resistor(value='2k', at=(20.0, 0.0))
    r3 = sch.add_resistor(value='3k', at=(30.0, 0.0))
    r4 = sch.add_resistor(value='4k', at=(40.0, 0.0))
    # Auto-counter заполняет дыры: после R5 — R1, R2, R3, R4, потом R6
    r6 = sch.add_resistor(value='6k', at=(50.0, 0.0))
    refs = (r5.reference, r1.reference, r2.reference, r3.reference,
            r4.reference, r6.reference)
    assert refs == ('R5', 'R1', 'R2', 'R3', 'R4', 'R6')


def test_auto_ref_tube_uses_x_prefix() -> None:
    """add_tube без reference: X1 (subckt SPICE convention)."""
    sch = Schematic('t')
    model = SpiceModel(
        id='6P14P', name='6П14П',
        category=ComponentCategory.TUBE, subcategory='pentode',
        source=ModelSource.CUSTOM,
        file_path=Path('/data/tubes/6P14P.lib'),
        subckt_pins=('P', 'G2', 'G', 'K'),
    )
    xv = sch.add_tube(spice_model=model, at=(0.0, 0.0))
    assert xv.reference == 'X1'


def test_auto_ref_explicit_overrides() -> None:
    """Explicit reference имеет приоритет — auto не вмешивается."""
    sch = Schematic('t')
    r = sch.add_resistor(reference='Rload', value='100k', at=(0.0, 0.0))
    assert r.reference == 'Rload'


# ---------- T101: add_diode with SpiceModel (library) ----------


def test_add_diode_with_spice_model_emits_subckt_properties() -> None:
    """add_diode(spice_model=...) → X-prefix ref + Sim.Device=subckt."""
    sch = Schematic('t')
    model = SpiceModel(
        id='1N4007', name='1N4007',
        category=ComponentCategory.DIODE, subcategory='rectifier',
        source=ModelSource.DUNCAN,
        file_path=Path('/data/diodes/1N4007.lib'),
        subckt_pins=('A', 'K'),
    )
    d = sch.add_diode(spice_model=model, at=(10.0, 10.0))
    assert d.reference == 'X1'   # auto X-prefix for subckt
    c = sch.to_spec().components[0]
    assert c.value == '1N4007'
    assert c.properties['Sim.Device'] == 'subckt'
    assert c.properties['Sim.Name'] == '1N4007'
    assert c.properties['Sim.Library'] == '/data/diodes/1N4007.lib'
    assert c.properties['Sim.Pins'] == '1=K 2=A'


def test_add_diode_with_spice_params_uses_d_prefix_inline() -> None:
    """add_diode(spice_params=...) → legacy D-primitive inline."""
    sch = Schematic('t')
    d = sch.add_diode(
        value='1N4148',
        spice_params='Is=2.52n N=1.752 Rs=0.568',
        at=(10.0, 10.0),
    )
    assert d.reference == 'D1'
    c = sch.to_spec().components[0]
    assert c.properties['Sim.Device'] == 'D'
    assert c.properties['Sim.Params'] == 'Is=2.52n N=1.752 Rs=0.568'
    assert 'Sim.Library' not in c.properties


def test_add_diode_rejects_both_spice_model_and_spice_params() -> None:
    """Нельзя передать оба — фасад просит выбрать один."""
    sch = Schematic('t')
    model = SpiceModel(
        id='1N4007', name='1N4007',
        category=ComponentCategory.DIODE, subcategory='rectifier',
        source=ModelSource.DUNCAN,
        file_path=Path('/data/1N4007.lib'),
        subckt_pins=('A', 'K'),
    )
    with pytest.raises(ValueError, match='только один'):
        sch.add_diode(
            spice_model=model, spice_params='Is=1n', at=(0.0, 0.0),
        )


def test_add_diode_rejects_neither() -> None:
    """Hardcoded default удалён в T101 — нужен spice_model или spice_params."""
    sch = Schematic('t')
    with pytest.raises(ValueError, match='spice_model.*spice_params'):
        sch.add_diode(at=(0.0, 0.0))


def test_add_diode_rejects_non_diode_category() -> None:
    """spice_model должен быть category=DIODE."""
    sch = Schematic('t')
    # Намеренно tube model — должен отбраковываться.
    tube = SpiceModel(
        id='6P14P', name='6P14P',
        category=ComponentCategory.TUBE, subcategory='pentode',
        source=ModelSource.CUSTOM,
        file_path=Path('/data/6P14P.lib'),
        subckt_pins=('P', 'G2', 'G', 'K'),
    )
    with pytest.raises(ValueError, match='category должна быть DIODE'):
        sch.add_diode(spice_model=tube, at=(0.0, 0.0))


def test_add_diode_spice_params_requires_value() -> None:
    sch = Schematic('t')
    with pytest.raises(ValueError, match='укажите value'):
        sch.add_diode(spice_params='Is=1n', at=(0.0, 0.0))
