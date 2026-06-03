"""
Physically-meaningful bounds для fitter'а (T031 §3 Functional Requirements).

Тuples `(lower, upper)`. Использует scipy.curve_fit вариант
`bounds=(lower_array, upper_array)` (A-C1: `method='trf'` обязателен
вместе с bounds — LM их не поддерживает).
"""

from __future__ import annotations

from typing import Final

KorenTriodeBounds = dict[str, tuple[float, float]]

KOREN_TRIODE_BOUNDS: Final[KorenTriodeBounds] = {
    'mu': (1.0, 500.0),
    'ex': (1.05, 2.95),
    'kg1': (1.0, 1e8),
    'kp': (1.0, 5000.0),
    'kvb': (1.0, 5000.0),
    'vct': (0.0, 5.0),
}

AYUMI_PENTODE_BOUNDS: Final[KorenTriodeBounds] = {
    'mu': (1.0, 500.0),
    'ex': (1.05, 2.95),
    'kg1': (1.0, 1e8),
    'kg2': (1.0, 1e8),
    'kp': (1.0, 5000.0),
    'kvb': (1.0, 1000.0),
}

# Типовой initial guess для multi-start: small-signal preamp triode.
KOREN_TRIODE_TYPICAL: Final[dict[str, float]] = {
    'mu': 70.0,
    'ex': 1.4,
    'kg1': 1500.0,
    'kp': 300.0,
    'kvb': 200.0,
    'vct': 0.5,
}

# Типовой initial guess для multi-start: audio output pentode.
AYUMI_PENTODE_TYPICAL: Final[dict[str, float]] = {
    'mu': 10.0,
    'ex': 1.3,
    'kg1': 1000.0,
    'kg2': 4000.0,
    'kp': 50.0,
    'kvb': 20.0,
}

# ============================== T182: modified variants ==============================

KOREN_MODIFIED_KNEE_PENTODE_BOUNDS: Final[KorenTriodeBounds] = {
    'mu': (1.0, 500.0),
    'ex': (1.05, 2.95),
    'kg1': (1.0, 1e8),
    'kg2': (1.0, 1e8),
    'kp': (1.0, 5000.0),
    'kvb': (1.0, 1000.0),
    'vk': (5.0, 500.0),
}
"""T182 §5: pentode-modified-knee. `vk` lower bound = 5 V — слишком
малый Vk даёт numerically-stiff gradient (sharp step), curve_fit
расходится."""

KOREN_MODIFIED_KNEE_PENTODE_TYPICAL: Final[dict[str, float]] = {
    'mu': 10.0,
    'ex': 1.3,
    'kg1': 1000.0,
    'kg2': 4000.0,
    'kp': 50.0,
    'kvb': 20.0,
    'vk': 50.0,
}

KOREN_MODIFIED_CUTOFF_TRIODE_BOUNDS: Final[KorenTriodeBounds] = {
    'mu': (1.0, 500.0),
    'ex': (1.05, 2.95),
    'kg1': (1.0, 1e8),
    'kp': (1.0, 5000.0),
    'kvb': (1.0, 5000.0),
    'vc_off': (-200.0, -0.5),
    'vs_off': (0.5, 30.0),
}
"""T182 §5: triode-modified-cutoff. `vc_off` negative range — A-W3
требует linear-uniform sampling (log-uniform не работает с negatives).
`vct` НЕ участвует (mutually-exclusive с этим variant'ом — A-W1)."""

# Two typicals для multi-start: small-signal preamp triode (как для
# canonical) и power triode (300B-style). Multi-start tries оба.
KOREN_MODIFIED_CUTOFF_TRIODE_TYPICAL: Final[dict[str, float]] = {
    'mu': 70.0,
    'ex': 1.4,
    'kg1': 1500.0,
    'kp': 300.0,
    'kvb': 200.0,
    'vc_off': -5.0,
    'vs_off': 1.0,
}
"""Small-signal preamp triode anchor (как 12AX7-ish с резким cutoff)."""

KOREN_MODIFIED_CUTOFF_TRIODE_POWER_TYPICAL: Final[dict[str, float]] = {
    'mu': 4.0,
    'ex': 1.4,
    'kg1': 1500.0,
    'kp': 800.0,
    'kvb': 200.0,
    'vc_off': -50.0,
    'vs_off': 5.0,
}
"""Power triode anchor (300B-ish). A-N2: добавлен как 2-ой start."""
