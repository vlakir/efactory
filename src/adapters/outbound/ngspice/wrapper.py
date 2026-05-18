"""Генератор ngspice batch-wrapper'а для заданного netlist + analysis (T008)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from domain.simulation import AcAnalysis, OpAnalysis, TranAnalysis

if TYPE_CHECKING:
    from pathlib import Path

    from domain.simulation import AnalysisSpec


_WRAPPER_TEMPLATE = """* efactory ngspice wrapper (T008)
{netlist}

{directive}

.control
  set filetype=ascii
  run
  write {raw_path} all
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
    cleaned = _strip_dot_end(netlist_content)
    directive = _format_directive(analysis)
    return _WRAPPER_TEMPLATE.format(
        netlist=cleaned,
        directive=directive,
        raw_path=raw_path,
    )


def _strip_dot_end(text: str) -> str:
    """Удалить любые `.end` (case-insensitive) — собственный `.END` ставит wrapper."""
    return '\n'.join(
        line for line in text.splitlines() if line.strip().lower() != '.end'
    )


def _format_directive(analysis: AnalysisSpec) -> str:
    if isinstance(analysis, OpAnalysis):
        return '.OP'
    if isinstance(analysis, TranAnalysis):
        parts = ['.TRAN', _num(analysis.t_step), _num(analysis.t_stop)]
        if analysis.t_start != 0.0 or analysis.uic:
            parts.append(_num(analysis.t_start))
        if analysis.uic:
            parts.append('UIC')
        return ' '.join(parts)
    if isinstance(analysis, AcAnalysis):
        return (
            f'.AC {analysis.sweep} {analysis.n_points} '
            f'{_num(analysis.f_start)} {_num(analysis.f_stop)}'
        )
    msg = f'Unsupported analysis: {type(analysis).__name__}'
    raise TypeError(msg)


def _num(value: float) -> str:
    return str(value)


__all__ = ['build_wrapper']
