"""FilesystemTubeLibWriter tests (T031 Phase 2)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from adapters.outbound.spice_models.tube_lib_writer import (
    FilesystemTubeLibWriter,
    TubeLibWriteError,
)
from domain.tube_fitting import (
    AyumiPentodeParams,
    KorenModifiedCutoffTriodeParams,
    KorenModifiedKneePentodeParams,
    KorenTriodeParams,
)
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


# ============================== T182: Modified-knee pentode .lib ==============================


def _mod_knee_params() -> KorenModifiedKneePentodeParams:
    return KorenModifiedKneePentodeParams(
        mu=11, ex=1.35, kg1=650, kg2=4500, kp=60, kvb=24, screen_v=250, vk=50.0
    )


def _mod_cutoff_params() -> KorenModifiedCutoffTriodeParams:
    return KorenModifiedCutoffTriodeParams(
        mu=4, ex=1.4, kg1=1500, kp=800, kvb=200, vc_off=-50.0, vs_off=5.0
    )


def test_writer_creates_modified_knee_pentode_lib(tmp_path: Path) -> None:
    writer = FilesystemTubeLibWriter()
    lib_path = tmp_path / 'EL34_MOD.lib'
    writer.write(
        lib_path, 'EL34_MOD', _mod_knee_params(),
        header_tube_type='pentode', meta=_meta(),
    )
    content = lib_path.read_text(encoding='utf-8')
    # Variant marker.
    assert 'fit variant: koren-modified-knee' in content
    # Standard pentode structure.
    assert '* tube_type: pentode' in content
    assert '.SUBCKT EL34_MOD P G2 G K' in content
    # Knee modifier B-source.
    assert 'B_KNEE 8 0 V=1-EXP(-V(P,K)/50.0000)' in content
    # G1 line multiplied by V(8) — the knee factor.
    assert '* ATAN(V(P,K)/24.0000) * V(8)' in content
    # Params dump.
    assert 'VK=50.0000' in content
    assert '.ENDS EL34_MOD' in content


def test_writer_creates_modified_cutoff_triode_lib(tmp_path: Path) -> None:
    writer = FilesystemTubeLibWriter()
    lib_path = tmp_path / 'X300B_MOD.lib'
    writer.write(
        lib_path, 'X300B_MOD', _mod_cutoff_params(),
        header_tube_type='triode', meta=_meta(),
    )
    content = lib_path.read_text(encoding='utf-8')
    assert 'fit variant: koren-modified-cutoff' in content
    assert '* tube_type: triode' in content
    assert '.SUBCKT X300B_MOD P G K' in content
    # Sigmoid B-source: (V(G,K)-VC_OFF)/VS_OFF; vc_off=-50.
    assert 'B_SIG 8 0 V=1/(1+EXP(-((V(G,K)-(-50.0000))/5.0000)))' in content
    # G1 multiplied by V(8).
    assert '/1500.0000*V(8)' in content
    # Params dump.
    assert 'VC_OFF=-50.0000' in content
    assert 'VS_OFF=5.0000' in content
    assert '.ENDS X300B_MOD' in content


def test_writer_rejects_modified_knee_pentode_with_triode_header(
    tmp_path: Path,
) -> None:
    writer = FilesystemTubeLibWriter()
    with pytest.raises(TypeError, match='KorenModifiedKneePentodeParams'):
        writer.write(
            tmp_path / 'x.lib', 'XX', _mod_knee_params(),
            header_tube_type='triode', meta=_meta(),
        )


def test_writer_rejects_modified_cutoff_triode_with_pentode_header(
    tmp_path: Path,
) -> None:
    writer = FilesystemTubeLibWriter()
    with pytest.raises(TypeError, match='KorenModifiedCutoffTriodeParams'):
        writer.write(
            tmp_path / 'x.lib', 'XX', _mod_cutoff_params(),
            header_tube_type='pentode', meta=_meta(),
        )
