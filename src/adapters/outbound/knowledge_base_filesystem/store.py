"""
`FileSystemKbStore` — KbStore impl поверх двух директорий (T134 Phase B).

Layout:
- `built_in_dir/<slug>.md` — запечённый в образ seed.
- `host_mutated_dir/<slug>.md` — user-added через `/kb-add` или
  `efactory kb add`.

`list()` scan'ит обе, merge с host-wins при совпадении topic'а.
`add()` пишет только в `host_mutated_dir`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from adapters.outbound.knowledge_base_filesystem.parser import (
    parse_kb_entry,
    render_kb_entry,
)
from domain.knowledge_base import KbConflictError, KbEntry, KbParseError

if TYPE_CHECKING:
    from pathlib import Path


_MARKDOWN_GLOB = '*.md'


class FileSystemKbStore:
    """`KbStore` implementation поверх built-in + host-mutated директорий."""

    def __init__(
        self,
        *,
        built_in_dir: Path,
        host_mutated_dir: Path,
    ) -> None:
        self._built_in_dir = built_in_dir
        self._host_mutated_dir = host_mutated_dir

    def list_all(self) -> tuple[KbEntry, ...]:
        by_topic: dict[str, KbEntry] = {}
        # Built-in first (lowest priority).
        for entry in self._scan_dir(self._built_in_dir, source='built-in'):
            by_topic[entry.topic] = entry
        # Host-mutated overrides built-in (Q-E → a host wins).
        for entry in self._scan_dir(
            self._host_mutated_dir,
            source='host-mutated',
        ):
            by_topic[entry.topic] = entry
        return tuple(sorted(by_topic.values(), key=lambda e: e.topic))

    def get(self, topic: str) -> KbEntry | None:
        for entry in self.list_all():
            if entry.topic == topic:
                return entry
        return None

    def add(self, entry: KbEntry, *, force: bool = False) -> None:
        existing = self.get(entry.topic)
        if existing is not None and not force:
            msg = (
                f'KB topic {entry.topic!r} already exists '
                f'(source={existing.source!r}); pass force=True to overwrite.'
            )
            raise KbConflictError(msg)
        self._host_mutated_dir.mkdir(parents=True, exist_ok=True)
        target = self._host_mutated_dir / f'{entry.topic}.md'
        target.write_text(render_kb_entry(entry), encoding='utf-8')

    def search(self, query: str) -> tuple[KbEntry, ...]:
        tokens = [t.lower() for t in query.split() if t.strip()]
        if not tokens:
            return ()
        matches: list[KbEntry] = []
        for entry in self.list_all():
            haystack = _entry_haystack(entry)
            if all(token in haystack for token in tokens):
                matches.append(entry)
        return tuple(matches)

    def _scan_dir(
        self,
        directory: Path,
        *,
        source: str,
    ) -> list[KbEntry]:
        if not directory.is_dir():
            return []
        entries: list[KbEntry] = []
        for md_path in sorted(directory.glob(_MARKDOWN_GLOB)):
            # KB entries имеют namespaced slug — filename содержит точку.
            # Произвольные `.md` в той же директории (README, NOTES) — skip.
            if '.' not in md_path.stem:
                continue
            content = md_path.read_text(encoding='utf-8')
            try:
                # Cast source to expected literal at call site.
                entry = parse_kb_entry(content, source=source)  # type: ignore[arg-type]
            except KbParseError as exc:
                msg = f'failed to parse KB entry at {md_path} (source={source}): {exc}'
                raise KbParseError(msg) from exc
            expected_topic = md_path.stem
            if entry.topic != expected_topic:
                msg = (
                    f'KB entry {md_path}: frontmatter topic '
                    f'{entry.topic!r} does not match filename slug '
                    f'{expected_topic!r}'
                )
                raise KbParseError(msg)
            entries.append(entry)
        return entries


def _entry_haystack(entry: KbEntry) -> str:
    """Lowercased concatenation of topic + description + tags + body."""
    return ' '.join(
        [
            entry.topic.lower(),
            entry.description.lower(),
            ' '.join(entry.tags).lower(),
            entry.body.lower(),
        ],
    )


__all__ = ['FileSystemKbStore']
