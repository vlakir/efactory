"""
AnalyticalLeakage — implementing `LeakageInductanceAnalyzer` port (T132 Phase C).

Pure-Python interleaved sandwich-transformer leakage Lσ через Erickson
formula (см. `formula.py`); geometry resolution через PyOM catalog
lookups (`geometry.py`); self-inductance L_self для coupling_factor —
inject'ится через `MagneticAnalytics` port (composition root инжектит
`PyOpenMagneticsAnalytics` instance).

Этот adapter — primary leakage backend в efactory; PyOM
`calculate_leakage_inductance` исключён из pipeline после Phase B
investigation (mesh backend broken, см. T135 BACKLOG).
"""

from __future__ import annotations

import asyncio
import math
from typing import TYPE_CHECKING, Any

from adapters.outbound.leakage_inductance_analytical.formula import (
    compute_leakage_inductance_h,
)
from adapters.outbound.leakage_inductance_analytical.geometry import (
    GeometryResolutionError,
    estimate_winding_thickness_m,
    resolve_core_geometry,
    resolve_wire_outer_diameter_m,
)
from domain.magnetic import LeakageInductanceResult
from ports.outbound.leakage_inductance_analyzer import (
    LeakageInductanceAnalyzerFailedError,
)

if TYPE_CHECKING:
    from domain.magnetic import MagneticComponent
    from ports.outbound.magnetic_analytics import MagneticAnalytics


class AnalyticalLeakage:
    """
    `LeakageInductanceAnalyzer` adapter поверх Erickson sandwich formula.

    Зависимости (DI):
    - `pyom_module` — PyOpenMagnetics .so handle (catalog-only access:
      `calculate_core_data`, `find_wire_by_name`).
    - `inductance_port` — `MagneticAnalytics` Protocol для L_self_primary
      (нужно для `coupling_factor`); typically `PyOpenMagneticsAnalytics`
      из composition.
    """

    def __init__(
        self,
        pyom_module: Any,  # noqa: ANN401
        inductance_port: MagneticAnalytics,
    ) -> None:
        self._pyom = pyom_module
        self._inductance = inductance_port

    async def calculate_leakage_inductance(
        self,
        component: MagneticComponent,
        source_winding: str | None = None,
    ) -> LeakageInductanceResult:
        return await self._compute(component, source_winding)

    async def _compute(
        self,
        component: MagneticComponent,
        source_winding: str | None,
    ) -> LeakageInductanceResult:
        if component.section_layout is None:
            msg = (
                f'analytical leakage расчёт для {component.name!r} '
                f'требует section_layout (interleaved pattern); '
                f'установите MagneticComponent.section_layout.'
            )
            raise LeakageInductanceAnalyzerFailedError(msg)

        layout = component.section_layout
        windings_by_name = {w.name: w for w in component.windings}

        if source_winding is None:
            try:
                source_name = component.primary_winding.name
            except ValueError as exc:
                msg = f'leakage source winding resolution failed: {exc}'
                raise LeakageInductanceAnalyzerFailedError(msg) from exc
        else:
            source_name = source_winding

        if source_name not in windings_by_name:
            msg = (
                f'source_winding={source_name!r} не найден в '
                f'{component.name!r}; available: {sorted(windings_by_name)}'
            )
            raise LeakageInductanceAnalyzerFailedError(msg)

        # Geometry — может быть expensive (PyOM C++ call), throw в executor.
        try:
            geom = await asyncio.to_thread(
                resolve_core_geometry,
                self._pyom,
                component,
            )
        except GeometryResolutionError as exc:
            msg = f'analytical leakage geometry resolution failed: {exc}'
            raise LeakageInductanceAnalyzerFailedError(msg) from exc

        thicknesses_m = await asyncio.to_thread(
            self._compute_winding_thicknesses,
            component,
            geom.window_height_m,
        )

        source_thickness = thicknesses_m[source_name]
        targets_thickness_sum = sum(
            t for name, t in thicknesses_m.items() if name != source_name
        )

        source_turns = windings_by_name[source_name].number_turns
        leakage_total_h = compute_leakage_inductance_h(
            primary_turns=source_turns,
            mean_turn_length_m=geom.mean_turn_length_m,
            window_height_m=geom.window_height_m,
            primary_thickness_m=source_thickness,
            secondary_thickness_m=targets_thickness_sum,
            inter_section_insulation_m=layout.inter_section_thickness_m,
            pattern=layout.pattern,
        )

        # Distribute Lσ_total между target обмотками weighted by turns²
        # (proxy для magnetic coupling strength).
        total_targets_turn_sq = sum(
            windings_by_name[name].number_turns ** 2
            for name in windings_by_name
            if name != source_name
        )
        leakage_to: dict[str, float] = {}
        for name, w in windings_by_name.items():
            if name == source_name:
                continue
            weight = (
                w.number_turns**2 / total_targets_turn_sq
                if total_targets_turn_sq > 0
                else 0.0
            )
            leakage_to[name] = leakage_total_h * weight

        # Coupling factor — нужна L_self_primary для k = √(1 - Lσ_total/L_self).
        try:
            l_self_h = await self._inductance.calculate_inductance(component)
        except Exception as exc:
            msg = (
                f'analytical leakage не смог получить L_self '
                f'(для coupling_factor): {exc}'
            )
            raise LeakageInductanceAnalyzerFailedError(msg) from exc

        if l_self_h <= 0:
            k = 0.0
        else:
            raw_k_sq = 1.0 - leakage_total_h / l_self_h
            k = math.sqrt(raw_k_sq) if raw_k_sq > 0 else 0.0
            k = min(k, 1.0)

        return LeakageInductanceResult(
            source_winding=source_name,
            leakage_to=leakage_to,
            coupling_factor=k,
        )

    def _compute_winding_thicknesses(
        self,
        component: MagneticComponent,
        window_height_m: float,
    ) -> dict[str, float]:
        """Per-winding total radial thickness в окне (всеми секциями)."""
        thicknesses: dict[str, float] = {}
        for w in component.windings:
            if w.wire_name is None:
                msg = (
                    f'winding {w.name!r} имеет wire_name=None; '
                    f'analytical leakage требует explicit wire для '
                    f'computing thickness'
                )
                raise LeakageInductanceAnalyzerFailedError(msg)
            try:
                od = resolve_wire_outer_diameter_m(self._pyom, w.wire_name)
                thickness = estimate_winding_thickness_m(
                    total_turns=w.number_turns,
                    wire_outer_diameter_m=od,
                    window_height_m=window_height_m,
                )
            except GeometryResolutionError as exc:
                msg = (
                    f'analytical leakage winding thickness resolution '
                    f'failed для {w.name!r}: {exc}'
                )
                raise LeakageInductanceAnalyzerFailedError(msg) from exc
            thicknesses[w.name] = thickness
        return thicknesses
