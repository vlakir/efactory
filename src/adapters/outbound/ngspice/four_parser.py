"""
Parser ngspice `.four` block из stdout/log → FourierResult (T131 Phase B).

ngspice batch-mode эмитит Fourier output через interactive команду
`fourier` (top-level `.four` директива не процессится при наличии
`.control` блока). Формат вывода (см. ngspice manual ch. 15.3.4):

    Fourier analysis for v(load):
      No. Harmonics: 10, THD: 0.149782 %, Gridsize: 200, Interpolation Degree: 1

    Harmonic  Frequency        Magnitude     Phase       Norm. Mag    Norm. Phase
    --------  ---------        ---------     -----       ---------    -----------
    0         0                0.0299822     0           0            0
    1         1000             1             -0.00149782 1            0
    ...

`No. Harmonics: N` — это **общее количество строк** (DC = n=0 + actual
harmonics 1..N-1), не «число гармоник без DC».
"""

from __future__ import annotations

import re

from domain.simulation import FourierResult, HarmonicSample


class NgspiceFourierParseError(Exception):
    """ngspice `.four` log block не parse'ится."""


_HEADER_RE = re.compile(
    r'Fourier analysis for\s+(?P<signal>\S+):\s*\n'
    r'\s*No\.\s+Harmonics:\s*(?P<n>\d+)\s*,\s*'
    r'THD:\s*(?P<thd>[-+0-9.eE]+)\s*%',
)

_DASH_SEPARATOR_RE = re.compile(r'^\s*-{2,}\s+-{2,}')

_MIN_ROW_TOKENS = 6


def parse_four_output(
    log_text: str,
    *,
    signal: str | None = None,
) -> FourierResult:
    """
    Parse ngspice `.four` block из ngspice log/stdout.

    Если `signal` задан — ищется блок именно для этого signal name
    (case-insensitive). Если `None` — возвращается первый найденный блок.
    """
    block_match = (
        _find_block_for_signal(log_text, signal)
        if signal is not None
        else _HEADER_RE.search(log_text)
    )
    if block_match is None:
        target = f' for signal {signal!r}' if signal is not None else ''
        msg = f'ngspice .four block not found in log{target}.'
        raise NgspiceFourierParseError(msg)

    n_rows = int(block_match.group('n'))
    thd_percent = float(block_match.group('thd'))
    body_lines = log_text[block_match.end() :].splitlines()
    rows_start = _skip_until_dash_separator(body_lines)
    harmonics = _parse_rows(body_lines, rows_start, n_rows)
    fundamental_hz = _resolve_fundamental(harmonics)

    return FourierResult(
        fundamental_hz=fundamental_hz,
        thd_percent=thd_percent,
        harmonics=tuple(harmonics),
    )


def _find_block_for_signal(
    log_text: str,
    signal: str,
) -> re.Match[str] | None:
    target = signal.strip().lower()
    for match in _HEADER_RE.finditer(log_text):
        if match.group('signal').strip().lower() == target:
            return match
    return None


def _skip_until_dash_separator(lines: list[str]) -> int:
    for idx, line in enumerate(lines):
        if _DASH_SEPARATOR_RE.match(line):
            return idx + 1
    msg = 'ngspice .four: dash-separator line not found after header.'
    raise NgspiceFourierParseError(msg)


def _parse_rows(
    lines: list[str],
    start_idx: int,
    expected_rows: int,
) -> list[HarmonicSample]:
    harmonics: list[HarmonicSample] = []
    idx = start_idx
    while idx < len(lines) and len(harmonics) < expected_rows:
        stripped = lines[idx].strip()
        if not stripped:
            idx += 1
            continue
        tokens = stripped.split()
        if len(tokens) < _MIN_ROW_TOKENS:
            break
        try:
            n = int(tokens[0])
            freq = float(tokens[1])
            magnitude = float(tokens[2])
            phase = float(tokens[3])
            normalized = float(tokens[4])
        except ValueError:
            break
        harmonics.append(
            HarmonicSample(
                n=n,
                frequency_hz=freq,
                magnitude=abs(magnitude),
                phase_deg=phase,
                normalized=abs(normalized),
            ),
        )
        idx += 1

    if len(harmonics) != expected_rows:
        msg = (
            f'ngspice .four: expected {expected_rows} harmonic rows, '
            f'parsed {len(harmonics)}.'
        )
        raise NgspiceFourierParseError(msg)
    return harmonics


def _resolve_fundamental(harmonics: list[HarmonicSample]) -> float:
    for sample in harmonics:
        if sample.n == 1:
            return sample.frequency_hz
    msg = 'ngspice .four: fundamental row (n=1) not found in harmonic table.'
    raise NgspiceFourierParseError(msg)


__all__ = ['NgspiceFourierParseError', 'parse_four_output']
