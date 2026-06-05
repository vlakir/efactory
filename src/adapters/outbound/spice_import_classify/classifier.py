"""
RegexSpiceModelClassifier — T030 adapter.

Detects `.SUBCKT` / `.MODEL` cards in a SPICE deck, joins continuation
`+` lines, parses parent comment headers (`* foo: bar`), maps cards to
(ComponentCategory, subcategory) per F8-F11 of T030 spec.

Pure regex / string-walking — no LLM, no external libs. Deterministic.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

from domain.spice_import import (
    ClassificationAmbiguousError,
    ClassificationResult,
    ContentRejectedError,
    ModelKind,
    ParsedModelCard,
)
from domain.spice_model import (
    BjtKind,
    ComponentCategory,
    DiodeKind,
    JfetKind,
    MosfetKind,
    OpampKind,
)

if TYPE_CHECKING:
    from domain.spice_import import RawImport


_ENCRYPTED_RE = re.compile(r'^\s*\*encrypted\b', re.IGNORECASE | re.MULTILINE)
_HTML_RE = re.compile(r'<(html|body|head|form|input|script)\b', re.IGNORECASE)
_HEADER_META_RE = re.compile(r'^\s*\*\s*([a-z_]+)\s*:\s*(\S.*?)\s*$', re.IGNORECASE)

_SUBCKT_OPEN_RE = re.compile(r'^\s*\.subckt\s+(\S+)\s+(.+?)\s*$', re.IGNORECASE)
_SUBCKT_END_RE = re.compile(r'^\s*\.ends\b', re.IGNORECASE)
_MODEL_OPEN_RE = re.compile(
    r'^\s*\.model\s+(\S+)\s+([A-Za-z][A-Za-z0-9]*)\b', re.IGNORECASE
)

_MODEL_TYPE_TO_CATEGORY: Final[dict[str, tuple[ComponentCategory, str]]] = {
    'NPN': (ComponentCategory.BJT, BjtKind.NPN.value),
    'PNP': (ComponentCategory.BJT, BjtKind.PNP.value),
    'NJF': (ComponentCategory.JFET, JfetKind.NJF.value),
    'PJF': (ComponentCategory.JFET, JfetKind.PJF.value),
    'NMOS': (ComponentCategory.MOSFET, MosfetKind.NMOS.value),
    'PMOS': (ComponentCategory.MOSFET, MosfetKind.PMOS.value),
    'D': (ComponentCategory.DIODE, DiodeKind.SIGNAL.value),
}

_OPAMP_PIN_HINTS: Final = frozenset(
    {
        'V+',
        'V-',
        'VCC',
        'VEE',
        'VS+',
        'VS-',
        'INP',
        'INM',
        'IN+',
        'IN-',
        'OUT',
        '+IN',
        '-IN',
    },
)

_PINS_TWO: Final = 2
_PINS_THREE: Final = 3
_PINS_OPAMP_MIN: Final = 5


class RegexSpiceModelClassifier:
    def classify_all(
        self,
        raw: RawImport,
    ) -> tuple[tuple[ParsedModelCard, ClassificationResult], ...]:
        text = raw.bytes_text
        self._reject_non_spice(text)
        joined_lines = _join_continuations(text.splitlines())
        cards = _extract_cards(joined_lines)
        out: list[tuple[ParsedModelCard, ClassificationResult]] = []
        for card in cards:
            classification = self._classify(card)
            out.append((card, classification))
        return tuple(out)

    @staticmethod
    def _reject_non_spice(text: str) -> None:
        if _ENCRYPTED_RE.search(text):
            msg = 'encrypted SPICE block (*encrypted...*endencrypted) — unsupported'
            raise ContentRejectedError(reason=msg)
        if _HTML_RE.search(text):
            reason = 'HTML content (login / portal page), not SPICE deck'
            raise ContentRejectedError(reason=reason)

    def _classify(self, card: ParsedModelCard) -> ClassificationResult:
        # 1. Header override приоритет (F11).
        hdr_cat = card.header_meta.get('category')
        hdr_sub = card.header_meta.get('subcategory')
        if hdr_cat is not None:
            try:
                category = ComponentCategory(hdr_cat.lower())
            except ValueError as exc:
                raise ClassificationAmbiguousError(
                    card=card,
                    reason=f'header category={hdr_cat!r} not in ComponentCategory',
                ) from exc
            subcategory = hdr_sub.lower() if hdr_sub else _default_subcategory(category)
            return ClassificationResult(
                category=category,
                subcategory=subcategory,
                reason=f'header override (category={hdr_cat}, subcategory={hdr_sub})',
                ambiguous=False,
            )

        # 2. Heuristic per kind.
        if card.kind is ModelKind.MODEL:
            return self._classify_model(card)
        return self._classify_subckt(card)

    def _classify_model(self, card: ParsedModelCard) -> ClassificationResult:
        assert card.model_type is not None  # noqa: S101 — invariant via VO validator
        mtype = card.model_type.upper()
        mapping = _MODEL_TYPE_TO_CATEGORY.get(mtype)
        if mapping is None:
            raise ClassificationAmbiguousError(
                card=card,
                reason=f'unknown .MODEL TYPE {mtype!r}',
            )
        category, subcategory = mapping
        # Refine DIODE subcategory из header'а (F11 partial).
        if category is ComponentCategory.DIODE:
            hdr_sub = card.header_meta.get('subcategory')
            if hdr_sub:
                subcategory = hdr_sub.lower()
        return ClassificationResult(
            category=category,
            subcategory=subcategory,
            reason=f'.MODEL TYPE={mtype}',
            ambiguous=False,
        )

    def _classify_subckt(self, card: ParsedModelCard) -> ClassificationResult:
        assert card.pins is not None  # noqa: S101 — invariant via VO validator
        n_pins = len(card.pins)
        upper_pins = {p.upper() for p in card.pins}

        # 5+ pins с op-amp-style names → OPAMP.
        if n_pins >= _PINS_OPAMP_MIN and upper_pins & _OPAMP_PIN_HINTS:
            return ClassificationResult(
                category=ComponentCategory.OPAMP,
                subcategory=OpampKind.FULL_VENDOR.value,
                reason=f'{n_pins}-pin SUBCKT с op-amp-style pin names',
                ambiguous=False,
            )

        # Internal `.MODEL` discovery — body-scan.
        internal_models = _scan_internal_model_types(card.body)
        if card.kind is ModelKind.SUBCKT and n_pins == _PINS_THREE:
            # 3-pin: ambiguous bipolar/FET/tube — refine internal cards.
            for itype in internal_models:
                mapping = _MODEL_TYPE_TO_CATEGORY.get(itype)
                if mapping is not None:
                    category, subcategory = mapping
                    return ClassificationResult(
                        category=category,
                        subcategory=subcategory,
                        reason=f'3-pin SUBCKT с internal .MODEL TYPE={itype}',
                        ambiguous=False,
                    )
            raise ClassificationAmbiguousError(
                card=card,
                reason=(
                    '3-pin SUBCKT без .MODEL внутри — нельзя дискриминировать '
                    'BJT / MOSFET / TUBE'
                ),
            )

        if n_pins == _PINS_TWO:
            # 2-pin + `.MODEL D` внутри → DIODE.
            if 'D' in internal_models:
                return ClassificationResult(
                    category=ComponentCategory.DIODE,
                    subcategory=DiodeKind.SIGNAL.value,
                    reason='2-pin SUBCKT с internal .MODEL D',
                    ambiguous=False,
                )
            raise ClassificationAmbiguousError(
                card=card,
                reason='2-pin SUBCKT без .MODEL D — нельзя классифицировать',
            )

        raise ClassificationAmbiguousError(
            card=card,
            reason=f'{n_pins}-pin SUBCKT без распознаваемых hints',
        )


def _default_subcategory(category: ComponentCategory) -> str:
    # Fallback subcategory если header не задал её (только для override flow).
    defaults: dict[ComponentCategory, str] = {
        ComponentCategory.BJT: BjtKind.NPN.value,
        ComponentCategory.JFET: JfetKind.NJF.value,
        ComponentCategory.MOSFET: MosfetKind.NMOS.value,
        ComponentCategory.DIODE: DiodeKind.SIGNAL.value,
        ComponentCategory.OPAMP: OpampKind.FULL_VENDOR.value,
    }
    if category not in defaults:
        msg = f'no default subcategory for {category}'
        raise ValueError(msg)
    return defaults[category]


def _join_continuations(lines: list[str]) -> list[tuple[int, str]]:
    """Склеить `+ ...` continuation lines к предыдущей, сохранив line numbers."""
    out: list[tuple[int, str]] = []
    for idx, raw in enumerate(lines):
        stripped = raw.lstrip()
        if stripped.startswith('+') and out:
            prev_idx, prev_line = out[-1]
            joined = prev_line.rstrip() + ' ' + stripped[1:].lstrip()
            out[-1] = (prev_idx, joined)
        else:
            out.append((idx, raw))
    return out


def _extract_cards(lines: list[tuple[int, str]]) -> list[ParsedModelCard]:
    """Walk через joined lines, собрать ParsedModelCard."""
    cards: list[ParsedModelCard] = []
    pending_headers: dict[str, str] = {}
    i = 0
    while i < len(lines):
        _, line = lines[i]
        header_match = _HEADER_META_RE.match(line)
        if header_match:
            key = header_match.group(1).lower()
            value = header_match.group(2).strip()
            pending_headers[key] = value
            i += 1
            continue

        subckt_match = _SUBCKT_OPEN_RE.match(line)
        if subckt_match:
            name = subckt_match.group(1).upper()
            pins_raw = subckt_match.group(2).split()
            pins = _strip_params(pins_raw)
            body_lines = [line]
            j = i + 1
            while j < len(lines):
                _, next_line = lines[j]
                body_lines.append(next_line)
                if _SUBCKT_END_RE.match(next_line):
                    break
                j += 1
            cards.append(
                ParsedModelCard(
                    kind=ModelKind.SUBCKT,
                    name=name,
                    body='\n'.join(body_lines) + '\n',
                    model_type=None,
                    pins=tuple(pins),
                    header_meta=dict(pending_headers),
                ),
            )
            pending_headers.clear()
            i = j + 1
            continue

        model_match = _MODEL_OPEN_RE.match(line)
        if model_match:
            name = model_match.group(1).upper()
            mtype = model_match.group(2).upper()
            cards.append(
                ParsedModelCard(
                    kind=ModelKind.MODEL,
                    name=name,
                    body=line + '\n',
                    model_type=mtype,
                    pins=None,
                    header_meta=dict(pending_headers),
                ),
            )
            pending_headers.clear()
            i += 1
            continue

        # Не-header, не-card строка — сбрасываем pending_headers (они
        # принадлежали к предыдущей секции).
        if line.strip() and not line.lstrip().startswith('*'):
            pending_headers.clear()
        i += 1

    return cards


def _strip_params(pins_raw: list[str]) -> list[str]:
    """Удалить `PARAMS:` хвост из pin-list, оставить только pin names."""
    out: list[str] = []
    for token in pins_raw:
        if token.upper().startswith('PARAMS:') or '=' in token:
            break
        out.append(token)
    return out


def _scan_internal_model_types(body: str) -> set[str]:
    """Найти все TYPE'ы у `.MODEL` карточек внутри SUBCKT body."""
    joined = _join_continuations(body.splitlines())
    types: set[str] = set()
    for _, line in joined:
        m = _MODEL_OPEN_RE.match(line)
        if m:
            types.add(m.group(2).upper())
    return types
