"""
Ngspice injection-netlist patcher (T153 Phase B.3, ADR-T153c + ADR-T153d).

Реализация `InjectionNetlistPatcher` outbound port — edge-aware
topology surgery поверх SPICE netlist'ов:

* `insert_voltage_source` — Middlebrook voltage method.
* `insert_current_source` — Middlebrook current method.
* `open_break` — Rosenstark open-circuit topology mod.
* `short_break` — Rosenstark short-circuit topology mod.

Edge задаётся парой `(break_node, break_element_ref)` (ADR-T153d).
Алгоритм для всех четырёх:

1. Найти top-level элементную строку с первым токеном
   `break_element_ref` (без учёта регистра, вне `.SUBCKT`/`.ENDS`
   блоков).
2. Переименовать в этой строке ссылку на `break_node` в
   `<break_node>__fwd`. Остальные ссылки на `break_node` в netlist'е
   не трогаются.
3. Вставить необходимые source/probe строки прямо перед `.end`-card
   (или в конец netlist'а если `.end` отсутствует).

Token-level замена идентификаторов нодов через whitespace-split:
ngspice-конвенция «node-name — любая alphanumeric/`/`/`+`/`-`/`_`-
строка, разделённая whitespace». Inline-комментарии (`;`, `$`)
сохраняются.

Probe pair naming (для downstream `InjectionStrategy.combine()`):

| Method | fwd | rev |
| --- | --- | --- |
| voltage | `v(<break>__fwd)` | `v(<break>)` |
| current | `i(v_fwd_probe)` | `i(v_rev_probe)` |
| open_break | `v(<break>__fwd)` | `v(<break>)` |
| short_break | `i(vrr_sc_drv)` | `i(vrr_sc_meas)` |

Trace-имена — lowercase (ngspice convention: trace names всегда
приводятся к lowercase независимо от регистра в netlist'е).

Фиксированные внутренние ref'ы `V_fwd_probe / V_rev_probe /
Vrr_oc_drv / Rrr_oc_pulldown / Vrr_sc_drv / Vrr_sc_meas` —
collision'ы с user-netlist'ом маловероятны, при необходимости
сделать pre-scan + suffix (Spec Q13=b, follow-up в Phase B.5
или composition root).

Short-break Rosenstark: drive — voltage source (Vrr_sc_drv AC 1V),
не current source. Причина — ngspice не сохраняет `i(I<src>)` для
independent current source'ов в AC sweep по умолчанию. Voltage drive
с probe через `i(v<src>)` даёт устойчивое решение без `.options
savecurrents`. Dimensionless T_sc остаётся = i(rev)/i(fwd) — оба
currents через voltage sources.

Note (Phase C calibration): physical correctness конкретных
topology'ей (DC op-point preservation, реалистичный pulldown
1 GΩ, направление current source) проверяется на op-amp inverting
amp + NFB SE amp fixture в Phase C. Этот файл фиксирует contract:
syntactic ngspice-validity + probe-pair name conformance с
domain strategy'ями.
"""

from __future__ import annotations

import re

from domain.injection_patcher import (
    NetlistPatchResult,
    ProbePair,
)

_SUBCKT_START_RE = re.compile(r'^\s*\.SUBCKT\b', re.IGNORECASE)
_SUBCKT_END_RE = re.compile(r'^\s*\.ENDS\b', re.IGNORECASE)
_END_CARD_RE = re.compile(r'^\s*\.end\b', re.IGNORECASE)


def _find_element_line_index(lines: list[str], element_ref: str) -> int | None:
    """Top-level element line whose first token matches `element_ref`."""
    target = element_ref.upper()
    subckt_depth = 0
    for idx, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped or stripped.startswith('*'):
            continue
        if _SUBCKT_START_RE.match(line):
            subckt_depth += 1
            continue
        if _SUBCKT_END_RE.match(line):
            subckt_depth = max(0, subckt_depth - 1)
            continue
        if subckt_depth > 0:
            continue
        if stripped.startswith('.'):
            continue
        first_token = stripped.split(maxsplit=1)[0]
        if first_token.upper() == target:
            return idx
    return None


