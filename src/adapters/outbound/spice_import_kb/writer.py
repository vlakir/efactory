"""
MarkdownSpiceKbWriter — T030 adapter.

Рендерит KB-topic markdown для импортированной модели. Топик имя =
`spice.<vendor>.<part>.md` (lowercase). Перезаписывает существующий
файл (overwrite-safe: топик derives from install state).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.spice_import import KbWriteError

if TYPE_CHECKING:
    from pathlib import Path

    from domain.spice_import import (
        ClassificationResult,
        ImportReport,
        ParsedModelCard,
    )


class MarkdownSpiceKbWriter:
    def write_topic(
        self,
        *,
        report: ImportReport,
        card: ParsedModelCard,
        classification: ClassificationResult,
        installed_path: Path,
        kb_root: Path,
    ) -> Path:
        topic_name = f'spice.{report.plan.vendor}.{card.name.lower()}'
        target = kb_root / f'{topic_name}.md'

        if not kb_root.exists():
            raise KbWriteError(
                topic=topic_name,
                message=f'kb_root does not exist: {kb_root}',
            )
        if not kb_root.is_dir():
            raise KbWriteError(
                topic=topic_name,
                message=f'kb_root is not a directory: {kb_root}',
            )

        outcome = next(
            (o for o in report.smoke_outcomes if o.card_name == card.name),
            None,
        )
        smoke_line = (
            f'{outcome.status.value}: {outcome.details}' if outcome else 'not run'
        )

        source = report.plan.raw.source
        source_repr = (
            source.location if source.kind == 'url' else f'local-file:{source.location}'
        )

        body = _render(
            topic=topic_name,
            card=card,
            classification=classification,
            installed_path=installed_path,
            vendor=report.plan.vendor,
            source_repr=source_repr,
            sha256=report.plan.raw.sha256,
            imported_at=report.plan.raw.downloaded_at.isoformat(),
            smoke_line=smoke_line,
        )
        try:
            target.write_text(body, encoding='utf-8')
        except OSError as exc:
            raise KbWriteError(topic=topic_name, message=str(exc)) from exc
        return target


def _render(
    *,
    topic: str,
    card: ParsedModelCard,
    classification: ClassificationResult,
    installed_path: Path,
    vendor: str,
    source_repr: str,
    sha256: str,
    imported_at: str,
    smoke_line: str,
) -> str:
    cat = classification.category.value
    sub = classification.subcategory
    pins_line = f'- **Pins:** {", ".join(card.pins)}\n' if card.pins else ''
    type_line = f'- **MODEL type:** {card.model_type}\n' if card.model_type else ''
    return (
        f'---\n'
        f'topic: {topic}\n'
        f'source: import\n'
        f'imported_at: {imported_at}\n'
        f'---\n\n'
        f'# SPICE model: {card.name} ({vendor})\n\n'
        f'- **Category:** {cat}/{sub}\n'
        f'{pins_line}'
        f'{type_line}'
        f'- **Source:** {source_repr}\n'
        f'- **Install path:** `{installed_path}`\n'
        f'- **SHA256:** `{sha256}`\n'
        f'- **Smoke:** {smoke_line}\n\n'
        f'## Usage\n\n'
        f'Symbol→model resolver finds this by part name `{card.name}`.\n'
        f'Set the schematic component `Sim_Model` field to `{card.name}`.\n'
    )
