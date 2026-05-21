"""
Frohlich-Kennelly nonlinear B-H material model (T129 Phase A, moved
to domain в T131 Phase E refactor).

Domain VO: cross-adapter материальная модель. Изначально жила в
`adapters/outbound/fem_solver_getdp/material.py` (T129 single-use),
переведена в domain layer в T131 Phase E когда стало consumer'ов
больше одного: GetDP FEM (ν(B) reluctivity table), ngspice saturable
transformer subckt (H-B array через XSPICE `core` element),
THD use case (FrohlichBHCurve как часть ThdSweepSpec).

Генерирует tabulated B-H кривую из 2 PyOM material параметров
(μ_initial, B_sat) для подачи в GetDP `InterpolationLinear` как
ν(B) = 1/μ_chord(B) reluctivity таблицу.

Формула Frohlich-Kennelly:
    B(H) = μ₀·μ_init·H / (1 + μ₀·μ_init·H / B_sat)
Inverse:
    H(B) = B · B_sat / (μ₀·μ_init·(B_sat − B)),    B ∈ [0, B_sat)
Chord-permeability:
    μ_chord(B) = B / H(B);   ν(B) = H(B) / B;
    ν(0) = 1 / (μ₀·μ_init)        (касательная в нуле)

PyOM 1.3.10 `bhCycle` пуст у всех 409 materials (probed 2026-05-20),
поэтому Frohlich-Kennelly — единственная analytical аппроксимация в
Phase 3 (см. T129 spec Q3 / `feedback_pyom_advisor_quirks`).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

MU_0 = 4.0e-7 * math.pi  # vacuum permeability, H/m

DEFAULT_NUM_POINTS = 16  # ≥10 по спеке; 16 даёт densely-sampled knee
MAX_B_FRACTION = 0.99  # верхняя граница B в таблице: 0.99·B_sat
MIN_NUM_POINTS = 2  # 1 точка — это не interpolation table


@dataclass(frozen=True)
class FrohlichBHCurve:
    """
    Tabulated B-H curve, сгенерированная из (μ_initial, B_sat).

    Поля:
        b_values: B[T], упорядоченные по возрастанию, b_values[0] == 0.
        h_values: H[A/m], упорядоченные по возрастанию, h_values[0] == 0.
        mu_initial: исходный параметр initial relative permeability.
        b_sat: исходный параметр saturation flux density [T].

    Создаётся через `FrohlichBHCurve.from_pyom_material(...)`.
    """

    b_values: tuple[float, ...]
    h_values: tuple[float, ...]
    mu_initial: float = field(repr=False)
    b_sat: float = field(repr=False)

    @classmethod
    def from_pyom_material(
        cls,
        *,
        mu_initial: float,
        b_sat: float,
        num_points: int = DEFAULT_NUM_POINTS,
    ) -> FrohlichBHCurve:
        """
        Сгенерировать BH-таблицу из 2 PyOM параметров.

        Args:
            mu_initial: initial relative permeability (`material.permeability.
                initial.value` в PyOM material JSON), безразмерная.
            b_sat: saturation flux density [T] (`material.saturation.value`).
            num_points: количество точек в таблице (≥2, default 16).

        Raises:
            ValueError: при невалидных параметрах.

        """
        if mu_initial <= 0.0:
            msg = f'mu_initial должен быть > 0, получено {mu_initial!r}'
            raise ValueError(msg)
        if b_sat <= 0.0:
            msg = f'b_sat должен быть > 0 (Tesla), получено {b_sat!r}'
            raise ValueError(msg)
        if num_points < MIN_NUM_POINTS:
            msg = f'num_points должен быть ≥ {MIN_NUM_POINTS}, получено {num_points!r}'
            raise ValueError(msg)

        b_top = MAX_B_FRACTION * b_sat
        # linear sampling по B: первая точка 0, последняя 0.99·B_sat
        b_vals = tuple(b_top * i / (num_points - 1) for i in range(num_points))
        h_vals = tuple(_h_from_b(b, mu_initial, b_sat) for b in b_vals)
        return cls(
            b_values=b_vals,
            h_values=h_vals,
            mu_initial=mu_initial,
            b_sat=b_sat,
        )

    def nu_of_b_table(self) -> tuple[tuple[float, float], ...]:
        """Reluctivity-таблица ν(B) = H/B; ν(0) = 1/(μ₀·μ_init) (касательная)."""
        nu_zero = 1.0 / (MU_0 * self.mu_initial)
        pairs: list[tuple[float, float]] = [(0.0, nu_zero)]
        for b, h in zip(self.b_values[1:], self.h_values[1:], strict=True):
            pairs.append((b, h / b))
        return tuple(pairs)

    def h_b_pairs(self) -> tuple[tuple[float, float], ...]:
        """(H, B) пары для ngspice PWL (T131 — companion к nu_of_b_table)."""
        return tuple(zip(self.h_values, self.b_values, strict=True))

    def as_getdp_list_literal(self) -> str:
        """Рендер `{B0, nu0, B1, nu1, ...}` для GetDP `InterpolationLinear`."""
        flat: list[str] = []
        for b, nu in self.nu_of_b_table():
            flat.append(f'{b:.9g}')
            flat.append(f'{nu:.9g}')
        return '{' + ', '.join(flat) + '}'


def _h_from_b(b: float, mu_initial: float, b_sat: float) -> float:
    """Inverse Frohlich: H = B · B_sat / (μ₀·μ_init·(B_sat − B))."""
    if b == 0.0:
        return 0.0
    return b * b_sat / (MU_0 * mu_initial * (b_sat - b))
