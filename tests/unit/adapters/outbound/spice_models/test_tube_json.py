"""FilesystemTubeIVRepository tests (T031 Phase 2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from adapters.outbound.spice_models.tube_json import (
    FilesystemTubeIVRepository,
    IVDatasetLoadError,
)
from domain.tube_fitting import AyumiPentodeParams, KorenTriodeParams


# ============================== load_iv_dataset ==============================


def _pentode_json(
    *, with_screen: bool = False, tube_name: str = '6Ж38П'
) -> dict[str, object]:
    payload: dict[str, object] = {
        'tube_name': tube_name,
        'tube_type': 'pentode',
        'source': 'Mullard 1962',
        'date_extracted': '2026-06-03',
        'screen_voltage_v': 250.0,
        'curves': [
            {'vg': -10.0, 'points': [[100.0, 75.0], [300.0, 145.0]]},
            {'vg': -15.0, 'points': [[100.0, 15.0], [300.0, 75.0]]},
        ],
    }
    if with_screen:
        payload['screen_curves'] = [
            {'vg': -10.0, 'points': [[250.0, 12.0]]},
        ]
    return payload


def _triode_json() -> dict[str, object]:
    return {
        'tube_name': '12AX7',
        'tube_type': 'triode',
        'source': 'Koren reference',
        'date_extracted': '2026-06-03',
        'curves': [
            {'vg': -1.0, 'points': [[100.0, 2.1], [200.0, 5.0]]},
            {'vg': -2.0, 'points': [[100.0, 0.4], [200.0, 1.3]]},
        ],
    }


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def test_load_pentode_json_round_trip(tmp_path: Path) -> None:
    p = tmp_path / 'el34.json'
    _write_json(p, _pentode_json(tube_name='EL34'))
    ds = FilesystemTubeIVRepository().load_iv_dataset(p)
    assert ds.tube_type == 'pentode'
    assert ds.tube_name == 'EL34'
    assert ds.screen_voltage_v == 250.0
    assert len(ds.curves) == 2
    assert ds.curves[0].vg == -10.0


def test_load_pentode_with_screen_curves(tmp_path: Path) -> None:
    p = tmp_path / 'el34.json'
    _write_json(p, _pentode_json(with_screen=True))
    ds = FilesystemTubeIVRepository().load_iv_dataset(p)
    assert len(ds.screen_curves) == 1
    assert ds.screen_curves[0].points[0] == (250.0, 12.0)


def test_load_triode_json_round_trip(tmp_path: Path) -> None:
    p = tmp_path / '12ax7.json'
    _write_json(p, _triode_json())
    ds = FilesystemTubeIVRepository().load_iv_dataset(p)
    assert ds.tube_type == 'triode'
    assert ds.screen_voltage_v is None


def test_load_preserves_cyrillic_tube_name(tmp_path: Path) -> None:
    p = tmp_path / 'cyrillic.json'
    _write_json(p, _pentode_json(tube_name='6Ж38П'))
    ds = FilesystemTubeIVRepository().load_iv_dataset(p)
    assert ds.tube_name == '6Ж38П'


# ============================== Errors ==============================


def test_load_missing_file_raises(tmp_path: Path) -> None:
    p = tmp_path / 'absent.json'
    with pytest.raises(IVDatasetLoadError, match='cannot read'):
        FilesystemTubeIVRepository().load_iv_dataset(p)


def test_load_invalid_json_raises(tmp_path: Path) -> None:
    p = tmp_path / 'broken.json'
    p.write_text('{not: valid', encoding='utf-8')
    with pytest.raises(IVDatasetLoadError, match='invalid JSON'):
        FilesystemTubeIVRepository().load_iv_dataset(p)


def test_load_pentode_missing_screen_voltage_raises(tmp_path: Path) -> None:
    data = _pentode_json()
    del data['screen_voltage_v']
    p = tmp_path / 'bad.json'
    _write_json(p, data)
    with pytest.raises(IVDatasetLoadError, match='validation failed'):
        FilesystemTubeIVRepository().load_iv_dataset(p)


def test_load_triode_with_screen_voltage_raises(tmp_path: Path) -> None:
    data = _triode_json()
    data['screen_voltage_v'] = 250.0
    p = tmp_path / 'bad.json'
    _write_json(p, data)
    with pytest.raises(IVDatasetLoadError, match='validation failed'):
        FilesystemTubeIVRepository().load_iv_dataset(p)


# ============================== load_seed_from_params ==============================


def test_load_seed_from_triode_params(tmp_path: Path) -> None:
    p = tmp_path / 'seed.json'
    truth = KorenTriodeParams(mu=70, ex=1.4, kg1=1500, kp=300, kvb=200)
    p.write_text(truth.model_dump_json(), encoding='utf-8')
    loaded = FilesystemTubeIVRepository().load_seed_from_params(p, tube_type='triode')
    assert isinstance(loaded, KorenTriodeParams)
    assert loaded.mu == 70


def test_load_seed_from_pentode_params(tmp_path: Path) -> None:
    p = tmp_path / 'seed.json'
    truth = AyumiPentodeParams(
        mu=10, ex=1.3, kg1=1000, kg2=4000, kp=50, kvb=20, screen_v=250
    )
    p.write_text(truth.model_dump_json(), encoding='utf-8')
    loaded = FilesystemTubeIVRepository().load_seed_from_params(
        p, tube_type='pentode'
    )
    assert isinstance(loaded, AyumiPentodeParams)
    assert loaded.kg2 == 4000


def test_load_seed_from_triode_json_with_pentode_type_raises(tmp_path: Path) -> None:
    p = tmp_path / 'seed.json'
    truth = KorenTriodeParams(mu=70, ex=1.4, kg1=1500, kp=300, kvb=200)
    p.write_text(truth.model_dump_json(), encoding='utf-8')
    with pytest.raises(IVDatasetLoadError, match='validation failed'):
        FilesystemTubeIVRepository().load_seed_from_params(p, tube_type='pentode')
