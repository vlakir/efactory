"""
PyOpenMagnetics analytical adapter (T113 Phase 2B + T132 Phase B).

Реализует ДВА outbound port'а:
- `MagneticAnalytics` — primary self-inductance через PyOM
  `calculate_inductance_from_number_turns_and_gapping`.
- `LeakageInductanceAnalyzer` — leakage Lσ через PyOM `wind` +
  `calculate_leakage_inductance` (T132).

Composite adapter pattern: один загруженный .so handle (`self._pyom`),
shared helpers (`_build_operating_point`, `_build_winding_dict`,
`_find_bobbin`). SRP per Protocol сохраняется на уровне port'ов; class
имплементит оба.

Host-safe analytical путь — без `design_*` / `calculate_advised_*`
(выжирают > 6 GB RAM, см. `feedback_pyopenmagnetics_advisor_oom`).

PyOM package не имеет `__init__.py` — нужно importlib boilerplate для
загрузки .so binding; `load_pyopenmagnetics()` вызывается один раз в
`composition`.

5 reluctance моделей доступны в PyOM (ZHANG / MUEHLETHALER /
BALAKRISHNAN / STENGLEIN / EFFECTIVE_AREA); адаптер использует ZHANG
по умолчанию (matches pilot baseline). Leakage путь использует PyOM
default leakage method (probe: `methodUsed='Energy'`).
"""

from __future__ import annotations

import asyncio
import importlib.util
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any

from domain.magnetic import LeakageInductanceResult
from ports.outbound.leakage_inductance_analyzer import (
    LeakageInductanceAnalyzerFailedError,
)
from ports.outbound.magnetic_analytics import (
    MagneticAnalyticsFailedError,
    MagneticAnalyticsUnavailableError,
)

if TYPE_CHECKING:
    from domain.magnetic import (
        InterleavingPattern,
        MagneticComponent,
        Winding,
    )

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
    или binary .so не найден в venv. (Тот же error type для обоих port'ов
    — leakage port имеет alias `LeakageInductanceAnalyzerUnavailableError`,
    raise происходит до class instantiation.)
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


# ---------------------------------------------------------------------------
# T132: leakage-path helpers (module-level, PyOM-agnostic)
# ---------------------------------------------------------------------------

# E 42/15 stack length [m] — fallback для bobbin columnDepth когда core
# processedDescription не содержит depth-like поля. Зафиксировано на pilot
# fixture; TODO: extract из core_full для произвольных shape'ов.
_E42_15_STACK_LENGTH_M = 0.015
_BOBBIN_COLUMN_DEPTH_GARBAGE_THRESHOLD = 1e-6


def _translate_pattern_to_indices(
    layout: InterleavingPattern,
    windings: tuple[Winding, ...],
) -> list[int]:
    """
    Перевести `layout.pattern` (имена обмоток) → indices в `windings` tuple.

    `pyom.wind` требует pattern как `list[int]` (0-based позиции в
    `coil.functionalDescription`). Domain хранит имена для читаемости;
    конверсия здесь (Analyze §A1).

    Hardening: бросает ValueError, если имя в pattern не присутствует
    в windings — обычно это validated на уровне `MagneticComponent`,
    но helper не должен trust input blindly.
    """
    name_to_index = {w.name: i for i, w in enumerate(windings)}
    indices: list[int] = []
    for section in layout.sections:
        idx = name_to_index.get(section.winding_name)
        if idx is None:
            msg = (
                f'unknown winding name {section.winding_name!r} in '
                f'interleaving pattern; available: {sorted(name_to_index)}'
            )
            raise ValueError(msg)
        indices.append(idx)
    return indices


