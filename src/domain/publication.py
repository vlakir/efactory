"""
Publication workflow VOs (T035 Phase 1).

Domain layer для двух slash-команд:
- `/export-schematic-publication` → `SchematicPublicationArtifacts`
  (color + bw × per-sheet ± combined PDF).
- `/export-sim-report` → `SimReportArtifacts` (Markdown отчёт +
  publication-grade PNG-плоты + опциональные tables).

Главная aggregate — `PublicationBundle` (один из двух наборов
артефактов обязателен; оба допустимы при совмещённом вызове).

VOs frozen, без IO. Timestamp UTC обязателен. Helper
`publication_timestamp_dirname` — единственная чистая функция
форматирования `<ts>`-каталога; collision-resolution с IO живёт
в use case layer (Phase 3).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from domain.simulation import AcSweep, DcSweep, TimeSeries


class PublicationLang(StrEnum):
    RU = 'ru'
    EN = 'en'


class MultiSheetMode(StrEnum):
    PER_SHEET = 'per-sheet'
    COMBINED = 'combined'


class SheetArtifactSet(BaseModel):
    """Тройка артефактов для одного листа схемы (SVG + PDF + PNG@300)."""

    model_config = ConfigDict(frozen=True)

    sheet_name: str = Field(min_length=1)
    svg: Path
    pdf: Path
    png: Path


class SchematicPublicationArtifacts(BaseModel):
    """
    Артефакты `/export-schematic-publication`.

    Color и BW наборы должны быть одинаковой длины (на один листы —
    оба варианта). `*_combined` поля включаются только при
    `--multi-sheet-mode combined`; если задан один — должен быть
    задан и другой.
    """

    model_config = ConfigDict(frozen=True)

    color_per_sheet: tuple[SheetArtifactSet, ...] = Field(min_length=1)
    bw_per_sheet: tuple[SheetArtifactSet, ...] = Field(min_length=1)
    color_combined: Path | None
    bw_combined: Path | None

    @model_validator(mode='after')
    def _check_per_sheet_length_match(self) -> Self:
        if len(self.color_per_sheet) != len(self.bw_per_sheet):
            msg = (
                f'SchematicPublicationArtifacts: color_per_sheet '
                f'({len(self.color_per_sheet)}) и bw_per_sheet '
                f'({len(self.bw_per_sheet)}) должны иметь одинаковую длину.'
            )
            raise ValueError(msg)
        return self

    @model_validator(mode='after')
    def _check_combined_pair(self) -> Self:
        if (self.color_combined is None) != (self.bw_combined is None):
            msg = (
                'SchematicPublicationArtifacts: color_combined и bw_combined '
                'должны быть оба None либо оба заданы (multi-sheet combined '
                'mode даёт обе цветовые версии одновременно).'
            )
            raise ValueError(msg)
        return self


class SimReportArtifacts(BaseModel):
    """
    Артефакты `/export-sim-report`.

    `source_simulation_ts` — UTC-aware timestamp оригинальной
    симуляции (когда команда вызвана без `--rerun`); None при
    свежем прогоне. README использует это поле для секции
    «based on simulation from …».
    """

    model_config = ConfigDict(frozen=True)

    report_md: Path
    plots: tuple[Path, ...]
    tables: tuple[Path, ...]
    source_simulation_ts: datetime | None

    @model_validator(mode='after')
    def _check_source_ts_is_utc_aware(self) -> Self:
        ts = self.source_simulation_ts
        if ts is None:
            return self
        if ts.tzinfo is None:
            msg = (
                'SimReportArtifacts.source_simulation_ts должен быть '
                'timezone-aware (UTC).'
            )
            raise ValueError(msg)
        if ts.utcoffset() != UTC.utcoffset(None):
            msg = (
                f'SimReportArtifacts.source_simulation_ts должен быть в UTC; '
                f'получен offset {ts.utcoffset()}.'
            )
            raise ValueError(msg)
        return self


class PublicationBundle(BaseModel):
    """
    Главная aggregate публикационного workflow.

    Один из `schematic` / `sim_report` обязателен (commands
    вызываются раздельно); допустим и совмещённый случай (когда
    Vladimir вызывает обе подряд и сшивает результат вручную —
    но domain не делает merge автоматически, см. spec N-2).
    """

    model_config = ConfigDict(frozen=True)

    project: str = Field(min_length=1)
    timestamp: datetime
    efactory_version: str = Field(min_length=1)
    lang: PublicationLang
    schematic: SchematicPublicationArtifacts | None
    sim_report: SimReportArtifacts | None

    @model_validator(mode='after')
    def _check_timestamp_is_utc_aware(self) -> Self:
        if self.timestamp.tzinfo is None:
            msg = 'PublicationBundle.timestamp должен быть timezone-aware (UTC).'
            raise ValueError(msg)
        if self.timestamp.utcoffset() != UTC.utcoffset(None):
            msg = (
                f'PublicationBundle.timestamp должен быть в UTC; '
                f'получен offset {self.timestamp.utcoffset()}.'
            )
            raise ValueError(msg)
        return self

    @model_validator(mode='after')
    def _check_at_least_one_artifact(self) -> Self:
        if self.schematic is None and self.sim_report is None:
            msg = (
                'PublicationBundle: должен быть задан хотя бы один из '
                'schematic / sim_report (иначе bundle пуст).'
            )
            raise ValueError(msg)
        return self


class MeasurementSummary(BaseModel):
    """
    Одна метрика для секции 'Сводка измерений' sim-report (T035 Phase 2.3+).

    `name` — машинно-читаемый ключ (например, `gain_v_per_v`); `description`
    — человекочитаемое имя для презентации; `unit` — SI-обозначение либо
    пустая строка для безразмерных. `value` — числовое значение метрики.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    value: float
    unit: str = ''
    description: str = ''


