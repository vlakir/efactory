"""Domain: SpiceModel (T006 + T007 generalization)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from domain.spice_model import (
    ComponentCategory,
    LoadKind,
    ModelSource,
    SpiceModel,
    TransformerKind,
    TubeType,
)


def _tube(**overrides: object) -> SpiceModel:
    defaults: dict[str, object] = {
        'id': 'GENERIC_TRIODE',
        'name': 'GENERIC_TRIODE',
        'category': ComponentCategory.TUBE,
        'subcategory': TubeType.TRIODE.value,
        'source': ModelSource.KOREN,
        'file_path': Path('/data/models/tubes/koren/GENERIC_TRIODE.lib'),
        'subckt_pins': ('P', 'G', 'K'),
    }
    defaults.update(overrides)
    return SpiceModel.model_validate(defaults)


def _opt(**overrides: object) -> SpiceModel:
    defaults: dict[str, object] = {
        'id': 'OPT_SE_5K_8',
        'name': 'OPT_SE_5K_8',
        'category': ComponentCategory.TRANSFORMER,
        'subcategory': TransformerKind.OPT.value,
        'source': ModelSource.GENERIC,
        'file_path': Path('/data/models/transformers/generic/OPT_SE_5K_8.lib'),
        'subckt_pins': ('P1', 'P2', 'S1', 'S2'),
    }
    defaults.update(overrides)
    return SpiceModel.model_validate(defaults)


def test_spice_model_tube_with_full_metadata() -> None:
    m = _tube()
    assert m.category is ComponentCategory.TUBE
    assert m.tube_type is TubeType.TRIODE


def test_spice_model_transformer_with_full_metadata() -> None:
    m = _opt()
    assert m.category is ComponentCategory.TRANSFORMER
    assert m.transformer_kind is TransformerKind.OPT


def test_spice_model_load() -> None:
    m = SpiceModel.model_validate(
        {
            'id': 'SPEAKER_8OHM',
            'name': 'SPEAKER_8OHM',
            'category': ComponentCategory.LOAD,
            'subcategory': LoadKind.SPEAKER.value,
            'source': ModelSource.GENERIC,
            'file_path': Path('/data/models/loads/generic/SPEAKER_8OHM.lib'),
            'subckt_pins': ('SP', 'SN'),
        },
    )
    assert m.load_kind is LoadKind.SPEAKER


def test_tube_type_accessor_raises_for_transformer() -> None:
    m = _opt()
    with pytest.raises(ValueError, match='tube_type accessor invalid'):
        _ = m.tube_type


def test_transformer_kind_accessor_raises_for_tube() -> None:
    m = _tube()
    with pytest.raises(ValueError, match='transformer_kind accessor invalid'):
        _ = m.transformer_kind


def test_load_kind_accessor_raises_for_tube() -> None:
    m = _tube()
    with pytest.raises(ValueError, match='load_kind accessor invalid'):
        _ = m.load_kind


@pytest.mark.parametrize(
    'good_id',
    ['EL34', '6N2P', '6P14P', '12AX7', 'GENERIC_TRIODE', 'EL34_KOREN',
     'OPT_SE_5K_8', 'SPEAKER_8OHM', 'SPEAKER_8OHM_RES'],
)
def test_spice_model_id_accepts_valid(good_id: str) -> None:
    m = _tube(id=good_id)
    assert m.id == good_id


@pytest.mark.parametrize(
    'bad_id',
    ['', 'el34', 'EL-34', 'EL 34', '_EL34', 'EL34!', 'a', 'A'],
)
def test_spice_model_id_rejects_invalid(bad_id: str) -> None:
    with pytest.raises(ValidationError):
        _tube(id=bad_id)


def test_spice_model_is_frozen() -> None:
    m = _tube()
    with pytest.raises(ValidationError):
        m.name = 'other'  # type: ignore[misc]


def test_spice_model_pins_tuple_preserved() -> None:
    m = _tube(
        subckt_pins=('P', 'G2', 'G', 'K', 'H'),
        subcategory=TubeType.PENTODE.value,
    )
    assert m.subckt_pins == ('P', 'G2', 'G', 'K', 'H')


def test_tube_type_enum_values() -> None:
    assert TubeType.TRIODE.value == 'triode'
    assert TubeType.PENTODE.value == 'pentode'
    assert TubeType.DUAL_TRIODE.value == 'dual_triode'
    assert TubeType.RECTIFIER.value == 'rectifier'


def test_component_category_enum_values() -> None:
    assert set(ComponentCategory) == {
        ComponentCategory.TUBE,
        ComponentCategory.TRANSFORMER,
        ComponentCategory.LOAD,
    }


def test_transformer_kind_enum() -> None:
    assert TransformerKind.OPT.value == 'opt'


def test_load_kind_enum_values() -> None:
    assert set(LoadKind) == {LoadKind.SPEAKER, LoadKind.RESISTIVE}


def test_model_source_enum_values() -> None:
    assert set(ModelSource) == {
        ModelSource.KOREN,
        ModelSource.AYUMI,
        ModelSource.DUNCAN,
        ModelSource.CUSTOM,
        ModelSource.GENERIC,
    }


def test_is_user_default_false() -> None:
    m = _tube()
    assert m.is_user is False
