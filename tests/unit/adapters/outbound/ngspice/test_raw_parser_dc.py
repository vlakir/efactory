"""DC sweep parser tests для ngspice raw_parser (T188)."""

from __future__ import annotations

from adapters.outbound.ngspice.raw_parser import parse_ngspice_raw

_DC_RAW_SAMPLE = """\
Title: DC transfer characteristic test
Date: Sat Jun 06 01:30:00 2026
Plotname: DC transfer characteristic
Flags: real
No. Variables: 2
No. Points: 3
Variables:
\t0\tv-sweep\tvoltage
\t1\tv(out)\tvoltage
Values:
 0\t0
\t0
 1\t1.0
\t0.7
 2\t2.0
\t1.4
"""


def test_dc_sweep_parsed() -> None:
    result = parse_ngspice_raw(_DC_RAW_SAMPLE)
    assert result.dc_sweep is not None
    assert result.dc_sweep.sweep_variable == 'v-sweep'
    assert result.dc_sweep.sweep_values == (0.0, 1.0, 2.0)
    assert result.dc_sweep.traces == {'v(out)': (0.0, 0.7, 1.4)}
    # Прочие ветви должны быть None.
    assert result.operating_points is None
    assert result.time_series is None
    assert result.ac_sweep is None
    assert result.fourier_result is None
