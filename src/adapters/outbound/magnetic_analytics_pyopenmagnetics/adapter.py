"""
PyOpenMagnetics analytical inductance adapter (T113 Phase 2B).

Реализует `MagneticAnalytics` outbound port: вычисляет primary
self-inductance через PyOM `calculate_inductance_from_number_turns_and_gapping`.
Это host-safe analytical путь (без `design_*` / `calculate_advised_*` —
последние выжирают > 6 GB RAM, см. `feedback_pyopenmagnetics_advisor_oom`
в auto-memory).

PyOM package не имеет `__init__.py` (см. AGENTS.md §2) — нужно importlib
boilerplate для загрузки .so binding. Loader реализован в
`load_pyopenmagnetics()` (вызывается один раз в `composition`).

5 reluctance моделей доступны в PyOM (ZHANG / MUEHLETHALER /
BALAKRISHNAN / STENGLEIN / EFFECTIVE_AREA); адаптер использует ZHANG
по умолчанию (matches pilot baseline).
"""

from __future__ import annotations

import asyncio
import importlib.util
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ports.outbound.magnetic_analytics import (
    MagneticAnalyticsFailedError,
    MagneticAnalyticsUnavailableError,
)

if TYPE_CHECKING:
    from domain.magnetic import MagneticComponent, Winding

DEFAULT_RELUCTANCE_MODEL = 'ZHANG'
# PyOM требует поле wire в каждой winding (schema validation в C++);
# для inductance расчётов wire diameter не используется (только для
# winding losses) — generic round 0.5mm grade 1 как sane default
# когда Winding.wire_name is None.
DEFAULT_WIRE_NAME = 'Round 0.5 - Grade 1'
_WAVEFORM_SAMPLES = 32  # 1 period @ frequency_hz; consistency с pilot build_fixture


def load_pyopenmagnetics() -> Any:  # noqa: ANN401  - PyOM module is dynamic .so
    """
    Загрузить PyOpenMagnetics через importlib (no __init__.py — AGENTS.md §2).

    Бросает `MagneticAnalyticsUnavailableError`, если wheel не установлен
    или binary .so не найден в venv.
    """
    try:
        pkg_path_str = __import__('PyOpenMagnetics').__path__[0]
    except ImportError as exc:
        msg = f'PyOpenMagnetics не установлен в venv: {exc}'
        raise MagneticAnalyticsUnavailableError(msg) from exc
    pkg_dir = Path(pkg_path_str).parent / 'PyOpenMagnetics'
    so_files = sorted(pkg_dir.glob('PyOpenMagnetics.cpython-*'))
    if not so_files:
        msg = f'PyOpenMagnetics .so не найден в {pkg_dir}'
        raise MagneticAnalyticsUnavailableError(msg)
    spec = importlib.util.spec_from_file_location('PyOpenMagnetics', so_files[0])
    if spec is None or spec.loader is None:
        msg = f'не удалось создать importlib spec для {so_files[0]}'
        raise MagneticAnalyticsUnavailableError(msg)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.load_databases({})
    return mod


def _sine_waveform(
    frequency_hz: float,
    peak: float,
    dc: float = 0.0,
) -> dict[str, list[float]]:
    """32-точечный sine waveform — minimal требование PyOM excitation."""
    period = 1.0 / frequency_hz
    times = [i * period / _WAVEFORM_SAMPLES for i in range(_WAVEFORM_SAMPLES)]
    data = [dc + peak * math.sin(2.0 * math.pi * frequency_hz * t) for t in times]
    return {'data': data, 'time': times}


def _build_winding_dict(w: Winding) -> dict[str, Any]:
    return {
        'name': w.name,
        'numberTurns': w.number_turns,
        'numberParallels': 1,
        'isolationSide': w.isolation_side.value,
        'wire': w.wire_name if w.wire_name is not None else DEFAULT_WIRE_NAME,
    }


class PyOpenMagneticsAnalytics:
    """
    `MagneticAnalytics` adapter поверх PyOpenMagnetics.

    Инстанцируется через `load_pyopenmagnetics()`-based factory в
    composition (DI). Содержит загруженный PyOM модуль как member,
    чтобы избежать перезагрузки .so на каждый вызов.
    """

    def __init__(
        self,
        pyom_module: Any,  # noqa: ANN401  - dynamic .so module
        *,
        reluctance_model: str = DEFAULT_RELUCTANCE_MODEL,
    ) -> None:
        self._pyom = pyom_module
        self._reluctance = reluctance_model

    async def calculate_inductance(
        self,
        component: MagneticComponent,
    ) -> float:
        """Async wrapper над blocking PyOM C++ call (asyncio.to_thread)."""
        return await asyncio.to_thread(self._calculate_blocking, component)

    def _find_bobbin(self, name: str) -> dict[str, Any]:
        for b in self._pyom.get_bobbins():
            if b.get('name') == name:
                return b
        msg = f'PyOM bobbin {name!r} не найден в catalog'
        raise MagneticAnalyticsFailedError(msg)

    def _calculate_blocking(self, component: MagneticComponent) -> float:
        core_fd = {
            'functionalDescription': {
                'type': 'two-piece set',
                'material': component.core.material_name,
                'shape': component.core.shape_name,
                'gapping': [
                    {
                        'type': component.core.gap_type.value,
                        'length': component.core.gap_length_m,
                    },
                ],
                'numberStacks': 1,
            },
        }
        try:
            core_full = self._pyom.calculate_core_data(
                core_fd,
                True,  # noqa: FBT003  - PyOM C++ binding не принимает kwargs
            )
        except Exception as exc:
            msg = (
                f'PyOM calculate_core_data failed для shape='
                f'{component.core.shape_name!r}, material='
                f'{component.core.material_name!r}: {exc}'
            )
            raise MagneticAnalyticsFailedError(msg) from exc

        if component.core.bobbin_name is None:
            msg = (
                f'PyOM analytical требует bobbin для shape='
                f'{component.core.shape_name!r}; задайте Core.bobbin_name '
                f'(каталог: pyom.get_bobbins())'
            )
            raise MagneticAnalyticsFailedError(msg)
        bobbin = self._find_bobbin(component.core.bobbin_name)
        coil = {
            'functionalDescription': [
                _build_winding_dict(w) for w in component.windings
            ],
            'bobbin': bobbin,
        }

        op = component.operating_point
        primary_voltage = _sine_waveform(
            op.frequency_hz,
            op.primary_peak_voltage_v,
        )
        primary_current = _sine_waveform(
            op.frequency_hz,
            op.primary_ac_peak_a,
            dc=op.primary_dc_bias_a,
        )
        excitations = [
            {
                'frequency': op.frequency_hz,
                'voltage': {'waveform': primary_voltage},
                'current': {'waveform': primary_current},
            }
            for _ in component.windings
        ]
        operating_point = {
            'name': op.name,
            'conditions': {'ambientTemperature': op.ambient_temperature_c},
            'excitationsPerWinding': excitations,
        }

        try:
            lp = self._pyom.calculate_inductance_from_number_turns_and_gapping(
                core_full,
                coil,
                operating_point,
                {'reluctance': self._reluctance},
            )
        except Exception as exc:
            msg = (
                f'PyOM calculate_inductance failed для component='
                f'{component.name!r} (reluctance={self._reluctance}): {exc}'
            )
            raise MagneticAnalyticsFailedError(msg) from exc

        return float(lp)
