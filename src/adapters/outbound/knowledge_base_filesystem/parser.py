r"""
Frontmatter parser/renderer для Knowledge Base markdown entries (T134).

Изолирует yaml-parsing от domain'а (`domain.knowledge_base.KbEntry`).
Format unified со slash-команд convention'ом (T014): yaml-frontmatter
между `---\\n` markers, затем body.

Frontmatter schema (Q-J → a, strict):
```yaml
---
topic: spice.saturable          # namespaced slug (Q-B → b)
description: One-liner для TOC
tags: [spice, magnetics]        # optional
---
# Body markdown
```

`source` field auto-set caller'ом (Analyze A7); в файле его нет.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import yaml
from pydantic import ValidationError

from domain.knowledge_base import KbEntry, KbParseError

if TYPE_CHECKING:
    from domain.knowledge_base import SourceKind


_FRONTMATTER_OPEN = '---\n'
_FRONTMATTER_CLOSE = '\n---\n'


def parse_kb_entry(content: str, *, source: SourceKind) -> KbEntry:
    """
    Распарсить markdown с frontmatter в `KbEntry`.

    Args:
        content: full file content (frontmatter + body).
        source: `'built-in'` для запечённого seed entry, `'host-mutated'`
            для user-added.

    Returns:
        Provider-frontmatter Pydantic-validated `KbEntry`.

    Raises:
        KbParseError: при отсутствии frontmatter, невалидном yaml,
            нарушении schema (Pydantic ValidationError wrapped).

    """
    if not content.startswith(_FRONTMATTER_OPEN):
        msg = f'KB entry must start with {_FRONTMATTER_OPEN!r}; got: {content[:40]!r}'
        raise KbParseError(msg)
    end = content.find(_FRONTMATTER_CLOSE, len(_FRONTMATTER_OPEN))
    if end == -1:
        msg = f'KB entry frontmatter not closed by {_FRONTMATTER_CLOSE!r}'
        raise KbParseError(msg)

    frontmatter_raw = content[len(_FRONTMATTER_OPEN) : end]
    body_start = end + len(_FRONTMATTER_CLOSE)
    body = content[body_start:].lstrip('\n')

    try:
        frontmatter = yaml.safe_load(frontmatter_raw)
    except yaml.YAMLError as exc:
        msg = f'KB entry frontmatter is not valid YAML: {exc}'
        raise KbParseError(msg) from exc

    if not isinstance(frontmatter, dict):
        msg = (
            f'KB entry frontmatter must be a YAML mapping, '
            f'got {type(frontmatter).__name__}'
        )
        raise KbParseError(msg)

    if 'source' in frontmatter:
        msg = (
            "KB entry frontmatter must not contain 'source' — это поле "
            "auto-set adapter'ом при load (built-in vs host-mutated)."
        )
        raise KbParseError(msg)

    data: dict[str, Any] = {
        **frontmatter,
        'source': source,
        'body': body,
    }
    if 'tags' in data and isinstance(data['tags'], list):
        data['tags'] = tuple(data['tags'])

    try:
        return KbEntry(**data)
    except ValidationError as exc:
        msg = f'KB entry validation failed: {exc}'
        raise KbParseError(msg) from exc


def render_kb_entry(entry: KbEntry) -> str:
    """
    Сериализовать `KbEntry` обратно в markdown (frontmatter + body).

    `source` НЕ записывается в файл (Analyze A7 — auto-set adapter'ом
    при load).
    """
    frontmatter_data: dict[str, Any] = {
        'topic': entry.topic,
        'description': entry.description,
    }
    if entry.tags:
        frontmatter_data['tags'] = list(entry.tags)
    frontmatter_yaml = yaml.safe_dump(
        frontmatter_data,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )
    return f'{_FRONTMATTER_OPEN}{frontmatter_yaml}---\n\n{entry.body}'


__all__ = ['parse_kb_entry', 'render_kb_entry']