def _split_inline_comment(line: str) -> tuple[str, str]:
    """Split into (code_part, comment_part_with_optional_newline)."""
    ending = '\n' if line.endswith('\n') else ''
    body = line[:-1] if ending else line
    for i, c in enumerate(body):
        if c in ';$':
            return body[:i], body[i:] + ending
    return body, ending


def _rename_node_in_element_line(
    line: str,
    old_node: str,
    new_node: str,
) -> str | None:
    """
    Replace exact-match pin tokens equal to `old_node` (case-insensitive).

    Returns the new line. Returns None if no pin token matched.
    First token (the element ref) is preserved as-is.
    """
    code_part, comment_part = _split_inline_comment(line)
    leading_ws_len = len(code_part) - len(code_part.lstrip())
    leading_ws = code_part[:leading_ws_len]
    body = code_part[leading_ws_len:]
    tokens = body.split()
    if not tokens:
        return None
    new_tokens = [tokens[0]]
    found = False
    target_lower = old_node.lower()
    for tok in tokens[1:]:
        if tok.lower() == target_lower:
            new_tokens.append(new_node)
            found = True
        else:
            new_tokens.append(tok)
    if not found:
        return None
    new_code = leading_ws + ' '.join(new_tokens)
    # Если comment_part пуст или только '\n' — join без extra-space.
    if comment_part in {'', '\n'}:
        return new_code + comment_part
    return new_code + ' ' + comment_part


def _insert_before_end_card(lines: list[str], insertion_text: str) -> str:
    """Insert `insertion_text` before `.end` card; append if no `.end`."""
    for idx, line in enumerate(lines):
        if _END_CARD_RE.match(line):
            return ''.join(lines[:idx]) + insertion_text + ''.join(lines[idx:])
    base = ''.join(lines)
    if base and not base.endswith('\n'):
        base += '\n'
    return base + insertion_text


def _g(value: float) -> str:
    """Compact float rendering — same convention as netlist_substitution._g."""
    return f'{value:.9g}'


def _apply_edge_cut(
    netlist: str,
    break_node: str,
    break_element_ref: str,
) -> tuple[list[str], str]:
    """
    Find target element line, rename break_node → <break_node>__fwd in it.

    Returns (mutated_lines_list, fwd_node_name).

    Raises:
        ValueError: element_ref not found at top-level / break_node not
            in pins of that element.

    """
    lines = netlist.splitlines(keepends=True)
    idx = _find_element_line_index(lines, break_element_ref)
    if idx is None:
        msg = (
            f'element_ref {break_element_ref!r} not found at top-level '
            f'in netlist (not inside .subckt blocks)'
        )
        raise ValueError(msg)
    fwd_node = f'{break_node}__fwd'
    new_line = _rename_node_in_element_line(lines[idx], break_node, fwd_node)
    if new_line is None:
        msg = (
            f'break_node {break_node!r} not in pins of element '
            f'{break_element_ref!r} (line: {lines[idx].rstrip()!r})'
        )
        raise ValueError(msg)
    if not new_line.endswith('\n'):
        new_line += '\n'
    lines[idx] = new_line
    return lines, fwd_node


# -------------------------------------------------- module-level operations ----


def insert_voltage_source(
    netlist: str,
    *,
    break_node: str,
    break_element_ref: str,
    source_ref: str,
    ac_magnitude: float = 1.0,
) -> NetlistPatchResult:
    """Middlebrook voltage injection. See module docstring."""
    lines, fwd_node = _apply_edge_cut(netlist, break_node, break_element_ref)
    src_line = f'{source_ref} {fwd_node} {break_node} AC {_g(ac_magnitude)} 0\n'
    patched = _insert_before_end_card(lines, src_line)
    return NetlistPatchResult(
        patched_netlist=patched,
        probe_pair=ProbePair(fwd=f'v({fwd_node})', rev=f'v({break_node})'),
    )


