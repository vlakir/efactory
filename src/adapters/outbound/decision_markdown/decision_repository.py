"""
FilesystemDecisionRepository — markdown сериализация Decision (T099).

Каждое решение — `<project>/decisions/D###_<slug>.md` по фиксированному
шаблону (CONCEPT §4.4 + Spec § 3 Adapter). Adapter атомарно пишет
(tmp + os.replace), парсит обратно по anchor-секциям; unknown секции
(например, ручные `## Context`) игнорируются (Analyze C1).
"""

from __future__ import annotations

import asyncio
import re
import unicodedata
from datetime import date as date_t
from typing import TYPE_CHECKING, Final

from pydantic import ValidationError

from domain.decision import Decision, DecisionStatus
from ports.outbound.decision_repository import (
    DecisionInvalidError,
    DecisionNotFoundError,
)

if TYPE_CHECKING:
    from pathlib import Path


DECISIONS_DIRNAME: Final = 'decisions'
_SLUG_MAX_LEN: Final = 50
_ID_GLOB_PATTERN: Final = 'D[0-9]*_*.md'

_NON_ALNUM_RE = re.compile(r'[^a-z0-9]+')
_HEADLINE_RE = re.compile(r'^# (D\d+): (.+)$', re.MULTILINE)
_DATE_RE = re.compile(r'^\*\*Дата:\*\* (.+)$', re.MULTILINE)
_STATUS_RE = re.compile(r'^\*\*Статус:\*\* (.+)$', re.MULTILINE)
_SESSION_RE = re.compile(r'^\*\*Сессия:\*\* (.+)$', re.MULTILINE)
_FILENAME_RE = re.compile(r'^(D\d+)_')


def _slugify(value: str) -> str:
    """ASCII slug; пустой → `untitled`; max 50 chars."""
    normalized = unicodedata.normalize('NFKD', value)
    ascii_only = normalized.encode('ascii', 'ignore').decode('ascii')
    lower = ascii_only.lower()
    slug = _NON_ALNUM_RE.sub('-', lower).strip('-')
    if not slug:
        return 'untitled'
    return slug[:_SLUG_MAX_LEN]


def _format_id(decision_id_num: int) -> str:
    """`D001`..`D999`, дальше `D1000+` без zero-pad."""
    if decision_id_num < 1000:  # noqa: PLR2004
        return f'D{decision_id_num:03d}'
    return f'D{decision_id_num}'


def _render(decision: Decision) -> str:
    parts: list[str] = [f'# {decision.id}: {decision.title}\n']
    parts.append(f'\n**Дата:** {decision.date.isoformat()}\n')
    parts.append(f'**Статус:** {decision.status.value}\n')
    if decision.session is not None:
        parts.append(f'**Сессия:** {decision.session}\n')
    parts.append(f'\n## Summary\n{decision.summary}\n')
    parts.append(f'\n## Rationale\n{decision.rationale}\n')
    if decision.evidence is not None:
        parts.append(f'\n## Evidence\n{decision.evidence}\n')
    return ''.join(parts)


def _extract_section(text: str, header: str) -> str | None:
    """Вернуть содержимое `## {header}` до следующего `##` или EOF; None если нет."""
    pattern = re.compile(
        rf'^## {re.escape(header)}\s*\n(.*?)(?=\n## |\Z)',
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    return match.group(1).strip() if match else None


def _parse(text: str, file_path: Path) -> Decision:
    headline = _HEADLINE_RE.search(text)
    date_match = _DATE_RE.search(text)
    status_match = _STATUS_RE.search(text)
    summary = _extract_section(text, 'Summary')
    rationale = _extract_section(text, 'Rationale')

    if not headline or not date_match or not status_match:
        msg = f'Invalid decision at {file_path}: missing headline/date/status'
        raise DecisionInvalidError(msg)
    if summary is None or rationale is None:
        msg = (
            f'Invalid decision at {file_path}: missing required section '
            '(Summary or Rationale)'
        )
        raise DecisionInvalidError(msg)

    session_match = _SESSION_RE.search(text)
    evidence = _extract_section(text, 'Evidence')

    try:
        return Decision(
            id=headline.group(1),
            title=headline.group(2).strip(),
            date=date_t.fromisoformat(date_match.group(1).strip()),
            status=DecisionStatus(status_match.group(1).strip()),
            summary=summary,
            rationale=rationale,
            evidence=evidence or None,  # type: ignore[arg-type]
            session=session_match.group(1).strip() if session_match else None,  # type: ignore[arg-type]
        )
    except (ValidationError, ValueError) as exc:
        msg = f'Invalid decision at {file_path}: {exc}'
        raise DecisionInvalidError(msg) from exc


def _find_file(project_path: Path, decision_id: str) -> Path | None:
    decisions_dir = project_path / DECISIONS_DIRNAME
    if not decisions_dir.is_dir():
        return None
    candidates = list(decisions_dir.glob(f'{decision_id}_*.md'))
    return candidates[0] if candidates else None


def _existing_ids(project_path: Path) -> list[int]:
    decisions_dir = project_path / DECISIONS_DIRNAME
    if not decisions_dir.is_dir():
        return []
    ids: list[int] = []
    for entry in decisions_dir.glob(_ID_GLOB_PATTERN):
        match = _FILENAME_RE.match(entry.name)
        if match:
            ids.append(int(match.group(1)[1:]))
    return ids


class FilesystemDecisionRepository:
    async def save(self, project_path: Path, decision: Decision) -> Path:
        decisions_dir = project_path / DECISIONS_DIRNAME
        slug = _slugify(decision.title)
        target = decisions_dir / f'{decision.id}_{slug}.md'
        text = _render(decision)

        def _atomic_write() -> Path:
            decisions_dir.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(target.suffix + '.tmp')
            tmp.write_text(text, encoding='utf-8')
            tmp.replace(target)
            return target

        return await asyncio.to_thread(_atomic_write)

    async def load(self, project_path: Path, decision_id: str) -> Decision:
        def _read() -> Decision:
            path = _find_file(project_path, decision_id)
            if path is None:
                msg = (
                    f'Decision {decision_id} not found in '
                    f'{project_path / DECISIONS_DIRNAME}'
                )
                raise DecisionNotFoundError(msg)
            return _parse(path.read_text(encoding='utf-8'), path)

        return await asyncio.to_thread(_read)

    async def list_all(self, project_path: Path) -> list[Decision]:
        def _scan() -> list[Decision]:
            decisions_dir = project_path / DECISIONS_DIRNAME
            if not decisions_dir.is_dir():
                return []
            results: list[tuple[int, Decision]] = []
            for entry in decisions_dir.glob(_ID_GLOB_PATTERN):
                match = _FILENAME_RE.match(entry.name)
                if not match:
                    continue
                decision = _parse(entry.read_text(encoding='utf-8'), entry)
                results.append((int(match.group(1)[1:]), decision))
            return [decision for _, decision in sorted(results, key=lambda x: x[0])]

        return await asyncio.to_thread(_scan)

    async def next_id(self, project_path: Path) -> str:
        def _compute() -> str:
            ids = _existing_ids(project_path)
            return _format_id(max(ids) + 1 if ids else 1)

        return await asyncio.to_thread(_compute)


__all__ = [
    'DECISIONS_DIRNAME',
    'FilesystemDecisionRepository',
]
