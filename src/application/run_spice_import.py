"""
run_spice_import use case (T030).

Pipeline: download → classify → plan → (dry-run early-out) → install
с staging + atomic move → smoke → KB topic write → ImportReport.

Atomicity: всё пишется сначала в `<user_library_root>/_imports/<sha256>/
staged/<category>/<vendor>/<PART>.lib`, на success атомарно move'ится
в `<user_library_root>/<category>/<vendor>/<PART>.lib`. Fail на любом
этапе после Stage оставляет staging (auto-cleanup в финале use case).

Raw download bytes сохраняются в `<user_library_root>/_imports/<sha256>/
raw.lib` для audit trail (T030 F6).
"""

from __future__ import annotations

import asyncio
import shutil
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Final
from urllib.parse import urlparse

from adapters.outbound.spice_models.conversion import convert_pwrs_to_ngspice
from domain.spice_import import (
    ImportDuplicateError,
    ImportPlan,
    ImportReport,
    SmokeOutcome,
    SmokeStatus,
)
from domain.spice_model import ComponentCategory

if TYPE_CHECKING:
    from pathlib import Path

    from domain.spice_import import (
        ClassificationResult,
        ImportSource,
        ParsedModelCard,
    )
    from ports.outbound.spice_import import (
        SpiceKbWriter,
        SpiceModelClassifier,
        SpiceModelDownloader,
        SpiceSmokeRunner,
    )


_DEFAULT_TIMEOUT_SECONDS: Final = 30.0
_DEFAULT_MAX_BYTES: Final = 1_048_576
_DEFAULT_SMOKE_TIMEOUT_SECONDS: Final = 15.0

_CATEGORY_PLURAL: Final[dict[ComponentCategory, str]] = {
    ComponentCategory.TUBE: 'tubes',
    ComponentCategory.TRANSFORMER: 'transformers',
    ComponentCategory.LOAD: 'loads',
    ComponentCategory.DIODE: 'diodes',
    ComponentCategory.OPAMP: 'opamps',
    ComponentCategory.BJT: 'bjt',
    ComponentCategory.JFET: 'jfet',
    ComponentCategory.MOSFET: 'mosfet',
}

_KNOWN_VENDOR_HOSTS: Final[dict[str, str]] = {
    'www.ti.com': 'ti',
    'ti.com': 'ti',
    'www.vishay.com': 'vishay',
    'vishay.com': 'vishay',
    'www.onsemi.com': 'onsemi',
    'onsemi.com': 'onsemi',
    'www.analog.com': 'analog',
    'analog.com': 'analog',
    'ww1.microchip.com': 'microchip',
    'www.microchip.com': 'microchip',
    'microchip.com': 'microchip',
    'www.infineon.com': 'infineon',
    'infineon.com': 'infineon',
    'www.st.com': 'st',
    'st.com': 'st',
    'www.nxp.com': 'nxp',
    'nxp.com': 'nxp',
}


