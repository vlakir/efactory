"""
Knowledge Base — domain VO для runtime-агента (T134).

Один `KbEntry` = один markdown topic в KB. Слой persistence (built-in
seed запекается в образ + host-mutated в `$HOME/efactory-state/`)
живёт в `adapters/outbound/knowledge_base_filesystem/`. Domain здесь —
без знания о yaml-parsing, file layout, или I/O.

Topic-naming convention (Clarify Q-B → b): namespaced slug
`<namespace>.<name>` (`spice.saturable`, `agent.command-routing`).
Namespace используется SessionStart hook'ом (T016 extension) для
group'ировки TOC (Clarify Q-C → c).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

SourceKind = Literal['built-in', 'host-mutated']

_TOPIC_PATTERN = r'^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]+)+$'
_TAG_PATTERN = r'^[a-z][a-z0-9-]*$'

_FROZEN = ConfigDict(frozen=True, extra='forbid')

Tag = Annotated[str, Field(pattern=_TAG_PATTERN, min_length=1)]


class KbConflictError(Exception):
    """
    Попытка добавить entry с topic, который уже существует.

    Caller может попробовать `--force` (overwrite) или выбрать другой
    slug. Поднимается из `KbStore.add()` adapter'ом.
    """


class KbParseError(Exception):
    """
    Markdown-файл нельзя распарсить в `KbEntry`.

    Причина: отсутствие frontmatter, невалидный yaml, missing required
    fields, schema-violation (Pydantic). Поднимается parser'ом или
    `KbStore.list()` при scan.
    """


class KbEntry(BaseModel):
    """
    Один topic в Knowledge Base.

    Frontmatter file:
    ```yaml
    ---
    topic: spice.saturable          # должен соответствовать filename slug
    description: Saturable магнетика в SPICE требует XSPICE gyrator-cap
    tags: [spice, magnetics, ngspice]
    ---
    # Body markdown ...
    ```

    `source` устанавливается adapter'ом при load (Analyze A7): `'built-
    in'` для запечённых entries из образа, `'host-mutated'` для
    user-added через `/kb-add` или `efactory kb add`.
    """

    model_config = _FROZEN

    topic: Annotated[str, Field(pattern=_TOPIC_PATTERN, min_length=3)]
    description: Annotated[str, Field(min_length=1, max_length=200)]
    tags: tuple[Tag, ...] = ()
    source: SourceKind
    body: Annotated[str, Field(min_length=1)]

    @property
    def namespace(self) -> str:
        """Часть до первой точки — например `'spice'` для `spice.saturable`."""
        return self.topic.split('.', 1)[0]

    @property
    def name(self) -> str:
        """Часть после первой точки — например `'saturable'`."""
        return self.topic.split('.', 1)[1]


__all__ = [
    'KbConflictError',
    'KbEntry',
    'KbParseError',
    'SourceKind',
    'Tag',
]
