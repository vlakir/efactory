"""
SchematicSnapshot — context manager для atomic multi-edit с rollback (T004b Phase 1).

Use case: bridge edit с multiple `--set` flags. Каждый per-edit
atomic, но multi-edit как batch — нет. Если 3-й edit fail'нул,
schematic уже изменён первыми двумя; manual rollback требует backup.

Pattern:
    with SchematicSnapshot(path) as snap:
        edit_component_value(path, 'R1', '10k')
        edit_component_value(path, 'R2', '20k')   # may raise
        snap.commit()
    # без commit() → rollback на exit (auto-restore оригинала)

Implementation: shutil.copy2 → backup tmp file перед первой edit'ой;
если commit() called — backup удалён на exit; иначе backup восстановлен
поверх schematic. Не использует git — работает на голом файле.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from types import TracebackType


class SchematicSnapshot:
    def __init__(self, schematic_path: Path) -> None:
        self._path = schematic_path
        self._backup: Path | None = None
        self._committed = False

    def __enter__(self) -> Self:
        # Snapshot текущего состояния в tmp файл рядом с schematic
        # (atomic rollback через os.replace в same filesystem).
        fd, name = tempfile.mkstemp(
            dir=str(self._path.parent),
            prefix=f'.{self._path.name}.snapshot.',
            suffix='.bak',
        )
        # Закрываем fd сразу — shutil.copy2 откроет файл сам.
        os.close(fd)
        self._backup = Path(name)
        shutil.copy2(self._path, self._backup)
        return self

    def commit(self) -> None:
        """Подтвердить успех multi-edit batch — backup удалится на exit."""
        self._committed = True

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._backup is None:
            return
        try:
            if self._committed and exc_type is None:
                # Успех — backup не нужен.
                self._backup.unlink(missing_ok=True)
            else:
                # Failure или explicit rollback — restore из backup.
                # Atomic replace — schematic либо старый, либо новый.
                self._backup.replace(self._path)
        finally:
            self._backup = None


__all__ = ['SchematicSnapshot']
