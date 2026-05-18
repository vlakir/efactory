"""TubeModelLibrary — outbound port для SPICE-моделей ламп (T006)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain.spice_model import SpiceModel


class TubeModelNotFoundError(Exception):
    """Модели с таким id нет в библиотеке."""


class TubeModelLibraryDuplicateError(Exception):
    """
    Несколько моделей в библиотеке имеют один id.

    Например, `data/models/tubes/koren/EL34_KOREN.lib` и
    `data/models/tubes/custom/EL34_KOREN.lib` — конфликт.
    Пользователь должен решить вручную (Resolved #9).
    """


class TubeModelLibrary(Protocol):
    """
    Каталог `data/models/tubes/{koren,ayumi,duncan,custom}/*.{lib,inc,cir}`
    как inventory (T006). Адаптер парсит `.SUBCKT` заголовки;
    содержимое выдаёт по запросу через `read_subckt`.
    """

    async def list_all(self) -> list[SpiceModel]: ...

    async def get_by_id(self, model_id: str) -> SpiceModel: ...

    async def read_subckt(self, model_id: str) -> str: ...
