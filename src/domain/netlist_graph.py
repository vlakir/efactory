"""
Netlist circuit graph — VOs + analyzer (T153 Phase B.5, ADR-T153b).

Pure-domain rule-based heuristic feedback detection без зависимости от
ports / external state.

VOs:

* `ElementType` Literal — 12 SPICE element classes (R/C/L/D/V/I/Q/M/J/E/F/H/X).
* `CircuitEdge` — один edge в graph: element_id + type + (net1, net2)
  pair. Multi-terminal elements (BJT/MOSFET/JFET/VCCS/subckt) парсятся
  в несколько pairwise edges (один CircuitEdge на каждую пин-пару).
* `CircuitGraph` — frozen multigraph: nets tuple + edges tuple.
  Validator: каждая ссылка из edges на net ∈ nets.

Analyzer (Phase B.5.3+, не в этом файле сразу):

* `parse(netlist) -> CircuitGraph` — regex line-by-line, skip
  `.SUBCKT/.ENDS` блоки.
* `find_cycles(graph) -> tuple[FeedbackCycle, ...]` — DFS simple
  cycles + active/passive classification.
* `score_break_candidates(cycles) -> AutoDetectInfo` — confidence
  scoring + edge-pair selection.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    from collections.abc import Iterable

    from domain.phase_margin import AutoDetectInfo, FeedbackCycle

_FROZEN = ConfigDict(frozen=True, extra='forbid')


ElementType = Literal[
    'resistor',
    'capacitor',
    'inductor',
    'diode',
    'bjt',
    'mosfet',
    'jfet',
    'voltage_source',
    'current_source',
    'voltage_controlled_source',
    'current_controlled_source',
    'subckt',
]


class CircuitEdge(BaseModel):
    """
    Одна edge в circuit graph — element с парой нет (net1, net2).

    Multi-terminal elements (BJT 3-pin, MOSFET 4-pin, subckt N-pin)
    раскладываются в несколько CircuitEdge'ов с одним element_id —
    по pairwise pin'ов.
    """

    model_config = _FROZEN

    element_id: Annotated[str, Field(min_length=1)]
    element_type: ElementType
    net_pair: tuple[
        Annotated[str, Field(min_length=1)],
        Annotated[str, Field(min_length=1)],
    ]


class CircuitGraph(BaseModel):
    """
    Frozen undirected multigraph: nets — вершины, CircuitEdges — ребра.

    Edges могут содержать дубликаты (multi-terminal elements, parallel
    elements). Order — порядок появления в netlist'е.
    """

    model_config = _FROZEN

    nets: tuple[str, ...]
    edges: tuple[CircuitEdge, ...] = ()

    @model_validator(mode='after')
    def _check_nets_unique(self) -> Self:
        seen = set()
        for net in self.nets:
            if net in seen:
                msg = f'CircuitGraph: duplicate net {net!r} in nets tuple'
                raise ValueError(msg)
            seen.add(net)
        return self

    @model_validator(mode='after')
    def _check_edges_reference_known_nets(self) -> Self:
        net_set = set(self.nets)
        for edge in self.edges:
            for net in edge.net_pair:
                if net not in net_set:
                    msg = (
                        f'CircuitGraph: edge {edge.element_id!r} references '
                        f'net {net!r} not declared in nets tuple'
                    )
                    raise ValueError(msg)
        return self


# ============================== parse(netlist) =============================

# Маппинг first-char ref'а → (ElementType, pin_count). None pin_count
# = variable (X subckt). F/H — 2 net pins, потом Vname (не нода).
_ELEMENT_TYPE_BY_PREFIX: dict[str, tuple[ElementType, int | None]] = {
    'R': ('resistor', 2),
    'C': ('capacitor', 2),
    'L': ('inductor', 2),
    'D': ('diode', 2),
    'V': ('voltage_source', 2),
    'I': ('current_source', 2),
    'Q': ('bjt', 3),
    'M': ('mosfet', 4),
    'J': ('jfet', 3),
    'E': ('voltage_controlled_source', 4),
    'G': ('voltage_controlled_source', 4),
    'F': ('current_controlled_source', 2),
    'H': ('current_controlled_source', 2),
    'X': ('subckt', None),  # variable pin count
}

_SUBCKT_START_RE = re.compile(r'^\s*\.SUBCKT\b', re.IGNORECASE)
_SUBCKT_END_RE = re.compile(r'^\s*\.ENDS\b', re.IGNORECASE)


def parse(netlist: str) -> CircuitGraph:
    """
    Parse SPICE netlist в `CircuitGraph` (ADR-T153b).

    Алгоритм:

    1. Line-by-line scan, пропускаем blank/comment/.directive строки.
    2. `.SUBCKT/.ENDS` — track depth; элементы внутри subckt блоков
       не парсятся (treated как black-box via X calls в top-level).
    3. Element-type detection по first char ref'а (case-insensitive).
       Неопознанные первые-charы (Z, U, B, K, ...) — silently skipped.
    4. Pin count:
       * R/C/L/D/V/I — 2 pins.
       * Q/J — 3 pins.
       * M — 4 pins.
       * E/G — 4 pins (2 net + 2 control net).
       * F/H — 2 net pins + Vname (ref, не нода).
       * X — variable: pins[:-1], last token = subckt name (или token
         перед первым `=` если есть params).
    5. Multi-terminal elements → pairwise CircuitEdges (n choose 2).
    6. Inline-комментарии (`;`, `$`) обрезаются перед tokenization.

    Args:
        netlist: text SPICE netlist'а.

    Returns:
        `CircuitGraph` с nets (в порядке первого появления) + edges.

    """
    edges: list[CircuitEdge] = []
    nets_order: list[str] = []
    nets_seen: set[str] = set()
    subckt_depth = 0

    for raw_line in netlist.splitlines():
        line = _strip_inline_comment(raw_line).strip()
        if not line:
            continue
        if line.startswith('*'):
            continue
        if _SUBCKT_START_RE.match(raw_line):
            subckt_depth += 1
            continue
        if _SUBCKT_END_RE.match(raw_line):
            subckt_depth = max(0, subckt_depth - 1)
            continue
        if subckt_depth > 0:
            continue
        if line.startswith('.'):
            continue

        tokens = line.split()
        if not tokens:
            continue
        ref = tokens[0]
        prefix = ref[:1].upper()
        if prefix not in _ELEMENT_TYPE_BY_PREFIX:
            continue
        element_type, pin_count = _ELEMENT_TYPE_BY_PREFIX[prefix]
        pins = _extract_pins(tokens, pin_count)
        if pins is None:
            continue

        for net in pins:
            if net not in nets_seen:
                nets_seen.add(net)
                nets_order.append(net)

        if len(pins) == 1:
            # degenerate edge case — single-pin element (unlikely valid SPICE)
            edges.append(
                CircuitEdge(
                    element_id=ref,
                    element_type=element_type,
                    net_pair=(pins[0], pins[0]),
                )
            )
        else:
            edges.extend(
                CircuitEdge(
                    element_id=ref,
                    element_type=element_type,
                    net_pair=(pins[i], pins[j]),
                )
                for i in range(len(pins))
                for j in range(i + 1, len(pins))
            )

    return CircuitGraph(nets=tuple(nets_order), edges=tuple(edges))


def _strip_inline_comment(line: str) -> str:
    """Cut at first ';' или '$' (ngspice inline comment markers)."""
    for i, c in enumerate(line):
        if c in ';$':
            return line[:i]
    return line


def _extract_pins(tokens: list[str], pin_count: int | None) -> list[str] | None:
    """
    Extract pin tokens after ref (`tokens[0]`).

    pin_count=None → X subckt convention: pins = tokens[1:-1] (last
    token = subckt name) или до first token с `=` (params start).
    Fixed pin_count → tokens[1:1+pin_count].
    """
    if pin_count is None:
        # X subckt: stop at first '=' token (params), or last token = subckt name
        param_idx = None
        for i, t in enumerate(tokens[1:], start=1):
            if '=' in t:
                param_idx = i
                break
        # pins are tokens[1:pin_end]; pin_end excludes subckt name.
        pin_end = param_idx - 1 if param_idx is not None else len(tokens) - 1
        pins = tokens[1:pin_end]
        if not pins:
            return None
        return pins
    if len(tokens) < 1 + pin_count:
        return None
    return tokens[1 : 1 + pin_count]


# ============================== find_cycles =================================

# Element-type classification per ADR-T153b:
_ACTIVE_TYPES: frozenset[ElementType] = frozenset(
    {
        'bjt',
        'mosfet',
        'jfet',
        'voltage_controlled_source',
        'current_controlled_source',
        'subckt',
    }
)
_PASSIVE_TYPES: frozenset[ElementType] = frozenset(
    {'resistor', 'capacitor', 'inductor'}
)
# Diode / V / I не входят ни в active ни в passive set:
# * V/I — terminal boundaries (stimulus/bias); если бы они traversable'ись,
#   они закрывали бы топологические cycles через ground — не настоящий
#   feedback. Cycle finder исключает их из adjacency.
# * D — nonlinear, но не "active gain" в feedback sense; считаем passive-
#   like (можно traverse, но не active).
_NON_FEEDBACK_TYPES: frozenset[ElementType] = frozenset(
    {'voltage_source', 'current_source'}
)

# Safety cap чтобы DFS не взрывался на больших схемах:
_MAX_CYCLES = 256
_MAX_CYCLE_LENGTH = 16
# Минимальное число distinct нет'ов в valid cycle (избегаем 2-cycles).
_MIN_CYCLE_LENGTH = 3

# Confidence weights — re-tuned для realistic opamp fixtures (Phase B.5
# empirical adjustment к ADR-T153b §5 initial weights — calibration
# в Phase C на ≥3 reference fixtures).
#
# Re-weighted к feedback-heavy: высокая доля passive elements в цикле
# характерна для «настоящего» feedback пути. Forward path scoring
# понижено, поскольку active element всегда ровно один в типичной
# Bode topology.
_W_FORWARD_ACTIVE = 0.2
_W_FEEDBACK_PASSIVE = 0.5
_W_SINGLE_DOMINANT = 0.2
_W_IMPEDANCE = 0.1  # currently unused — Phase C calibration
# Linear penalty за multi-cycle убран: pairwise expansion многотерминальных
# элементов даёт топологически реальные multiple cycles даже в одной
# feedback loop; penalty wipe'ил confidence до 0. Single-dominant flag
# выступает достаточным сигналом «uniqueness».

# Ground-containing cycles — penalty.
# Op-amp с output stage обычно имеет несколько cycles одинаковой
# topology (R_fb-feedback vs R_load/C_amp-via-ground), все три с
# одинаковыми forward/feedback ratios → confidence равна. Без penalty
# primary cycle определяется первым DFS hit — детерминирован, но
# физически бессмысленный (ground — reference, не loop break edge;
# Vinj N 0 даёт probe `v(0)` которого нет в ngspice output).
# Penalty depresses ground-routed cycles на тех же фикстурах, в которых
# есть настоящий feedback path не через ground.
_GROUND_NETS: frozenset[str] = frozenset({'0', 'gnd', 'GND', 'ground'})
_P_GROUND_CYCLE = 0.3


def find_cycles(graph: CircuitGraph) -> tuple[FeedbackCycle, ...]:
    """
    Detect simple feedback cycles в graph'е.

    Cycle definition: closed walk через distinct nets с each element_id
    used at most once (multi-terminal pairwise edges одного элемента
    считаются как один "use"). Минимальная длина — 3 net'а.

    Valid feedback cycle:
    * ≥1 unique active element_id (BJT/FET/E/G/F/H/subckt),
    * ≥1 unique passive element_id (R/C/L).

    Возвращает tuple `FeedbackCycle` per cycle с derived:
    * `nodes` — net'ы цикла (в порядке traversal'а).
    * `elements` — unique element_id'ы (active + passive).
    * `forward_path_score` — (active edges) / (active + passive edges).
    * `feedback_path_score` — (passive edges) / (active + passive edges).
    * `suggested_break_node` — net на границе active/passive в цикле.
    * `suggested_break_element_ref` — passive element_id на этой границе.
    * `confidence` — placeholder 0.5; финальный confidence ставится
      `score_break_candidates`.

    Cap: max 256 cycles, max length 16.
    """
    from domain.phase_margin import FeedbackCycle  # noqa: PLC0415

    id_to_type = {e.element_id: e.element_type for e in graph.edges}
    raw_cycles = _enumerate_simple_cycles(graph)
    valid: list[FeedbackCycle] = []
    for net_path, element_ids in raw_cycles:
        unique_ids = _unique_preserving_order(element_ids)
        active_ids = [eid for eid in unique_ids if id_to_type[eid] in _ACTIVE_TYPES]
        passive_ids = [eid for eid in unique_ids if id_to_type[eid] in _PASSIVE_TYPES]
        if not active_ids or not passive_ids:
            continue

        n_total = len(active_ids) + len(passive_ids)
        forward_score = len(active_ids) / n_total
        feedback_score = len(passive_ids) / n_total

        suggested_node, suggested_ref = _pick_break_edge(
            net_path, element_ids, id_to_type
        )
        valid.append(
            FeedbackCycle(
                nodes=tuple(net_path[:-1]),  # последний == первый, дропаем
                elements=tuple(unique_ids),
                forward_path_score=forward_score,
                feedback_path_score=feedback_score,
                suggested_break_node=suggested_node,
                suggested_break_element_ref=suggested_ref,
                confidence=0.5,  # baseline; финальный — в score_break_candidates
            )
        )
    return tuple(valid)


def score_break_candidates(
    cycles: tuple[FeedbackCycle, ...],
) -> AutoDetectInfo:
    """
    Aggregate FeedbackCycles → AutoDetectInfo с edge-pair selection.

    Per ADR-T153b §5 confidence formula (initial weights из ADR;
    calibration в Phase C):

        confidence = w1·forward_active + w2·feedback_passive
                   + w3·single_dominant + w4·impedance_norm
                   - p1·multi_cycle_penalty

    Highest-confidence FeedbackCycle → chosen edge.
    Остальные → alternatives (sorted desc by confidence).

    Raises:
        ValueError: пустой cycles tuple (нет feedback loop).

    """
    from domain.phase_margin import AutoDetectInfo  # noqa: PLC0415

    if not cycles:
        msg = 'score_break_candidates: no feedback cycles to score'
        raise ValueError(msg)

    single_dominant = 1.0 if len(cycles) == 1 else 0.0

    scored: list[tuple[FeedbackCycle, float]] = []
    for c in cycles:
        confidence = (
            _W_FORWARD_ACTIVE * c.forward_path_score
            + _W_FEEDBACK_PASSIVE * c.feedback_path_score
            + _W_SINGLE_DOMINANT * single_dominant
            + _W_IMPEDANCE * 0.5  # placeholder — Phase C calibration
        )
        if any(n in _GROUND_NETS for n in c.nodes):
            confidence -= _P_GROUND_CYCLE
        confidence = max(0.0, min(1.0, confidence))
        scored.append((c, confidence))

    scored.sort(key=lambda x: x[1], reverse=True)
    primary_cycle, primary_conf = scored[0]
    alternatives = tuple(
        (c.suggested_break_node, c.suggested_break_element_ref, conf)
        for c, conf in scored[1:]
    )
    return AutoDetectInfo(
        chosen_node=primary_cycle.suggested_break_node,
        chosen_element_ref=primary_cycle.suggested_break_element_ref,
        confidence=primary_conf,
        alternatives=alternatives,
        algorithm_notes=(
            f'{len(cycles)} feedback cycle(s); '
            f'forward={primary_cycle.forward_path_score:.2f}, '
            f'feedback={primary_cycle.feedback_path_score:.2f}'
        ),
    )


# ============================== private helpers ==============================


def _enumerate_simple_cycles(
    graph: CircuitGraph,
) -> list[tuple[list[str], list[str]]]:
    """
    Enumerate simple cycles на уровне ЭЛЕМЕНТОВ (не pairwise edges).

    Каждый element_id участвует в cycle'е не более одного раза.
    Multi-terminal elements (pairwise edges) — это всё ещё один
    логический «hop» через element_id. Cycle key — frozenset
    element_ids.

    Returns list of (net_path, element_id_list).
    """
    # adj: net → ordered list of (other_net, element_id) с дедупликацией.
    # Дедуплицируем pairwise дубли одного элемента (E_amp может иметь
    # 2 pairwise edge'а к одному net'у; нас интересует только сам факт
    # связи). Исключаем V/I sources — они закрывают топологические
    # cycles через ground/bias, не настоящий feedback.
    #
    # ВАЖНО: список, а не set. Set iteration order зависит от
    # `PYTHONHASHSEED` (для строк — randomized по умолчанию), что делает
    # DFS-порядок добавления cycles non-deterministic между runs.
    # При равном confidence у нескольких cycles primary получался разным
    # (stable sort сохранял случайный ordering из cycles list).
    adj: dict[str, list[tuple[str, str]]] = {n: [] for n in graph.nets}
    adj_seen: dict[str, set[tuple[str, str]]] = {n: set() for n in graph.nets}
    for e in graph.edges:
        if e.element_type in _NON_FEEDBACK_TYPES:
            continue
        a, b = e.net_pair
        if a == b:
            continue
        ab = (b, e.element_id)
        if ab not in adj_seen[a]:
            adj[a].append(ab)
            adj_seen[a].add(ab)
        ba = (a, e.element_id)
        if ba not in adj_seen[b]:
            adj[b].append(ba)
            adj_seen[b].add(ba)

    cycles: list[tuple[list[str], list[str]]] = []
    seen_cycle_keys: set[frozenset[str]] = set()
    net_index = {n: i for i, n in enumerate(graph.nets)}

    for start_idx, start_net in enumerate(graph.nets):
        if len(cycles) >= _MAX_CYCLES:
            break
        stack: list[tuple[str, list[str], list[str]]] = [(start_net, [start_net], [])]
        while stack:
            cur, path_nets, used_elts = stack.pop()
            if len(path_nets) > _MAX_CYCLE_LENGTH:
                continue
            used_set = set(used_elts)
            for next_net, elt_id in adj[cur]:
                if elt_id in used_set:
                    continue
                if next_net == start_net and len(path_nets) >= _MIN_CYCLE_LENGTH:
                    cycle_key = frozenset([*used_elts, elt_id])
                    if cycle_key in seen_cycle_keys:
                        continue
                    seen_cycle_keys.add(cycle_key)
                    cycles.append(([*path_nets, start_net], [*used_elts, elt_id]))
                    if len(cycles) >= _MAX_CYCLES:
                        break
                elif next_net in path_nets:
                    continue
                else:
                    # Дедупликация по start point: не ходим на net'ы с
                    # индексом < start_idx (они уже стартовали поиск).
                    if net_index[next_net] < start_idx:
                        continue
                    stack.append(
                        (
                            next_net,
                            [*path_nets, next_net],
                            [*used_elts, elt_id],
                        )
                    )
    return cycles


def _unique_preserving_order(items: Iterable[str]) -> list[str]:
    """Dedup preserving order of first appearance."""
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _pick_break_edge(
    net_path: list[str],
    element_ids: list[str],
    id_to_type: dict[str, ElementType],
) -> tuple[str, str]:
    """
    Pick break point: passive element adjacent to active в цикле walk.

    Cycle representation: net_path[i] → element_ids[i] → net_path[i+1].
    Длина element_ids = len(net_path) - 1.

    Heuristic: первый passive element в walk'е, чей **next** или
    **prev** element в цикле — active. Break_node = shared net между
    ними. Это формализует «boundary между active и passive run'ами».
    """
    n = len(element_ids)
    for i, elt_id in enumerate(element_ids):
        if id_to_type.get(elt_id) not in _PASSIVE_TYPES:
            continue
        next_elt = element_ids[(i + 1) % n]
        prev_elt = element_ids[(i - 1) % n]
        if id_to_type.get(next_elt) in _ACTIVE_TYPES:
            # boundary: passive elt_id at net_path[i+1] meets active next_elt
            return net_path[i + 1], elt_id
        if id_to_type.get(prev_elt) in _ACTIVE_TYPES:
            # boundary: passive elt_id at net_path[i] meets active prev_elt
            return net_path[i], elt_id

    # Fallback: первый passive elt, net на ИХ начале
    for i, elt_id in enumerate(element_ids):
        if id_to_type.get(elt_id) in _PASSIVE_TYPES:
            return net_path[i], elt_id

    # Не должно достижимо (find_cycles гарантирует ≥1 passive)
    msg = '_pick_break_edge: no passive element in cycle'
    raise ValueError(msg)


__all__ = [
    'CircuitEdge',
    'CircuitGraph',
    'ElementType',
    'find_cycles',
    'parse',
    'score_break_candidates',
]
