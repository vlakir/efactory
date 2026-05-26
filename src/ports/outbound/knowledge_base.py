"""
KbStore — outbound port для Knowledge Base persistence (T134).

Два источника entries (Clarify Q-A → a, Q-E → a host-wins):
- `built-in` seed — запекается в образ через Dockerfile (`docker/
  runtime-agent-knowledge-base/`).
- `host-mutated` — persistence между `docker rm` через bind-mount
  (`$HOME/efactory-state/knowledge-base/`).

`add()` пишет только в host-mutated (Analyze A6); built-in mutate'ится
исключительно через PR в репо.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain.knowledge_base import KbEntry


class KbStore(Protocol):
    """Persistence + retrieval для `KbEntry`."""

    def list_all(self) -> tuple[KbEntry, ...]:
        """
        Все entries: built-in merged with host-mutated (host wins).

        Sorted by `topic`. Conflict resolution per Q-E → a: при
        совпадении topic'а host-mutated overrides built-in.
        (Method named `list_all`, not `list`, чтобы не shadow builtin.)
        """
        ...

    def get(self, topic: str) -> KbEntry | None:
        """Один entry по namespaced slug (или None если не найден)."""
        ...

    def add(self, entry: KbEntry, *, force: bool = False) -> None:
        """
        Сохранить entry в host-mutated директорию.

        Built-in seed read-only runtime; `entry.source` ignored —
        adapter всегда пишет в host-mutated.

        Raises:
            KbConflictError: при существующем topic'е без `force=True`.

        """
        ...

    def search(self, query: str) -> tuple[KbEntry, ...]:
        """
        Token-AND поиск (Q-D → b) по `topic` + `description` + `tags` + `body`.

        Query split'ится whitespace; case-insensitive substring match;
        все tokens должны встретиться (хотя бы в одном из четырёх
        полей entry).
        """
        ...


__all__ = ['KbStore']
