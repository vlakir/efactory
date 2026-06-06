"""T192: multi-sheet facade + writer s-expr emission tests."""

from __future__ import annotations

from pathlib import Path

from adapters.outbound.schematic_kicad.facade import Schematic
from adapters.outbound.schematic_kicad.writer import KicadSchematicWriter
from domain.schematic import Position, SubSheetSpec


def test_facade_add_sub_sheet() -> None:
    # Use on-grid coordinates (1.27 mm KiCad grid) — facade snaps inputs.
    sch = Schematic(name='parent')
    sch.add_sub_sheet(
        sheet_name='psu',
        sheet_file='psu.kicad_sch',
        at=(50.8, 60.96),
        width_mm=30.0,
        height_mm=20.0,
    )
    spec = sch.to_spec()
    assert len(spec.sub_sheets) == 1
    sub = spec.sub_sheets[0]
    assert sub.sheet_name == 'psu'
    assert sub.sheet_file == 'psu.kicad_sch'
    assert sub.position == Position(x_mm=50.8, y_mm=60.96)


def test_facade_multiple_sub_sheets_preserve_order() -> None:
    sch = Schematic(name='parent')
    sch.add_sub_sheet(
        sheet_name='psu', sheet_file='psu.kicad_sch', at=(10.16, 10.16)
    )
    sch.add_sub_sheet(
        sheet_name='preamp', sheet_file='preamp.kicad_sch', at=(60.96, 10.16)
    )
    spec = sch.to_spec()
    names = [s.sheet_name for s in spec.sub_sheets]
    assert names == ['psu', 'preamp']


def test_writer_emits_sheet_block(tmp_path: Path) -> None:
    sch = Schematic(name='parent')
    sch.add_sub_sheet(
        sheet_name='psu',
        sheet_file='psu.kicad_sch',
        at=(50.8, 60.96),
    )
    out = tmp_path / 'parent.kicad_sch'
    KicadSchematicWriter().write(sch.to_spec(), out)
    text = out.read_text(encoding='utf-8')
    assert '(sheet' in text
    assert '(property "Sheetname" "psu"' in text
    assert '(property "Sheetfile" "psu.kicad_sch"' in text
    assert '(size 30 20)' in text  # _fmt uses .6g → 30.0 → "30"


def test_writer_emits_multiple_sheets(tmp_path: Path) -> None:
    sch = Schematic(name='parent')
    sch.add_sub_sheet(
        sheet_name='psu', sheet_file='psu.kicad_sch', at=(10.16, 10.16)
    )
    sch.add_sub_sheet(
        sheet_name='preamp', sheet_file='preamp.kicad_sch', at=(60.96, 10.16)
    )
    out = tmp_path / 'parent.kicad_sch'
    KicadSchematicWriter().write(sch.to_spec(), out)
    text = out.read_text(encoding='utf-8')
    assert text.count('\t(sheet\n') == 2
    assert 'preamp.kicad_sch' in text
    assert 'psu.kicad_sch' in text


def test_sub_sheet_spec_validation() -> None:
    SubSheetSpec(
        sheet_name='x',
        sheet_file='x.kicad_sch',
        position=Position(x_mm=0.0, y_mm=0.0),
        width_mm=10.0,
        height_mm=10.0,
    )

    # Zero width/height rejected.
    import pytest

    with pytest.raises(ValueError):
        SubSheetSpec(
            sheet_name='x',
            sheet_file='x.kicad_sch',
            position=Position(x_mm=0.0, y_mm=0.0),
            width_mm=0.0,
            height_mm=10.0,
        )


def test_facade_save_round_trip(tmp_path: Path) -> None:
    """End-to-end: child + parent schematic write через facade.save."""
    child = Schematic(name='psu')
    child.add_resistor(value='10k', at=(0.0, 0.0))
    child_path = tmp_path / 'psu.kicad_sch'
    child.save(child_path)
    assert child_path.is_file()

    parent = Schematic(name='top')
    parent.add_sub_sheet(
        sheet_name='psu', sheet_file='psu.kicad_sch', at=(50.8, 60.96)
    )
    parent_path = tmp_path / 'top.kicad_sch'
    parent.save(parent_path)
    assert parent_path.is_file()
    parent_text = parent_path.read_text(encoding='utf-8')
    assert 'psu.kicad_sch' in parent_text
