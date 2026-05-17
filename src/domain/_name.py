"""
Path-safe name validator (T092) — общий для Project.name и Decision.title.

Выделено в отдельный модуль, чтобы разорвать циклический импорт
`domain.project` ↔ `domain.decision`.
"""

from __future__ import annotations


def validate_name(value: str) -> str:
    if not value.strip():
        msg = 'Name must not be empty or whitespace-only'
        raise ValueError(msg)
    if value in {'.', '..'}:
        msg = 'Name must not be "." or ".."'
        raise ValueError(msg)
    if '/' in value or '\\' in value:
        msg = 'Name must not contain path separators ("/" or "\\")'
        raise ValueError(msg)
    return value
