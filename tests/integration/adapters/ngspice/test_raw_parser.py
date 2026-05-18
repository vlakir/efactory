"""Unit-стиль: parse_ngspice_raw на фиксированных ASCII raw фикстурах (T008)."""

from __future__ import annotations

import pytest

from adapters.outbound.ngspice.raw_parser import (
    NgspiceRawParseError,
    parse_ngspice_raw,
)

_OP_RAW = """Title: * op test
Date: Mon May 18 12:00:00  2026
Command: ngspice-45.2
Plotname: Operating Point
Flags: real
No. Variables: 3
No. Points: 1
Variables:
\t0\tv(in)\tvoltage
\t1\tv(out)\tvoltage
\t2\ti(v1)\tcurrent
Values:
 0\t1.000000000000000e+00
\t1.000000000000000e+00
\t-1.000000000000000e-03
"""

_TRAN_RAW = """Title: * tran test
Date: Mon May 18 12:00:00  2026
Command: ngspice-45.2
Plotname: Transient Analysis
Flags: real
No. Variables: 3
No. Points: 2
Variables:
\t0\ttime\ttime
\t1\tv(in)\tvoltage
\t2\tv(out)\tvoltage
Values:
 0\t0.000000000000000e+00
\t1.000000000000000e+00
\t0.000000000000000e+00

 1\t1.000000000000000e-03
\t1.000000000000000e+00
\t5.000000000000000e-01
"""

_AC_RAW = """Title: * ac test
Date: Mon May 18 12:00:00  2026
Command: ngspice-45.2
Plotname: AC Analysis
Flags: complex
No. Variables: 2
No. Points: 2
Variables:
\t0\tfrequency\tfrequency grid=3
\t1\tv(out)\tvoltage
Values:
 0\t1.000000000000000e+01,0.000000000000000e+00
\t9.960676824071726e-01,-6.258477827057168e-02

 1\t1.000000000000000e+02,0.000000000000000e+00
\t7.169568003248977e-01,-4.504772433683887e-01
"""


def test_parse_op_returns_operating_points() -> None:
    result = parse_ngspice_raw(_OP_RAW)
    assert result.operating_points == {
        'v(in)': 1.0,
        'v(out)': 1.0,
        'i(v1)': -1e-3,
    }
    assert result.time_series is None
    assert result.ac_sweep is None


def test_parse_tran_returns_time_series() -> None:
    result = parse_ngspice_raw(_TRAN_RAW)
    assert result.time_series is not None
    ts = result.time_series
    assert ts.time == (0.0, 1e-3)
    assert ts.traces == {
        'v(in)': (1.0, 1.0),
        'v(out)': (0.0, 0.5),
    }
    assert result.operating_points is None
    assert result.ac_sweep is None


def test_parse_ac_returns_ac_sweep() -> None:
    result = parse_ngspice_raw(_AC_RAW)
    assert result.ac_sweep is not None
    ac = result.ac_sweep
    assert ac.frequency == (10.0, 100.0)
    assert ac.traces_real == {
        'v(out)': (
            pytest.approx(0.9960676824071726),
            pytest.approx(0.7169568003248977),
        ),
    }
    assert ac.traces_imag == {
        'v(out)': (
            pytest.approx(-0.06258477827057168),
            pytest.approx(-0.4504772433683887),
        ),
    }
    assert result.operating_points is None
    assert result.time_series is None


def test_parse_rejects_empty_content() -> None:
    with pytest.raises(NgspiceRawParseError):
        parse_ngspice_raw('')


def test_parse_rejects_missing_plotname() -> None:
    bad = _OP_RAW.replace('Plotname: Operating Point\n', '')
    with pytest.raises(NgspiceRawParseError, match='Plotname'):
        parse_ngspice_raw(bad)


def test_parse_rejects_unknown_plotname() -> None:
    bad = _OP_RAW.replace('Operating Point', 'Noise Analysis')
    with pytest.raises(NgspiceRawParseError, match='Noise Analysis'):
        parse_ngspice_raw(bad)


def test_parse_rejects_missing_variables_section() -> None:
    bad = _OP_RAW.replace('Variables:\n', '')
    with pytest.raises(NgspiceRawParseError, match='Variables'):
        parse_ngspice_raw(bad)


def test_parse_rejects_missing_values_section() -> None:
    bad = _OP_RAW.split('Values:')[0]
    with pytest.raises(NgspiceRawParseError, match='Values'):
        parse_ngspice_raw(bad)


def test_parse_rejects_short_values_block() -> None:
    bad = _TRAN_RAW.rstrip().rsplit('\n', 3)[0] + '\n'
    with pytest.raises(NgspiceRawParseError, match='Values'):
        parse_ngspice_raw(bad)


def test_parse_rejects_complex_in_real_analysis() -> None:
    """Если Flags=real, значения не должны содержать запятую (complex)."""
    bad = _OP_RAW.replace(
        '\t1.000000000000000e+00\n\t-1.000000000000000e-03',
        '\t1.0,0.0\n\t-1.0e-3,0.0',
    )
    with pytest.raises(NgspiceRawParseError):
        parse_ngspice_raw(bad)