def insert_current_source(
    netlist: str,
    *,
    break_node: str,
    break_element_ref: str,
    source_ref: str,
    ac_magnitude: float = 1.0,
) -> NetlistPatchResult:
    """Middlebrook current injection. See module docstring."""
    lines, fwd_node = _apply_edge_cut(netlist, break_node, break_element_ref)
    probe_node = f'{break_node}__probe'
    patch = (
        f'V_fwd_probe {fwd_node} {probe_node} 0\n'
        f'V_rev_probe {break_node} {probe_node} 0\n'
        f'{source_ref} {probe_node} 0 DC 0 AC {_g(ac_magnitude)}\n'
    )
    patched = _insert_before_end_card(lines, patch)
    return NetlistPatchResult(
        patched_netlist=patched,
        probe_pair=ProbePair(fwd='i(v_fwd_probe)', rev='i(v_rev_probe)'),
    )


def open_break(
    netlist: str,
    *,
    break_node: str,
    break_element_ref: str,
) -> NetlistPatchResult:
    """Rosenstark open-circuit. See module docstring."""
    lines, fwd_node = _apply_edge_cut(netlist, break_node, break_element_ref)
    patch = f'Vrr_oc_drv {fwd_node} 0 AC 1 0\nRrr_oc_pulldown {break_node} 0 1G\n'
    patched = _insert_before_end_card(lines, patch)
    return NetlistPatchResult(
        patched_netlist=patched,
        probe_pair=ProbePair(fwd=f'v({fwd_node})', rev=f'v({break_node})'),
    )


def short_break(
    netlist: str,
    *,
    break_node: str,
    break_element_ref: str,
    gnd_node: str = '0',
) -> NetlistPatchResult:
    """Rosenstark short-circuit. See module docstring."""
    lines, fwd_node = _apply_edge_cut(netlist, break_node, break_element_ref)
    patch = f'Vrr_sc_drv {fwd_node} 0 AC 1 0\nVrr_sc_meas {break_node} {gnd_node} 0\n'
    patched = _insert_before_end_card(lines, patch)
    return NetlistPatchResult(
        patched_netlist=patched,
        probe_pair=ProbePair(fwd='i(vrr_sc_drv)', rev='i(vrr_sc_meas)'),
    )


# -------------------------------------------------------------- class adapter ----


class NgspiceInjectionNetlistPatcher:
    """
    `InjectionNetlistPatcher` adapter поверх ngspice text conventions.

    Тонкая обёртка над module-level functions для conformance с
    `domain.injection_patcher.InjectionNetlistPatcher`
    Protocol.
    """

    def insert_voltage_source(
        self,
        netlist: str,
        *,
        break_node: str,
        break_element_ref: str,
        source_ref: str,
        ac_magnitude: float = 1.0,
    ) -> NetlistPatchResult:
        return insert_voltage_source(
            netlist,
            break_node=break_node,
            break_element_ref=break_element_ref,
            source_ref=source_ref,
            ac_magnitude=ac_magnitude,
        )

    def insert_current_source(
        self,
        netlist: str,
        *,
        break_node: str,
        break_element_ref: str,
        source_ref: str,
        ac_magnitude: float = 1.0,
    ) -> NetlistPatchResult:
        return insert_current_source(
            netlist,
            break_node=break_node,
            break_element_ref=break_element_ref,
            source_ref=source_ref,
            ac_magnitude=ac_magnitude,
        )

    def open_break(
        self,
        netlist: str,
        *,
        break_node: str,
        break_element_ref: str,
    ) -> NetlistPatchResult:
        return open_break(
            netlist,
            break_node=break_node,
            break_element_ref=break_element_ref,
        )

    def short_break(
        self,
        netlist: str,
        *,
        break_node: str,
        break_element_ref: str,
        gnd_node: str = '0',
    ) -> NetlistPatchResult:
        return short_break(
            netlist,
            break_node=break_node,
            break_element_ref=break_element_ref,
            gnd_node=gnd_node,
        )


__all__ = [
    'NgspiceInjectionNetlistPatcher',
    'insert_current_source',
    'insert_voltage_source',
    'open_break',
    'short_break',
]
