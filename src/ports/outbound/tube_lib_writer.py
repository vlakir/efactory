"""
TubeLibWriter — outbound port для записи tube-modeled `.lib` (T031).

Реализуется `FilesystemTubeLibWriter` в `adapters.outbound.spice_models.
tube_lib_writer`. Tests могут мокать через простой stub-класс.

`TubeLibMeta` — concrete VO header metadata, лежит здесь (не в adapter),
чтобы application использовал его без import'а concrete adapter.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Literal, Protocol

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from pathlib import Path

    from domain.tube_fitting import AyumiPentodeParams, KorenTriodeParams

HeaderTubeType = Literal['triode', 'pentode', 'tetrode']


class TubeLibMeta(BaseModel):
    """Header metadata, передаваемый writer'у."""

    model_config = ConfigDict(frozen=True, extra='forbid')

    display_name: str
    """User-friendly имя (например, '6Ж38П') — пишется только в header
    comment, не в `.SUBCKT`."""

    source: str
    """Источник datasheet (e.g., 'Mullard 1962')."""

    date_extracted: date
    """Дата извлечения IV-точек (из IVDataset.date_extracted)."""

    date_fitted: date
    """Дата прогона fitter'а."""

    rms_residual_ma: float
    """RMS residual из FitResult (mА)."""

    n_points: int
    """Общее число точек в fit (Ia + Ig2 если screen_curves задан)."""


class TubeLibWriter(Protocol):
    """Запись `.lib` файла с fitted моделью."""

    def write(
        self,
        path: Path,
        spice_name: str,
        params: KorenTriodeParams | AyumiPentodeParams,
        *,
        header_tube_type: HeaderTubeType,
        meta: TubeLibMeta,
        force: bool = False,
    ) -> None:
        """
        Записать .lib.

        Контракт:

        * `spice_name` валидируется по `[A-Z0-9][A-Z0-9_]+`.
        * `header_tube_type` должен соответствовать runtime типу
          `params` (KorenTriodeParams → 'triode'; AyumiPentodeParams →
          'pentode'/'tetrode').
        * existing файл при `force=False` → исключение
          (`TubeLibWriteError` или совместимое).
        """
        ...
