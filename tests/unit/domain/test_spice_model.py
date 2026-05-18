"""Domain: SpiceModel (T006)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from domain.spice_model import (
    ModelSource,
    SpiceModel,
    TubeType,
)


def _model(**overrides: object) -> SpiceModel:
    defaults: dict[str, object] = {
        'id': 'GENERIC_TRIODE',
        'name': 'GENERIC_TRIODE',
        'tube_type': TubeType.TRIODE,
        'source': ModelSource.KOREN,
        'file_path': Path('/data/models/tubes/koren/GENERIC_TRIODE.lib'),
        'subckt_pins': ('P', 'G', 'K'),
    }
    defaults.update(overrides)
    return SpiceModel.model_validate(defaults)


def test_spice_model_minimum_fields() -> None:
    m = _model()
    assert m.id == 'GENERIC_TRIODE'
    assert m.tube_type is TubeType.TRIODE
    assert m.source is ModelSource.KOREN


@pytest.mark.parametrize(
    'good_id',
    ['EL34', '6N2P', '6P14P', '12AX7', 'GENERIC_TRIODE', 'EL34_KOREN'],
)
def test_spice_model_id_accepts_uppercase_alnum_underscore(good_id: str) -> None:
    m = _model(id=good_id)
    assert m.id == good_id


@pytest.mark.parametrize(
    'bad_id',
    ['', 'el34', 'EL-34', 'EL 34', '_EL34', 'EL34!', 'a', 'A'],
)
def test_spice_model_id_rejects_bad_format(bad_id: str) -> None:
    with pytest.raises(ValidationError):
        _model(id=bad_id)


def test_spice_model_is_frozen() -> None:
    m = _model()
    with pytest.raises(ValidationError):
        m.name = 'other'  # type: ignore[misc]


def test_spice_model_pins_tuple_preserved() -> None:
    m = _model(subckt_pins=('P', 'G2', 'G', 'K', 'H'), tube_type=TubeType.PENTODE)
    assert m.subckt_pins == ('P', 'G2', 'G', 'K', 'H')


def test_tube_type_enum_values() -> None:
    assert TubeType.TRIODE.value == 'triode'
    assert TubeType.PENTODE.value == 'pentode'
    assert TubeType.DUAL_TRIODE.value == 'dual_triode'


def test_model_source_enum_values() -> None:
    assert set(ModelSource) == {
        ModelSource.KOREN,
        ModelSource.AYUMI,
        ModelSource.DUNCAN,
        ModelSource.CUSTOM,
    }
