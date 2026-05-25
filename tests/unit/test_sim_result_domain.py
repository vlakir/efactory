"""Unit tests для domain VO `SimResult` (T016 Phase B)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from domain.sim_results import (
    SIM_RESULTS_SCHEMA_VERSION,
    AnalysisType,
    SimResult,
)


def _minimal_kwargs() -> dict[str, object]:
    return {
        'timestamp': '2026-05-25T14:30:00Z',
        'analysis_type': AnalysisType.TRAN,
        'source_file': 'amp.cir',
        'tool': 'ngspice',
        'duration_seconds': 1.5,
        'summary': 'transient analysis 0..10 ms',
    }


def test_minimal_sim_result_validates() -> None:
    result = SimResult(**_minimal_kwargs())  # type: ignore[arg-type]
    assert result.schema_version == SIM_RESULTS_SCHEMA_VERSION
    assert result.tool == 'ngspice'
    assert result.metrics is None
    assert result.artefacts == ()
    assert result.tool_version is None


def test_summary_required() -> None:
    kwargs = _minimal_kwargs()
    del kwargs['summary']
    with pytest.raises(ValidationError):
        SimResult(**kwargs)  # type: ignore[arg-type]


def test_duration_must_be_non_negative() -> None:
    kwargs = {**_minimal_kwargs(), 'duration_seconds': -0.1}
    with pytest.raises(ValidationError):
        SimResult(**kwargs)  # type: ignore[arg-type]


def test_metrics_optional_dict() -> None:
    kwargs = {**_minimal_kwargs(), 'metrics': {'gain_db': 24.5, 'thd_percent': 9.6}}
    result = SimResult(**kwargs)  # type: ignore[arg-type]
    assert result.metrics == {'gain_db': 24.5, 'thd_percent': 9.6}


def test_artefacts_as_tuple() -> None:
    kwargs = {**_minimal_kwargs(), 'artefacts': ['tran.log', 'tran.raw']}
    result = SimResult(**kwargs)  # type: ignore[arg-type]
    assert result.artefacts == ('tran.log', 'tran.raw')


def test_frozen_cannot_mutate() -> None:
    result = SimResult(**_minimal_kwargs())  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        result.tool = 'getdp'  # type: ignore[misc]


def test_extra_fields_forbidden() -> None:
    kwargs = {**_minimal_kwargs(), 'unknown_field': 42}
    with pytest.raises(ValidationError):
        SimResult(**kwargs)  # type: ignore[arg-type]


def test_analysis_type_accepts_string_value() -> None:
    kwargs = {**_minimal_kwargs(), 'analysis_type': 'thd'}
    result = SimResult(**kwargs)  # type: ignore[arg-type]
    assert result.analysis_type is AnalysisType.THD


def test_analysis_type_rejects_unknown() -> None:
    kwargs = {**_minimal_kwargs(), 'analysis_type': 'nuclear-fusion'}
    with pytest.raises(ValidationError):
        SimResult(**kwargs)  # type: ignore[arg-type]


def test_schema_version_fixed_to_1() -> None:
    kwargs = {**_minimal_kwargs(), 'schema_version': 2}
    with pytest.raises(ValidationError):
        SimResult(**kwargs)  # type: ignore[arg-type]


def test_known_analysis_types_present() -> None:
    expected = {
        'tran',
        'ac',
        'dc',
        'op',
        'four',
        'thd',
        'fem_field',
        'leakage',
        'bracket_sheet_metal',
        'other',
    }
    actual = {t.value for t in AnalysisType}
    assert expected.issubset(actual)
