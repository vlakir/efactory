"""FilesystemTubeLibWriter tests (T031 Phase 2)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from adapters.outbound.spice_models.tube_lib_writer import (
    FilesystemTubeLibWriter,
    TubeLibWriteError,
)
from domain.tube_fitting import AyumiPentodeParams, KorenTriodeParams
from ports.outbound.tube_lib_writer import TubeLibMeta


def _meta() -> TubeLibMeta:
    return TubeLibMeta(
        display_name='12AX7',
        source='Koren reference',
        date_extracted=date(2026, 1, 15),
        date_fitted=date(2026, 6, 3),
        rms_residual_ma=0.012,
        n_points=40,
    )


def _triode_params() -> KorenTriodeParams:
    return KorenTriodeParams(mu=100, ex=1.4, kg1=1060, kp=600, kvb=300)


def _pentode_params() -> AyumiPentodeParams:
    return AyumiPentodeParams(
        mu=11, ex=1.35, kg1=650, kg2=4500, kp=60, kvb=24, screen_v=250
    )


# ============================== Triode .lib ==============================


def test_writer_creates_triode_lib(tmp_path: Path) -> None:
    writer = FilesystemTubeLibWriter()
    lib_path = tmp_path / '12AX7.lib'
    writer.write(
        lib_path,
        '12AX7',
        _triode_params(),
        header_tube_type='triode',
        meta=_meta(),
    )
    content = lib_path.read_text(encoding='utf-8')
    assert '* tube_type: triode' in content
    assert '.SUBCKT 12AX7 P G K' in content
    assert 'MU=100.0000' in content
    assert 'KG1=1060.0000' in content
    assert '.ENDS 12AX7' in content


def test_writer_triode_with_vct(tmp_path: Path) -> None:
    writer = FilesystemTubeLibWriter()
    lib_path = tmp_path / '12AX7VCT.lib'
    params = KorenTriodeParams(mu=100, ex=1.4, kg1=1060, kp=600, kvb=300, vct=0.5)
    writer.write(
        lib_path,
        '12AX7VCT',
        params,
        header_tube_type='triode',
        meta=_meta(),
    )
    content = lib_path.read_text(encoding='utf-8')
    assert 'VCT=0.5000' in content
    assert 'V(G,K)+0.5000' in content


# ============================== Pentode .lib ==============================


def test_writer_creates_pentode_lib(tmp_path: Path) -> None:
    writer = FilesystemTubeLibWriter()
    lib_path = tmp_path / 'EL34.lib'
    writer.write(
        lib_path,
        'EL34',
        _pentode_params(),
        header_tube_type='pentode',
        meta=_meta(),
    )
    content = lib_path.read_text(encoding='utf-8')
    assert '* tube_type: pentode' in content
    assert '.SUBCKT EL34 P G2 G K' in content
    assert 'KG2=4500.0000' in content
    assert 'ATAN(V(P,K)/24.0000)' in content


def test_writer_tetrode_header(tmp_path: Path) -> None:
    writer = FilesystemTubeLibWriter()
    lib_path = tmp_path / 'KT88.lib'
    writer.write(
        lib_path,
        'KT88',
        _pentode_params(),
        header_tube_type='tetrode',
        meta=_meta(),
    )
    content = lib_path.read_text(encoding='utf-8')
    assert '* tube_type: tetrode' in content


# ============================== Validation ==============================


@pytest.mark.parametrize('bad_name', ['lower', '_a', '6', '12AX7!', ''])
def test_writer_rejects_invalid_spice_name(tmp_path: Path, bad_name: str) -> None:
    writer = FilesystemTubeLibWriter()
    with pytest.raises(ValueError, match='spice_name must match'):
        writer.write(
            tmp_path / 'x.lib',
            bad_name,
            _triode_params(),
            header_tube_type='triode',
            meta=_meta(),
        )


def test_writer_rejects_triode_params_with_pentode_header(tmp_path: Path) -> None:
    writer = FilesystemTubeLibWriter()
    with pytest.raises(TypeError, match='KorenTriodeParams'):
        writer.write(
            tmp_path / 'x.lib',
            'TRIODE',
            _triode_params(),
            header_tube_type='pentode',
            meta=_meta(),
        )


def test_writer_rejects_pentode_params_with_triode_header(tmp_path: Path) -> None:
    writer = FilesystemTubeLibWriter()
    with pytest.raises(TypeError, match='AyumiPentodeParams'):
        writer.write(
            tmp_path / 'x.lib',
            'PENTODE',
            _pentode_params(),
            header_tube_type='triode',
            meta=_meta(),
        )


def test_writer_refuses_overwrite_without_force(tmp_path: Path) -> None:
    writer = FilesystemTubeLibWriter()
    lib_path = tmp_path / '12AX7.lib'
    writer.write(
        lib_path, '12AX7', _triode_params(),
        header_tube_type='triode', meta=_meta(),
    )
    with pytest.raises(TubeLibWriteError, match='already exists'):
        writer.write(
            lib_path, '12AX7', _triode_params(),
            header_tube_type='triode', meta=_meta(),
        )


def test_writer_force_overwrites_existing(tmp_path: Path) -> None:
    writer = FilesystemTubeLibWriter()
    lib_path = tmp_path / '12AX7.lib'
    writer.write(
        lib_path, '12AX7', _triode_params(),
        header_tube_type='triode', meta=_meta(),
    )
    new_params = KorenTriodeParams(mu=110, ex=1.4, kg1=1060, kp=600, kvb=300)
    writer.write(
        lib_path, '12AX7', new_params,
        header_tube_type='triode', meta=_meta(), force=True,
    )
    assert 'MU=110.0000' in lib_path.read_text()


def test_writer_creates_parent_dirs(tmp_path: Path) -> None:
    writer = FilesystemTubeLibWriter()
    lib_path = tmp_path / 'deep' / 'nested' / 'dir' / 'X.lib'
    writer.write(
        lib_path, 'X9', _triode_params(),
        header_tube_type='triode', meta=_meta(),
    )
    assert lib_path.is_file()
