"""
SimReportWriter — outbound port для publication-grade sim-report (T035 Phase 2.3).

Записывает `report.md` + `plots/*.png` (300 DPI publication-grade,
из `cli/publication_plots.py`) + optional `tables/*.md` в `out_dir`.
Возвращает frozen `SimReportArtifacts` (Phase 1 VO) с путями.

Localization (`lang`) применяется к секциям report.md и подписям
графиков (передаётся в render-функции).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from domain.publication import (
        PublicationLang,
        SimReportArtifacts,
        SimulationResultsBundle,
    )


class SimReportWriteError(Exception):
    """SimReportWriter не смог сгенерировать report.md / plots."""


class SimReportWriter(Protocol):
    """Publication-grade sim-report writer (T035 Phase 2.3)."""

    async def write(
        self,
        sim_results: SimulationResultsBundle,
        *,
        out_dir: Path,
        lang: PublicationLang,
    ) -> SimReportArtifacts:
        """
        Generate sim-report под `out_dir`.

        Создаёт `out_dir/report.md`, `out_dir/plots/*.png` (300 DPI
        publication-grade). Optional `out_dir/tables/*.md`.

        Magnetics M-thin (FR §3): если `sim_results.magnetics_summary_path`
        задан и файл валиден — секция включается; иначе skip с явным
        notice в report.md (T189 BACKLOG addresses persistence).

        Возвращает `SimReportArtifacts` с путями (frozen).

        Raises:
            SimReportWriteError: writer не смог создать report.md / plots
                (например, IO error либо invalid signal name в
                `tran_signals` / `ac_signals`).

        """
        ...


__all__ = ['SimReportWriteError', 'SimReportWriter']
