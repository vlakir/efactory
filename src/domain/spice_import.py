"""
SPICE-model import pipeline domain layer (T030).

Value objects + exceptions для use case `run_spice_import` (download →
classify → convert PWRS → install под user_library_root → smoke → KB).

Frozen pydantic VO (audit trail важнее mutability). Exceptions с
typed payloads — adapter / use case переносят их в CLI exit codes.

Тубы / трансформаторы / loads не оптимизированы под этот pipeline
(основной источник tube-моделей — T031 fitter), но импортировать
такие модели через `import-file` технически возможно (smoke skipped).
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, BaseModel, ConfigDict, model_validator

from domain.spice_model import ComponentCategory

_FROZEN = ConfigDict(frozen=True, extra='forbid')

_SHA256_RE = re.compile(r'^[0-9a-f]{64}$')
_VENDOR_RE = re.compile(r'^[a-z][a-z0-9_-]*$')


def _validate_sha256(value: str) -> str:
    if not _SHA256_RE.match(value):
        msg = f'sha256 must be 64 lowercase hex chars, got {value!r}'
        raise ValueError(msg)
    return value


def _validate_vendor(value: str) -> str:
    if not _VENDOR_RE.match(value):
        msg = (
            f'vendor must match {_VENDOR_RE.pattern} '
            f'(lowercase, starts with letter), got {value!r}'
        )
        raise ValueError(msg)
    return value


Sha256Hex = Annotated[str, AfterValidator(_validate_sha256)]
VendorName = Annotated[str, AfterValidator(_validate_vendor)]


class ModelKind(StrEnum):
    """SPICE card kind: `.SUBCKT` wrapper vs primitive `.MODEL`."""

    SUBCKT = 'subckt'
    MODEL = 'model'


class SmokeStatus(StrEnum):
    PASSED = 'passed'
    FAILED = 'failed'
    SKIPPED = 'skipped'


class ImportSource(BaseModel):
    """Где взять SPICE-deck: HTTP URL или локальный файл."""

    model_config = _FROZEN

    kind: Literal['url', 'file']
    location: str
    vendor_hint: str | None = None


class RawImport(BaseModel):
    """Downloaded / read SPICE-deck bytes + provenance."""

    model_config = _FROZEN

    source: ImportSource
    bytes_text: str
    sha256: Sha256Hex
    downloaded_at: datetime


class ParsedModelCard(BaseModel):
    """Один `.SUBCKT` или `.MODEL` блок, извлечённый из RawImport."""

    model_config = _FROZEN

    kind: ModelKind
    name: str
    body: str
    model_type: str | None  # для .MODEL — NPN/PNP/NJF/.../D; None для .SUBCKT
    pins: tuple[str, ...] | None  # для .SUBCKT; None для .MODEL
    header_meta: dict[str, str]  # parsed `* foo: bar` headers выше карточки

    @model_validator(mode='after')
    def _kind_payload_consistent(self) -> Self:
        if self.kind is ModelKind.SUBCKT and self.pins is None:
            msg = 'kind=SUBCKT requires pins (not None)'
            raise ValueError(msg)
        if self.kind is ModelKind.MODEL and self.model_type is None:
            msg = 'kind=MODEL requires model_type (NPN/PNP/D/...)'
            raise ValueError(msg)
        return self


class ClassificationResult(BaseModel):
    """Итог классификации одной ParsedModelCard."""

    model_config = _FROZEN

    category: ComponentCategory
    subcategory: str
    reason: str
    ambiguous: bool


class ImportPlan(BaseModel):
    """План установки: что куда положим (до начала записи)."""

    model_config = _FROZEN

    raw: RawImport
    cards: tuple[tuple[ParsedModelCard, ClassificationResult], ...]
    vendor: VendorName
    target_paths: tuple[Path, ...]

    @model_validator(mode='after')
    def _paths_match_cards(self) -> Self:
        if len(self.cards) != len(self.target_paths):
            msg = (
                f'target_paths length {len(self.target_paths)} != '
                f'cards length {len(self.cards)}'
            )
            raise ValueError(msg)
        return self


class SmokeOutcome(BaseModel):
    """Результат per-card ngspice smoke OP analysis."""

    model_config = _FROZEN

    card_name: str
    status: SmokeStatus
    details: str


class ImportReport(BaseModel):
    """Итог пайплайна для CLI / KB / agent."""

    model_config = _FROZEN

    plan: ImportPlan
    installed_paths: tuple[Path, ...]
    smoke_outcomes: tuple[SmokeOutcome, ...]
    kb_topics: tuple[Path, ...]
    started_at: datetime
    finished_at: datetime


# === Exceptions ===


class SpiceImportError(Exception):
    """Базовый класс ошибок пайплайна импорта."""


class DownloadError(SpiceImportError):
    """Network / HTTP / TLS / redirect / 4xx / 5xx."""

    def __init__(self, *, url: str, status: int | None, message: str) -> None:
        self.url = url
        self.status = status
        super().__init__(f'download failed [{status}]: {url} — {message}')


class ContentRejectedError(SpiceImportError):
    """Тело — не SPICE deck (HTML, binary, encrypted)."""

    def __init__(self, *, reason: str) -> None:
        self.reason = reason
        super().__init__(f'content rejected: {reason}')


class ClassificationAmbiguousError(SpiceImportError):
    """Эвристика не смогла однозначно определить category/subcategory."""

    def __init__(self, *, card: ParsedModelCard, reason: str) -> None:
        self.card = card
        self.reason = reason
        super().__init__(
            f'classification ambiguous for {card.name!r}: {reason}. '
            f'Override via --category=<cat> --subcategory=<sub>.',
        )


class ImportDuplicateError(SpiceImportError):
    """Целевой путь уже существует, --force не задан."""

    def __init__(self, *, target_path: Path) -> None:
        self.target_path = target_path
        super().__init__(
            f'already installed at {target_path} (use --force to overwrite)'
        )


class SmokeFailedError(SpiceImportError):
    """ngspice OP сошёлся, но invariant не выполняется (либо ошибка ngspice)."""

    def __init__(self, *, card_name: str, stdout: str, stderr: str) -> None:
        self.card_name = card_name
        self.stdout = stdout
        self.stderr = stderr
        super().__init__(f'smoke fail for {card_name}: {stderr or stdout}'.strip())


class SmokeTimeoutError(SpiceImportError):
    """ngspice subprocess превысил smoke timeout."""

    def __init__(self, *, card_name: str, timeout_seconds: float) -> None:
        self.card_name = card_name
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f'smoke for {card_name} timed out after {timeout_seconds:g}s',
        )


class KbWriteError(SpiceImportError):
    """Запись KB topic упала на IO."""

    def __init__(self, *, topic: str, message: str) -> None:
        self.topic = topic
        super().__init__(f'KB write failed for {topic}: {message}')
