"""Unit-тесты domain VO для T100 schematic facade."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.schematic import (
    ComponentSpec,
    JunctionSpec,
    LabelSpec,
    Position,
    SchematicSpec,
    WireSpec,
)


def test_position_is_immutable() -> None:
    pos = Position(x_mm=1.0, y_mm=2.0)
    with pytest.raises(ValidationError):
        pos.x_mm = 9.0  # type: ignore[misc]


def test_wire_zero_length_rejected() -> None:
    with pytest.raises(ValidationError):
        WireSpec(
            start=Position(x_mm=5.0, y_mm=5.0),
            end=Position(x_mm=5.0, y_mm=5.0),
        )


def test_wire_non_degenerate_ok() -> None:
    wire = WireSpec(
        start=Position(x_mm=1.0, y_mm=2.0),
        end=Position(x_mm=1.0, y_mm=3.0),
    )
    assert wire.end.y_mm == 3.0


def test_component_spec_required_fields() -> None:
    comp = ComponentSpec(
        lib_id='Device:R',
        reference='R1',
        value='1k',
        position=Position(x_mm=10.0, y_mm=20.0),
        pins=('1', '2'),
    )
    assert comp.rotation == 0.0
    assert comp.properties == {}
    assert comp.pins == ('1', '2')


def test_schematic_spec_defaults_empty() -> None:
    spec = SchematicSpec(name='empty')
    assert spec.components == ()
    assert spec.wires == ()
    assert spec.junctions == ()
    assert spec.labels == ()


def test_schematic_spec_holds_all_sections() -> None:
    spec = SchematicSpec(
        name='rc',
        components=(
            ComponentSpec(
                lib_id='Device:R',
                reference='R1',
                value='1k',
                position=Position(x_mm=0.0, y_mm=0.0),
                pins=('1', '2'),
            ),
        ),
        wires=(
            WireSpec(
                start=Position(x_mm=0.0, y_mm=0.0),
                end=Position(x_mm=10.0, y_mm=0.0),
            ),
        ),
        junctions=(JunctionSpec(at=Position(x_mm=5.0, y_mm=0.0)),),
        labels=(
            LabelSpec(text='out', position=Position(x_mm=5.0, y_mm=2.0)),
        ),
    )
    assert len(spec.components) == 1
    assert len(spec.wires) == 1
    assert len(spec.junctions) == 1
    assert len(spec.labels) == 1