def _normalize_bobbin_columns(
    bobbin: dict[str, Any],
    core_full: dict[str, Any],
) -> dict[str, Any]:
    """
    Заполнить null/garbage поля `processedDescription.columnWidth/Depth`.

    PyOM bobbin'ы из `get_bobbins()` имеют `columnWidth=None` и
    `columnDepth ≈ 5e-315` (uninitialized memory) — `calculate_leakage_
    inductance` падает на raw bobbin (Analyze §A2, probe confirmed).

    Заполняем:
    - `columnWidth` ← `functionalDescription.windingWindow.width`.
    - `columnDepth` ← `core_full.processedDescription.depth` (если есть),
       иначе fallback `_E42_15_STACK_LENGTH_M` (pilot E 42/15).

    Возвращает **новый** dict (не мутирует input).
    """
    new_bobbin = dict(bobbin)
    pd = dict(bobbin.get('processedDescription') or {})

    if not pd.get('columnWidth'):
        fd = bobbin.get('functionalDescription') or {}
        ww_raw = fd.get('windingWindow') or fd.get('windingWindows')
        if isinstance(ww_raw, list) and ww_raw:
            ww = ww_raw[0]
        elif isinstance(ww_raw, dict):
            ww = ww_raw
        else:
            ww = {}
        width = ww.get('width')
        if width:
            pd['columnWidth'] = float(width)

    existing_depth = pd.get('columnDepth')
    if (
        existing_depth is None
        or not isinstance(existing_depth, (int, float))
        or existing_depth < _BOBBIN_COLUMN_DEPTH_GARBAGE_THRESHOLD
    ):
        core_pd = core_full.get('processedDescription') or {}
        depth = core_pd.get('depth')
        pd['columnDepth'] = float(depth) if depth else _E42_15_STACK_LENGTH_M

    new_bobbin['processedDescription'] = pd
    return new_bobbin