class ParametricSweepPoint(BaseModel):
    """
    Один (parameters, values) ряд parametric-sweep'а (T035 Phase 2.3+).

    Domain-уровневая замена `application.bridge_sweep.SweepRun` для
    публикационного отчёта: без `error` и `result` полей (caller
    заранее отфильтровывает failed combinations).
    """

    model_config = ConfigDict(frozen=True)

    parameters: dict[str, str] = Field(min_length=1)
    values: dict[str, float] = Field(min_length=1)


class ParametricSweepSection(BaseModel):
    """
    Одна parametric-sweep секция в publication-report (T035 Phase 2.3+).

    `name` — короткое описание свипа (например, 'gain vs R1');
    `x_param`/`y_field` — ключи для оси X / Y из `rows`;
    `group_by` — optional ключ для multi-line plot.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    x_param: str = Field(min_length=1)
    y_field: str = Field(min_length=1)
    group_by: str | None = None
    rows: tuple[ParametricSweepPoint, ...] = Field(min_length=1)


class SimulationResultsBundle(BaseModel):
    """
    Гетерогенный набор данных для одного `report.md` (T035 Phase 2.3+).

    Все аналитические поля optional — пустые секции опускаются в
    отчёте (FR §3 «МОЖЕТ генерировать пустые секции»).
    `tran_signals` / `ac_signals` — список trace-имён для рендера
    (caller сам решает, какие сигналы показать; пустой list →
    секция отсутствует).

    M-thin режим: `magnetics_summary_path` — путь к T113 summary JSON.
    Writer делает graceful skip если путь None / файл отсутствует /
    JSON не парсится (T189 BACKLOG addresses persistence).
    """

    model_config = ConfigDict(frozen=True)

    project: str = Field(min_length=1)
    efactory_version: str = Field(min_length=1)
    publication_timestamp: datetime
    source_simulation_timestamp: datetime | None = None

    tran: TimeSeries | None = None
    tran_signals: tuple[str, ...] = ()

    ac_sweep: AcSweep | None = None
    ac_signals: tuple[str, ...] = ()

    dc_sweep: DcSweep | None = None
    dc_signals: tuple[str, ...] = ()

    parametric_sweeps: tuple[ParametricSweepSection, ...] = ()

    magnetics_summary_path: Path | None = None

    measurements: tuple[MeasurementSummary, ...] = ()

    @model_validator(mode='after')
    def _check_publication_ts_is_utc_aware(self) -> Self:
        ts = self.publication_timestamp
        if ts.tzinfo is None:
            msg = (
                'SimulationResultsBundle.publication_timestamp должен быть '
                'timezone-aware (UTC).'
            )
            raise ValueError(msg)
        if ts.utcoffset() != UTC.utcoffset(None):
            msg = (
                f'SimulationResultsBundle.publication_timestamp должен быть в '
                f'UTC; получен offset {ts.utcoffset()}.'
            )
            raise ValueError(msg)
        return self

    @model_validator(mode='after')
    def _check_source_simulation_ts_is_utc_aware(self) -> Self:
        ts = self.source_simulation_timestamp
        if ts is None:
            return self
        if ts.tzinfo is None:
            msg = (
                'SimulationResultsBundle.source_simulation_timestamp должен '
                'быть timezone-aware (UTC).'
            )
            raise ValueError(msg)
        if ts.utcoffset() != UTC.utcoffset(None):
            msg = (
                f'SimulationResultsBundle.source_simulation_timestamp должен '
                f'быть в UTC; получен offset {ts.utcoffset()}.'
            )
            raise ValueError(msg)
        return self

    @model_validator(mode='after')
    def _check_signals_have_backing_analysis(self) -> Self:
        if self.tran_signals and self.tran is None:
            msg = (
                'SimulationResultsBundle: tran_signals задан '
                f'({list(self.tran_signals)!r}), но tran=None.'
            )
            raise ValueError(msg)
        if self.ac_signals and self.ac_sweep is None:
            msg = (
                'SimulationResultsBundle: ac_signals задан '
                f'({list(self.ac_signals)!r}), но ac_sweep=None.'
            )
            raise ValueError(msg)
        if self.dc_signals and self.dc_sweep is None:
            msg = (
                'SimulationResultsBundle: dc_signals задан '
                f'({list(self.dc_signals)!r}), но dc_sweep=None.'
            )
            raise ValueError(msg)
        return self


_TS_FORMAT = '%Y%m%dT%H%M%SZ'


def publication_timestamp_dirname(timestamp: datetime) -> str:
    """
    Format UTC timestamp в имя `<ts>`-каталога публикации.

    Consistent с T025 (`KicadCliSchematicRenderer._TS_FORMAT`):
    `YYYYMMDDTHHMMSSZ`. Чистая функция без IO; collision-resolution
    с проверкой existence — в use case layer (Phase 3).

    Args:
        timestamp: UTC-aware datetime (отвергает naive и не-UTC).

    Returns:
        Строка имени каталога, например `'20260605T184530Z'`.

    Raises:
        ValueError: timestamp не timezone-aware либо tz не UTC.

    """
    if timestamp.tzinfo is None:
        msg = 'publication_timestamp_dirname: timestamp должен быть timezone-aware.'
        raise ValueError(msg)
    if timestamp.utcoffset() != UTC.utcoffset(None):
        msg = (
            f'publication_timestamp_dirname: timestamp должен быть в UTC; '
            f'получен offset {timestamp.utcoffset()}.'
        )
        raise ValueError(msg)
    return timestamp.strftime(_TS_FORMAT)


__all__ = [
    'MeasurementSummary',
    'MultiSheetMode',
    'ParametricSweepPoint',
    'ParametricSweepSection',
    'PublicationBundle',
    'PublicationLang',
    'SchematicPublicationArtifacts',
    'SheetArtifactSet',
    'SimReportArtifacts',
    'SimulationResultsBundle',
    'publication_timestamp_dirname',
]
