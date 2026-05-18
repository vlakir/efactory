"""Unit-тесты на edit_component_value (T004b)."""

from __future__ import annotations

import pytest

from application.edit_component_value import (
    ComponentNotFoundError,
    MultipleMatchesError,
    edit_component_value,
)

_MINIMAL_SCH = '''(kicad_sch
	(version 20240128)
	(lib_symbols
		(symbol "Device:R"
			(property "Value" "R" (at 0 0 0))
		)
	)
	(symbol
		(lib_id "Device:R")
		(at 50.8 50.8 0)
		(uuid "00000000-0000-0000-0000-000000000001")
		(property "Reference" "R1" (at 52 49 0))
		(property "Value" "1k" (at 52 51 0))
	)
	(symbol
		(lib_id "Device:R")
		(at 70.0 50.8 0)
		(uuid "00000000-0000-0000-0000-000000000002")
		(property "Reference" "R2" (at 71 49 0))
		(property "Value" "2k2" (at 71 51 0))
	)
)
'''


def test_edit_replaces_value_and_returns_old(tmp_path) -> None:  # noqa: ANN001
    path = tmp_path / 'test.kicad_sch'
    path.write_text(_MINIMAL_SCH, encoding='utf-8')

    old = edit_component_value(path, 'R1', '10k')

    assert old == '1k'
    text = path.read_text(encoding='utf-8')
    assert '(property "Value" "10k"' in text
    assert '(property "Value" "1k"' not in text
    # R2 untouched
    assert '(property "Value" "2k2"' in text


def test_edit_idempotent_noop_returns_same(tmp_path) -> None:  # noqa: ANN001
    path = tmp_path / 'test.kicad_sch'
    path.write_text(_MINIMAL_SCH, encoding='utf-8')

    old = edit_component_value(path, 'R1', '1k')   # same value

    assert old == '1k'
    # File still contains '1k', untouched
    assert '(property "Value" "1k"' in path.read_text(encoding='utf-8')


def test_edit_missing_reference_raises(tmp_path) -> None:  # noqa: ANN001
    path = tmp_path / 'test.kicad_sch'
    path.write_text(_MINIMAL_SCH, encoding='utf-8')

    with pytest.raises(ComponentNotFoundError, match='R999'):
        edit_component_value(path, 'R999', '5k')


def test_edit_duplicate_reference_raises(tmp_path) -> None:  # noqa: ANN001
    # Synthetic: 2 symbols с одинаковым Reference R1 (annotation collision).
    dup = _MINIMAL_SCH.replace('"R2"', '"R1"')
    path = tmp_path / 'test.kicad_sch'
    path.write_text(dup, encoding='utf-8')

    with pytest.raises(MultipleMatchesError, match='Multiple'):
        edit_component_value(path, 'R1', '5k')


def test_edit_does_not_touch_lib_symbols_section(tmp_path) -> None:  # noqa: ANN001
    """Value-edit ищет symbol-instance по Reference; lib_symbols не имеют Reference и пропускаются."""
    path = tmp_path / 'test.kicad_sch'
    path.write_text(_MINIMAL_SCH, encoding='utf-8')

    edit_component_value(path, 'R1', '10k')

    text = path.read_text(encoding='utf-8')
    # lib_symbols Device:R сохранил оригинальный Value="R"
    assert '(symbol "Device:R"' in text
    assert '(property "Value" "R"' in text
