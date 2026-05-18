"""SessionLogger — outbound port для structured CLI-операций (T010)."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol


class SessionEventStatus(StrEnum):
    OK = 'ok'
    ERROR = 'error'


class SessionLogger(Protocol):
    """
    Append-only JSONL log CLI-операций в каталог сессии.

    `<session_root>/<session_id>/log.jsonl` (T010 Resolved #1 (A)
    global). Best-effort: сбой записи не прерывает CLI flow
    (Resolved #8) — реализация должна сама обработать I/O ошибки
    и не пробрасывать.
    """

    async def log_event(
        self,
        event: str,
        *,
        status: SessionEventStatus,
        project: str | None = None,
        payload: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None: ...
