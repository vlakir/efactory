"""NgspiceSmokeRunner — T030 Phase 2.

Real-ngspice integration test. Если ngspice отсутствует — skip.
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from adapters.outbound.ngspice.simulator import NgspiceSimulator
from adapters.outbound.platform_native.platform_layer import NativePlatformLayer
from adapters.outbound.spice_import_smoke.runner import NgspiceSmokeRunner
from adapters.outbound.subprocess_apps.app_manager import SubprocessAppManager
from domain.spice_import import (
    ClassificationResult,
    ImportSource,
    ModelKind,
    ParsedModelCard,
    RawImport,
    SmokeFailedError,
    SmokeStatus,
)
from domain.spice_model import ComponentCategory

_NGSPICE_AVAILABLE = shutil.which('ngspice') is not None

needs_ngspice = pytest.mark.skipif(
    not _NGSPICE_AVAILABLE,
    reason='ngspice not installed',
)

_FIXTURES = (
    Path(__file__).resolve().parents[3] / 'data' / 'spice_import' / 'vendor_samples'
)


def _make_runner() -> NgspiceSmokeRunner:
    sim = NgspiceSimulator(SubprocessAppManager(NativePlatformLayer()))
    return NgspiceSmokeRunner(simulator=sim)


def _card(kind: ModelKind, name: str, **extras: object) -> ParsedModelCard:
    defaults: dict[str, object] = {
        'kind': kind,
        'name': name,
        'body': '',
        'model_type': None,
        'pins': None,
        'header_meta': {},
    }
    defaults.update(extras)
    return ParsedModelCard.model_validate(defaults)


def _classification(category: ComponentCategory, subcategory: str) -> ClassificationResult:
    return ClassificationResult(
        category=category,
        subcategory=subcategory,
        reason='test',
        ambiguous=False,
    )


@needs_ngspice
async def test_smoke_bjt_npn_passes(tmp_path: Path) -> None:
    model_path = tmp_path / '2n3904.lib'
    model_path.write_text((_FIXTURES / '2n3904_bjt_npn.lib').read_text())
    card = _card(ModelKind.MODEL, 'Q2N3904', model_type='NPN')
    cls = _classification(ComponentCategory.BJT, 'npn')
    runner = _make_runner()
    outcome = await runner.smoke(
        card=card, classification=cls, model_path=model_path, timeout_seconds=15.0,
    )
    assert outcome.status is SmokeStatus.PASSED
    assert outcome.card_name == 'Q2N3904'


@needs_ngspice
async def test_smoke_bjt_pnp_passes(tmp_path: Path) -> None:
    model_path = tmp_path / '2n3906.lib'
    model_path.write_text((_FIXTURES / '2n3906_bjt_pnp.lib').read_text())
    card = _card(ModelKind.MODEL, 'Q2N3906', model_type='PNP')
    cls = _classification(ComponentCategory.BJT, 'pnp')
    runner = _make_runner()
    outcome = await runner.smoke(
        card=card, classification=cls, model_path=model_path, timeout_seconds=15.0,
    )
    assert outcome.status is SmokeStatus.PASSED


@needs_ngspice
async def test_smoke_jfet_njf_passes(tmp_path: Path) -> None:
    model_path = tmp_path / '2n5457.lib'
    model_path.write_text((_FIXTURES / '2n5457_jfet_njf.lib').read_text())
    card = _card(ModelKind.MODEL, 'J2N5457', model_type='NJF')
    cls = _classification(ComponentCategory.JFET, 'njf')
    runner = _make_runner()
    outcome = await runner.smoke(
        card=card, classification=cls, model_path=model_path, timeout_seconds=15.0,
    )
    assert outcome.status is SmokeStatus.PASSED


@needs_ngspice
async def test_smoke_mosfet_nmos_passes(tmp_path: Path) -> None:
    model_path = tmp_path / 'irf540.lib'
    model_path.write_text((_FIXTURES / 'irf540_mosfet_nmos.lib').read_text())
    card = _card(ModelKind.MODEL, 'IRF540', model_type='NMOS')
    cls = _classification(ComponentCategory.MOSFET, 'nmos')
    runner = _make_runner()
    outcome = await runner.smoke(
        card=card, classification=cls, model_path=model_path, timeout_seconds=15.0,
    )
    assert outcome.status is SmokeStatus.PASSED


@needs_ngspice
async def test_smoke_diode_passes(tmp_path: Path) -> None:
    model_path = tmp_path / '1n4148.lib'
    model_path.write_text((_FIXTURES / '1n4148_diode.lib').read_text())
    card = _card(ModelKind.MODEL, 'D1N4148', model_type='D')
    cls = _classification(ComponentCategory.DIODE, 'signal')
    runner = _make_runner()
    outcome = await runner.smoke(
        card=card, classification=cls, model_path=model_path, timeout_seconds=15.0,
    )
    assert outcome.status is SmokeStatus.PASSED


@needs_ngspice
async def test_smoke_opamp_passes(tmp_path: Path) -> None:
    model_path = tmp_path / 'opagen.lib'
    model_path.write_text((_FIXTURES / 'opa_generic.lib').read_text())
    card = _card(
        ModelKind.SUBCKT,
        'OPAGEN',
        pins=('VCC', 'VEE', 'INP', 'INM', 'OUT'),
    )
    cls = _classification(ComponentCategory.OPAMP, 'full_vendor')
    runner = _make_runner()
    outcome = await runner.smoke(
        card=card, classification=cls, model_path=model_path, timeout_seconds=15.0,
    )
    assert outcome.status is SmokeStatus.PASSED


@needs_ngspice
async def test_smoke_broken_model_fails(tmp_path: Path) -> None:
    model_path = tmp_path / 'broken.lib'
    # Имя .MODEL не совпадает с тем, что smoke template подставит в
    # Q1 c b 0 Q2N3904 — ngspice выкинет "Unable to find definition".
    model_path.write_text('.MODEL QSOMETHINGELSE NPN (BF=200)\n')
    card = _card(ModelKind.MODEL, 'Q2N3904', model_type='NPN')
    cls = _classification(ComponentCategory.BJT, 'npn')
    runner = _make_runner()
    with pytest.raises(SmokeFailedError):
        await runner.smoke(
            card=card, classification=cls, model_path=model_path, timeout_seconds=15.0,
        )


async def test_smoke_tube_category_skipped(tmp_path: Path) -> None:
    """TUBE / TRANSFORMER / LOAD — smoke skipped, ngspice не вызывается."""
    model_path = tmp_path / 'fake-tube.lib'
    model_path.write_text('* not actually loaded\n')
    card = _card(
        ModelKind.SUBCKT,
        'FAKE6N1P',
        pins=('P', 'G', 'K'),
    )
    cls = _classification(ComponentCategory.TUBE, 'triode')
    runner = _make_runner()
    outcome = await runner.smoke(
        card=card, classification=cls, model_path=model_path, timeout_seconds=15.0,
    )
    assert outcome.status is SmokeStatus.SKIPPED
    assert 'tube' in outcome.details.lower() or 'unsupported' in outcome.details.lower()


def test_raw_import_for_test_setup_completeness() -> None:
    # Sanity для VO setup (smoke runner ничего от него не требует).
    src = ImportSource(kind='url', location='https://x.com/m.lib')
    raw = RawImport(
        source=src,
        bytes_text='.MODEL QQ NPN',
        sha256='2' * 64,
        downloaded_at=datetime(2026, 6, 5, tzinfo=UTC),
    )
    assert raw.source == src
