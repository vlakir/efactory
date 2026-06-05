"""Domain VOs для публикационного workflow (T035 Phase 1)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from domain.publication import (
    MeasurementSummary,
    MultiSheetMode,
    ParametricSweepPoint,
    ParametricSweepSection,
    PublicationBundle,
    PublicationLang,
    SchematicPublicationArtifacts,
    SheetArtifactSet,
    SimReportArtifacts,
    SimulationResultsBundle,
    publication_timestamp_dirname,
)
from domain.simulation import AcSweep, TimeSeries


# ────────────────────── enums ──────────────────────


def test_publication_lang_enum_values() -> None:
    assert PublicationLang.RU.value == 'ru'
    assert PublicationLang.EN.value == 'en'
    assert PublicationLang('ru') is PublicationLang.RU
    assert PublicationLang('en') is PublicationLang.EN


def test_publication_lang_is_str_enum() -> None:
    assert isinstance(PublicationLang.RU, str)
    assert PublicationLang.RU == 'ru'


def test_multi_sheet_mode_enum_values() -> None:
    assert MultiSheetMode.PER_SHEET.value == 'per-sheet'
    assert MultiSheetMode.COMBINED.value == 'combined'
    assert MultiSheetMode('per-sheet') is MultiSheetMode.PER_SHEET
    assert MultiSheetMode('combined') is MultiSheetMode.COMBINED


# ────────────────────── SheetArtifactSet ──────────────────────


def _sheet_set(name: str = 'main') -> SheetArtifactSet:
    return SheetArtifactSet(
        sheet_name=name,
        svg=Path(f'/tmp/{name}.svg'),
        pdf=Path(f'/tmp/{name}.pdf'),
        png=Path(f'/tmp/{name}.png'),
    )


def test_sheet_artifact_set_construction() -> None:
    s = _sheet_set('root')
    assert s.sheet_name == 'root'
    assert s.svg == Path('/tmp/root.svg')
    assert s.pdf == Path('/tmp/root.pdf')
    assert s.png == Path('/tmp/root.png')


def test_sheet_artifact_set_rejects_empty_sheet_name() -> None:
    with pytest.raises(ValidationError):
        SheetArtifactSet(
            sheet_name='',
            svg=Path('/tmp/x.svg'),
            pdf=Path('/tmp/x.pdf'),
            png=Path('/tmp/x.png'),
        )


def test_sheet_artifact_set_is_frozen() -> None:
    s = _sheet_set()
    with pytest.raises(ValidationError):
        s.sheet_name = 'other'  # type: ignore[misc]


# ────────────────────── SchematicPublicationArtifacts ──────────────────────


def test_schematic_artifacts_per_sheet_only() -> None:
    color = (_sheet_set('root'),)
    bw = (_sheet_set('root'),)
    art = SchematicPublicationArtifacts(
        color_per_sheet=color,
        bw_per_sheet=bw,
        color_combined=None,
        bw_combined=None,
    )
    assert art.color_per_sheet == color
    assert art.bw_per_sheet == bw
    assert art.color_combined is None
    assert art.bw_combined is None


def test_schematic_artifacts_with_combined() -> None:
    color = (_sheet_set('root'),)
    bw = (_sheet_set('root'),)
    art = SchematicPublicationArtifacts(
        color_per_sheet=color,
        bw_per_sheet=bw,
        color_combined=Path('/tmp/all-color.pdf'),
        bw_combined=Path('/tmp/all-bw.pdf'),
    )
    assert art.color_combined == Path('/tmp/all-color.pdf')
    assert art.bw_combined == Path('/tmp/all-bw.pdf')


def test_schematic_artifacts_rejects_empty_color_per_sheet() -> None:
    with pytest.raises(ValidationError):
        SchematicPublicationArtifacts(
            color_per_sheet=(),
            bw_per_sheet=(_sheet_set('root'),),
            color_combined=None,
            bw_combined=None,
        )


def test_schematic_artifacts_rejects_empty_bw_per_sheet() -> None:
    with pytest.raises(ValidationError):
        SchematicPublicationArtifacts(
            color_per_sheet=(_sheet_set('root'),),
            bw_per_sheet=(),
            color_combined=None,
            bw_combined=None,
        )


def test_schematic_artifacts_rejects_per_sheet_length_mismatch() -> None:
    with pytest.raises(ValidationError):
        SchematicPublicationArtifacts(
            color_per_sheet=(_sheet_set('a'), _sheet_set('b')),
            bw_per_sheet=(_sheet_set('a'),),
            color_combined=None,
            bw_combined=None,
        )


def test_schematic_artifacts_rejects_color_combined_without_bw_combined() -> None:
    with pytest.raises(ValidationError):
        SchematicPublicationArtifacts(
            color_per_sheet=(_sheet_set('root'),),
            bw_per_sheet=(_sheet_set('root'),),
            color_combined=Path('/tmp/all.pdf'),
            bw_combined=None,
        )


def test_schematic_artifacts_rejects_bw_combined_without_color_combined() -> None:
    with pytest.raises(ValidationError):
        SchematicPublicationArtifacts(
            color_per_sheet=(_sheet_set('root'),),
            bw_per_sheet=(_sheet_set('root'),),
            color_combined=None,
            bw_combined=Path('/tmp/all.pdf'),
        )


def test_schematic_artifacts_is_frozen() -> None:
    art = SchematicPublicationArtifacts(
        color_per_sheet=(_sheet_set('root'),),
        bw_per_sheet=(_sheet_set('root'),),
        color_combined=None,
        bw_combined=None,
    )
    with pytest.raises(ValidationError):
        art.color_combined = Path('/tmp/x.pdf')  # type: ignore[misc]


# ────────────────────── SimReportArtifacts ──────────────────────


def test_sim_report_artifacts_minimum() -> None:
    r = SimReportArtifacts(
        report_md=Path('/tmp/report.md'),
        plots=(),
        tables=(),
        source_simulation_ts=None,
    )
    assert r.report_md == Path('/tmp/report.md')
    assert r.plots == ()
    assert r.tables == ()
    assert r.source_simulation_ts is None


def test_sim_report_artifacts_with_plots_and_tables() -> None:
    r = SimReportArtifacts(
        report_md=Path('/tmp/report.md'),
        plots=(Path('/tmp/plots/tran.png'), Path('/tmp/plots/ac.png')),
        tables=(Path('/tmp/tables/summary.md'),),
        source_simulation_ts=datetime(2026, 6, 5, 12, 30, tzinfo=UTC),
    )
    assert len(r.plots) == 2
    assert len(r.tables) == 1
    assert r.source_simulation_ts is not None
    assert r.source_simulation_ts.tzinfo is UTC


def test_sim_report_artifacts_rejects_naive_source_ts() -> None:
    with pytest.raises(ValidationError):
        SimReportArtifacts(
            report_md=Path('/tmp/report.md'),
            plots=(),
            tables=(),
            source_simulation_ts=datetime(2026, 6, 5, 12, 30),  # noqa: DTZ001
        )


def test_sim_report_artifacts_rejects_non_utc_source_ts() -> None:
    moscow = timezone(timedelta(hours=3))
    with pytest.raises(ValidationError):
        SimReportArtifacts(
            report_md=Path('/tmp/report.md'),
            plots=(),
            tables=(),
            source_simulation_ts=datetime(2026, 6, 5, 12, 30, tzinfo=moscow),
        )


def test_sim_report_artifacts_is_frozen() -> None:
    r = SimReportArtifacts(
        report_md=Path('/tmp/report.md'),
        plots=(),
        tables=(),
        source_simulation_ts=None,
    )
    with pytest.raises(ValidationError):
        r.report_md = Path('/tmp/other.md')  # type: ignore[misc]


# ────────────────────── PublicationBundle ──────────────────────


def _schematic_art() -> SchematicPublicationArtifacts:
    return SchematicPublicationArtifacts(
        color_per_sheet=(_sheet_set('root'),),
        bw_per_sheet=(_sheet_set('root'),),
        color_combined=None,
        bw_combined=None,
    )


def _sim_report_art() -> SimReportArtifacts:
    return SimReportArtifacts(
        report_md=Path('/tmp/report.md'),
        plots=(),
        tables=(),
        source_simulation_ts=None,
    )


def _bundle(**overrides: object) -> PublicationBundle:
    defaults: dict[str, object] = {
        'project': 'se-amp',
        'timestamp': datetime(2026, 6, 5, 18, 45, tzinfo=UTC),
        'efactory_version': '0.1.0',
        'lang': PublicationLang.RU,
        'schematic': _schematic_art(),
        'sim_report': None,
    }
    defaults.update(overrides)
    return PublicationBundle(**defaults)  # type: ignore[arg-type]


def test_publication_bundle_with_schematic_only() -> None:
    b = _bundle()
    assert b.project == 'se-amp'
    assert b.lang is PublicationLang.RU
    assert b.schematic is not None
    assert b.sim_report is None


def test_publication_bundle_with_sim_report_only() -> None:
    b = _bundle(schematic=None, sim_report=_sim_report_art())
    assert b.schematic is None
    assert b.sim_report is not None


def test_publication_bundle_with_both() -> None:
    b = _bundle(sim_report=_sim_report_art())
    assert b.schematic is not None
    assert b.sim_report is not None


def test_publication_bundle_rejects_no_artifacts() -> None:
    with pytest.raises(ValidationError):
        _bundle(schematic=None, sim_report=None)


def test_publication_bundle_rejects_empty_project_slug() -> None:
    with pytest.raises(ValidationError):
        _bundle(project='')


def test_publication_bundle_rejects_empty_version() -> None:
    with pytest.raises(ValidationError):
        _bundle(efactory_version='')


def test_publication_bundle_rejects_naive_timestamp() -> None:
    with pytest.raises(ValidationError):
        _bundle(timestamp=datetime(2026, 6, 5, 18, 45))  # noqa: DTZ001


def test_publication_bundle_rejects_non_utc_timestamp() -> None:
    moscow = timezone(timedelta(hours=3))
    with pytest.raises(ValidationError):
        _bundle(timestamp=datetime(2026, 6, 5, 18, 45, tzinfo=moscow))


def test_publication_bundle_lang_en() -> None:
    b = _bundle(lang=PublicationLang.EN)
    assert b.lang is PublicationLang.EN


def test_publication_bundle_is_frozen() -> None:
    b = _bundle()
    with pytest.raises(ValidationError):
        b.project = 'other'  # type: ignore[misc]


# ────────────────────── publication_timestamp_dirname ──────────────────────


def test_publication_timestamp_dirname_format() -> None:
    dt = datetime(2026, 6, 5, 18, 45, 30, tzinfo=UTC)
    assert publication_timestamp_dirname(dt) == '20260605T184530Z'


def test_publication_timestamp_dirname_pads_zero() -> None:
    dt = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    assert publication_timestamp_dirname(dt) == '20260102T030405Z'


def test_publication_timestamp_dirname_rejects_naive() -> None:
    with pytest.raises(ValueError, match='timezone-aware'):
        publication_timestamp_dirname(datetime(2026, 6, 5, 18, 45))  # noqa: DTZ001


def test_publication_timestamp_dirname_rejects_non_utc() -> None:
    moscow = timezone(timedelta(hours=3))
    with pytest.raises(ValueError, match='UTC'):
        publication_timestamp_dirname(datetime(2026, 6, 5, 18, 45, tzinfo=moscow))


# ────────────────────── MeasurementSummary ──────────────────────


def test_measurement_summary_minimum_fields() -> None:
    m = MeasurementSummary(name='gain_v_per_v', value=12.5)
    assert m.unit == ''
    assert m.description == ''


def test_measurement_summary_full_fields() -> None:
    m = MeasurementSummary(
        name='bandwidth_3db_hz', value=24000.0, unit='Hz', description='-3 dB полоса',
    )
    assert m.unit == 'Hz'
    assert m.description == '-3 dB полоса'


def test_measurement_summary_is_frozen() -> None:
    m = MeasurementSummary(name='x', value=1.0)
    with pytest.raises(ValidationError):
        m.value = 2.0  # type: ignore[misc]


def test_measurement_summary_rejects_empty_name() -> None:
    with pytest.raises(ValidationError):
        MeasurementSummary(name='', value=1.0)


# ────────────────────── ParametricSweepPoint ──────────────────────


def test_parametric_sweep_point_valid() -> None:
    p = ParametricSweepPoint(
        parameters={'R1': '1k'},
        values={'gain_v_per_v': 10.0},
    )
    assert p.parameters == {'R1': '1k'}
    assert p.values == {'gain_v_per_v': 10.0}


def test_parametric_sweep_point_is_frozen() -> None:
    p = ParametricSweepPoint(parameters={'R': '1k'}, values={'g': 1.0})
    with pytest.raises(ValidationError):
        p.parameters = {'R': '2k'}  # type: ignore[misc]


def test_parametric_sweep_point_rejects_empty_parameters() -> None:
    with pytest.raises(ValidationError):
        ParametricSweepPoint(parameters={}, values={'g': 1.0})


def test_parametric_sweep_point_rejects_empty_values() -> None:
    with pytest.raises(ValidationError):
        ParametricSweepPoint(parameters={'R': '1k'}, values={})


# ────────────────────── ParametricSweepSection ──────────────────────


def _point(r: str = '1k', g: float = 10.0) -> ParametricSweepPoint:
    return ParametricSweepPoint(parameters={'R1': r}, values={'gain': g})


def test_parametric_sweep_section_valid_single_param() -> None:
    s = ParametricSweepSection(
        name='gain vs R1',
        x_param='R1',
        y_field='gain',
        rows=(_point('1k', 10.0), _point('2k', 12.0)),
    )
    assert s.group_by is None
    assert len(s.rows) == 2


def test_parametric_sweep_section_with_group_by() -> None:
    s = ParametricSweepSection(
        name='gain vs R1 grouped by C1',
        x_param='R1',
        y_field='gain',
        group_by='C1',
        rows=(_point(),),
    )
    assert s.group_by == 'C1'


def test_parametric_sweep_section_rejects_empty_rows() -> None:
    with pytest.raises(ValidationError):
        ParametricSweepSection(
            name='x', x_param='X', y_field='Y', rows=(),
        )


def test_parametric_sweep_section_is_frozen() -> None:
    s = ParametricSweepSection(
        name='s', x_param='X', y_field='Y', rows=(_point(),),
    )
    with pytest.raises(ValidationError):
        s.group_by = 'B'  # type: ignore[misc]


# ────────────────────── SimulationResultsBundle ──────────────────────


def _utc(year: int = 2026, month: int = 6, day: int = 5, hour: int = 18) -> datetime:
    return datetime(year, month, day, hour, 0, 0, tzinfo=UTC)


def _ts(*, signal: str = 'v(load)') -> TimeSeries:
    return TimeSeries(time=(0.0, 1e-6, 2e-6), traces={signal: (0.0, 0.5, 1.0)})


def _ac(*, signal: str = 'v(load)') -> AcSweep:
    return AcSweep(
        frequency=(1.0, 10.0, 100.0),
        traces_real={signal: (1.0, 0.95, 0.9)},
        traces_imag={signal: (0.0, 0.0, 0.0)},
    )


def test_bundle_minimum_required_fields() -> None:
    bundle = SimulationResultsBundle(
        project='se-amp',
        efactory_version='0.3.0-dev',
        publication_timestamp=_utc(),
    )
    assert bundle.tran is None
    assert bundle.ac_sweep is None
    assert bundle.parametric_sweeps == ()
    assert bundle.magnetics_summary_path is None
    assert bundle.measurements == ()
    assert bundle.source_simulation_timestamp is None


def test_bundle_with_full_payload() -> None:
    bundle = SimulationResultsBundle(
        project='se-amp',
        efactory_version='0.3.0-dev',
        publication_timestamp=_utc(),
        source_simulation_timestamp=_utc(hour=17),
        tran=_ts(),
        tran_signals=('v(load)',),
        ac_sweep=_ac(),
        ac_signals=('v(load)',),
        parametric_sweeps=(
            ParametricSweepSection(
                name='gain vs R1',
                x_param='R1',
                y_field='gain',
                rows=(_point(),),
            ),
        ),
        magnetics_summary_path=Path('/tmp/se-amp/out/fem/ts/summary.json'),
        measurements=(MeasurementSummary(name='gain', value=12.5),),
    )
    assert bundle.tran is not None
    assert bundle.tran_signals == ('v(load)',)


def test_bundle_is_frozen() -> None:
    bundle = SimulationResultsBundle(
        project='x',
        efactory_version='0.0.1',
        publication_timestamp=_utc(),
    )
    with pytest.raises(ValidationError):
        bundle.project = 'y'  # type: ignore[misc]


def test_bundle_rejects_naive_publication_timestamp() -> None:
    with pytest.raises(ValidationError, match='timezone-aware'):
        SimulationResultsBundle(
            project='x',
            efactory_version='0.0.1',
            publication_timestamp=datetime(2026, 6, 5, 18, 0, 0),
        )


def test_bundle_rejects_non_utc_publication_timestamp() -> None:
    moscow = timezone(timedelta(hours=3))
    with pytest.raises(ValidationError, match='UTC'):
        SimulationResultsBundle(
            project='x',
            efactory_version='0.0.1',
            publication_timestamp=datetime(2026, 6, 5, 18, 0, 0, tzinfo=moscow),
        )


def test_bundle_rejects_naive_source_simulation_timestamp() -> None:
    with pytest.raises(ValidationError, match='timezone-aware'):
        SimulationResultsBundle(
            project='x',
            efactory_version='0.0.1',
            publication_timestamp=_utc(),
            source_simulation_timestamp=datetime(2026, 6, 5, 17, 0, 0),
        )


def test_bundle_rejects_tran_signals_without_tran() -> None:
    with pytest.raises(ValidationError, match='tran_signals'):
        SimulationResultsBundle(
            project='x',
            efactory_version='0.0.1',
            publication_timestamp=_utc(),
            tran_signals=('v(load)',),
        )


def test_bundle_rejects_ac_signals_without_ac_sweep() -> None:
    with pytest.raises(ValidationError, match='ac_signals'):
        SimulationResultsBundle(
            project='x',
            efactory_version='0.0.1',
            publication_timestamp=_utc(),
            ac_signals=('v(load)',),
        )


def test_bundle_accepts_tran_without_signals_empty_tran_section() -> None:
    """tran present + tran_signals=() — валидно, секция отсутствует в report."""
    bundle = SimulationResultsBundle(
        project='x',
        efactory_version='0.0.1',
        publication_timestamp=_utc(),
        tran=_ts(),
    )
    assert bundle.tran is not None
    assert bundle.tran_signals == ()
