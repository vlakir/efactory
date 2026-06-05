"""
SPICE model import outbound ports (T030).

Pipeline: download (URL or local file) → classify (`.SUBCKT` / `.MODEL`
cards → ComponentCategory + subcategory) → per-card ngspice smoke →
KB topic write.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from domain.spice_import import (
        ClassificationResult,
        ImportReport,
        ImportSource,
        ParsedModelCard,
        RawImport,
        SmokeOutcome,
    )


class SpiceModelDownloader(Protocol):
    async def download(
        self,
        source: ImportSource,
        *,
        timeout_seconds: float,
        max_bytes: int,
        verify_tls: bool,
    ) -> RawImport: ...


class SpiceModelClassifier(Protocol):
    def classify_all(
        self,
        raw: RawImport,
    ) -> tuple[tuple[ParsedModelCard, ClassificationResult], ...]: ...


class SpiceSmokeRunner(Protocol):
    async def smoke(
        self,
        *,
        card: ParsedModelCard,
        classification: ClassificationResult,
        model_path: Path,
        timeout_seconds: float,
    ) -> SmokeOutcome: ...


class SpiceKbWriter(Protocol):
    def write_topic(
        self,
        *,
        report: ImportReport,
        card: ParsedModelCard,
        classification: ClassificationResult,
        installed_path: Path,
        kb_root: Path,
    ) -> Path: ...
