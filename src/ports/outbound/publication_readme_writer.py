"""
PublicationReadmeWriter — outbound port для README.md публикации (T035 Phase 2.4).

Финальный README сводит вместе артефакты `SchematicPublicationArtifacts`
(Phase 2.1) и `SimReportArtifacts` (Phase 2.3) bundle'а. Содержит
описание файлов с DPI / форматом / датой генерации / версией efactory
/ именем проекта (FR §3).

Localization (`bundle.lang`) применяется к section titles + table
headers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from domain.publication import PublicationBundle


class PublicationReadmeWriteError(Exception):
    """README writer не смог сгенерировать README.md."""


class PublicationReadmeWriter(Protocol):
    """README writer для корня `<ts>`-каталога публикации (T035)."""

    async def write(
        self,
        bundle: PublicationBundle,
        *,
        out_dir: Path,
    ) -> Path:
        """
        Generate README.md в `out_dir` с описанием артефактов bundle'а.

        `out_dir` — обычно `<project>/out/publications/<ts>/`. README
        ссылается на schematic/ и sim-report/ относительными путями
        от `out_dir` (если файлы под `out_dir`) либо абсолютными
        (fallback).

        Возвращает Path созданного README.md.

        Raises:
            PublicationReadmeWriteError: IO error при создании файла.

        """
        ...


__all__ = ['PublicationReadmeWriteError', 'PublicationReadmeWriter']