async def run_spice_import(
    *,
    source: ImportSource,
    user_library_root: Path,
    kb_root: Path,
    downloader: SpiceModelDownloader,
    classifier: SpiceModelClassifier,
    smoke: SpiceSmokeRunner,
    kb_writer: SpiceKbWriter,
    force: bool = False,
    skip_smoke: bool = False,
    dry_run: bool = False,
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = _DEFAULT_MAX_BYTES,
    verify_tls: bool = True,
    vendor_override: str | None = None,
    category_override: ComponentCategory | None = None,
    subcategory_override: str | None = None,
    smoke_timeout_seconds: float = _DEFAULT_SMOKE_TIMEOUT_SECONDS,
) -> ImportReport:
    started_at = datetime.now(UTC)

    raw = await downloader.download(
        source,
        timeout_seconds=timeout_seconds,
        max_bytes=max_bytes,
        verify_tls=verify_tls,
    )

    classification_pairs = classifier.classify_all(raw)
    if not classification_pairs:
        msg = 'no .SUBCKT / .MODEL cards detected in downloaded SPICE deck'
        raise ValueError(msg)

    # Apply overrides.
    cards = tuple(
        (
            card,
            _apply_overrides(
                classification=cls,
                category_override=category_override,
                subcategory_override=subcategory_override,
            ),
        )
        for card, cls in classification_pairs
    )

    vendor = _resolve_vendor(source, vendor_override)
    target_paths = tuple(
        _compute_target_path(user_library_root, vendor, card, cls)
        for card, cls in cards
    )

    plan = ImportPlan(
        raw=raw,
        cards=cards,
        vendor=vendor,
        target_paths=target_paths,
    )

    if dry_run:
        return ImportReport(
            plan=plan,
            installed_paths=(),
            smoke_outcomes=(),
            kb_topics=(),
            started_at=started_at,
            finished_at=datetime.now(UTC),
        )

    if not force:
        for target in target_paths:
            if target.exists():
                raise ImportDuplicateError(target_path=target)

    # Provenance raw cache.
    raw_cache_dir = user_library_root / '_imports' / raw.sha256
    raw_cache_dir.mkdir(parents=True, exist_ok=True)
    (raw_cache_dir / 'raw.lib').write_text(raw.bytes_text, encoding='utf-8')

    staging_dir = raw_cache_dir / 'staged'
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir()

    staged_paths: list[tuple[Path, Path]] = []
    for (card, cls), target in zip(cards, target_paths, strict=True):
        body = _inject_headers(
            body=convert_pwrs_to_ngspice(card.body),
            vendor=vendor,
            source=source,
            sha256=raw.sha256,
            imported_at=raw.downloaded_at.isoformat(),
            subcategory=cls.subcategory,
        )
        staged_target = staging_dir / target.relative_to(user_library_root)
        staged_target.parent.mkdir(parents=True, exist_ok=True)
        staged_target.write_text(body, encoding='utf-8')
        staged_paths.append((staged_target, target))

    smoke_outcomes: list[SmokeOutcome] = []
    for (card, cls), (staged_target, _) in zip(cards, staged_paths, strict=True):
        if skip_smoke:
            smoke_outcomes.append(
                SmokeOutcome(
                    card_name=card.name,
                    status=SmokeStatus.SKIPPED,
                    details='--skip-smoke',
                ),
            )
            continue
        try:
            outcome = await smoke.smoke(
                card=card,
                classification=cls,
                model_path=staged_target,
                timeout_seconds=smoke_timeout_seconds,
            )
        except Exception:
            await _cleanup_staging(staging_dir)
            raise
        smoke_outcomes.append(outcome)

    # Atomic promote: staged → final. shutil.move через os.replace где возможно.
    installed_paths: list[Path] = []
    for staged_target, target in staged_paths:
        target.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(_atomic_replace, staged_target, target)
        installed_paths.append(target)

    await _cleanup_staging(staging_dir)

    finished_at = datetime.now(UTC)
    pre_kb_report = ImportReport(
        plan=plan,
        installed_paths=tuple(installed_paths),
        smoke_outcomes=tuple(smoke_outcomes),
        kb_topics=(),
        started_at=started_at,
        finished_at=finished_at,
    )

    kb_topics: list[Path] = []
    for (card, cls), install in zip(cards, installed_paths, strict=True):
        topic_path = kb_writer.write_topic(
            report=pre_kb_report,
            card=card,
            classification=cls,
            installed_path=install,
            kb_root=kb_root,
        )
        kb_topics.append(topic_path)

    return ImportReport(
        plan=plan,
        installed_paths=tuple(installed_paths),
        smoke_outcomes=tuple(smoke_outcomes),
        kb_topics=tuple(kb_topics),
        started_at=started_at,
        finished_at=datetime.now(UTC),
    )


def _resolve_vendor(source: ImportSource, override: str | None) -> str:
    if override:
        return override
    if source.kind == 'file':
        return 'unknown'
    parsed = urlparse(source.location)
    host = parsed.netloc.split(':', 1)[0].lower()
    return _KNOWN_VENDOR_HOSTS.get(host, 'unknown')


def _apply_overrides(
    *,
    classification: ClassificationResult,
    category_override: ComponentCategory | None,
    subcategory_override: str | None,
) -> ClassificationResult:
    if category_override is None and subcategory_override is None:
        return classification
    new_category = category_override or classification.category
    new_subcategory = subcategory_override or classification.subcategory
    reason = (
        classification.reason
        + ' [CLI override: '
        + (f'category={category_override.value} ' if category_override else '')
        + (f'subcategory={subcategory_override}' if subcategory_override else '')
        + ']'
    )
    return type(classification)(
        category=new_category,
        subcategory=new_subcategory,
        reason=reason,
        ambiguous=False,
    )


def _compute_target_path(
    user_library_root: Path,
    vendor: str,
    card: ParsedModelCard,
    classification: ClassificationResult,
) -> Path:
    plural = _CATEGORY_PLURAL.get(classification.category)
    if plural is None:
        msg = f'no plural-dir mapping for category={classification.category}'
        raise ValueError(msg)
    return user_library_root / plural / vendor / f'{card.name}.lib'


def _inject_headers(
    *,
    body: str,
    vendor: str,
    source: ImportSource,
    sha256: str,
    imported_at: str,
    subcategory: str,
) -> str:
    source_repr = (
        source.location if source.kind == 'url' else f'local-file:{source.location}'
    )
    header_block = (
        f'* vendor: {vendor}\n'
        f'* source_url: {source_repr}\n'
        f'* sha256: {sha256}\n'
        f'* imported_at: {imported_at}\n'
        f'* subcategory: {subcategory}\n'
    )
    cleaned = _strip_existing_header_lines(body, {'vendor', 'subcategory'})
    return header_block + cleaned


def _strip_existing_header_lines(body: str, keys: set[str]) -> str:
    """Удалить leading '* key:' строки из body, если key in keys."""
    lines = body.splitlines(keepends=True)
    kept: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('*') and ':' in stripped:
            try:
                _, key_value = stripped.split('*', 1)
                key = key_value.split(':', 1)[0].strip().lower()
            except (ValueError, IndexError):
                key = ''
            if key in keys:
                continue
        kept.append(line)
    return ''.join(kept)


def _atomic_replace(src: Path, dst: Path) -> None:
    """os.replace через shutil.move для cross-fs совместимости."""
    if dst.exists():
        dst.unlink()
    shutil.move(str(src), str(dst))


async def _cleanup_staging(staging_dir: Path) -> None:
    def _rm() -> None:
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)

    await asyncio.to_thread(_rm)


__all__ = ['run_spice_import']
