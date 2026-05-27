"""SweepConfig: validators metric/analysis compatibility (T022 Phase A, A1)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from application.bridge_sweep import SweepConfig

# ────────── 5 строго совместимых пар (Analyze A1) ──────────


def test_op_op_pair_valid() -> None:
    cfg = SweepConfig(metric='op', analysis='op')
    assert cfg.metric == 'op'
    assert cfg.analysis == 'op'


def test_gain_small_ac_pair_valid() -> None:
    cfg = SweepConfig(
        metric='gain', mode='small', analysis='ac', frequency_hz=1000.0,
    )
    assert cfg.metric == 'gain'
    assert cfg.mode == 'small'
    assert cfg.analysis == 'ac'


def test_gain_large_tran_pair_valid() -> None:
    cfg = SweepConfig(
        metric='gain', mode='large', analysis='tran',
        frequency_hz=1000.0, v_in_peak=0.1,
    )
    assert cfg.metric == 'gain'
    assert cfg.mode == 'large'
    assert cfg.analysis == 'tran'


def test_bandwidth_ac_pair_valid() -> None:
    cfg = SweepConfig(
        metric='bandwidth', analysis='ac', f_low_hz=20.0, f_high_hz=20000.0,
    )
    assert cfg.metric == 'bandwidth'
    assert cfg.analysis == 'ac'


def test_thd_tran_pair_valid() -> None:
    cfg = SweepConfig(
        metric='thd', analysis='tran', frequency_hz=1000.0, v_in_peak=0.1,
    )
    assert cfg.metric == 'thd'
    assert cfg.analysis == 'tran'


# ────────── auto-mapping --analysis из --metric ──────────


def test_metric_op_defaults_analysis_op() -> None:
    cfg = SweepConfig(metric='op')
    assert cfg.analysis == 'op'


def test_metric_gain_small_defaults_analysis_ac() -> None:
    cfg = SweepConfig(metric='gain', mode='small', frequency_hz=1000.0)
    assert cfg.analysis == 'ac'


def test_metric_gain_large_defaults_analysis_tran() -> None:
    cfg = SweepConfig(
        metric='gain', mode='large', frequency_hz=1000.0, v_in_peak=0.1,
    )
    assert cfg.analysis == 'tran'


def test_metric_bandwidth_defaults_analysis_ac() -> None:
    cfg = SweepConfig(metric='bandwidth', f_low_hz=20.0, f_high_hz=20000.0)
    assert cfg.analysis == 'ac'


def test_metric_thd_defaults_analysis_tran() -> None:
    cfg = SweepConfig(metric='thd', frequency_hz=1000.0, v_in_peak=0.1)
    assert cfg.analysis == 'tran'


# ────────── incompatible combinations (Analyze A1) ──────────


@pytest.mark.parametrize(
    ('metric', 'analysis', 'mode'),
    [
        ('op', 'tran', None),
        ('op', 'ac', None),
        ('gain', 'op', 'small'),
        ('gain', 'tran', 'small'),  # small + tran — wrong
        ('gain', 'ac', 'large'),    # large + ac — wrong
        ('gain', 'op', 'large'),
        ('bandwidth', 'tran', None),
        ('bandwidth', 'op', None),
        ('thd', 'ac', None),
        ('thd', 'op', None),
    ],
)
def test_incompatible_pair_rejected(
    metric: str, analysis: str, mode: str | None,
) -> None:
    kwargs: dict[str, object] = {
        'metric': metric, 'analysis': analysis,
    }
    if mode is not None:
        kwargs['mode'] = mode
    if metric in ('gain', 'thd'):
        kwargs['frequency_hz'] = 1000.0
    if metric == 'gain' and mode == 'large':
        kwargs['v_in_peak'] = 0.1
    if metric == 'thd':
        kwargs['v_in_peak'] = 0.1
    if metric == 'bandwidth':
        kwargs['f_low_hz'] = 20.0
        kwargs['f_high_hz'] = 20000.0

    with pytest.raises(ValidationError, match='incompatible'):
        SweepConfig(**kwargs)  # type: ignore[arg-type]


# ────────── required-fields per metric ──────────


def test_gain_requires_frequency_hz() -> None:
    with pytest.raises(ValidationError, match='frequency_hz'):
        SweepConfig(metric='gain', mode='small')


def test_thd_requires_frequency_hz() -> None:
    with pytest.raises(ValidationError, match='frequency_hz'):
        SweepConfig(metric='thd', v_in_peak=0.1)


def test_thd_requires_v_in_peak() -> None:
    with pytest.raises(ValidationError, match='v_in_peak'):
        SweepConfig(metric='thd', frequency_hz=1000.0)


def test_gain_large_requires_v_in_peak() -> None:
    with pytest.raises(ValidationError, match='v_in_peak'):
        SweepConfig(metric='gain', mode='large', frequency_hz=1000.0)


def test_gain_small_does_not_require_v_in_peak() -> None:
    cfg = SweepConfig(metric='gain', mode='small', frequency_hz=1000.0)
    assert cfg.v_in_peak is None


def test_bandwidth_defaults_f_low_f_high() -> None:
    """FR: --f-low default 1, --f-high default 1e6."""
    cfg = SweepConfig(metric='bandwidth')
    assert cfg.f_low_hz == pytest.approx(1.0)
    assert cfg.f_high_hz == pytest.approx(1e6)


# ────────── mode default + validation ──────────


def test_gain_mode_defaults_small() -> None:
    cfg = SweepConfig(metric='gain', frequency_hz=1000.0)
    assert cfg.mode == 'small'


def test_invalid_metric_rejected() -> None:
    with pytest.raises(ValidationError):
        SweepConfig(metric='unknown')  # type: ignore[arg-type]


def test_invalid_analysis_rejected() -> None:
    with pytest.raises(ValidationError):
        SweepConfig(metric='op', analysis='four')  # type: ignore[arg-type]
