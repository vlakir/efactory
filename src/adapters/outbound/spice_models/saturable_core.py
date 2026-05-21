"""
Saturable transformer subckt generator (T131 Phase A + Phase E redesign).

Генерирует ngspice `.subckt` для saturable трансформатора используя
**XSPICE gyrator-capacitor model** (Hamill 1993): primary/secondary
обмотки через `lcouple` gyrator'ы преобразуют электрическую область
(V, I) в магнитную (MMF, dψ/dt), а нелинейная B-H curve моделируется
через XSPICE `core` element с tabulated H_array/B_array.

**Почему gyrator-capacitor, а не current-source PWL (revision):**

Первая версия (Phase A, до Phase E refactor) использовала B-source
`B_Lm` с PWL-таблицей (ψ_link, i_Lm) + capacitor-as-integrator
(`C_int N_psi 0 1 + G_int N_psi 0 N_a P2 1`). На стенде «лампа + saturable
OPT» это давало численный blow-up (magnitudes ≈ 1e+65) из-за algebraic
loop через current-source `B_Lm` и G-source лампы Koren-модели —
Newton-Raphson не сходился.

XSPICE `lcouple + core` решает все три проблемы:

1. **Нет algebraic loop**: gyrator — алгебраический элемент
   (V_e = N·I_m; I_e = (1/N)·V_m), но **нелинейная B-H модель сидит
   в магнитной области**, изолирована от electrical Newton iterations.
2. **DC-стабильность**: магнитный поток ψ интегрируется внутри core
   element'а (a_core) с собственным state, без external integrator
   capacitor'а.
3. **ngspice-native**: реализован C-кодом внутри XSPICE library;
   numerically tuned для transient analysis магнетических цепей
   (см. `transformers1.cir` пример в `ngspice/examples/various/`).

Trade-off: B-H curve задаётся не Frohlich-формулой напрямую, а
tabulated H_array/B_array (symmetric, odd-extended из FrohlichBHCurve).
ngspice `core` использует PWL с гладкой interpolation на углах
(`input_domain=0.01 fraction=true`), что устраняет non-smooth
поведение на углах таблицы — в отличие от PWL B-source.

**Topology:**

::

    P1 ── R_pri ── pri_int ─┐                         ┌─ S1
                            │ lcouple (N_pri turns)   │
    P2 ─────────────────────┘                         │
                              ↕ (magnetic mc1, mc2)   │
                            ┌─ a_core ─┐              │
                            │  (B-H)   │              │
                            └──────────┘              │
                              ↕ (magnetic 0, mc2)     │
                                                      │
                            ┌ lcouple (N_sec turns) ──┘
                            │ (reverse polarity для dot convention)
    S2 ─── sec_int ── R_sec ┘

Primary gyrator: `a1 (pri_int P2) (mc1 0) primary` — MMF от primary winding
появляется между mc1 и 0; flux integration выполняется core element'ом.

Secondary gyrator: `a2 (sec_int S2) (0 mc2) secondary` — polarity reversed
(0,mc2 vs mc1,0) для правильной dot-convention (primary + secondary MMF
суммируются на core, как в реальном transformer'е).

Core element: `a_core (mc1 mc2) magcore` — нелинейный bidirectional B-H
с tabulated curve.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adapters.outbound.fem_solver_getdp.material import FrohlichBHCurve

# Smoothing параметры XSPICE core element'а.
# input_domain=0.01 fraction=true → 1% от input span получает
# parabolic-blend interpolation на угловых точках PWL (вместо
# discontinuous derivative). Стандартный default из ngspice docs.
_CORE_INPUT_DOMAIN = 0.01
_CORE_FRACTION = 'true'


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

    h_array_literal, b_array_literal = _build_symmetric_h_b_arrays(
        bh_curve.h_b_pairs(),
    )

    return _SUBCKT_TEMPLATE.format(
        name=subckt_name,
        n_primary=n_primary,
        n_secondary=n_secondary,
        a_core=_g(a_core_m2),
        l_path=_g(l_path_m),
        r_pri=_g(r_primary_ohm),
        r_sec=_g(r_secondary_ohm),
        mu_init=bh_curve.mu_initial,
        b_sat=bh_curve.b_sat,
        h_array=h_array_literal,
        b_array=b_array_literal,
        input_domain=_CORE_INPUT_DOMAIN,
        fraction=_CORE_FRACTION,
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


def _build_symmetric_h_b_arrays(
    h_b_pairs: tuple[tuple[float, float], ...],
) -> tuple[str, str]:
    """
    Преобразовать positive-only (H, B) pairs в symmetric arrays для XSPICE.

    Frohlich curve задаётся только для B ∈ [0, b_top]. Магнитный материал
    odd-симметричен: B(-H) = -B(H). XSPICE `core` element требует **полный
    monotonic array** от minimum H до maximum H — extend'им через
    odd reflection.

    Output формат:

    - h_array: ``"[-h_max, ..., -h1, 0, h1, ..., h_max]"``
    - b_array: ``"[-b_max, ..., -b1, 0, b1, ..., b_max]"``
    """
    positive = list(h_b_pairs[1:])  # skip origin (0, 0)
    negative_reversed = [(-h, -b) for h, b in reversed(positive)]
    origin = (0.0, 0.0)
    symmetric: list[tuple[float, float]] = [
        *negative_reversed,
        origin,
        *positive,
    ]
    h_values = [_g(h) for h, _ in symmetric]
    b_values = [_g(b) for _, b in symmetric]
    return (
        '[' + ' '.join(h_values) + ']',
        '[' + ' '.join(b_values) + ']',
    )


def _g(x: float) -> str:
    """Compact float rendering для SPICE (no trailing zeros, no `e0`)."""
    return f'{x:.9g}'


_SUBCKT_TEMPLATE = """\
.SUBCKT {name} P1 P2 S1 S2
* T131 saturable transformer (XSPICE gyrator-capacitor, Hamill 1993).
* Material: mu_init={mu_init}, B_sat={b_sat} T.
* Geometry: N_pri={n_primary}, N_sec={n_secondary},
*           A_core={a_core} m^2, l_path={l_path} m.
* DCR: R_pri={r_pri} Ohm, R_sec={r_sec} Ohm.
*
* Primary side: P1 → R_pri → pri_int, lcouple to magnetic (mc1, 0).
* Secondary side: S1 → sec_int → R_sec, lcouple to magnetic (0, mc2)
* (reverse polarity for dot convention — MMF sums on core).
* a_core: nonlinear B-H curve from Frohlich-Kennelly (odd-symmetric).
*
R_pri P1 pri_int {r_pri}
a1 (pri_int P2) (mc1 0) primary_{name}
.model primary_{name} lcouple(num_turns={n_primary})
a2 (sec_int S2) (0 mc2) secondary_{name}
.model secondary_{name} lcouple(num_turns={n_secondary})
R_sec sec_int S1 {r_sec}
a_core (mc1 mc2) magcore_{name}
.model magcore_{name} core(H_array={h_array} B_array={b_array}
+ area={a_core} length={l_path}
+ input_domain={input_domain} fraction={fraction})
.ENDS {name}
"""


__all__ = ['generate_saturable_transformer_subckt']
