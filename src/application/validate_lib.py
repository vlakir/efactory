"""
SPICE-models static validator (T146).

Floating-node detection в `.SUBCKT` блоках. Heuristic parser для типичных
SPICE elements: каждая нода subckt должна встречаться ≥ 2 раз (external
pin счёт + internal touches). Ноды с count == 1 — floating, как `P3` /
`S3` в pre-T147 `OPT_SE_5K_8.lib`.

Ground node (`0` / `GND`) — special-case, не считается floating даже
при single occurrence (концептуально global net).

X-subckt references — variable arity (зависит от target subckt'а),
без catalog'а не distinguish'ить ноды от param-токенов. Такие subckt'ы
полностью пропускаются с записью в `skipped_subckts`.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel, ConfigDict

# Element-letter → количество nodes, которые он подключает (по SPICE-conventions).
# X-subckt и K (coupling) обработаны отдельно — variable / no-node.
_ELEMENT_NODE_COUNT: dict[str, int] = {
    'R': 2,  # resistor
    'L': 2,  # inductor
    'C': 2,  # capacitor
    'V': 2,  # voltage source
    'I': 2,  # current source
    'D': 2,  # diode
    'E': 4,  # VCVS — out+ out- in+ in-
    'F': 2,  # CCCS — out+ out- (+ V-source ref + gain)
    'G': 4,  # VCCS — out+ out- in+ in-
    'H': 2,  # CCVS — out+ out- (+ V-source ref + gain)
    'Q': 3,  # BJT — C B E
    'J': 3,  # JFET — D G S
    'M': 4,  # MOSFET — D G S B
    'S': 4,  # voltage-controlled switch
    'W': 2,  # current-controlled switch (gets V-ref + model)
    'T': 4,  # lossless transmission line
    'O': 4,  # lossy transmission line
}

# `_GROUND_TOKENS` — special-case ground references (не floating даже single).
_GROUND_TOKENS = frozenset({'0', 'GND', 'gnd'})

_SUBCKT_HEADER_RE = re.compile(
    r'^\s*\.SUBCKT\s+(\S+)\s+(.*?)$',
    re.IGNORECASE,
)
_SUBCKT_END_RE = re.compile(r'^\s*\.ENDS\b', re.IGNORECASE)
_COMMENT_RE = re.compile(r'^\s*[*;]')


class FloatingNodeReport(BaseModel):
    """Single floating node finding."""

    model_config = ConfigDict(frozen=True)

    subckt: str
    node: str
    occurrences: int


class LibValidationReport(BaseModel):
    """Aggregate report для одного `.lib` файла."""

    model_config = ConfigDict(frozen=True)

    lib_path: Path
    subckts_validated: int
    floating_nodes: list[FloatingNodeReport]
    skipped_subckts: list[str]


def validate_lib(lib_path: Path) -> LibValidationReport:
    """
    Parse `.lib`, detect floating nodes per subckt.

    Args:
        lib_path: Path to SPICE `.lib` (or `.cir`/`.net`) с `.SUBCKT`-блоками.

    Returns:
        `LibValidationReport` с floating_nodes (если есть) +
        skipped_subckts (containing X-references).

    Raises:
        FileNotFoundError: lib_path не существует.

    """
    text = lib_path.read_text(encoding='utf-8')
    lines = text.splitlines()
    floating: list[FloatingNodeReport] = []
    skipped: list[str] = []
    subckts_count = 0

    cur_name: str | None = None
    cur_external: list[str] = []
    cur_node_counts: dict[str, int] = {}
    cur_has_x_ref = False

    for raw_line in lines:
        if _COMMENT_RE.match(raw_line):
            continue
        line = raw_line.strip()
        if not line:
            continue

        header = _SUBCKT_HEADER_RE.match(line)
        if header is not None:
            cur_name = header.group(1)
            pins_part = header.group(2).strip()
            # Strip params (`param=val`); pins до первого `=` token.
            cur_external = [tok for tok in pins_part.split() if '=' not in tok]
            cur_node_counts = dict.fromkeys(cur_external, 1)  # external = 1 touch.
            cur_has_x_ref = False
            continue

        if _SUBCKT_END_RE.match(line):
            if cur_name is None:
                continue
            subckts_count += 1
            if cur_has_x_ref:
                skipped.append(cur_name)
            else:
                for node, count in cur_node_counts.items():
                    if count < 2 and node not in _GROUND_TOKENS:  # noqa: PLR2004
                        floating.append(
                            FloatingNodeReport(
                                subckt=cur_name,
                                node=node,
                                occurrences=count,
                            ),
                        )
            cur_name = None
            cur_external = []
            cur_node_counts = {}
            cur_has_x_ref = False
            continue

        if cur_name is None:
            continue

        nodes = _extract_element_nodes(line)
        if nodes is None:
            cur_has_x_ref = True
            continue
        for node in nodes:
            cur_node_counts[node] = cur_node_counts.get(node, 0) + 1

    return LibValidationReport(
        lib_path=lib_path,
        subckts_validated=subckts_count,
        floating_nodes=floating,
        skipped_subckts=skipped,
    )


def _extract_element_nodes(line: str) -> list[str] | None:
    """
    Return nodes for SPICE element line, or `None` if X-subckt encountered.

    Heuristic: первый токен — element name (letter + identifier). Letter
    определяет ожидаемое количество nodes из `_ELEMENT_NODE_COUNT`.
    K (coupling) — references inductor names, не nodes — return [].
    X (subckt) — variable arity, не можем определить без catalog —
    return None (caller помечает subckt как skipped).
    Unknown letters — return [] (conservative).
    """
    tokens = line.split()
    if not tokens:
        return []
    ref = tokens[0]
    letter = ref[0].upper()
    if letter == 'X':
        return None
    if letter == 'K':
        # K<name> Lref1 Lref2 coupling — Lref'ы это references, не nodes.
        return []
    n_nodes = _ELEMENT_NODE_COUNT.get(letter)
    if n_nodes is None:
        return []
    # tokens[1:1+n_nodes] — nodes; остальное — model/value/params.
    return tokens[1 : 1 + n_nodes]


__all__ = [
    'FloatingNodeReport',
    'LibValidationReport',
    'validate_lib',
]
