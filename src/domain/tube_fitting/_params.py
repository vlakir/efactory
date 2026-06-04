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

FormulaVariant = Literal[
    'koren-canonical',
    'koren-modified-knee',
    'koren-modified-cutoff',
    'koren-reefman-pentode',
    'koren-derk-pentode',
]
"""Forward-formula variant (T182, T184).

* `'koren-canonical'` — оригинальный Koren triode + Ayumi/Koren-pentode
  (T031 baseline). Default. Каноничные `KorenTriodeParams` /
  `AyumiPentodeParams`.
* `'koren-modified-knee'` — pentode-only: plate-term получает
  `(1 - exp(-Va/Vk))` множитель, knee region резче. Используется с
  `KorenModifiedKneePentodeParams` (+1 параметр `vk` сверх canonical
  pentode). См. T182 spec §3.
* `'koren-modified-cutoff'` — triode-only: Ia умножается на
  sigmoid((Vg − Vc_off)/Vs_off), strong cutoff резче без overshoot
  в mid-region. Используется с `KorenModifiedCutoffTriodeParams`
  (+2 параметра `vc_off`, `vs_off` сверх canonical triode). См.
  T182 spec §3.
* `'koren-reefman-pentode'` — pentode-only: Reefman 2016 paper Sec 4.2
  Eq 14-17. Same param count как canonical Ayumi, но E1 form
  использует `sqrt(kVB + Vg2²)` для triode-strapped consistency.
  Для high-Vg2 power-pentodes (EL34 типичный) numerically near-
  identical canonical (Vg2 ≫ √kVB → identity). Польза проявляется
  на low-Vg2 small-signal pentodes и triode-strapped configurations.
  Cite: Reefman, "Spice models for vacuum tubes using the uTracer"
  (2016), Sec 4.2.
* `'koren-derk-pentode'` — pentode-only: Reefman 2016 paper Sec 4.4
  Eq 23-27 (Derk model). Constant Space Charge + screen scaling +
  anode penetration. Same backbone E1 как Reefman (`sqrt(kVB+Vg2²)`)
  + три новых параметра: `alpha_s` (screen current correction),
  `beta` (knee width 1/(1+βV_a)), `A` (anode penetration linear
  term). `alpha` derived constraint: α = 1 - (k_g1/k_g2)(1+α_s).
  Reefman claim: "amazingly accurate" даже для secondary-emission
  pentodes. EL34 acceptance target — closing knee region <30%.

Совместимость triode/pentode → variant: `koren-modified-knee` +
`koren-reefman-pentode` + `koren-derk-pentode` ↔ pentode only;
`koren-modified-cutoff` ↔ triode only. Mismatch ловится use case'ом
до запуска fitter'а (A-W5).
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


class KorenModifiedKneePentodeParams(BaseModel):
    """
    Modified Koren-pentode (T182): canonical pentode + knee modifier.

    Forward Ia:
        E1 = (Vg2/KP) * ln(1 + exp(KP * (1/MU + Vg/Vg2)))
        Ia = (2 * E1^EX / KG1) * atan(Va/KVB) * (1 - exp(-Va/Vk))

    `vk` (V) — knee voltage scale: меньший Vk → резче подъём в knee
    region; при Va → ∞ модификатор → 1 (plateau не меняется по
    сравнению с canonical Koren-pentode).

    Backwards-compat: для `vk → ∞` modifier ≡ 1 → формула вырождается
    в canonical, но т.к. `vk` имеет positive lower bound (5 V), это
    asymptotic property, не bit-exact.
    """

    model_config = _FROZEN

    mu: Annotated[float, Field(gt=0)]
    ex: Annotated[float, Field(gt=1.0, lt=3.0)]
    kg1: Annotated[float, Field(gt=0)]
    kg2: Annotated[float, Field(gt=0)]
    kp: Annotated[float, Field(gt=0)]
    kvb: Annotated[float, Field(gt=0)]
    screen_v: Annotated[float, Field(gt=0)]
    vk: Annotated[float, Field(gt=0)]
    """Knee voltage scale (V). Typical: 30-100 V для receiving
    pentodes, 50-200 V для power pentodes."""


class KorenReefmanPentodeParams(BaseModel):
    """
    Reefman pentode (T184): canonical Ayumi-pentode параметры, но E1
    form использует `sqrt(kVB + Vg2²)` (triode-like).

    Forward Ia:
        E1 = (Vg2/KP) · ln(1 + exp(KP · (1/MU + Vg/sqrt(KVB+Vg2²))))
        Ia = (E1^EX / KG1) · atan(Va/KVB)         при E1>0
        Ig2 = E1^EX / KG2

    Note: Reefman convention НЕ имеет 2× factor в I_{P,Koren} (Eq 14:
    ½·E^x·(1+sgn(E)) = E^x для E>0). Численно полученные KG1/KG2
    будут в **2× меньше** канонических Ayumi values для тех же IV-
    кривых. Это convention-difference, не bug. .lib emission
    использует Reefman convention.

    Same param count как `AyumiPentodeParams` (mu/ex/kg1/kg2/kp/kvb/
    screen_v) — никаких новых fit params.
    """

    model_config = _FROZEN

    mu: Annotated[float, Field(gt=0)]
    ex: Annotated[float, Field(gt=1.0, lt=3.0)]
    kg1: Annotated[float, Field(gt=0)]
    kg2: Annotated[float, Field(gt=0)]
    kp: Annotated[float, Field(gt=0)]
    kvb: Annotated[float, Field(gt=0)]
    screen_v: Annotated[float, Field(gt=0)]


class KorenDerkPentodeParams(BaseModel):
    """
    Derk pentode (T186): Reefman 2016 paper Sec 4.4 Eq 23-27.

    Forward Ia:
        E1 = (Vg2/KP) · ln(1 + exp(KP · (1/MU + Vg/sqrt(KVB+Vg2²))))
        I_P,Koren = E1^EX                    (при E1>0; 0 иначе)
        α = 1 - (KG1/KG2)(1+α_s)             (derived constraint, Eq 27)
        I_a = I_P,Koren · [
            1/KG1 - 1/KG2
            + A·V_a/KG1
            - 1/(1+β·V_a) · (α/KG1 + α_s/KG2)
        ]                                    (Eq 25)
        I_g2 = (I_P,Koren / KG2) · (1 + α_s/(1+β·V_a))  (Eq 23)

    Constraint construction guarantees I_a(V_a=0) = 0 ("knee at zero").

    Params: canonical Reefman 6 (MU/EX/KG1/KG2/KP/KVB/screen_v) +
    Derk extension 3 (alpha_s, beta, A) = 9 fit params. α derived,
    не fit.

    Bounds rationale:
    - `alpha_s`: screen correction at low V_a; typical 0.1-5 для
      small-signal pentodes, может расти для power tubes.
    - `beta`: knee width; 1/(1+β·V_a)=0.5 при V_a=1/β; typical
      0.01-0.1 для V_a~10-100 V knee.
    - `A`: anode penetration linear coefficient; 0 для "ideal"
      pentodes, ~0.001-0.01 для power pentodes.
    """

    model_config = _FROZEN

    mu: Annotated[float, Field(gt=0)]
    ex: Annotated[float, Field(gt=1.0, lt=3.0)]
    kg1: Annotated[float, Field(gt=0)]
    kg2: Annotated[float, Field(gt=0)]
    kp: Annotated[float, Field(gt=0)]
    kvb: Annotated[float, Field(gt=0)]
    screen_v: Annotated[float, Field(gt=0)]
    alpha_s: Annotated[float, Field(gt=0)]
    """Reefman Sec 4.4 screen current correction at low V_a."""

    beta: Annotated[float, Field(gt=0)]
    """Reefman Sec 4.4 knee width param (1/(1+β·V_a))."""

    a_penetration: Annotated[float, Field(ge=0)]
    """Reefman Sec 4.4 anode penetration linear coefficient."""


class KorenModifiedCutoffTriodeParams(BaseModel):
    """
    Modified Koren-triode (T182): canonical triode + sigmoid cutoff.

    Forward Ia:
        E1 = (Va/KP) * ln(1 + exp(KP * (1/MU + (Vg+Vct)/sqrt(KVB+Va²))))
        Ia_canonical = 2 * E1^EX / KG1
        Ia = Ia_canonical * sigmoid((Vg - Vc_off) / Vs_off)
             где sigmoid(x) = 1/(1 + exp(-x))

    `Vc_off` (V, **negative**) — cutoff threshold center; для 300B
    typical: -50..-60 V. При `Vg ≫ Vc_off` (нормальная mid-region)
    sigmoid → 1 → Ia ≡ canonical. При `Vg ≪ Vc_off` sigmoid → 0 →
    Ia → 0 (sharp cutoff).

    `Vs_off` (V, positive) — sigmoid transition width: меньший Vs_off
    → резче cutoff edge.

    Совместимость с A-W1: при использовании этого variant'а
    `--include-vct` запрещён CLI (cathode-contact `vct` и cutoff
    threshold `vc_off` semantically overlap).
    """

    model_config = _FROZEN

    mu: Annotated[float, Field(gt=0)]
    ex: Annotated[float, Field(gt=1.0, lt=3.0)]
    kg1: Annotated[float, Field(gt=0)]
    kp: Annotated[float, Field(gt=0)]
    kvb: Annotated[float, Field(gt=0)]
    vct: Annotated[float, Field(ge=0, le=5)] | None = None
    """`Vct` остаётся в VO для совместимости с canonical schema, но
    use case при variant='koren-modified-cutoff' форсирует `vct=None`
    (см. A-W1)."""

    vc_off: Annotated[float, Field(lt=0, gt=-300)]
    """Cutoff threshold center (V, negative)."""

    vs_off: Annotated[float, Field(gt=0)]
    """Sigmoid transition width (V, positive)."""


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
    """Constant-Vg Ia curves (plate current). Non-empty."""

    screen_voltage_v: Annotated[float, Field(gt=0)] | None = None
    """Vg2 для pentode. Required для tube_type='pentode', None для triode."""

    screen_curves: tuple[CurveData, ...] = ()
    """
    Optional constant-Vg Ig2 curves (screen current).

    Если задано — fitter использует joint Ia+Ig2 loss, KG2 становится
    identifiable (см. `fit_ayumi_pentode` docstring). Если пусто — KG2
    из формулы Ia никак не извлекается; Phase 2 .lib writer должен
    подставить typical ratio (KG2 ≈ 5·KG1).

    Только для pentode; triode не имеет screen grid.
    """

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
        if self.tube_type == 'triode' and self.screen_curves:
            msg = "tube_type='triode' must not have screen_curves"
            raise ValueError(msg)
        return self

    def flatten(self) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
        """
        Развернуть Ia-curves в плоские (vg, va, ia) arrays для fitter'а.

        Возвращает 3 tuple'а одинаковой длины, выровненные по index.
        """
        return _flatten_curves(self.curves)

    def flatten_screen(
        self,
    ) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
        """
        Развернуть Ig2-curves в плоские (vg, va, ig2) arrays.

        Возвращает пустые tuple'ы, если `screen_curves` пуст.
        """
        return _flatten_curves(self.screen_curves)


def _flatten_curves(
    curves: tuple[CurveData, ...],
) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
    """Generic flatten: (Vg constant per curve, list of (Va, y)) → 3 parallel arrays."""
    vgs: list[float] = []
    vas: list[float] = []
    ys: list[float] = []
    for curve in curves:
        for va, y in curve.points:
            vgs.append(curve.vg)
            vas.append(va)
            ys.append(y)
    return tuple(vgs), tuple(vas), tuple(ys)


class FitResult(BaseModel):
    """Результат fitter'а: params + diagnostics."""

    model_config = _FROZEN

    params: (
        KorenTriodeParams
        | AyumiPentodeParams
        | KorenModifiedKneePentodeParams
        | KorenModifiedCutoffTriodeParams
        | KorenReefmanPentodeParams
        | KorenDerkPentodeParams
    )
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
