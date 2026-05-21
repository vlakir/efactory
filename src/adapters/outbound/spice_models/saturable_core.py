"""
Saturable transformer subckt generator (T131 Phase A).

Генерирует ngspice `.subckt` для T-model трансформатора с нелинейной
магнитной ветвью (saturation primary side) на базе Frohlich-Kennelly
B-H curve из T129 Phase A.

Topology (T-equivalent с saturable magnetizing branch):

    P1 ─── R_pri ───┬─── Ideal Trans (n) ─── R_sec ─── S1
                    │
                  B_Lm (current source, nonlinear)
                    │
    P2 ────────────┴────── Ideal Trans GND ────────── S2

`B_Lm` — magnetizing current source, controlled by flux-linkage state
ψ_link через integrator `B_psi` (Faraday): ψ_link(t) = ∫V_Lm dt.

PWL table maps ψ_link → i_Lm: для каждой Frohlich пары (H, B) генератор
вычисляет (ψ_link = N_pri·A·B, i_Lm = H·l/N_pri) — обоюдо-однозначно из
B-H и геометрии. Symmetric continuation на отрицательную сторону через
odd-symmetry (B(-H) = -B(H), значит и (ψ_link, i_Lm) одинаково odd).

Coupling secondary side через ideal-transformer reflection
(VCVS `E_sec` + CCCS `F_pri` с ratio n = N_sec/N_pri) — для MVP без
leakage inductance Lσ (вне scope T131; см. T132).

Numerical стабильность: формулировка через **VCCS+capacitor integrator**
(`G_int + C_int = ∫V_Lm dt = ψ_link`) — классический SPICE pattern для
flux-linkage state. ngspice 45.2 не поддерживает `idt()` в B-source
expressions; capacitor-as-integrator работает на всех версиях ngspice.
Current-source magnetizing branch (`B_Lm I=pwl(...)`) избегает algebraic
derivative loop типа `ddt(V(B-source-output))`, который вешает convergence
на saturation knee.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adapters.outbound.fem_solver_getdp.material import FrohlichBHCurve


def generate_saturable_transformer_subckt(
    *,
    subckt_name: str,
    n_primary: int,
    n_secondary: int,
    a_core_m2: float,
    l_path_m: float,
    r_primary_ohm: float,
    r_secondary_ohm: float,
    bh_curve: FrohlichBHCurve,
) -> str:
    """
    Сгенерировать текст ngspice `.subckt` для saturable transformer.

    Args:
        subckt_name: имя subckt'а (например ``'OPT_SE_5K_8'``); должно
            совпадать с именем X-инстанса в netlist'е, который заменяет.
        n_primary: количество витков первичной обмотки (≥1).
        n_secondary: количество витков вторичной обмотки (≥1).
        a_core_m2: cross-section area сердечника, м² (>0).
        l_path_m: mean magnetic path length, м (>0).
        r_primary_ohm: DCR первичной обмотки, Ω (≥0).
        r_secondary_ohm: DCR вторичной обмотки, Ω (≥0).
        bh_curve: B-H curve из T129 Phase A (Frohlich-Kennelly).

    Returns:
        Текст subckt'а, ready to be inlined в ngspice netlist.

    Raises:
        ValueError: при невалидных входных параметрах.

    """
    _validate_inputs(
        subckt_name=subckt_name,
        n_primary=n_primary,
        n_secondary=n_secondary,
        a_core_m2=a_core_m2,
        l_path_m=l_path_m,
        r_primary_ohm=r_primary_ohm,
        r_secondary_ohm=r_secondary_ohm,
    )

    pwl_args = _psi_to_imag_pwl_arglist(
        bh_curve.h_b_pairs(),
        n_primary=n_primary,
        a_core_m2=a_core_m2,
        l_path_m=l_path_m,
    )
    turns_ratio = n_secondary / n_primary

    return _SUBCKT_TEMPLATE.format(
        name=subckt_name,
        n_primary=n_primary,
        n_secondary=n_secondary,
        a_core=a_core_m2,
        l_path=l_path_m,
        r_pri=r_primary_ohm,
        r_sec=r_secondary_ohm,
        mu_init=bh_curve.mu_initial,
        b_sat=bh_curve.b_sat,
        turns_ratio=_g(turns_ratio),
        pwl_args=pwl_args,
    )


def _validate_inputs(
    *,
    subckt_name: str,
    n_primary: int,
    n_secondary: int,
    a_core_m2: float,
    l_path_m: float,
    r_primary_ohm: float,
    r_secondary_ohm: float,
) -> None:
    if not subckt_name or not subckt_name.strip():
        msg = f'subckt_name не может быть пустым, получено {subckt_name!r}'
        raise ValueError(msg)
    if n_primary < 1:
        msg = f'n_primary должен быть ≥ 1, получено {n_primary!r}'
        raise ValueError(msg)
    if n_secondary < 1:
        msg = f'n_secondary должен быть ≥ 1, получено {n_secondary!r}'
        raise ValueError(msg)
    if a_core_m2 <= 0.0:
        msg = f'a_core_m2 должен быть > 0, получено {a_core_m2!r}'
        raise ValueError(msg)
    if l_path_m <= 0.0:
        msg = f'l_path_m должен быть > 0, получено {l_path_m!r}'
        raise ValueError(msg)
    if r_primary_ohm < 0.0:
        msg = f'r_primary_ohm должен быть ≥ 0, получено {r_primary_ohm!r}'
        raise ValueError(msg)
    if r_secondary_ohm < 0.0:
        msg = f'r_secondary_ohm должен быть ≥ 0, получено {r_secondary_ohm!r}'
        raise ValueError(msg)


def _psi_to_imag_pwl_arglist(
    h_b_pairs: tuple[tuple[float, float], ...],
    *,
    n_primary: int,
    a_core_m2: float,
    l_path_m: float,
) -> str:
    """
    Построить symmetric (ψ_link, i_Lm) PWL arglist для ngspice ``pwl(...)``.

    Преобразование Frohlich (H, B) → (ψ_link, i_Lm) по формулам:

        ψ_link = N_pri · A_core · B
        i_Lm   = H · l_path / N_pri

    Symmetric continuation (odd-symmetry):
        (..., (-ψ_N, -i_N), ..., (-ψ_1, -i_1), (0, 0), (ψ_1, i_1), ..., (ψ_N, i_N))
    """
    positive = [
        (n_primary * a_core_m2 * b, h * l_path_m / n_primary)
        for h, b in h_b_pairs[1:]  # skip origin (0, 0)
    ]
    negative_reversed = tuple(reversed([(-p, -i) for p, i in positive]))
    origin = (0.0, 0.0)
    symmetric = (*negative_reversed, origin, *positive)
    flat: list[str] = []
    for psi, i_lm in symmetric:
        flat.append(_g(psi))
        flat.append(_g(i_lm))
    return ', '.join(flat)


def _g(x: float) -> str:
    """Compact float rendering для SPICE (no trailing zeros, no `e0`)."""
    return f'{x:.9g}'


_SUBCKT_TEMPLATE = """\
.SUBCKT {name} P1 P2 S1 S2
* T131 saturable transformer (Frohlich-Kennelly B-H, T-model).
* Material: mu_init={mu_init}, B_sat={b_sat} T.
* Geometry: N_pri={n_primary}, N_sec={n_secondary},
*           A_core={a_core} m^2, l_path={l_path} m.
* DCR: R_pri={r_pri} Ohm, R_sec={r_sec} Ohm.
* turns_ratio (N_sec/N_pri) = {turns_ratio}.
*
* Flux-linkage integrator (VCCS + capacitor = SPICE classic pattern):
*   i_G = V(N_a, P2);  V(N_psi) = ∫i_G dt / C = ∫V_Lm dt = psi_link.
* Magnetizing branch (saturable): current source B_Lm via PWL lookup
* (psi_link → i_Lm), symmetric (odd) extension from Frohlich pairs.
* Secondary side: ideal-transformer reflection (no leakage in MVP).
*
R_pri P1 N_a {r_pri}
G_int N_psi 0 N_a P2 1
C_int N_psi 0 1
B_Lm N_a P2 I=pwl(V(N_psi), {pwl_args})
V_jsense N_c N_d DC 0
E_sec N_c S2 N_a P2 {turns_ratio}
F_pri N_a P2 V_jsense {turns_ratio}
R_sec N_d S1 {r_sec}
.ENDS {name}
"""


__all__ = ['generate_saturable_transformer_subckt']
