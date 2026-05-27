"""Генератор ngspice batch-wrapper'а для заданного netlist + analysis (T008)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from domain.simulation import (
    AcAnalysis,
    FourierAnalysis,
    OpAnalysis,
    TranAnalysis,
)

if TYPE_CHECKING:
    from pathlib import Path

    from domain.simulation import AnalysisSpec

# KiCad SPICE export использует power-symbol Value как net name (`GND`).
# ngspice ожидает ground node = `0`. Делаем substitution token-wise,
# чтобы пользователь мог использовать стандартный KiCad GND symbol.
_GND_TOKEN_RE = re.compile(r'\bGND\b')

# KiCad SPICE export встраивает Simulator-card директиву из `.kicad_sch`
# (`.tran`, `.ac` и т.п.) в netlist. Если оставить — ngspice выполнит
# её при `run`, а наш appended directive останется в queue и `write all`
# отдаст результаты не той analysis (например, operating_points={} при
# `OpAnalysis` поверх netlist'а с `.tran`). T144 root cause —
# стрипим все top-level analysis directives.
_EMBEDDED_ANALYSIS_RE = re.compile(
    r'^\s*\.(op|tran|ac|dc|four|noise|tf|sens|disto)\b.*$',
    re.IGNORECASE,
)


_WRAPPER_TEMPLATE = """* efactory ngspice wrapper (T008)
{netlist}

{directive}

.control
{control_pre}  set filetype=ascii
  run
{control_post}  write {raw_path} all
  exit
.endc
.END
"""


def build_wrapper(
    netlist_content: str,
    analysis: AnalysisSpec,
    raw_path: Path,
) -> str:
    """Сформировать текст wrapper-файла для `ngspice -b`."""
    cleaned = _normalize_ground(
        _strip_analysis_directives(_strip_dot_end(netlist_content)),
    )
    directive = _format_directive(analysis)
    pre_lines, post_lines = _format_control_blocks(analysis)
    control_pre = ''.join(f'  {line}\n' for line in pre_lines)
    control_post = ''.join(f'  {line}\n' for line in post_lines)
    return _WRAPPER_TEMPLATE.format(
        netlist=cleaned,
        directive=directive,
        control_pre=control_pre,
        control_post=control_post,
        raw_path=raw_path,
    )


def _normalize_ground(text: str) -> str:
    """Заменить SPICE-токен `GND` на `0` (ngspice ground node)."""
    return _GND_TOKEN_RE.sub('0', text)


def _strip_dot_end(text: str) -> str:
    """Удалить любые `.end` (case-insensitive) — собственный `.END` ставит wrapper."""
    return '\n'.join(
        line for line in text.splitlines() if line.strip().lower() != '.end'
    )


def _strip_analysis_directives(text: str) -> str:
    """Удалить top-level analysis directives — wrapper ставит свою."""
    return '\n'.join(
        line for line in text.splitlines() if not _EMBEDDED_ANALYSIS_RE.match(line)
    )


def _format_directive(analysis: AnalysisSpec) -> str:
    if isinstance(analysis, OpAnalysis):
        return '.OP'
    if isinstance(analysis, TranAnalysis):
        return _format_tran(analysis)
    if isinstance(analysis, AcAnalysis):
        return (
            f'.AC {analysis.sweep} {analysis.n_points} '
            f'{_num(analysis.f_start)} {_num(analysis.f_stop)}'
        )
    if isinstance(analysis, FourierAnalysis):
        # `.four` top-level directive не процессится ngspice при наличии
        # `.control` блока с `run` — Fourier эмитим как interactive команду
        # `fourier <fund> <signal>` после `run` (см. `_format_control_blocks`).
        return _format_tran(analysis.tran)
    msg = f'Unsupported analysis: {type(analysis).__name__}'
    raise TypeError(msg)


def _format_tran(analysis: TranAnalysis) -> str:
    parts = ['.TRAN', _num(analysis.t_step), _num(analysis.t_stop)]
    if analysis.t_start != 0.0 or analysis.uic:
        parts.append(_num(analysis.t_start))
    if analysis.uic:
        parts.append('UIC')
    return ' '.join(parts)


def _format_control_blocks(
    analysis: AnalysisSpec,
) -> tuple[list[str], list[str]]:
    """
    `.control` pre/post lines (до `set filetype=ascii` и после `run`).

    Для `FourierAnalysis`:
    - pre: `set nfreqs=N` (управляет числом harmonic-строк в `.four` output).
    - post: `fourier <fund> <signal>` (interactive команда, выполняется
      после `run` — `.four` top-level директива не работает с `.control`).
    """
    if isinstance(analysis, FourierAnalysis):
        return (
            [f'set nfreqs={analysis.n_harmonics}'],
            [f'fourier {_num(analysis.fundamental_hz)} {analysis.signal}'],
        )
    return ([], [])


def _num(value: float) -> str:
    return str(value)


__all__ = ['build_wrapper']
