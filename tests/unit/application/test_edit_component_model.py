"""Unit-тесты на edit_component_model (T005 Phase 1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from application.edit_component_model import edit_component_model
from application.edit_component_value import ComponentNotFoundError
from domain.spice_model import ComponentCategory, ModelSource, SpiceModel

_SCH_WITH_SUBCKT = '''(kicad_sch
	(version 20240128)
	(lib_symbols
		(symbol "Valve:EL84"
			(property "Value" "EL84" (at 0 0 0))
		)
	)
	(symbol
		(lib_id "Valve:EL84")
		(at 100 80 0)
		(property "Reference" "X1" (at 105 70 0))
		(property "Value" "6P14P" (at 105 90 0))
		(property "Sim.Device" "subckt" (at 100 80 0))
		(property "Sim.Library" "/old/path/6P14P.lib" (at 100 80 0))
		(property "Sim.Name" "6P14P" (at 100 80 0))
	)
	(symbol
		(lib_id "Device:R")
		(at 50 80 0)
		(property "Reference" "R1" (at 52 79 0))
		(property "Value" "10k" (at 52 81 0))
	)
)
'''


def _make_tube_model(model_id: str, file_path: str) -> SpiceModel:
    return SpiceModel(
        id=model_id, name=model_id,
        category=ComponentCategory.TUBE, subcategory='triode',
        source=ModelSource.CUSTOM,
        file_path=Path(file_path),
        subckt_pins=('P', 'G', 'K'),
    )


def test_model_swap_updates_three_properties(tmp_path: Path) -> None:
    sch = tmp_path / 'amp.kicad_sch'
    sch.write_text(_SCH_WITH_SUBCKT, encoding='utf-8')

    old = edit_component_model(
        sch, 'X1',
        _make_tube_model('6N1P', '/data/tubes/6N1P.lib'),
    )

    assert old == {
        'Value': '6P14P',
        'Sim.Library': '/old/path/6P14P.lib',
        'Sim.Name': '6P14P',
    }
    text = sch.read_text(encoding='utf-8')
    assert '(property "Value" "6N1P"' in text
    assert '(property "Sim.Library" "/data/tubes/6N1P.lib"' in text
    assert '(property "Sim.Name" "6N1P"' in text


def test_model_swap_noop_returns_old_values_unchanged(tmp_path: Path) -> None:
    sch = tmp_path / 'amp.kicad_sch'
    sch.write_text(_SCH_WITH_SUBCKT, encoding='utf-8')

    old = edit_component_model(
        sch, 'X1',
        _make_tube_model('6P14P', '/old/path/6P14P.lib'),
    )

    assert old == {
        'Value': '6P14P',
        'Sim.Library': '/old/path/6P14P.lib',
        'Sim.Name': '6P14P',
    }


def test_model_swap_missing_reference_raises(tmp_path: Path) -> None:
    sch = tmp_path / 'amp.kicad_sch'
    sch.write_text(_SCH_WITH_SUBCKT, encoding='utf-8')

    with pytest.raises(ComponentNotFoundError, match='X999'):
        edit_component_model(
            sch, 'X999',
            _make_tube_model('6N1P', '/x.lib'),
        )


def test_model_swap_on_non_subckt_component_raises(tmp_path: Path) -> None:
    """R1 не имеет Sim.Library — edit_component_model должен бросить."""
    sch = tmp_path / 'amp.kicad_sch'
    sch.write_text(_SCH_WITH_SUBCKT, encoding='utf-8')

    with pytest.raises(ComponentNotFoundError, match='Sim.Library'):
        edit_component_model(
            sch, 'R1',
            _make_tube_model('6N1P', '/x.lib'),
        )
