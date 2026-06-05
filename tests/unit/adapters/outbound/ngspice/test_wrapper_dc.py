"""DC sweep wrapper formatting tests (T188)."""

from __future__ import annotations

from pathlib import Path

from adapters.outbound.ngspice.wrapper import build_wrapper
from domain.simulation import DcSweepAnalysis


def test_dc_directive_emitted() -> None:
    netlist = '* dummy\nV1 in 0 0\nR1 in out 1k\nR2 out 0 1k\n'
    text = build_wrapper(
        netlist,
        DcSweepAnalysis(source='V1', start=0.0, stop=5.0, step=0.1),
        Path('/tmp/out.raw'),
    )
    assert '.DC V1 0.0 5.0 0.1' in text


def test_dc_directive_with_descending_range() -> None:
    text = build_wrapper(
        '* d\n',
        DcSweepAnalysis(source='V2', start=5.0, stop=-2.0, step=0.5),
        Path('/tmp/x.raw'),
    )
    assert '.DC V2 5.0 -2.0 0.5' in text
