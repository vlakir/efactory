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
