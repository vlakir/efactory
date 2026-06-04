"""
Filesystem implementation of `TubeLibWriter` для T031 use case.

Формат — близко к built-in `data/models/tubes/*.lib`:

* header (multiline comment) с metadata: source datasheet, date,
  RMS residual, display name;
* `tube_type:` line — необходима для `FilesystemSpiceModelLibrary`
  (T006/T007) tube-type detection;
* `.SUBCKT NAME P G K` (triode) или `P G2 G K` (pentode/tetrode);
* E1/G1/G2/C/RGI — Koren-канонический ngspice-syntax (`sgn(x)*pwr(
  abs(x),y)`, без HSPICE `pwr()`), без `^` (с `**`).

Capacitances и tube-shape (envelope) — typical defaults; в production
адаптируются под конкретный datasheet (out of scope T031, см. spec
§7 Out of Scope).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from domain.tube_fitting import (
    AyumiPentodeParams,
    KorenDerkPentodeParams,
    KorenModifiedCutoffTriodeParams,
    KorenModifiedKneePentodeParams,
    KorenReefmanPentodeParams,
    KorenTriodeParams,
)

if TYPE_CHECKING:
    from pathlib import Path

    from ports.outbound.tube_lib_writer import (
        HeaderTubeType,
        TubeLibMeta,
        TubeParamsForWriter,
    )

_SPICE_NAME_RE = re.compile(r'^[A-Z0-9][A-Z0-9_]+$')


class TubeLibWriteError(RuntimeError):
    """Запись .lib файла невозможна (existing файл без --force и т.п.)."""


# Typical capacitance defaults (pF) per tube class. См. § Out of Scope:
# точные значения требуют per-tube datasheet extraction.
_TRIODE_TYPICAL_CAPS = {'cgk': 2.0, 'cgp': 2.0, 'cpk': 1.0}
_PENTODE_TYPICAL_CAPS = {'cgk': 10.0, 'cgp': 1.0, 'cpk': 10.0}


class FilesystemTubeLibWriter:
    """`TubeLibWriter` implementation: пишет .lib на локальный диск."""

    def write(
        self,
        path: Path,
        spice_name: str,
        params: TubeParamsForWriter,
        *,
        header_tube_type: HeaderTubeType,
        meta: TubeLibMeta,
        force: bool = False,
    ) -> None:
        _validate_spice_name(spice_name)
        _validate_params_match_header(params, header_tube_type)
        if path.exists() and not force:
            msg = f'.lib file already exists: {path} (use force=True to overwrite)'
            raise TubeLibWriteError(msg)

        content = _render_lib(
            spice_name, params, header_tube_type=header_tube_type, meta=meta
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + '.tmp')
        tmp.write_text(content, encoding='utf-8')
        tmp.replace(path)


def _validate_spice_name(spice_name: str) -> None:
    if not _SPICE_NAME_RE.match(spice_name):
        msg = (
            f'spice_name must match {_SPICE_NAME_RE.pattern} '
            f"(uppercase letters/digits/underscore, ≥2 chars), got '{spice_name}'"
        )
        raise ValueError(msg)


def _validate_params_match_header(
    params: TubeParamsForWriter,
    header_tube_type: HeaderTubeType,
) -> None:
    if (
        isinstance(params, KorenTriodeParams | KorenModifiedCutoffTriodeParams)
        and header_tube_type != 'triode'
    ):
        msg = (
            f'{type(params).__name__} requires header_tube_type=triode, '
            f"got '{header_tube_type}'"
        )
        raise TypeError(msg)
    if isinstance(
        params,
        AyumiPentodeParams
        | KorenModifiedKneePentodeParams
        | KorenReefmanPentodeParams
        | KorenDerkPentodeParams,
    ) and header_tube_type not in (
        'pentode',
        'tetrode',
    ):
        msg = (
            f'{type(params).__name__} requires header_tube_type in '
            f"('pentode', 'tetrode'), got '{header_tube_type}'"
        )
        raise TypeError(msg)


def _render_lib(
    spice_name: str,
    params: TubeParamsForWriter,
    *,
    header_tube_type: HeaderTubeType,
    meta: TubeLibMeta,
) -> str:
    if isinstance(params, KorenModifiedCutoffTriodeParams):
        return _render_modified_cutoff_triode(spice_name, params, meta=meta)
    if isinstance(params, KorenTriodeParams):
        return _render_triode(spice_name, params, meta=meta)
    if isinstance(params, KorenModifiedKneePentodeParams):
        return _render_modified_knee_pentode(
            spice_name, params, header_tube_type=header_tube_type, meta=meta
        )
    if isinstance(params, KorenReefmanPentodeParams):
        return _render_reefman_pentode(
            spice_name, params, header_tube_type=header_tube_type, meta=meta
        )
    if isinstance(params, KorenDerkPentodeParams):
        return _render_derk_pentode(
            spice_name, params, header_tube_type=header_tube_type, meta=meta
        )
    return _render_pentode(
        spice_name, params, header_tube_type=header_tube_type, meta=meta
    )


def _render_triode(
    spice_name: str,
    p: KorenTriodeParams,
    *,
    meta: TubeLibMeta,
) -> str:
    vct = p.vct if p.vct is not None else 0.0
    vct_line = f' VCT={vct:.4f}' if p.vct is not None else ''
    vg_term = f'V(G,K)+{vct:.4f}' if p.vct is not None else 'V(G,K)'
    caps = _TRIODE_TYPICAL_CAPS

    return (
        f'* {meta.display_name} — fitted by `efactory tube fit-from-points` (T031).\n'
        f'*\n'
        f'* Source: {meta.source}\n'
        f'* IV points extracted: {meta.date_extracted.isoformat()}\n'
        f'* Fitted:              {meta.date_fitted.isoformat()}\n'
        f'* RMS residual: {meta.rms_residual_ma:.3f} mA over {meta.n_points} points\n'
        f'*\n'
        f'* tube_type: triode\n'
        f'* Pins: P (plate), G (grid), K (cathode).\n'
        f'.SUBCKT {spice_name} P G K\n'
        f'* Koren parameters: MU={p.mu:.4f} EX={p.ex:.4f} '
        f'KG1={p.kg1:.4f} KP={p.kp:.4f} KVB={p.kvb:.4f}{vct_line}\n'
        f'E1 7 0 VALUE={{V(P,K)/{p.kp:.4f}*LN(1+EXP({p.kp:.4f}*'
        f'(1/{p.mu:.4f}+({vg_term})/SQRT({p.kvb:.4f}+V(P,K)*V(P,K)))))}}\n'
        f'G1 P K VALUE={{(sgn(V(7))*pwr(abs(V(7)),{p.ex:.4f})'
        f'+sgn(V(7))*pwr(abs(V(7)),{p.ex:.4f}))/{p.kg1:.4f}}}\n'
        f'* Inter-electrode capacitances — typical small-signal triode defaults\n'
        f'* (см. spec T031 §7 Out of Scope: per-tube extraction).\n'
        f'C1 G K {caps["cgk"]:.1f}p\n'
        f'C2 G P {caps["cgp"]:.1f}p\n'
        f'C3 P K {caps["cpk"]:.1f}p\n'
        f'RGI G K 1MEG\n'
        f'.ENDS {spice_name}\n'
    )


def _render_modified_cutoff_triode(
    spice_name: str,
    p: KorenModifiedCutoffTriodeParams,
    *,
    meta: TubeLibMeta,
) -> str:
    """
    T182: triode + sigmoid cutoff modifier.

    `vct` всегда None (use case форсирует — A-W1). `vc_off` отрицателен;
    в ngspice-syntax `(V(G,K) - VC_OFF)` корректно для negative VC_OFF
    через дробное представление `... + (-VC_OFF)` — но проще писать
    разность напрямую: `(V(G,K) - {p.vc_off:.4f})` где vc_off negative
    числу включает знак.
    """
    caps = _TRIODE_TYPICAL_CAPS
    sigmoid_arg = f'(V(G,K)-({p.vc_off:.4f}))/{p.vs_off:.4f}'
    return (
        f'* {meta.display_name} — fitted by `efactory tube fit-from-points` (T182).\n'
        f'*\n'
        f'* Source: {meta.source}\n'
        f'* IV points extracted: {meta.date_extracted.isoformat()}\n'
        f'* Fitted:              {meta.date_fitted.isoformat()}\n'
        f'* RMS residual: {meta.rms_residual_ma:.3f} mA over {meta.n_points} points\n'
        f'*\n'
        f'* fit variant: koren-modified-cutoff (T182)\n'
        f'* tube_type: triode\n'
        f'* Pins: P (plate), G (grid), K (cathode).\n'
        f'.SUBCKT {spice_name} P G K\n'
        f'* Koren-modified-cutoff parameters: MU={p.mu:.4f} EX={p.ex:.4f} '
        f'KG1={p.kg1:.4f} KP={p.kp:.4f} KVB={p.kvb:.4f} '
        f'VC_OFF={p.vc_off:.4f} VS_OFF={p.vs_off:.4f}\n'
        f'E1 7 0 VALUE={{V(P,K)/{p.kp:.4f}*LN(1+EXP({p.kp:.4f}*'
        f'(1/{p.mu:.4f}+V(G,K)/SQRT({p.kvb:.4f}+V(P,K)*V(P,K)))))}}\n'
        f'* Sigmoid cutoff factor: 1/(1+EXP(-(V(G,K)-VC_OFF)/VS_OFF))\n'
        f'B_SIG 8 0 V=1/(1+EXP(-({sigmoid_arg})))\n'
        f'G1 P K VALUE={{(sgn(V(7))*pwr(abs(V(7)),{p.ex:.4f})'
        f'+sgn(V(7))*pwr(abs(V(7)),{p.ex:.4f}))/{p.kg1:.4f}*V(8)}}\n'
        f'* Inter-electrode capacitances — typical small-signal triode defaults.\n'
        f'C1 G K {caps["cgk"]:.1f}p\n'
        f'C2 G P {caps["cgp"]:.1f}p\n'
        f'C3 P K {caps["cpk"]:.1f}p\n'
        f'RGI G K 1MEG\n'
        f'.ENDS {spice_name}\n'
    )


def _render_modified_knee_pentode(
    spice_name: str,
    p: KorenModifiedKneePentodeParams,
    *,
    header_tube_type: HeaderTubeType,
    meta: TubeLibMeta,
) -> str:
    """T182: pentode + knee modifier `(1 - EXP(-V(P,K)/VK))`."""
    caps = _PENTODE_TYPICAL_CAPS
    return (
        f'* {meta.display_name} — fitted by `efactory tube fit-from-points` (T182).\n'
        f'*\n'
        f'* Source: {meta.source}\n'
        f'* IV points extracted: {meta.date_extracted.isoformat()}\n'
        f'* Fitted:              {meta.date_fitted.isoformat()}\n'
        f'* RMS residual: {meta.rms_residual_ma:.3f} mA over {meta.n_points} points\n'
        f'*\n'
        f'* fit variant: koren-modified-knee (T182)\n'
        f'* tube_type: {header_tube_type}\n'
        f'* Pins: P (plate), G2 (screen), G (grid 1), K (cathode).\n'
        f'.SUBCKT {spice_name} P G2 G K\n'
        f'* Koren-modified-knee parameters:\n'
        f'* MU={p.mu:.4f} EX={p.ex:.4f} KG1={p.kg1:.4f} KG2={p.kg2:.4f} '
        f'KP={p.kp:.4f} KVB={p.kvb:.4f} VK={p.vk:.4f}\n'
        f'E1 7 0 VALUE={{V(G2,K)/{p.kp:.4f}*LN(1+EXP({p.kp:.4f}*'
        f'(1/{p.mu:.4f}+V(G,K)/V(G2,K))))}}\n'
        f'* Knee modifier: (1 - EXP(-V(P,K)/VK))\n'
        f'B_KNEE 8 0 V=1-EXP(-V(P,K)/{p.vk:.4f})\n'
        f'G1 P K VALUE={{(sgn(V(7))*pwr(abs(V(7)),{p.ex:.4f})'
        f'+sgn(V(7))*pwr(abs(V(7)),{p.ex:.4f}))/{p.kg1:.4f} '
        f'* ATAN(V(P,K)/{p.kvb:.4f}) * V(8)}}\n'
        f'G2 G2 K VALUE={{(sgn(V(7))*pwr(abs(V(7)),{p.ex:.4f})'
        f'+sgn(V(7))*pwr(abs(V(7)),{p.ex:.4f}))/{p.kg2:.4f}}}\n'
        f'* Inter-electrode capacitances — typical pentode defaults.\n'
        f'C1 G K {caps["cgk"]:.1f}p\n'
        f'C2 G P {caps["cgp"]:.1f}p\n'
        f'C3 P K {caps["cpk"]:.1f}p\n'
        f'RGI G K 1MEG\n'
        f'.ENDS {spice_name}\n'
    )


def _render_reefman_pentode(
    spice_name: str,
    p: KorenReefmanPentodeParams,
    *,
    header_tube_type: HeaderTubeType,
    meta: TubeLibMeta,
) -> str:
    """T184: Reefman pentode (no 2× factor; E1 uses sqrt(KVB+Vg2²))."""
    caps = _PENTODE_TYPICAL_CAPS
    # Pre-compute sqrt(KVB + screen_v²) literal so ngspice doesn't compute it.
    g2_norm = (p.kvb + p.screen_v * p.screen_v) ** 0.5
    return (
        f'* {meta.display_name} — fitted by `efactory tube fit-from-points` (T184).\n'
        f'*\n'
        f'* Source: {meta.source}\n'
        f'* IV points extracted: {meta.date_extracted.isoformat()}\n'
        f'* Fitted:              {meta.date_fitted.isoformat()}\n'
        f'* RMS residual: {meta.rms_residual_ma:.3f} mA over {meta.n_points} points\n'
        f'*\n'
        f'* fit variant: koren-reefman-pentode (T184)\n'
        f'* tube_type: {header_tube_type}\n'
        f'* Pins: P (plate), G2 (screen), G (grid 1), K (cathode).\n'
        f'.SUBCKT {spice_name} P G2 G K\n'
        f'* Reefman-pentode parameters (no 2x factor; '
        f'E1 uses sqrt(KVB+Vg2^2)):\n'
        f'* MU={p.mu:.4f} EX={p.ex:.4f} KG1={p.kg1:.4f} KG2={p.kg2:.4f} '
        f'KP={p.kp:.4f} KVB={p.kvb:.4f}\n'
        f'E1 7 0 VALUE={{V(G2,K)/{p.kp:.4f}*LN(1+EXP({p.kp:.4f}*'
        f'(1/{p.mu:.4f}+V(G,K)/{g2_norm:.4f})))}}\n'
        f'G1 P K VALUE={{sgn(V(7))*pwr(abs(V(7)),{p.ex:.4f})/{p.kg1:.4f} '
        f'* ATAN(V(P,K)/{p.kvb:.4f})}}\n'
        f'G2 G2 K VALUE={{sgn(V(7))*pwr(abs(V(7)),{p.ex:.4f})/{p.kg2:.4f}}}\n'
        f'* Inter-electrode capacitances — typical pentode defaults.\n'
        f'C1 G K {caps["cgk"]:.1f}p\n'
        f'C2 G P {caps["cgp"]:.1f}p\n'
        f'C3 P K {caps["cpk"]:.1f}p\n'
        f'RGI G K 1MEG\n'
        f'.ENDS {spice_name}\n'
    )


def _render_derk_pentode(
    spice_name: str,
    p: KorenDerkPentodeParams,
    *,
    header_tube_type: HeaderTubeType,
    meta: TubeLibMeta,
) -> str:
    """T186: Derk pentode (Reefman 2016 Sec 4.4 Eq 23-27)."""
    caps = _PENTODE_TYPICAL_CAPS
    g2_norm = (p.kvb + p.screen_v * p.screen_v) ** 0.5
    alpha = 1.0 - (p.kg1 / p.kg2) * (1.0 + p.alpha_s)
    return (
        f'* {meta.display_name} — fitted by `efactory tube fit-from-points` (T186).\n'
        f'*\n'
        f'* Source: {meta.source}\n'
        f'* IV points extracted: {meta.date_extracted.isoformat()}\n'
        f'* Fitted:              {meta.date_fitted.isoformat()}\n'
        f'* RMS residual: {meta.rms_residual_ma:.3f} mA over {meta.n_points} points\n'
        f'*\n'
        f'* fit variant: koren-derk-pentode (T186, Reefman 2016 Sec 4.4)\n'
        f'* tube_type: {header_tube_type}\n'
        f'* Pins: P (plate), G2 (screen), G (grid 1), K (cathode).\n'
        f'.SUBCKT {spice_name} P G2 G K\n'
        f'* Derk-pentode parameters: MU={p.mu:.4f} EX={p.ex:.4f} '
        f'KG1={p.kg1:.4f} KG2={p.kg2:.4f}\n'
        f'* KP={p.kp:.4f} KVB={p.kvb:.4f} ALPHA_S={p.alpha_s:.4f} '
        f'BETA={p.beta:.6f} A={p.a_penetration:.6f}\n'
        f'* alpha (derived) = 1-(KG1/KG2)(1+ALPHA_S) = {alpha:.6f}\n'
        f'E1 7 0 VALUE={{V(G2,K)/{p.kp:.4f}*LN(1+EXP({p.kp:.4f}*'
        f'(1/{p.mu:.4f}+V(G,K)/{g2_norm:.4f})))}}\n'
        f'* knee_factor: 1/(1+BETA*V(P,K))\n'
        f'B_KF 8 0 V=1/(1+{p.beta:.6f}*V(P,K))\n'
        f'* bracket: 1/KG1 - 1/KG2 + A*Va/KG1 - knee_factor*(alpha/KG1 + alpha_s/KG2)\n'
        f'B_BR 9 0 V=1/{p.kg1:.4f}-1/{p.kg2:.4f}+{p.a_penetration:.6f}*V(P,K)'
        f'/{p.kg1:.4f}-V(8)*({alpha:.6f}/{p.kg1:.4f}+{p.alpha_s:.4f}/{p.kg2:.4f})\n'
        f'G1 P K VALUE={{sgn(V(7))*pwr(abs(V(7)),{p.ex:.4f})*V(9)}}\n'
        f'G2 G2 K VALUE={{sgn(V(7))*pwr(abs(V(7)),{p.ex:.4f})/{p.kg2:.4f}'
        f'*(1+{p.alpha_s:.4f}*V(8))}}\n'
        f'* Inter-electrode capacitances — typical pentode defaults.\n'
        f'C1 G K {caps["cgk"]:.1f}p\n'
        f'C2 G P {caps["cgp"]:.1f}p\n'
        f'C3 P K {caps["cpk"]:.1f}p\n'
        f'RGI G K 1MEG\n'
        f'.ENDS {spice_name}\n'
    )


def _render_pentode(
    spice_name: str,
    p: AyumiPentodeParams,
    *,
    header_tube_type: HeaderTubeType,
    meta: TubeLibMeta,
) -> str:
    caps = _PENTODE_TYPICAL_CAPS
    return (
        f'* {meta.display_name} — fitted by `efactory tube fit-from-points` (T031).\n'
        f'*\n'
        f'* Source: {meta.source}\n'
        f'* IV points extracted: {meta.date_extracted.isoformat()}\n'
        f'* Fitted:              {meta.date_fitted.isoformat()}\n'
        f'* RMS residual: {meta.rms_residual_ma:.3f} mA over {meta.n_points} points\n'
        f'*\n'
        f'* tube_type: {header_tube_type}\n'
        f'* Pins: P (plate), G2 (screen), G (grid 1), K (cathode).\n'
        f'.SUBCKT {spice_name} P G2 G K\n'
        f'* Koren-pentode parameters (calibrated on Ayumi baseline):\n'
        f'* MU={p.mu:.4f} EX={p.ex:.4f} KG1={p.kg1:.4f} KG2={p.kg2:.4f} '
        f'KP={p.kp:.4f} KVB={p.kvb:.4f}\n'
        f'E1 7 0 VALUE={{V(G2,K)/{p.kp:.4f}*LN(1+EXP({p.kp:.4f}*'
        f'(1/{p.mu:.4f}+V(G,K)/V(G2,K))))}}\n'
        f'G1 P K VALUE={{(sgn(V(7))*pwr(abs(V(7)),{p.ex:.4f})'
        f'+sgn(V(7))*pwr(abs(V(7)),{p.ex:.4f}))/{p.kg1:.4f} '
        f'* ATAN(V(P,K)/{p.kvb:.4f})}}\n'
        f'G2 G2 K VALUE={{(sgn(V(7))*pwr(abs(V(7)),{p.ex:.4f})'
        f'+sgn(V(7))*pwr(abs(V(7)),{p.ex:.4f}))/{p.kg2:.4f}}}\n'
        f'* Inter-electrode capacitances — typical pentode defaults\n'
        f'* (см. spec T031 §7 Out of Scope: per-tube extraction).\n'
        f'C1 G K {caps["cgk"]:.1f}p\n'
        f'C2 G P {caps["cgp"]:.1f}p\n'
        f'C3 P K {caps["cpk"]:.1f}p\n'
        f'RGI G K 1MEG\n'
        f'.ENDS {spice_name}\n'
    )
