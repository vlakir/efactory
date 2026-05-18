r"""
FilesystemJsonlSessionLogger — append-only JSONL session log (T010).

Каждая запись — одна валидная JSON-строка с trailing `\n`:
`{"ts":"...","event":"...","status":"ok","project":"...","payload":{...}}`.

`<session_root>/<session_id>/log.jsonl`. Каталог создаётся lazy
на первый write. Best-effort (Resolved #8): I/O сбой пишется в
stderr, CLI flow продолжается.

Без stdlib `logging`: тот канал — diagnostic INFO/WARNING; session
log структурный, append-only, JSONL.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

    from ports.outbound.session_logger import SessionEventStatus


_LOG_FILENAME = 'log.jsonl'


class FilesystemJsonlSessionLogger:
    def __init__(self, session_root: Path, session_id: str) -> None:
        self._session_root = session_root
        self._session_id = session_id

    @property
    def log_path(self) -> Path:
        return self._session_root / self._session_id / _LOG_FILENAME

    async def log_event(
        self,
        event: str,
        *,
        status: SessionEventStatus,
        project: str | None = None,
        payload: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        record: dict[str, Any] = {
            'ts': datetime.now(UTC).isoformat(),
            'event': event,
            'status': status.value,
        }
        if project is not None:
            record['project'] = project
        if payload:
            record['payload'] = payload
        if error is not None:
            record['error'] = error
        line = json.dumps(record, ensure_ascii=False, separators=(',', ':'))

        def _append() -> None:
            try:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                with self.log_path.open('a', encoding='utf-8') as fp:
                    fp.write(line + '\n')
            except OSError as exc:
                # Best-effort (Resolved #8): не прерываем CLI flow.
                sys.stderr.write(
                    f'session-log: failed to write to {self.log_path}: {exc}\n',
                )

        await asyncio.to_thread(_append)


__all__ = ['FilesystemJsonlSessionLogger']
