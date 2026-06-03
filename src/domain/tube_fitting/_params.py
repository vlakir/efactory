"""
Tube-curve-fitting params + dataset VOs (T031 Phase 1, spec §5).

Канонические Koren-формулы используют 2× множитель в числителе (см.
Norman Koren «Improved vacuum tube models for SPICE simulations»):

    Ia = 2 * E1^EX / KG1 * <plate-term>

где `<plate-term>` зависит от типа лампы (см. `_formulas.py`). Это
**не** артефакт ngspice-syntax — это часть оригинальной формулы;
именно так все built-in `data/models/tubes/*.lib` рендерят G1/G2
(Phase 0 probe подтвердил для 12AX7 + EL34).

Параметры — это same parameters что в built-in `.lib` файлах (MU/EX/
KG1/KP/KVB для triode; +KG2/screen_v для pentode/tetrode). Fitter
восстанавливает их из IV-датасета.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

TubeType = Literal['triode', 'pentode']
"""tube_type header в .lib (см. data/models/tubes/README.md).

`'pentode'` покрывает и beam tetrode — выбор header'а в .lib
(`pentode` vs `tetrode`) делается в CLI флагом `--header-type` уже
post-fit (Phase 2, A-W1).
"""


_FROZEN = ConfigDict(frozen=True, extra='forbid')


class KorenTriodeParams(BaseModel):
    """Каноническая Koren triode: MU, EX, KG1, KP, KVB + optional V_ct."""

    model_config = _FROZEN

    mu: Annotated[float, Field(gt=0)]
    """Amplification factor (μ). Typical: 10-100."""

    ex: Annotated[float, Field(gt=1.0, lt=3.0)]
    """Exponent (~1.4 typical small-signal, ~1.5 medium-power)."""

    kg1: Annotated[float, Field(gt=0)]
    """Plate current scaling (mA·V^-EX). Larger → smaller currents."""

    kp: Annotated[float, Field(gt=0)]
    """Plate-to-grid coupling factor."""

    kvb: Annotated[float, Field(gt=0)]
    """Plate-impedance factor (V²)."""

    vct: Annotated[float, Field(ge=0, le=5)] | None = None
    """Optional cathode contact potential (0..5 V). `None` → 0 V."""


class AyumiPentodeParams(BaseModel):
    """
    Ayumi-style pentode params (=Koren-pentode form, calibrated on Ayumi tubes).

    Spec C1 (Approved): «Ayumi» здесь означает калибровочный baseline
    (built-in `data/models/tubes/ayumi/`), а форма формулы — Koren-
    pentode (one term + atan plate-term + 2× multiplier). Phase 0
    confirmed: built-in ayumi/6V6_AYUMI.inc использует exactly эту
    форму.
    """

    model_config = _FROZEN

    mu: Annotated[float, Field(gt=0)]
    ex: Annotated[float, Field(gt=1.0, lt=3.0)]
    kg1: Annotated[float, Field(gt=0)]
    """Plate-circuit scaling."""

    kg2: Annotated[float, Field(gt=0)]
    """Screen-grid current scaling."""

    kp: Annotated[float, Field(gt=0)]
    kvb: Annotated[float, Field(gt=0)]
    """Plate impedance factor inside atan(Va/KVB)."""

    screen_v: Annotated[float, Field(gt=0)]
    """Screen-grid voltage Vg2 at which datasheet curves были measured."""


class IVPoint(BaseModel):
    """Один (Vg, Va) → Ia measurement."""

    model_config = _FROZEN

    vg: float
    """Control-grid voltage (V). Typically ≤ 0 for normal bias."""

    va: Annotated[float, Field(gt=0)]
    """Plate (anode) voltage (V)."""

    ia: Annotated[float, Field(ge=0)]
    """Plate current (mA). 0 разрешён — cutoff."""


class CurveData(BaseModel):
    """Одна curve constant-Vg: список (Va, Ia) точек."""

    model_config = _FROZEN

    vg: float

    points: tuple[tuple[float, float], ...]
    """Tuple of (Va, Ia) pairs; Va in V, Ia in mA. Non-empty."""

    @model_validator(mode='after')
    def _check_non_empty(self) -> CurveData:
        if not self.points:
            msg = f'CurveData(vg={self.vg}) must have at least 1 point'
            raise ValueError(msg)
        for va, ia in self.points:
            if va <= 0:
                msg = f'CurveData(vg={self.vg}) point has Va={va} ≤ 0'
                raise ValueError(msg)
            if ia < 0:
                msg = f'CurveData(vg={self.vg}) point has Ia={ia} < 0'
                raise ValueError(msg)
        return self


class IVDataset(BaseModel):
    """
    Multi-curve IV dataset, готовый к fitter'у.

    Pentode требует `screen_voltage_v` (Vg2 at which curves measured);
    triode — нет.
    """

    model_config = _FROZEN

    tube_name: str
    """Имя лампы, slash-safe (как в .lib). Не валидируется регексом
    здесь — это VO, не identifier; CLI Phase 2 проверит matching
    SpiceModelId pattern перед записью .lib."""

    tube_type: TubeType
    source: str
    """Источник датасета: datasheet ref / measurement campaign."""

    date_extracted: date

    curves: tuple[CurveData, ...]
    """Список constant-Vg curves. Non-empty."""

    screen_voltage_v: Annotated[float, Field(gt=0)] | None = None
    """Vg2 для pentode. Required для tube_type='pentode', None для triode."""

    @model_validator(mode='after')
    def _check_consistency(self) -> IVDataset:
        if not self.curves:
            msg = 'IVDataset must have at least 1 curve'
            raise ValueError(msg)
        if self.tube_type == 'pentode' and self.screen_voltage_v is None:
            msg = "tube_type='pentode' requires screen_voltage_v"
            raise ValueError(msg)
        if self.tube_type == 'triode' and self.screen_voltage_v is not None:
            msg = "tube_type='triode' must not have screen_voltage_v"
            raise ValueError(msg)
        return self

    def flatten(self) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
        """
        Развернуть в плоские (vg, va, ia) arrays — convenience для fitter'а.

        Возвращает 3 tuple'а одинаковой длины, выровненные по index.
        """
        vgs: list[float] = []
        vas: list[float] = []
        ias: list[float] = []
        for curve in self.curves:
            for va, ia in curve.points:
                vgs.append(curve.vg)
                vas.append(va)
                ias.append(ia)
        return tuple(vgs), tuple(vas), tuple(ias)


class FitResult(BaseModel):
    """Результат fitter'а: params + diagnostics."""

    model_config = _FROZEN

    params: KorenTriodeParams | AyumiPentodeParams
    rms_residual_ma: Annotated[float, Field(ge=0)]
    """RMS residual Ia error по всему датасету (mA)."""

    per_param_stderr: dict[str, float]
    """Stderr по каждому fit-параметру (из covariance diagonal)."""

    n_points: Annotated[int, Field(ge=1)]
    converged: bool
    n_starts_tried: Annotated[int, Field(ge=1)]
    """Сколько initial-guess startов прогнал multi-start."""

    best_start_index: Annotated[int, Field(ge=0)]
    """Индекс start'а с минимальным residual (0-based)."""
