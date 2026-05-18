"""Unit-тесты `KicadSchematicWriter` — текстовая сериализация + ошибки."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from adapters.outbound.schematic_kicad.writer import KicadSchematicWriter
from domain.schematic import ComponentSpec, Position, SchematicSpec
from ports.outbound.schematic_writer import SchematicWriteError

if TYPE_CHECKING:
    from pathlib import Path


def _minimal_spec() -> SchematicSpec:
    return SchematicSpec(
        name='unit',
        components=(
            ComponentSpec(
                lib_id='Device:R',
                reference='R1',
                value='1k',
                position=Position(x_mm=10.0, y_mm=20.0),
                pins=('1', '2'),
            ),
        ),
    )


def test_writer_creates_file_and_returns_path(tmp_path: Path) -> None:
    out = tmp_path / 'nested' / 'sch.kicad_sch'
    result = KicadSchematicWriter().write(_minimal_spec(), out)
    assert result == out
    assert out.is_file()


def test_writer_header_contains_kicad_marker(tmp_path: Path) -> None:
    out = tmp_path / 'sch.kicad_sch'
    KicadSchematicWriter().write(_minimal_spec(), out)
    text = out.read_text(encoding='utf-8')
    assert text.startswith('(kicad_sch')
    assert '(version 20240128)' in text
    assert '(generator "efactory")' in text
    assert '(generator_version "10.0")' in text
    assert '(paper "A4")' in text


def test_writer_embeds_lib_symbol_snippet(tmp_path: Path) -> None:
    out = tmp_path / 'sch.kicad_sch'
    KicadSchematicWriter().write(_minimal_spec(), out)
    text = out.read_text(encoding='utf-8')
    # Snippet содержит `(symbol "Device:R"` внутри `(lib_symbols ...)`.
    lib_start = text.index('(lib_symbols')
    lib_end = text.index('\n\t)', lib_start)
    assert '(symbol "Device:R"' in text[lib_start:lib_end]


def test_writer_symbol_instance_includes_project_name(tmp_path: Path) -> None:
    out = tmp_path / 'sch.kicad_sch'
    KicadSchematicWriter().write(_minimal_spec(), out)
    text = out.read_text(encoding='utf-8')
    assert '(instances (project "unit"' in text
    assert '(reference "R1")' in text


def test_writer_power_symbol_omits_footprint(tmp_path: Path) -> None:
    spec = SchematicSpec(
        name='t',
        components=(
            ComponentSpec(
                lib_id='power:GND',
                reference='#PWR01',
                value='GND',
                position=Position(x_mm=0.0, y_mm=0.0),
                pins=('1',),
            ),
        ),
    )
    out = tmp_path / 'sch.kicad_sch'
    KicadSchematicWriter().write(spec, out)
    text = out.read_text(encoding='utf-8')
    # `power:*` пишется без Footprint/Datasheet.
    power_start = text.index('(symbol (lib_id "power:GND")')
    power_end = text.index('\n\t)', power_start)
    assert '"Footprint"' not in text[power_start:power_end]
    assert '"Datasheet"' not in text[power_start:power_end]


def test_writer_unknown_lib_id_raises(tmp_path: Path) -> None:
    spec = SchematicSpec(
        name='t',
        components=(
            ComponentSpec(
                lib_id='NoSuch:Symbol',
                reference='X1',
                value='?',
                position=Position(x_mm=0.0, y_mm=0.0),
                pins=('1',),
            ),
        ),
    )
    with pytest.raises(SchematicWriteError, match='NoSuch:Symbol'):
        KicadSchematicWriter().write(spec, tmp_path / 'sch.kicad_sch')


def test_writer_emits_junction_block(tmp_path: Path) -> None:
    from domain.schematic import JunctionSpec, LabelSpec, WireSpec

    spec = SchematicSpec(
        name='t',
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
            LabelSpec(text='net', position=Position(x_mm=5.0, y_mm=2.0)),
        ),
    )
    out = tmp_path / 'sch.kicad_sch'
    KicadSchematicWriter().write(spec, out)
    text = out.read_text(encoding='utf-8')
    assert '(junction (at 5 0)' in text


def test_writer_dedupes_lib_symbols(tmp_path: Path) -> None:
    spec = SchematicSpec(
        name='t',
        components=(
            ComponentSpec(
                lib_id='Device:R',
                reference='R1',
                value='1k',
                position=Position(x_mm=0.0, y_mm=0.0),
                pins=('1', '2'),
            ),
            ComponentSpec(
                lib_id='Device:R',
                reference='R2',
                value='2k',
                position=Position(x_mm=10.0, y_mm=0.0),
                pins=('1', '2'),
            ),
        ),
    )
    out = tmp_path / 'sch.kicad_sch'
    KicadSchematicWriter().write(spec, out)
    text = out.read_text(encoding='utf-8')
    assert text.count('(symbol "Device:R"') == 1
