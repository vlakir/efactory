"""PlatformLayer — outbound port для resolution внешних приложений (T009)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from domain.application import ApplicationKind, OsKind


class PlatformLayer(Protocol):
    """
    Платформо-зависимая resolution внешних приложений efactory.

    Не управляет процессами (это AppManager); только отвечает на
    «где лежит kicad-cli» и «как его запустить» (с учётом
    multi-call AppImage обёрток типа sharun).
    """

    def os_kind(self) -> OsKind: ...

    def resolve_command(
        self,
        kind: ApplicationKind,
    ) -> list[str] | None:
        """
        Вернуть argv-prefix для запуска приложения, или None если не найдено.

        Для большинства apps — `[executable_path]`. Для multi-call
        AppImage (KICAD_CLI внутри KiCad AppImage) — например,
        `['/home/u/kicad.AppImage', 'kicad-cli']`. CLI bridges
        дополняют этот префикс своими args.
        """
        ...