def _parse_leakage_result(
    pyom_result: dict[str, Any],
    *,
    component: MagneticComponent,
    source_index: int,
    l_self_primary_h: float,
) -> LeakageInductanceResult:
    """
    Распарсить PyOM `calculate_leakage_inductance` dict → domain VO.

    Shape (probe-confirmed):
    ```
    {'leakageInductancePerWinding': [{'nominal': float, ...}, ...],
     'methodUsed': 'Energy', 'origin': 'simulation'}
    ```

    Entry по `source_index` — self-leakage (PyOM convention: 0.0);
    остальные — Lσ от source ко всем target обмоткам.

    `coupling_factor` k = √(1 - Lσ_to_first_target / L_self_primary),
    clamp'нутый в [0, 1] (физически k ∈ (0, 1]; защита от
    численного < 0 при `Lσ > L_self`, что possible на патологических
    fixture'ах).
    """
    per_winding = pyom_result.get('leakageInductancePerWinding') or []
    if len(per_winding) != len(component.windings):
        msg = (
            f'PyOM leakageInductancePerWinding length {len(per_winding)} '
            f'!= component.windings length {len(component.windings)}'
        )
        raise ValueError(msg)

    leakage_to: dict[str, float] = {}
    for i, entry in enumerate(per_winding):
        if i == source_index:
            continue
        nominal = entry.get('nominal') if isinstance(entry, dict) else None
        if nominal is None:
            msg = (
                f'PyOM leakage entry #{i} имеет nominal=None '
                f'(winding={component.windings[i].name!r})'
            )
            raise ValueError(msg)
        leakage_to[component.windings[i].name] = float(nominal)

    first_target_leakage = next(iter(leakage_to.values()))
    raw_k_squared = 1.0 - first_target_leakage / l_self_primary_h
    k = math.sqrt(raw_k_squared) if raw_k_squared > 0 else 0.0
    k = min(k, 1.0)

    return LeakageInductanceResult(
        source_winding=component.windings[source_index].name,
        leakage_to=leakage_to,
        coupling_factor=k,
    )


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

    async def calculate_leakage_inductance(
        self,
        component: MagneticComponent,
        source_winding: str | None = None,
    ) -> LeakageInductanceResult:
        """
        Async wrapper над blocking PyOM leakage call (T132 Phase B).

        `source_winding=None` → берётся `component.primary_winding.name`.
        Backend: `pyom.wind(coil, len(pattern), proportion, pattern,
        margin_pairs)` → `pyom.calculate_leakage_inductance(magnetic,
        freq, source_index)`.
        """
        return await asyncio.to_thread(
            self._calculate_leakage_blocking,
            component,
            source_winding,
        )

    def _find_bobbin(self, name: str) -> dict[str, Any]:
        for b in self._pyom.get_bobbins():
            if b.get('name') == name:
                return b
        msg = f'PyOM bobbin {name!r} не найден в catalog'
        raise MagneticAnalyticsFailedError(msg)

    def _build_core_full(self, component: MagneticComponent) -> dict[str, Any]:
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
            return self._pyom.calculate_core_data(
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

    def _build_operating_point(
        self,
        component: MagneticComponent,
    ) -> dict[str, Any]:
        """
        Построить PyOM `operatingPoint` JSON с одним waveform на все обмотки.

        Shared между magnetizing inductance и leakage path'ами
        (T132 Analyze §W2). Excitation копируется на каждую обмотку —
        PyOM требует `excitationsPerWinding` длины len(windings); для
        leakage расчёта фактически используется только source winding
        excitation.
        """
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
        return {
            'name': op.name,
            'conditions': {'ambientTemperature': op.ambient_temperature_c},
            'excitationsPerWinding': excitations,
        }

    def _require_bobbin(self, component: MagneticComponent) -> dict[str, Any]:
        if component.core.bobbin_name is None:
            msg = (
                f'PyOM analytical требует bobbin для shape='
                f'{component.core.shape_name!r}; задайте Core.bobbin_name '
                f'(каталог: pyom.get_bobbins())'
            )
            raise MagneticAnalyticsFailedError(msg)
        return self._find_bobbin(component.core.bobbin_name)

    def _calculate_blocking(self, component: MagneticComponent) -> float:
        core_full = self._build_core_full(component)
        bobbin = self._require_bobbin(component)
        coil = {
            'functionalDescription': [
                _build_winding_dict(w) for w in component.windings
            ],
            'bobbin': bobbin,
        }
        operating_point = self._build_operating_point(component)

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

    def _calculate_leakage_blocking(
        self,
        component: MagneticComponent,
        source_winding: str | None,
    ) -> LeakageInductanceResult:
        """
        Blocking путь для leakage Lσ (T132 Phase B).

        Шаги:
        1. Validate `section_layout` присутствует, `source_winding`
           разрешён.
        2. Build core_full + coil dict + operating_point (shared helpers).
        3. `pyom.wind(coil, ...)` — layered coil description.
        4. Patch wound bobbin columns (`_normalize_bobbin_columns`).
        5. `pyom.calculate_leakage_inductance(magnetic, freq, idx)`.
        6. Self-call `calculate_inductance` для L_self (нужно для k).
        7. `_parse_leakage_result` → domain VO.
        """
        if component.section_layout is None:
            msg = (
                f'leakage расчёт для {component.name!r} требует '
                f'section_layout (interleaved pattern); component передан '
                f'без layout — установите MagneticComponent.section_layout.'
            )
            raise LeakageInductanceAnalyzerFailedError(msg)

        if source_winding is None:
            source_name = component.primary_winding.name
        else:
            source_name = source_winding
        name_to_index = {w.name: i for i, w in enumerate(component.windings)}
        source_index = name_to_index.get(source_name)
        if source_index is None:
            msg = (
                f'source_winding={source_name!r} не найден в '
                f'{component.name!r}; available: {sorted(name_to_index)}'
            )
            raise LeakageInductanceAnalyzerFailedError(msg)

        core_full = self._build_core_full(component)
        bobbin = self._require_bobbin(component)
        coil = {
            'functionalDescription': [
                _build_winding_dict(w) for w in component.windings
            ],
            'bobbin': bobbin,
        }

        layout = component.section_layout
        pattern_indices = _translate_pattern_to_indices(layout, component.windings)
        proportion = self._compute_proportion(pattern_indices, len(component.windings))
        margin_pairs = [[layout.bobbin_margin_m, layout.bobbin_margin_m]]

        try:
            wound_coil = self._pyom.wind(
                coil,
                len(pattern_indices),
                proportion,
                pattern_indices,
                margin_pairs,
            )
        except Exception as exc:
            msg = (
                f'PyOM wind failed для {component.name!r} pattern='
                f'{layout.pattern}: {exc}'
            )
            raise LeakageInductanceAnalyzerFailedError(msg) from exc

        # T132 Analyze §W1: PyOM эмитит "exception-as-data" — при
        # turns-don't-fit / bad-geometry wind возвращает str с error
        # вместо dict. Surface как fail-loud, не silent AttributeError.
        if not isinstance(wound_coil, dict):
            msg = (
                f'PyOM wind вернул non-dict (type='
                f'{type(wound_coil).__name__}) для {component.name!r} '
                f'pattern={layout.pattern}; возможные причины: '
                f'turns не помещаются в window для wire_name'
                f' или геометрия bobbin/core несовместима. '
                f'Payload (truncated): {str(wound_coil)[:200]}'
            )
            raise LeakageInductanceAnalyzerFailedError(msg)

        # PyOM `wind` иногда заменяет coil['bobbin'] на string-имя
        # (вместо полного dict) — fall back на original bobbin dict.
        wound_bobbin = wound_coil.get('bobbin')
        if not isinstance(wound_bobbin, dict):
            wound_bobbin = bobbin
        wound_coil['bobbin'] = _normalize_bobbin_columns(wound_bobbin, core_full)

        operating_point = self._build_operating_point(component)
        magnetic = {
            'core': core_full,
            'coil': wound_coil,
            'operatingPoint': operating_point,
        }
        try:
            leakage_dict = self._pyom.calculate_leakage_inductance(
                magnetic,
                component.operating_point.frequency_hz,
                source_index,
            )
        except Exception as exc:
            msg = (
                f'PyOM calculate_leakage_inductance failed для '
                f'{component.name!r} source={source_name!r}: {exc}'
            )
            raise LeakageInductanceAnalyzerFailedError(msg) from exc

        # T132 Analyze §W1: PyOM эмитит "exception-as-data" — leakage
        # backend требует FEM/mesh deps (доступны в efactory:linux,
        # не на bare host). Detection here surfaces clear error.
        if (
            isinstance(leakage_dict, dict)
            and isinstance(leakage_dict.get('data'), str)
            and 'Exception:' in leakage_dict['data']
        ):
            msg = (
                f'PyOM leakage backend error для {component.name!r}: '
                f'{leakage_dict["data"]}'
            )
            raise LeakageInductanceAnalyzerFailedError(msg)

        l_self_primary_h = self._calculate_blocking(component)

        return _parse_leakage_result(
            leakage_dict,
            component=component,
            source_index=source_index,
            l_self_primary_h=l_self_primary_h,
        )

    @staticmethod
    def _compute_proportion(
        pattern_indices: list[int],
        num_windings: int,
    ) -> list[float]:
        """
        Доля окна на одну секцию для каждой обмотки.

        PyOM `wind` принимает `proportion_per_winding` как list[float]
        длины num_windings: `proportion[i]` = доля window space, которую
        ОДНА секция обмотки `i` занимает (sum proportion[i] * count(i)
        ≤ 1.0 ожидается).

        Простейшая равномерная стратегия: `proportion[i] = 1 / count(i)`,
        тогда все секции обмотки `i` суммарно покрывают 100% window.
        Это работает для symmetric sandwich (P-S-P-S-P, P-S и т.д.) —
        PyOM сам балансирует общий объём через wind algorithm.
        """
        counts = [pattern_indices.count(i) for i in range(num_windings)]
        return [1.0 / c if c > 0 else 0.0 for c in counts]
