"""Unit-тесты `Schematic` facade — без I/O (через `to_spec()`)."""

from __future__ import annotations

import math

import pytest

from adapters.outbound.schematic_kicad.facade import Schematic
from domain.schematic import Position


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
    """180° инвертирует Y: (0, +2.54) → (0, -2.54)."""
    sch = Schematic('t')
    v = sch.add_v_dc(
        reference='V1', value='1', at=(50.8, 62.23), rotation=180.0,
    )
    assert v.pin_plus.x_mm == pytest.approx(50.8)
    assert v.pin_plus.y_mm == pytest.approx(62.23 - 2.54)
    assert v.pin_minus.y_mm == pytest.approx(62.23 + 2.54)


def test_vdc_default_sim_properties_include_value_in_params() -> None:
    sch = Schematic('t')
    sch.add_v_dc(reference='V1', value='5', at=(0.0, 0.0))
    spec = sch.to_spec()
    props = spec.components[0].properties
    assert props['Sim.Device'] == 'SPICE'
    assert props['Sim.Type'] == 'V'
    assert 'dc=5' in props['Sim.Params']


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
