"""Domain: AnalysisSpec discriminated union (T008)."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from domain.simulation import (
    AcAnalysis,
    AnalysisSpec,
    OpAnalysis,
    TranAnalysis,
)

_ADAPTER: TypeAdapter[AnalysisSpec] = TypeAdapter(AnalysisSpec)


def test_op_analysis_default_construction() -> None:
    op = OpAnalysis()
    assert op.type == 'op'


def test_op_analysis_is_frozen() -> None:
    op = OpAnalysis()
    with pytest.raises(ValidationError):
        op.type = 'tran'  # type: ignore[misc,assignment]


def test_tran_analysis_construction() -> None:
    tran = TranAnalysis(t_step=1e-5, t_stop=20e-3)
    assert tran.type == 'tran'
    assert tran.t_step == pytest.approx(1e-5)
    assert tran.t_stop == pytest.approx(20e-3)
    assert tran.t_start == 0.0
    assert tran.uic is False


def test_tran_analysis_with_t_start_and_uic() -> None:
    tran = TranAnalysis(t_step=1e-5, t_stop=20e-3, t_start=1e-3, uic=True)
    assert tran.t_start == pytest.approx(1e-3)
    assert tran.uic is True


def test_tran_analysis_t_stop_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        TranAnalysis(t_step=1e-5, t_stop=0.0)


def test_tran_analysis_t_step_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        TranAnalysis(t_step=0.0, t_stop=1e-3)


def test_tran_analysis_t_stop_greater_than_t_start() -> None:
    with pytest.raises(ValidationError):
        TranAnalysis(t_step=1e-5, t_stop=1e-3, t_start=2e-3)


def test_tran_analysis_is_frozen() -> None:
    tran = TranAnalysis(t_step=1e-5, t_stop=1e-3)
    with pytest.raises(ValidationError):
        tran.t_stop = 2e-3  # type: ignore[misc]


def test_ac_analysis_construction_defaults_to_dec_sweep() -> None:
    ac = AcAnalysis(n_points=20, f_start=1.0, f_stop=1e6)
    assert ac.type == 'ac'
    assert ac.sweep == 'dec'
    assert ac.n_points == 20
    assert ac.f_start == pytest.approx(1.0)
    assert ac.f_stop == pytest.approx(1e6)


def test_ac_analysis_with_explicit_sweep_lin() -> None:
    ac = AcAnalysis(sweep='lin', n_points=100, f_start=1.0, f_stop=1000.0)
    assert ac.sweep == 'lin'


def test_ac_analysis_with_oct_sweep() -> None:
    ac = AcAnalysis(sweep='oct', n_points=10, f_start=1.0, f_stop=1000.0)
    assert ac.sweep == 'oct'


def test_ac_analysis_rejects_unknown_sweep_kind() -> None:
    with pytest.raises(ValidationError):
        AcAnalysis(
            sweep='quadratic',  # type: ignore[arg-type]
            n_points=10,
            f_start=1.0,
            f_stop=1000.0,
        )


def test_ac_analysis_n_points_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        AcAnalysis(n_points=0, f_start=1.0, f_stop=1e3)


def test_ac_analysis_f_start_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        AcAnalysis(n_points=10, f_start=0.0, f_stop=1e3)


def test_ac_analysis_f_stop_greater_than_f_start() -> None:
    with pytest.raises(ValidationError):
        AcAnalysis(n_points=10, f_start=1e3, f_stop=1.0)


def test_ac_analysis_is_frozen() -> None:
    ac = AcAnalysis(n_points=10, f_start=1.0, f_stop=1e3)
    with pytest.raises(ValidationError):
        ac.n_points = 20  # type: ignore[misc]


def test_discriminator_parses_op() -> None:
    parsed = _ADAPTER.validate_python({'type': 'op'})
    assert isinstance(parsed, OpAnalysis)


def test_discriminator_parses_tran() -> None:
    parsed = _ADAPTER.validate_python(
        {'type': 'tran', 't_step': 1e-5, 't_stop': 1e-3},
    )
    assert isinstance(parsed, TranAnalysis)
    assert parsed.t_stop == pytest.approx(1e-3)


def test_discriminator_parses_ac() -> None:
    parsed = _ADAPTER.validate_python(
        {'type': 'ac', 'sweep': 'dec', 'n_points': 20, 'f_start': 1.0, 'f_stop': 1e6},
    )
    assert isinstance(parsed, AcAnalysis)
    assert parsed.sweep == 'dec'


def test_discriminator_rejects_unknown_type() -> None:
    with pytest.raises(ValidationError):
        _ADAPTER.validate_python({'type': 'noise', 'n_points': 10})
