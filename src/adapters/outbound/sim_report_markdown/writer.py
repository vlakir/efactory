"""
MarkdownSimReportWriter — publication-grade sim-report (T035 Phase 2.3).

Layout (FR §3):

    <out_dir>/
      report.md
      plots/
        tran-<signal>.png
        ac-<signal>.png
        param-sweep-<name>.png

Секции `report.md` (опускаются если данных нет):

1. Header + Метаданные (project, дата, версия, источник sim).
2. TRAN — по одному PNG на каждый `tran_signal`.
3. AC sweep — по одному PNG на каждый `ac_signal`.
4. Parametric sweep — по одному PNG на каждый `ParametricSweepSection`.
5. Magnetics M-thin — table из summary JSON либо graceful-skip notice.
6. Measurements summary — table из `MeasurementSummary` tuple.

i18n: dict `_REPORT_LABELS[PublicationLang]` (key/value, 10-15 строк на
язык, A-7).
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from adapters.inbound.cli.publication_plots import (
    render_ac_sweep_publication_png,
    render_dc_sweep_publication_png,
    render_sweep_plot_publication_png,
    render_time_series_publication_png,
)
from application.bridge_sweep import SweepRun
from domain.publication import PublicationLang, SimReportArtifacts
from ports.outbound.sim_report_writer import SimReportWriteError

if TYPE_CHECKING:
    from pathlib import Path

    from domain.publication import (
        ParametricSweepPoint,
        SimulationResultsBundle,
    )
    from domain.simulation import AcSweep, DcSweep, TimeSeries


_REPORT_LABELS: dict[PublicationLang, dict[str, str]] = {
    PublicationLang.RU: {
        'title': 'Отчёт о симуляции',
        'metadata_h2': 'Метаданные',
        'project': 'Проект',
        'publication_date': 'Дата публикации',
        'efactory_version': 'Версия efactory',
        'source_sim_ts': 'Источник симуляции',
        'fresh_run': 'свежий прогон (--rerun)',
        'lang': 'Язык отчёта',
        'tran_h2': 'Анализ переходных процессов (TRAN)',
        'ac_h2': 'Малосигнальный анализ (AC sweep)',
        'dc_h2': 'DC-развёртка (transfer characteristic)',
        'sweep_h2': 'Параметрические свипы',
        'magnetics_h2': 'Магнитные компоненты',
        'magnetics_missing': (
            '*Магнитные артефакты не найдены в `out/fem/`. '
            'Запустите `/mag-verify <project>` для генерации.*'
        ),
        'magnetics_invalid': (
            '*Магнитные артефакты найдены, но формат не распознан '
            '(см. T189 в BACKLOG — persistence T113).*'
        ),
        'measurements_h2': 'Сводка измерений',
        'metric_col': 'Метрика',
        'value_col': 'Значение',
        'unit_col': 'Единица',
        'description_col': 'Описание',
        'l_self_label': 'Индуктивность L_self',
        'b_peak_label': 'B_peak (пиковая индукция)',
        'fem_method_label': 'Метод FEM',
        'analytical_vs_fem_label': 'Аналитика vs FEM',
        'unit_henry': 'Гн',
        'unit_tesla': 'Тл',
        'unit_percent': '%',
        'unit_dimensionless': '—',
    },
    PublicationLang.EN: {
        'title': 'Simulation Report',
        'metadata_h2': 'Metadata',
        'project': 'Project',
        'publication_date': 'Publication date',
        'efactory_version': 'efactory version',
        'source_sim_ts': 'Simulation source',
        'fresh_run': 'fresh run (--rerun)',
        'lang': 'Report language',
        'tran_h2': 'Transient analysis (TRAN)',
        'ac_h2': 'Small-signal analysis (AC sweep)',
        'dc_h2': 'DC sweep (transfer characteristic)',
        'sweep_h2': 'Parametric sweeps',
        'magnetics_h2': 'Magnetic components',
        'magnetics_missing': (
            '*Magnetic artefacts not found in `out/fem/`. '
            'Run `/mag-verify <project>` to generate.*'
        ),
        'magnetics_invalid': (
            '*Magnetic artefacts found, but format not recognized '
            '(see T189 in BACKLOG — T113 persistence).*'
        ),
        'measurements_h2': 'Measurements summary',
        'metric_col': 'Metric',
        'value_col': 'Value',
        'unit_col': 'Unit',
        'description_col': 'Description',
        'l_self_label': 'Self-inductance L',
        'b_peak_label': 'B_peak',
        'fem_method_label': 'FEM method',
        'analytical_vs_fem_label': 'Analytical vs FEM',
        'unit_henry': 'H',
        'unit_tesla': 'T',
        'unit_percent': '%',
        'unit_dimensionless': '—',
    },
}


class MarkdownSimReportWriter:
    """SimReportWriter на Markdown + matplotlib publication-grade plots."""

    async def write(
        self,
        sim_results: SimulationResultsBundle,
        *,
        out_dir: Path,
        lang: PublicationLang,
    ) -> SimReportArtifacts:
        return await asyncio.to_thread(
            self._write_sync,
            sim_results,
            out_dir,
            lang,
        )

    def _write_sync(
        self,
        bundle: SimulationResultsBundle,
        out_dir: Path,
        lang: PublicationLang,
    ) -> SimReportArtifacts:
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            plots_dir = out_dir / 'plots'
            plots_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            msg = f'MarkdownSimReportWriter: cannot create {out_dir}: {exc}'
            raise SimReportWriteError(msg) from exc

        labels = _REPORT_LABELS[lang]
        plot_paths: list[Path] = []
        lines: list[str] = []

        lines.append(f'# {labels["title"]} — {bundle.project}')
        lines.append('')

        lines.extend(_render_metadata(bundle, labels, lang))

        if bundle.tran is not None and bundle.tran_signals:
            lines.extend(
                _render_tran_section(
                    bundle.tran,
                    bundle.tran_signals,
                    plots_dir,
                    out_dir,
                    labels,
                    lang,
                    plot_paths,
                ),
            )

        if bundle.ac_sweep is not None and bundle.ac_signals:
            lines.extend(
                _render_ac_section(
                    bundle.ac_sweep,
                    bundle.ac_signals,
                    plots_dir,
                    out_dir,
                    labels,
                    lang,
                    plot_paths,
                ),
            )

        if bundle.dc_sweep is not None and bundle.dc_signals:
            lines.extend(
                _render_dc_section(
                    bundle.dc_sweep,
                    bundle.dc_signals,
                    plots_dir,
                    out_dir,
                    labels,
                    lang,
                    plot_paths,
                ),
            )

        if bundle.parametric_sweeps:
            lines.extend(
                _render_sweep_section(
                    bundle,
                    plots_dir,
                    out_dir,
                    labels,
                    lang,
                    plot_paths,
                ),
            )

        lines.extend(
            _render_magnetics_section(
                bundle.magnetics_summary_path,
                labels,
            ),
        )

        if bundle.measurements:
            lines.extend(_render_measurements_section(bundle, labels))

        report_md = out_dir / 'report.md'
        try:
            report_md.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        except OSError as exc:
            msg = f'MarkdownSimReportWriter: cannot write {report_md}: {exc}'
            raise SimReportWriteError(msg) from exc

        return SimReportArtifacts(
            report_md=report_md,
            plots=tuple(plot_paths),
            tables=(),
            source_simulation_ts=bundle.source_simulation_timestamp,
        )


def _render_metadata(
    bundle: SimulationResultsBundle,
    labels: dict[str, str],
    lang: PublicationLang,
) -> list[str]:
    lines = [f'## {labels["metadata_h2"]}', '']
    lines.append(f'- **{labels["project"]}:** {bundle.project}')
    lines.append(
        f'- **{labels["publication_date"]}:** '
        f'{bundle.publication_timestamp.isoformat()}',
    )
    lines.append(
        f'- **{labels["efactory_version"]}:** {bundle.efactory_version}',
    )
    source_display = (
        bundle.source_simulation_timestamp.isoformat()
        if bundle.source_simulation_timestamp is not None
        else labels['fresh_run']
    )
    lines.append(f'- **{labels["source_sim_ts"]}:** {source_display}')
    lines.append(f'- **{labels["lang"]}:** {lang.value}')
    lines.append('')
    return lines


def _render_tran_section(
    tran: TimeSeries,
    signals: tuple[str, ...],
    plots_dir: Path,
    out_dir: Path,
    labels: dict[str, str],
    lang: PublicationLang,
    accumulated_plots: list[Path],
) -> list[str]:
    lines = [f'## {labels["tran_h2"]}', '']
    for signal in signals:
        png_path = plots_dir / f'tran-{_safe_filename(signal)}.png'
        render_time_series_publication_png(
            tran,
            signal=signal,
            output=png_path,
            lang=lang,
        )
        accumulated_plots.append(png_path)
        rel = png_path.relative_to(out_dir).as_posix()
        lines.append(f'![{signal}]({rel})')
        lines.append('')
    return lines


def _render_ac_section(
    ac_sweep: AcSweep,
    signals: tuple[str, ...],
    plots_dir: Path,
    out_dir: Path,
    labels: dict[str, str],
    lang: PublicationLang,
    accumulated_plots: list[Path],
) -> list[str]:
    lines = [f'## {labels["ac_h2"]}', '']
    for signal in signals:
        png_path = plots_dir / f'ac-{_safe_filename(signal)}.png'
        render_ac_sweep_publication_png(
            ac_sweep,
            signal=signal,
            output=png_path,
            lang=lang,
        )
        accumulated_plots.append(png_path)
        rel = png_path.relative_to(out_dir).as_posix()
        lines.append(f'![{signal}]({rel})')
        lines.append('')
    return lines


def _render_dc_section(
    dc_sweep: DcSweep,
    signals: tuple[str, ...],
    plots_dir: Path,
    out_dir: Path,
    labels: dict[str, str],
    lang: PublicationLang,
    accumulated_plots: list[Path],
) -> list[str]:
    lines = [f'## {labels["dc_h2"]}', '']
    for signal in signals:
        png_path = plots_dir / f'dc-{_safe_filename(signal)}.png'
        render_dc_sweep_publication_png(
            dc_sweep,
            signal=signal,
            output=png_path,
            lang=lang,
        )
        accumulated_plots.append(png_path)
        rel = png_path.relative_to(out_dir).as_posix()
        lines.append(f'![{signal}]({rel})')
        lines.append('')
    return lines


def _render_sweep_section(
    bundle: SimulationResultsBundle,
    plots_dir: Path,
    out_dir: Path,
    labels: dict[str, str],
    lang: PublicationLang,
    accumulated_plots: list[Path],
) -> list[str]:
    lines = [f'## {labels["sweep_h2"]}', '']
    for section in bundle.parametric_sweeps:
        lines.append(f'### {section.name}')
        lines.append('')
        png_path = plots_dir / f'param-sweep-{_safe_filename(section.name)}.png'
        sweep_runs = [_point_to_sweep_run(p) for p in section.rows]
        render_sweep_plot_publication_png(
            sweep_runs,
            x_param=section.x_param,
            y_field=section.y_field,
            output=png_path,
            lang=lang,
            group_by=section.group_by,
        )
        accumulated_plots.append(png_path)
        rel = png_path.relative_to(out_dir).as_posix()
        lines.append(f'![{section.y_field} vs {section.x_param}]({rel})')
        lines.append('')
    return lines


def _render_magnetics_section(
    summary_path: Path | None,
    labels: dict[str, str],
) -> list[str]:
    lines = [f'## {labels["magnetics_h2"]}', '']
    if summary_path is None or not summary_path.is_file():
        lines.append(labels['magnetics_missing'])
        lines.append('')
        return lines
    try:
        data = json.loads(summary_path.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        lines.append(labels['magnetics_invalid'])
        lines.append('')
        return lines
    if not isinstance(data, dict):
        lines.append(labels['magnetics_invalid'])
        lines.append('')
        return lines

    rows: list[tuple[str, str, str]] = []
    l_fem = data.get('fem_inductance_h')
    if isinstance(l_fem, (int, float)):
        rows.append((labels['l_self_label'], f'{l_fem:.6g}', labels['unit_henry']))
    b_peak = data.get('peak_flux_density_t')
    if isinstance(b_peak, (int, float)):
        rows.append((labels['b_peak_label'], f'{b_peak:.6g}', labels['unit_tesla']))
    fem_method = data.get('fem_method')
    if isinstance(fem_method, str) and fem_method:
        rows.append(
            (labels['fem_method_label'], fem_method, labels['unit_dimensionless'])
        )
    rel_diff = data.get('relative_difference')
    if isinstance(rel_diff, (int, float)):
        rows.append(
            (
                labels['analytical_vs_fem_label'],
                f'{rel_diff * 100.0:.2f}',
                labels['unit_percent'],
            ),
        )

    if not rows:
        lines.append(labels['magnetics_invalid'])
        lines.append('')
        return lines

    lines.append(
        f'| {labels["metric_col"]} | {labels["value_col"]} | {labels["unit_col"]} |',
    )
    lines.append('|---|---|---|')
    for name, value, unit in rows:
        lines.append(f'| {name} | {value} | {unit} |')
    lines.append('')
    return lines


def _render_measurements_section(
    bundle: SimulationResultsBundle,
    labels: dict[str, str],
) -> list[str]:
    lines = [f'## {labels["measurements_h2"]}', '']
    lines.append(
        f'| {labels["metric_col"]} | {labels["value_col"]} | '
        f'{labels["unit_col"]} | {labels["description_col"]} |',
    )
    lines.append('|---|---|---|---|')
    for m in bundle.measurements:
        unit = m.unit or labels['unit_dimensionless']
        desc = m.description or labels['unit_dimensionless']
        lines.append(f'| {m.name} | {m.value:.6g} | {unit} | {desc} |')
    lines.append('')
    return lines


def _safe_filename(name: str) -> str:
    """Sanitize trace/section name for use in filename. `v(load)` → `v_load`."""
    result = []
    for ch in name:
        if ch.isalnum() or ch in '-_':
            result.append(ch)
        else:
            result.append('_')
    cleaned = ''.join(result).strip('_')
    return cleaned or 'unnamed'


def _point_to_sweep_run(point: ParametricSweepPoint) -> SweepRun:
    return SweepRun(
        parameters=dict(point.parameters),
        result=None,
        values=dict(point.values),
        error=None,
    )


__all__ = ['MarkdownSimReportWriter']
