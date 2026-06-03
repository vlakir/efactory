"""
TubeIVRepository — outbound port для чтения IVDataset + seed-from params (T031).

Реализуется `FilesystemTubeIVRepository` в `adapters.outbound.spice_models.
tube_json`. Tests могут мокать через простой stub-класс.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from domain.tube_fitting import AyumiPentodeParams, IVDataset, KorenTriodeParams


class TubeIVRepository(Protocol):
    """Чтение IV-точек + seed-from params из persistent storage."""

    def load_iv_dataset(self, path: Path) -> IVDataset:
        """
        Прочитать IVDataset из JSON-файла.

        Должен бросать `IVDatasetLoadError` (или совместимое исключение)
        при отсутствии файла / битом JSON / failed Pydantic validation.
        """
        ...

    def load_seed_from_params(
        self, path: Path, tube_type: str
    ) -> KorenTriodeParams | AyumiPentodeParams:
        """
        Прочитать existing tube params как `--seed-from` hint (S3).

        `tube_type` ∈ {'triode', 'pentode'}; диктует, какую model
        validator применять.
        """
        ...
