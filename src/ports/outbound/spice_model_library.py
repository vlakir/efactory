"""SpiceModelLibrary — outbound port для библиотеки SPICE-моделей (T006/T007)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain.spice_model import SpiceModel


class SpiceModelNotFoundError(Exception):
    """Модели с таким id нет в библиотеке."""


class SpiceModelLibraryDuplicateError(Exception):
    """
    Несколько моделей в библиотеке имеют один id.

    Например, `data/models/tubes/koren/EL34.lib` и
    `data/models/tubes/custom/EL34.lib` — конфликт.
    Пользователь должен решить вручную (T006 Resolved #9).
    """


class SpiceModelInvalidError(Exception):
    """
    Модель не парсится или не соответствует контракту (T007 C2).

    Например, transformer/load файл без обязательного header
    `* subcategory: <value>`.
    """


class SpiceModelLibrary(Protocol):
    """
    Generic библиотека SPICE-моделей всех категорий
    (tubes / transformers / loads — T006, T007).

    Adapter сканирует `<root>/<category>/<source>/*.{lib,inc,cir}`;
    парсит `.SUBCKT` заголовки + header `* subcategory:` (legacy
    `* tube_type:` для T006 моделей). Содержимое выдаёт по запросу
    через `read_subckt`.
    """

    async def list_all(self) -> list[SpiceModel]: ...

    async def get_by_id(self, model_id: str) -> SpiceModel: ...

    async def read_subckt(self, model_id: str) -> str: ...
