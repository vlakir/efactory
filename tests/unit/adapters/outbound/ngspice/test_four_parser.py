"""Parser ngspice `.four` log → FourierResult (T131 Phase B)."""

from __future__ import annotations

import pytest

from adapters.outbound.ngspice.four_parser import (
    NgspiceFourierParseError,
    parse_four_output,
)

# Канонический ngspice .four output, аналогичный примерам из manual
# (ch. 15.3.4). 10 harmonics — DC (n=0) + 9 actual harmonics 1..9.
_CANNED_LOG_PURE_SINE = """\
ngspice 41 done.

Fourier analysis for v(load):
  No. Harmonics: 10, THD: 0.149782 %, Gridsize: 200, Interpolation Degree: 1

Harmonic  Frequency        Magnitude     Phase       Norm. Mag    Norm. Phase
--------  ---------        ---------     -----       ---------    -----------
0         0                0.0299822     0           0            0
1         1000             1             -0.00149782 1            0
2         2000             0.00149782    180         0.00149782   180
3         3000             0.000998547   -90         0.000998547  -89.99
4         4000             0.000748910   0           0.000748910  0.01
5         5000             0.000599128   -90         0.000599128  -89.99
6         6000             0.000499274   180         0.000499274  180
7         7000             0.000427949   -90         0.000427949  -89.99
8         8000             0.000374454   0           0.000374454  0.01
9         9000             0.000332846   -90         0.000332846  -89.99

"""

_CANNED_LOG_CLIPPED_SINE = """\
Fourier analysis for v(load):
  No. Harmonics: 10, THD: 12.345 %, Gridsize: 200, Interpolation Degree: 1

Harmonic  Frequency        Magnitude     Phase       Norm. Mag    Norm. Phase
--------  ---------        ---------     -----       ---------    -----------
0         0                0.001         0           0            0
1         1000             1.0           0           1            0
2         2000             0.1           45          0.1          45
3         3000             0.05          90          0.05          90
4         4000             0.025         135         0.025         135
5         5000             0.012         180         0.012         180
6         6000             0.006         -135        0.006         -135
7         7000             0.003         -90         0.003         -90
8         8000             0.0015        -45         0.0015        -45
9         9000             0.00075       0           0.00075       0

"""


def test_parse_pure_sine_returns_low_thd() -> None:
    result = parse_four_output(_CANNED_LOG_PURE_SINE)

    assert result.fundamental_hz == pytest.approx(1000.0)
    assert result.thd_percent == pytest.approx(0.149782)
    assert len(result.harmonics) == 10
    assert result.harmonics[0].n == 0
    assert result.harmonics[1].n == 1
    assert result.harmonics[1].magnitude == pytest.approx(1.0)
    assert result.harmonics[1].frequency_hz == pytest.approx(1000.0)


def test_parse_clipped_sine_returns_high_thd() -> None:
    result = parse_four_output(_CANNED_LOG_CLIPPED_SINE)

    assert result.thd_percent == pytest.approx(12.345)
    # 2nd harmonic dominant in clipped sine (saturation distortion sample)
    assert result.harmonics[2].magnitude > result.harmonics[3].magnitude


def test_parse_explicit_signal_match() -> None:
    multi_log = (
        'Fourier analysis for v(grid):\n'
        '  No. Harmonics: 4, THD: 0.5 %, Gridsize: 100, Interpolation Degree: 1\n'
        '\n'
        'Harmonic  Frequency        Magnitude     Phase       Norm. Mag    Norm. Phase\n'
        '--------  ---------        ---------     -----       ---------    -----------\n'
        '0         0                0.0           0           0            0\n'
        '1         1000             0.5           0           1            0\n'
        '2         2000             0.0025        0           0.005        0\n'
        '3         3000             0.0           0           0            0\n'
        '\n'
        'Fourier analysis for v(load):\n'
        '  No. Harmonics: 4, THD: 5.0 %, Gridsize: 100, Interpolation Degree: 1\n'
        '\n'
        'Harmonic  Frequency        Magnitude     Phase       Norm. Mag    Norm. Phase\n'
        '--------  ---------        ---------     -----       ---------    -----------\n'
        '0         0                0.0           0           0            0\n'
        '1         1000             1.0           0           1            0\n'
        '2         2000             0.05          0           0.05         0\n'
        '3         3000             0.005         0           0.005        0\n'
    )

    grid = parse_four_output(multi_log, signal='v(grid)')
    load = parse_four_output(multi_log, signal='v(load)')

    assert grid.thd_percent == pytest.approx(0.5)
    assert load.thd_percent == pytest.approx(5.0)
    assert load.harmonics[1].magnitude == pytest.approx(1.0)


def test_parse_raises_on_missing_block() -> None:
    with pytest.raises(NgspiceFourierParseError, match='not found'):
        parse_four_output('no fourier here\nrandom log\n')


def test_parse_raises_when_signal_not_found() -> None:
    with pytest.raises(NgspiceFourierParseError, match='not found'):
        parse_four_output(_CANNED_LOG_PURE_SINE, signal='v(nonexistent)')


def test_parse_raises_on_truncated_table() -> None:
    truncated = (
        'Fourier analysis for v(load):\n'
        '  No. Harmonics: 10, THD: 1.0 %, Gridsize: 200, Interpolation Degree: 1\n'
        '\n'
        'Harmonic  Frequency        Magnitude     Phase       Norm. Mag    Norm. Phase\n'
        '--------  ---------        ---------     -----       ---------    -----------\n'
    )
    with pytest.raises(NgspiceFourierParseError):
        parse_four_output(truncated)
