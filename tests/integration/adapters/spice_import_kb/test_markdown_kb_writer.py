"""MarkdownSpiceKbWriter — T030 Phase 2.

Pure-IO writer для KB-topic markdown'а после успешного import.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from adapters.outbound.spice_import_kb.writer import MarkdownSpiceKbWriter
from domain.spice_import import (
    ClassificationResult,
    ImportPlan,
    ImportReport,
    ImportSource,
    KbWriteError,
    ModelKind,
    ParsedModelCard,
    RawImport,
    SmokeOutcome,
    SmokeStatus,
)
from domain.spice_model import ComponentCategory


def _make_card_and_classification() -> tuple[ParsedModelCard, ClassificationResult]:
    card = ParsedModelCard(
        kind=ModelKind.MODEL,
        name='Q2N3904',
        body='.MODEL Q2N3904 NPN (BF=200)\n',
        model_type='NPN',
        pins=None,
        header_meta={},
    )
    cls = ClassificationResult(
        category=ComponentCategory.BJT,
        subcategory='npn',
        reason='.MODEL TYPE=NPN',
        ambiguous=False,
    )
    return card, cls


def _make_report(*, vendor: str = 'onsemi') -> ImportReport:
    card, cls = _make_card_and_classification()
    raw = RawImport(
        source=ImportSource(kind='url', location='https://onsemi.com/Q2N3904.lib'),
        bytes_text='.MODEL Q2N3904 NPN (BF=200)\n',
        sha256='a' * 64,
        downloaded_at=datetime(2026, 6, 5, 12, 0, tzinfo=UTC),
    )
    plan = ImportPlan(
        raw=raw,
        cards=((card, cls),),
        vendor=vendor,
        target_paths=(Path('/lib/bjt/onsemi/Q2N3904.lib'),),
    )
    return ImportReport(
        plan=plan,
        installed_paths=(Path('/lib/bjt/onsemi/Q2N3904.lib'),),
        smoke_outcomes=(
            SmokeOutcome(
                card_name='Q2N3904',
                status=SmokeStatus.PASSED,
                details='OP ok, V(c)=4.5',
            ),
        ),
        kb_topics=(),
        started_at=datetime(2026, 6, 5, 12, 0, tzinfo=UTC),
        finished_at=datetime(2026, 6, 5, 12, 0, 5, tzinfo=UTC),
    )


def test_write_topic_creates_file(tmp_path: Path) -> None:
    report = _make_report()
    card, cls = report.plan.cards[0]
    writer = MarkdownSpiceKbWriter()
    path = writer.write_topic(
        report=report,
        card=card,
        classification=cls,
        installed_path=report.installed_paths[0],
        kb_root=tmp_path,
    )
    assert path == tmp_path / 'spice.onsemi.q2n3904.md'
    assert path.is_file()


def test_write_topic_content_has_expected_fields(tmp_path: Path) -> None:
    report = _make_report()
    card, cls = report.plan.cards[0]
    writer = MarkdownSpiceKbWriter()
    path = writer.write_topic(
        report=report,
        card=card,
        classification=cls,
        installed_path=report.installed_paths[0],
        kb_root=tmp_path,
    )
    text = path.read_text()
    assert 'topic: spice.onsemi.q2n3904' in text
    assert 'Q2N3904' in text
    assert 'onsemi' in text
    assert 'bjt/npn' in text
    assert 'https://onsemi.com/Q2N3904.lib' in text
    assert 'aaaaaaaa' in text  # sha256
    assert 'passed' in text


def test_write_topic_lowercase_filename_for_uppercase_part(tmp_path: Path) -> None:
    report = _make_report()
    card, cls = report.plan.cards[0]
    writer = MarkdownSpiceKbWriter()
    path = writer.write_topic(
        report=report,
        card=card,
        classification=cls,
        installed_path=report.installed_paths[0],
        kb_root=tmp_path,
    )
    assert path.name == 'spice.onsemi.q2n3904.md'  # all-lowercase


def test_write_topic_unknown_vendor(tmp_path: Path) -> None:
    report = _make_report(vendor='unknown')
    card, cls = report.plan.cards[0]
    writer = MarkdownSpiceKbWriter()
    path = writer.write_topic(
        report=report,
        card=card,
        classification=cls,
        installed_path=report.installed_paths[0],
        kb_root=tmp_path,
    )
    assert path.name == 'spice.unknown.q2n3904.md'


def test_write_topic_overwrites_existing(tmp_path: Path) -> None:
    report = _make_report()
    card, cls = report.plan.cards[0]
    writer = MarkdownSpiceKbWriter()
    path = writer.write_topic(
        report=report, card=card, classification=cls,
        installed_path=report.installed_paths[0], kb_root=tmp_path,
    )
    first = path.read_text()
    # Перепишем — content идентичный (overwrite ok).
    path2 = writer.write_topic(
        report=report, card=card, classification=cls,
        installed_path=report.installed_paths[0], kb_root=tmp_path,
    )
    assert path == path2
    assert path.read_text() == first


def test_write_topic_kb_root_must_exist(tmp_path: Path) -> None:
    report = _make_report()
    card, cls = report.plan.cards[0]
    writer = MarkdownSpiceKbWriter()
    missing = tmp_path / 'nonexistent' / 'kb'
    with pytest.raises(KbWriteError):
        writer.write_topic(
            report=report, card=card, classification=cls,
            installed_path=report.installed_paths[0], kb_root=missing,
        )


def test_write_topic_local_file_source_renders_local_file_uri(tmp_path: Path) -> None:
    card, cls = _make_card_and_classification()
    raw = RawImport(
        source=ImportSource(kind='file', location='/home/user/2n3904.lib'),
        bytes_text='.MODEL Q2N3904 NPN (BF=200)\n',
        sha256='b' * 64,
        downloaded_at=datetime(2026, 6, 5, 12, 0, tzinfo=UTC),
    )
    plan = ImportPlan(
        raw=raw,
        cards=((card, cls),),
        vendor='unknown',
        target_paths=(Path('/lib/bjt/unknown/Q2N3904.lib'),),
    )
    report = ImportReport(
        plan=plan,
        installed_paths=(Path('/lib/bjt/unknown/Q2N3904.lib'),),
        smoke_outcomes=(
            SmokeOutcome(card_name='Q2N3904', status=SmokeStatus.SKIPPED, details='--skip'),
        ),
        kb_topics=(),
        started_at=datetime(2026, 6, 5, 12, 0, tzinfo=UTC),
        finished_at=datetime(2026, 6, 5, 12, 0, 5, tzinfo=UTC),
    )
    writer = MarkdownSpiceKbWriter()
    path = writer.write_topic(
        report=report, card=card, classification=cls,
        installed_path=report.installed_paths[0], kb_root=tmp_path,
    )
    text = path.read_text()
    assert 'local-file:/home/user/2n3904.lib' in text
    assert 'skipped' in text
