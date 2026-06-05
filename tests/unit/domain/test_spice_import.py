"""Domain layer для T030 SPICE-model import — VO + exceptions."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from domain.spice_import import (
    ClassificationAmbiguousError,
    ClassificationResult,
    ContentRejectedError,
    DownloadError,
    ImportDuplicateError,
    ImportPlan,
    ImportReport,
    ImportSource,
    KbWriteError,
    ModelKind,
    ParsedModelCard,
    RawImport,
    SmokeFailedError,
    SmokeOutcome,
    SmokeStatus,
    SmokeTimeoutError,
    SpiceImportError,
)
from domain.spice_model import ComponentCategory


# === ModelKind ===


def test_model_kind_values() -> None:
    assert ModelKind.SUBCKT.value == 'subckt'
    assert ModelKind.MODEL.value == 'model'


# === SmokeStatus ===


def test_smoke_status_values() -> None:
    assert SmokeStatus.PASSED.value == 'passed'
    assert SmokeStatus.FAILED.value == 'failed'
    assert SmokeStatus.SKIPPED.value == 'skipped'


# === ImportSource ===


def test_import_source_url() -> None:
    src = ImportSource(kind='url', location='https://example.com/model.lib')
    assert src.kind == 'url'
    assert src.location == 'https://example.com/model.lib'
    assert src.vendor_hint is None


def test_import_source_file_with_vendor_hint() -> None:
    src = ImportSource(
        kind='file',
        location='/tmp/model.lib',
        vendor_hint='ti',
    )
    assert src.kind == 'file'
    assert src.vendor_hint == 'ti'


def test_import_source_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        ImportSource(kind='ftp', location='ftp://example.com/model.lib')  # type: ignore[arg-type]


def test_import_source_is_frozen() -> None:
    src = ImportSource(kind='url', location='https://example.com/m.lib')
    with pytest.raises(ValidationError):
        src.location = 'other'  # type: ignore[misc]


# === RawImport ===


def _raw(**overrides: object) -> RawImport:
    defaults: dict[str, object] = {
        'source': ImportSource(kind='url', location='https://x.com/m.lib'),
        'bytes_text': '.MODEL Q2N3904 NPN (BF=200)\n',
        'sha256': 'a' * 64,
        'downloaded_at': datetime(2026, 6, 5, 12, 0, tzinfo=UTC),
    }
    defaults.update(overrides)
    return RawImport.model_validate(defaults)


def test_raw_import_holds_full_metadata() -> None:
    raw = _raw()
    assert raw.bytes_text.startswith('.MODEL')
    assert len(raw.sha256) == 64
    assert raw.downloaded_at.tzinfo is UTC


def test_raw_import_is_frozen() -> None:
    raw = _raw()
    with pytest.raises(ValidationError):
        raw.bytes_text = 'mutated'  # type: ignore[misc]


def test_raw_import_rejects_non_hex_sha256() -> None:
    with pytest.raises(ValidationError):
        _raw(sha256='zzz')


# === ParsedModelCard ===


def _card_model(**overrides: object) -> ParsedModelCard:
    defaults: dict[str, object] = {
        'kind': ModelKind.MODEL,
        'name': 'Q2N3904',
        'body': '.MODEL Q2N3904 NPN (BF=200 IS=1e-14)\n',
        'model_type': 'NPN',
        'pins': None,
        'header_meta': {},
    }
    defaults.update(overrides)
    return ParsedModelCard.model_validate(defaults)


def _card_subckt(**overrides: object) -> ParsedModelCard:
    defaults: dict[str, object] = {
        'kind': ModelKind.SUBCKT,
        'name': 'OPA1612',
        'body': '.SUBCKT OPA1612 V+ V- INP INM OUT\n... .ENDS\n',
        'model_type': None,
        'pins': ('V+', 'V-', 'INP', 'INM', 'OUT'),
        'header_meta': {'subcategory': 'full_vendor', 'vendor': 'ti'},
    }
    defaults.update(overrides)
    return ParsedModelCard.model_validate(defaults)


def test_parsed_model_card_model_kind() -> None:
    card = _card_model()
    assert card.kind is ModelKind.MODEL
    assert card.model_type == 'NPN'
    assert card.pins is None


def test_parsed_model_card_subckt_kind() -> None:
    card = _card_subckt()
    assert card.kind is ModelKind.SUBCKT
    assert card.pins == ('V+', 'V-', 'INP', 'INM', 'OUT')
    assert card.model_type is None


def test_parsed_model_card_subckt_requires_pins() -> None:
    with pytest.raises(ValidationError, match='pins'):
        _card_subckt(pins=None)


def test_parsed_model_card_model_requires_model_type() -> None:
    with pytest.raises(ValidationError, match='model_type'):
        _card_model(model_type=None)


def test_parsed_model_card_is_frozen() -> None:
    card = _card_model()
    with pytest.raises(ValidationError):
        card.name = 'other'  # type: ignore[misc]


# === ClassificationResult ===


def test_classification_result_basic() -> None:
    cls = ClassificationResult(
        category=ComponentCategory.BJT,
        subcategory='npn',
        reason='`.MODEL` TYPE=NPN',
        ambiguous=False,
    )
    assert cls.category is ComponentCategory.BJT
    assert cls.subcategory == 'npn'
    assert not cls.ambiguous


def test_classification_result_ambiguous_keeps_best_guess() -> None:
    cls = ClassificationResult(
        category=ComponentCategory.BJT,
        subcategory='npn',
        reason='3-pin SUBCKT, no internal Q-card',
        ambiguous=True,
    )
    assert cls.ambiguous


def test_classification_result_is_frozen() -> None:
    cls = ClassificationResult(
        category=ComponentCategory.DIODE,
        subcategory='signal',
        reason='.MODEL TYPE=D, 2-pin',
        ambiguous=False,
    )
    with pytest.raises(ValidationError):
        cls.subcategory = 'rectifier'  # type: ignore[misc]


# === ImportPlan ===


def _plan(**overrides: object) -> ImportPlan:
    raw = _raw()
    card = _card_model()
    cls = ClassificationResult(
        category=ComponentCategory.BJT,
        subcategory='npn',
        reason='.MODEL NPN',
        ambiguous=False,
    )
    defaults: dict[str, object] = {
        'raw': raw,
        'cards': ((card, cls),),
        'vendor': 'onsemi',
        'target_paths': (Path('/lib/bjt/onsemi/Q2N3904.lib'),),
    }
    defaults.update(overrides)
    return ImportPlan.model_validate(defaults)


def test_import_plan_basic() -> None:
    plan = _plan()
    assert plan.vendor == 'onsemi'
    assert len(plan.cards) == 1
    assert plan.target_paths[0].name == 'Q2N3904.lib'


def test_import_plan_rejects_mismatched_cards_and_paths() -> None:
    raw = _raw()
    card = _card_model()
    cls = ClassificationResult(
        category=ComponentCategory.BJT,
        subcategory='npn',
        reason='r',
        ambiguous=False,
    )
    with pytest.raises(ValidationError, match='target_paths'):
        ImportPlan.model_validate(
            {
                'raw': raw,
                'cards': ((card, cls),),
                'vendor': 'onsemi',
                'target_paths': (
                    Path('/lib/bjt/onsemi/Q2N3904.lib'),
                    Path('/lib/bjt/onsemi/Q2N3905.lib'),
                ),
            },
        )


def test_import_plan_vendor_validation() -> None:
    with pytest.raises(ValidationError, match='vendor'):
        _plan(vendor='Bad Vendor!')


def test_import_plan_is_frozen() -> None:
    plan = _plan()
    with pytest.raises(ValidationError):
        plan.vendor = 'other'  # type: ignore[misc]


# === SmokeOutcome ===


def test_smoke_outcome_passed() -> None:
    o = SmokeOutcome(card_name='Q2N3904', status=SmokeStatus.PASSED, details='Vc=4.5V')
    assert o.status is SmokeStatus.PASSED


def test_smoke_outcome_failed() -> None:
    o = SmokeOutcome(
        card_name='Q2N3904',
        status=SmokeStatus.FAILED,
        details='Vc=10V (transistor off)',
    )
    assert o.status is SmokeStatus.FAILED


def test_smoke_outcome_skipped() -> None:
    o = SmokeOutcome(
        card_name='Q2N3904',
        status=SmokeStatus.SKIPPED,
        details='--skip-smoke',
    )
    assert o.status is SmokeStatus.SKIPPED


def test_smoke_outcome_is_frozen() -> None:
    o = SmokeOutcome(card_name='X', status=SmokeStatus.PASSED, details='ok')
    with pytest.raises(ValidationError):
        o.details = 'other'  # type: ignore[misc]


# === ImportReport ===


def test_import_report_basic() -> None:
    plan = _plan()
    started = datetime(2026, 6, 5, 12, 0, tzinfo=UTC)
    finished = datetime(2026, 6, 5, 12, 0, 5, tzinfo=UTC)
    outcome = SmokeOutcome(
        card_name='Q2N3904',
        status=SmokeStatus.PASSED,
        details='ok',
    )
    report = ImportReport(
        plan=plan,
        installed_paths=(Path('/lib/bjt/onsemi/Q2N3904.lib'),),
        smoke_outcomes=(outcome,),
        kb_topics=(Path('/kb/spice.onsemi.q2n3904.md'),),
        started_at=started,
        finished_at=finished,
    )
    assert report.installed_paths[0].name == 'Q2N3904.lib'
    assert report.finished_at >= report.started_at


def test_import_report_is_frozen() -> None:
    plan = _plan()
    ts = datetime(2026, 6, 5, 12, 0, tzinfo=UTC)
    report = ImportReport(
        plan=plan,
        installed_paths=(),
        smoke_outcomes=(),
        kb_topics=(),
        started_at=ts,
        finished_at=ts,
    )
    with pytest.raises(ValidationError):
        report.installed_paths = (Path('/x.lib'),)  # type: ignore[misc]


# === Exceptions ===


def test_spice_import_error_is_base() -> None:
    exc_cls: type[Exception] = SpiceImportError
    for sub in (
        DownloadError,
        ContentRejectedError,
        ClassificationAmbiguousError,
        ImportDuplicateError,
        SmokeFailedError,
        SmokeTimeoutError,
        KbWriteError,
    ):
        assert issubclass(sub, exc_cls)


def test_download_error_carries_url_and_status() -> None:
    exc = DownloadError(url='https://x.com/m.lib', status=404, message='not found')
    assert exc.url == 'https://x.com/m.lib'
    assert exc.status == 404
    assert 'not found' in str(exc)


def test_content_rejected_error_explains_reason() -> None:
    exc = ContentRejectedError(reason='content-type=text/html (login page)')
    assert 'text/html' in str(exc)


def test_classification_ambiguous_error_carries_card() -> None:
    card = _card_subckt(pins=('A', 'B', 'C'), header_meta={})
    exc = ClassificationAmbiguousError(
        card=card,
        reason='3-pin SUBCKT, no Q-card / M-card / tube lookup',
    )
    assert exc.card.name == 'OPA1612'
    assert '3-pin' in str(exc)


def test_import_duplicate_error_carries_path() -> None:
    p = Path('/lib/bjt/onsemi/Q2N3904.lib')
    exc = ImportDuplicateError(target_path=p)
    assert exc.target_path == p
    assert 'Q2N3904.lib' in str(exc)


def test_smoke_failed_error_carries_details() -> None:
    exc = SmokeFailedError(
        card_name='Q2N3904',
        stdout='ngspice: ok',
        stderr='convergence fail',
    )
    assert exc.card_name == 'Q2N3904'
    assert 'convergence fail' in str(exc)


def test_smoke_timeout_error_carries_seconds() -> None:
    exc = SmokeTimeoutError(card_name='Q2N3904', timeout_seconds=15.0)
    assert exc.timeout_seconds == 15.0
    assert '15' in str(exc)


def test_kb_write_error_carries_path() -> None:
    exc = KbWriteError(topic='spice.onsemi.q2n3904', message='disk full')
    assert 'spice.onsemi.q2n3904' in str(exc)
    assert 'disk full' in str(exc)
