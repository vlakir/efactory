"""
detect_feedback_break_node — auto-detect break edge (T153 Phase B.5).

Use case wrapping `NetlistGraphAnalyzer` (parse → find_cycles →
score_break_candidates) для определения наиболее вероятного break edge
в feedback loop.

Pipeline:

1. `parse(netlist_text)` → `CircuitGraph`.
2. `find_cycles(graph)` → `tuple[FeedbackCycle, ...]`. Если пусто →
   `NoFeedbackLoopDetectedError`.
3. `score_break_candidates(cycles)` → `AutoDetectInfo`.
4. Проверка `confidence ≥ confidence_threshold`. Иначе →
   `AutoDetectConfidenceTooLowError`.

Phase B.5 — explicit-only path в `measure_phase_margin` (option B);
этот use case standalone'но возвращает AutoDetectInfo для caller'ов
(CLI в Phase B.6, integration в `measure_phase_margin` тоже B.6+).
"""

from __future__ import annotations

from domain.netlist_graph import find_cycles, parse, score_break_candidates
from domain.phase_margin import (
    AutoDetectConfidenceTooLowError,
    AutoDetectInfo,
    NoFeedbackLoopDetectedError,
)

_DEFAULT_CONFIDENCE_THRESHOLD = 0.8


def detect_feedback_break_node(
    *,
    netlist_text: str,
    confidence_threshold: float = _DEFAULT_CONFIDENCE_THRESHOLD,
) -> AutoDetectInfo:
    """
    Авто-определение break edge для phase-margin measurement.

    Args:
        netlist_text: исходный SPICE netlist.
        confidence_threshold: минимально допустимый confidence (по
            умолчанию 0.8 per Spec §3 C4 convention).

    Returns:
        `AutoDetectInfo` с chosen_node + chosen_element_ref + alternatives
        + confidence.

    Raises:
        NoFeedbackLoopDetectedError: graph не содержит valid feedback
            cycle (нет active+passive комбинации).
        AutoDetectConfidenceTooLowError: best candidate confidence
            ниже threshold (в non-TTY должно быть caught caller'ом
            с actionable error message).
        ValueError: confidence_threshold не в [0, 1].

    """
    if not (0.0 <= confidence_threshold <= 1.0):
        msg = (
            f'detect_feedback_break_node: confidence_threshold '
            f'{confidence_threshold!r} not in [0, 1]'
        )
        raise ValueError(msg)

    graph = parse(netlist_text)
    cycles = find_cycles(graph)
    if not cycles:
        msg = (
            'no feedback loop detected in netlist (no cycle with both '
            'active and passive elements); if loop exists, pass '
            '--loop-break-node + --loop-break-element explicitly'
        )
        raise NoFeedbackLoopDetectedError(msg)

    info = score_break_candidates(cycles, graph)
    if info.confidence < confidence_threshold:
        msg = (
            f'auto-detect confidence {info.confidence:.3f} below threshold '
            f'{confidence_threshold:.3f}; please pass --loop-break-node + '
            f'--loop-break-element explicitly. Best candidate: '
            f'(node={info.chosen_node!r}, element={info.chosen_element_ref!r})'
        )
        raise AutoDetectConfidenceTooLowError(msg)

    return info


__all__ = ['detect_feedback_break_node']
