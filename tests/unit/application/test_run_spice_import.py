"""run_spice_import use case — TDD with fake adapters (T030 Phase 3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest

from application.run_spice_import import run_spice_import
from domain.spice_import import (
    ClassificationResult,
    ImportDuplicateError,
    ImportSource,
    ModelKind,
    ParsedModelCard,
    RawImport,
    SmokeOutcome,
    SmokeStatus,
)
from domain.spice_model import ComponentCategory


def _raw(*, source: ImportSource | None = None) -> RawImport:
    return RawImport(
        source=source
        or ImportSource(kind='url', location='https://onsemi.com/Q2N3904.lib'),
        bytes_text='.MODEL Q2N3904 NPN (BF=200)\n',
        sha256='a' * 64,
        downloaded_at=datetime(2026, 6, 5, 12, 0, tzinfo=UTC),
    )


def _card() -> ParsedModelCard:
    return ParsedModelCard(
        kind=ModelKind.MODEL,
        name='Q2N3904',
        body='.MODEL Q2N3904 NPN (BF=200)\n',
        model_type='NPN',
        pins=None,
        header_meta={},
    )


def _classification() -> ClassificationResult:
    return ClassificationResult(
        category=ComponentCategory.BJT,
        subcategory='npn',
        reason='.MODEL NPN',
        ambiguous=False,
    )


@dataclass
class _FakeDownloader:
    raw: RawImport
    calls: int = 0

    async def download(
        self,
        source: ImportSource,
        *,
        timeout_seconds: float,
        max_bytes: int,
        verify_tls: bool,
    ) -> RawImport:
        _ = (source, timeout_seconds, max_bytes, verify_tls)
        self.calls += 1
        return self.raw


@dataclass
class _FakeClassifier:
    results: tuple[tuple[ParsedModelCard, ClassificationResult], ...]

    def classify_all(
        self, raw: RawImport,
    ) -> tuple[tuple[ParsedModelCard, ClassificationResult], ...]:
        _ = raw
        return self.results


@dataclass
class _FakeSmoke:
    outcomes: dict[str, SmokeOutcome] = field(default_factory=dict)
    calls: int = 0

    async def smoke(
        self,
        *,
        card: ParsedModelCard,
        classification: ClassificationResult,
        model_path: Path,
        timeout_seconds: float,
    ) -> SmokeOutcome:
        _ = (classification, model_path, timeout_seconds)
        self.calls += 1
        return self.outcomes.get(
            card.name,
            SmokeOutcome(card_name=card.name, status=SmokeStatus.PASSED, details='ok'),
        )


@dataclass
class _FakeKbWriter:
    captured: list[tuple[str, Path, Path]] = field(default_factory=list)

    def write_topic(
        self,
        *,
        report,  # noqa: ANN001
        card: ParsedModelCard,
        classification: ClassificationResult,
        installed_path: Path,
        kb_root: Path,
    ) -> Path:
        _ = (report, classification)
        target = kb_root / f'spice.{report.plan.vendor}.{card.name.lower()}.md'
        target.write_text('# fake topic\n')
        self.captured.append((card.name, installed_path, target))
        return target


def _make_adapters(
    *,
    smoke_overrides: dict[str, SmokeOutcome] | None = None,
) -> tuple[_FakeDownloader, _FakeClassifier, _FakeSmoke, _FakeKbWriter]:
    raw = _raw()
    classifier = _FakeClassifier(results=((_card(), _classification()),))
    return (
        _FakeDownloader(raw=raw),
        classifier,
        _FakeSmoke(outcomes=smoke_overrides or {}),
        _FakeKbWriter(),
    )


# === Happy path ===


async def test_url_import_end_to_end(tmp_path: Path) -> None:
    lib_root = tmp_path / 'user_lib'
    kb_root = tmp_path / 'kb'
    lib_root.mkdir()
    kb_root.mkdir()
    dl, cls, sm, kb = _make_adapters()

    report = await run_spice_import(
        source=ImportSource(kind='url', location='https://onsemi.com/Q2N3904.lib'),
        user_library_root=lib_root,
        kb_root=kb_root,
        downloader=dl,
        classifier=cls,
        smoke=sm,
        kb_writer=kb,
    )

    assert len(report.installed_paths) == 1
    install = report.installed_paths[0]
    assert install == lib_root / 'bjt' / 'onsemi' / 'Q2N3904.lib'
    assert install.is_file()
    body = install.read_text()
    assert '.MODEL Q2N3904 NPN' in body
    assert '* vendor: onsemi' in body
    assert '* source_url: https://onsemi.com/Q2N3904.lib' in body
    assert '* sha256: aaaaaaaa' in body
    assert '* subcategory: npn' in body
    assert sm.calls == 1
    assert len(report.smoke_outcomes) == 1
    assert report.smoke_outcomes[0].status is SmokeStatus.PASSED
    assert len(report.kb_topics) == 1
    assert report.kb_topics[0].name == 'spice.onsemi.q2n3904.md'


async def test_file_import_with_unknown_vendor(tmp_path: Path) -> None:
    lib_root = tmp_path / 'user_lib'
    kb_root = tmp_path / 'kb'
    lib_root.mkdir()
    kb_root.mkdir()
    src = ImportSource(kind='file', location='/home/x/Q2N3904.lib')
    dl, cls, sm, kb = _make_adapters()
    dl.raw = _raw(source=src)

    report = await run_spice_import(
        source=src,
        user_library_root=lib_root,
        kb_root=kb_root,
        downloader=dl,
        classifier=cls,
        smoke=sm,
        kb_writer=kb,
    )

    install = report.installed_paths[0]
    assert install == lib_root / 'bjt' / 'unknown' / 'Q2N3904.lib'
    body = install.read_text()
    assert '* vendor: unknown' in body
    assert '* source_url: local-file:/home/x/Q2N3904.lib' in body


async def test_vendor_override(tmp_path: Path) -> None:
    lib_root = tmp_path / 'user_lib'
    kb_root = tmp_path / 'kb'
    lib_root.mkdir()
    kb_root.mkdir()
    dl, cls, sm, kb = _make_adapters()

    report = await run_spice_import(
        source=ImportSource(kind='url', location='https://x.com/foo.lib'),
        user_library_root=lib_root,
        kb_root=kb_root,
        downloader=dl,
        classifier=cls,
        smoke=sm,
        kb_writer=kb,
        vendor_override='diyaudio',
    )
    assert report.installed_paths[0].parent.name == 'diyaudio'


# === Dry-run ===


async def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    lib_root = tmp_path / 'user_lib'
    kb_root = tmp_path / 'kb'
    lib_root.mkdir()
    kb_root.mkdir()
    dl, cls, sm, kb = _make_adapters()

    report = await run_spice_import(
        source=ImportSource(kind='url', location='https://onsemi.com/Q2N3904.lib'),
        user_library_root=lib_root,
        kb_root=kb_root,
        downloader=dl,
        classifier=cls,
        smoke=sm,
        kb_writer=kb,
        dry_run=True,
    )

    assert report.installed_paths == ()
    assert report.smoke_outcomes == ()
    assert report.kb_topics == ()
    # Plan заполнен (для CLI вывода).
    assert len(report.plan.cards) == 1
    assert report.plan.target_paths[0] == lib_root / 'bjt' / 'onsemi' / 'Q2N3904.lib'
    # Disk untouched.
    assert not (lib_root / 'bjt').exists()
    assert sm.calls == 0
    assert kb.captured == []


# === Duplicate ===


async def test_duplicate_without_force_raises(tmp_path: Path) -> None:
    lib_root = tmp_path / 'user_lib'
    kb_root = tmp_path / 'kb'
    lib_root.mkdir()
    kb_root.mkdir()
    existing = lib_root / 'bjt' / 'onsemi' / 'Q2N3904.lib'
    existing.parent.mkdir(parents=True)
    existing.write_text('old content\n')
    dl, cls, sm, kb = _make_adapters()

    with pytest.raises(ImportDuplicateError) as ei:
        await run_spice_import(
            source=ImportSource(kind='url', location='https://onsemi.com/Q2N3904.lib'),
            user_library_root=lib_root,
            kb_root=kb_root,
            downloader=dl,
            classifier=cls,
            smoke=sm,
            kb_writer=kb,
        )
    assert ei.value.target_path == existing
    assert existing.read_text() == 'old content\n'


async def test_duplicate_with_force_overwrites(tmp_path: Path) -> None:
    lib_root = tmp_path / 'user_lib'
    kb_root = tmp_path / 'kb'
    lib_root.mkdir()
    kb_root.mkdir()
    existing = lib_root / 'bjt' / 'onsemi' / 'Q2N3904.lib'
    existing.parent.mkdir(parents=True)
    existing.write_text('old content\n')
    dl, cls, sm, kb = _make_adapters()

    await run_spice_import(
        source=ImportSource(kind='url', location='https://onsemi.com/Q2N3904.lib'),
        user_library_root=lib_root,
        kb_root=kb_root,
        downloader=dl,
        classifier=cls,
        smoke=sm,
        kb_writer=kb,
        force=True,
    )
    assert '.MODEL Q2N3904 NPN' in existing.read_text()


# === Smoke skip & smoke failure rollback ===


async def test_skip_smoke_records_skipped_outcome(tmp_path: Path) -> None:
    lib_root = tmp_path / 'user_lib'
    kb_root = tmp_path / 'kb'
    lib_root.mkdir()
    kb_root.mkdir()
    dl, cls, sm, kb = _make_adapters()

    report = await run_spice_import(
        source=ImportSource(kind='url', location='https://onsemi.com/Q2N3904.lib'),
        user_library_root=lib_root,
        kb_root=kb_root,
        downloader=dl,
        classifier=cls,
        smoke=sm,
        kb_writer=kb,
        skip_smoke=True,
    )
    assert sm.calls == 0
    assert report.smoke_outcomes[0].status is SmokeStatus.SKIPPED
    # Файл install'нут (skipped не = rollback).
    assert report.installed_paths[0].is_file()


async def test_smoke_fail_rollback(tmp_path: Path) -> None:
    from domain.spice_import import SmokeFailedError

    lib_root = tmp_path / 'user_lib'
    kb_root = tmp_path / 'kb'
    lib_root.mkdir()
    kb_root.mkdir()

    @dataclass
    class _FailingSmoke:
        async def smoke(  # noqa: D401
            self,
            *,
            card: ParsedModelCard,
            classification: ClassificationResult,
            model_path: Path,
            timeout_seconds: float,
        ) -> SmokeOutcome:
            _ = (classification, model_path, timeout_seconds)
            raise SmokeFailedError(
                card_name=card.name,
                stdout='',
                stderr='convergence fail',
            )

    dl, cls, _, kb = _make_adapters()
    failing = _FailingSmoke()

    with pytest.raises(SmokeFailedError):
        await run_spice_import(
            source=ImportSource(kind='url', location='https://onsemi.com/Q2N3904.lib'),
            user_library_root=lib_root,
            kb_root=kb_root,
            downloader=dl,
            classifier=cls,
            smoke=failing,
            kb_writer=kb,
        )

    target = lib_root / 'bjt' / 'onsemi' / 'Q2N3904.lib'
    assert not target.exists()
    # staging тоже не остался
    assert not any((lib_root / '_imports').rglob('Q2N3904.lib'))
    assert kb.captured == []


# === Multi-card split ===


async def test_multi_subckt_splits_to_two_files(tmp_path: Path) -> None:
    lib_root = tmp_path / 'user_lib'
    kb_root = tmp_path / 'kb'
    lib_root.mkdir()
    kb_root.mkdir()
    card_one = ParsedModelCard(
        kind=ModelKind.SUBCKT,
        name='OPAONE',
        body='.SUBCKT OPAONE VCC VEE INP INM OUT\n.ENDS\n',
        model_type=None,
        pins=('VCC', 'VEE', 'INP', 'INM', 'OUT'),
        header_meta={},
    )
    card_two = ParsedModelCard(
        kind=ModelKind.SUBCKT,
        name='OPATWO',
        body='.SUBCKT OPATWO VCC VEE INP INM OUT\n.ENDS\n',
        model_type=None,
        pins=('VCC', 'VEE', 'INP', 'INM', 'OUT'),
        header_meta={},
    )
    cls_op = ClassificationResult(
        category=ComponentCategory.OPAMP,
        subcategory='full_vendor',
        reason='5-pin SUBCKT',
        ambiguous=False,
    )
    classifier = _FakeClassifier(results=((card_one, cls_op), (card_two, cls_op)))
    dl = _FakeDownloader(raw=_raw())
    sm = _FakeSmoke()
    kb = _FakeKbWriter()

    report = await run_spice_import(
        source=ImportSource(kind='url', location='https://ti.com/dual.lib'),
        user_library_root=lib_root,
        kb_root=kb_root,
        downloader=dl,
        classifier=classifier,
        smoke=sm,
        kb_writer=kb,
    )

    assert len(report.installed_paths) == 2
    names = {p.name for p in report.installed_paths}
    assert names == {'OPAONE.lib', 'OPATWO.lib'}
    for p in report.installed_paths:
        assert p.parent == lib_root / 'opamps' / 'ti'


# === PWRS conversion idempotence ===


async def test_pwrs_in_subckt_is_converted_on_install(tmp_path: Path) -> None:
    lib_root = tmp_path / 'user_lib'
    kb_root = tmp_path / 'kb'
    lib_root.mkdir()
    kb_root.mkdir()
    card = ParsedModelCard(
        kind=ModelKind.SUBCKT,
        name='X',
        body='.SUBCKT X A K\nE1 A K VOL=\'PWRS(V(A,K), 1.5)\'\n.ENDS\n',
        model_type=None,
        pins=('A', 'K'),
        header_meta={'subcategory': 'signal'},
    )
    cls_d = ClassificationResult(
        category=ComponentCategory.DIODE,
        subcategory='signal',
        reason='header',
        ambiguous=False,
    )
    classifier = _FakeClassifier(results=((card, cls_d),))
    raw_with_pwrs = RawImport(
        source=ImportSource(kind='url', location='https://x.com/x.lib'),
        bytes_text=card.body,
        sha256='b' * 64,
        downloaded_at=datetime(2026, 6, 5, tzinfo=UTC),
    )
    dl = _FakeDownloader(raw=raw_with_pwrs)
    sm = _FakeSmoke()
    kb = _FakeKbWriter()

    report = await run_spice_import(
        source=raw_with_pwrs.source,
        user_library_root=lib_root,
        kb_root=kb_root,
        downloader=dl,
        classifier=classifier,
        smoke=sm,
        kb_writer=kb,
    )

    text = report.installed_paths[0].read_text()
    # PWRS должен быть сконвертирован в sgn(...)*pwr(abs(...), ...)
    assert 'PWRS' not in text.upper() or 'sgn' in text or 'pwr' in text


# === Raw cache provenance ===


async def test_raw_cache_written_for_provenance(tmp_path: Path) -> None:
    lib_root = tmp_path / 'user_lib'
    kb_root = tmp_path / 'kb'
    lib_root.mkdir()
    kb_root.mkdir()
    dl, cls, sm, kb = _make_adapters()

    report = await run_spice_import(
        source=ImportSource(kind='url', location='https://onsemi.com/Q2N3904.lib'),
        user_library_root=lib_root,
        kb_root=kb_root,
        downloader=dl,
        classifier=cls,
        smoke=sm,
        kb_writer=kb,
    )
    sha = report.plan.raw.sha256
    raw_cache = lib_root / '_imports' / sha / 'raw.lib'
    assert raw_cache.is_file()
    assert raw_cache.read_text() == '.MODEL Q2N3904 NPN (BF=200)\n'
