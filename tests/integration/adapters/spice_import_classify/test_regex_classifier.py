"""RegexSpiceModelClassifier — T030 Phase 2.

Hybrid tests: unit-level через ad-hoc synthetic decks + integration через
tests/data/spice_import/vendor_samples/ фикстуры.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from adapters.outbound.spice_import_classify.classifier import (
    RegexSpiceModelClassifier,
)
from domain.spice_import import (
    ClassificationAmbiguousError,
    ImportSource,
    ModelKind,
    RawImport,
)
from domain.spice_model import ComponentCategory

_FIXTURES = (
    Path(__file__).resolve().parents[3] / 'data' / 'spice_import' / 'vendor_samples'
)


def _raw_from_text(text: str) -> RawImport:
    return RawImport(
        source=ImportSource(kind='file', location='/synthetic.lib'),
        bytes_text=text,
        sha256='0' * 64,
        downloaded_at=datetime(2026, 6, 5, 12, 0, tzinfo=UTC),
    )


def _raw_from_fixture(name: str) -> RawImport:
    text = (_FIXTURES / name).read_text(encoding='utf-8')
    return RawImport(
        source=ImportSource(kind='file', location=str(_FIXTURES / name)),
        bytes_text=text,
        sha256='1' * 64,
        downloaded_at=datetime(2026, 6, 5, 12, 0, tzinfo=UTC),
    )


# === Fixture-based: vendor sample files ===


def test_classify_2n3904_npn() -> None:
    cls = RegexSpiceModelClassifier()
    raw = _raw_from_fixture('2n3904_bjt_npn.lib')
    results = cls.classify_all(raw)
    assert len(results) == 1
    card, classification = results[0]
    assert card.kind is ModelKind.MODEL
    assert card.name == 'Q2N3904'
    assert card.model_type == 'NPN'
    assert classification.category is ComponentCategory.BJT
    assert classification.subcategory == 'npn'
    assert not classification.ambiguous


def test_classify_2n3906_pnp() -> None:
    cls = RegexSpiceModelClassifier()
    results = cls.classify_all(_raw_from_fixture('2n3906_bjt_pnp.lib'))
    card, classification = results[0]
    assert classification.category is ComponentCategory.BJT
    assert classification.subcategory == 'pnp'


def test_classify_2n5457_njf() -> None:
    cls = RegexSpiceModelClassifier()
    results = cls.classify_all(_raw_from_fixture('2n5457_jfet_njf.lib'))
    card, classification = results[0]
    assert card.model_type == 'NJF'
    assert classification.category is ComponentCategory.JFET
    assert classification.subcategory == 'njf'


def test_classify_irf540_nmos() -> None:
    cls = RegexSpiceModelClassifier()
    results = cls.classify_all(_raw_from_fixture('irf540_mosfet_nmos.lib'))
    card, classification = results[0]
    assert card.name == 'IRF540'
    assert classification.category is ComponentCategory.MOSFET
    assert classification.subcategory == 'nmos'


def test_classify_1n4148_diode_with_subcategory_header() -> None:
    cls = RegexSpiceModelClassifier()
    results = cls.classify_all(_raw_from_fixture('1n4148_diode.lib'))
    card, classification = results[0]
    assert card.name == 'D1N4148'
    assert classification.category is ComponentCategory.DIODE
    assert classification.subcategory == 'signal'  # из header'а
    assert card.header_meta.get('subcategory') == 'signal'


def test_classify_opa_generic_subckt_with_header_vendor() -> None:
    cls = RegexSpiceModelClassifier()
    results = cls.classify_all(_raw_from_fixture('opa_generic.lib'))
    card, classification = results[0]
    assert card.kind is ModelKind.SUBCKT
    assert card.name == 'OPAGEN'
    assert card.pins == ('VCC', 'VEE', 'INP', 'INM', 'OUT')
    assert classification.category is ComponentCategory.OPAMP
    assert classification.subcategory == 'full_vendor'
    assert card.header_meta.get('vendor') == 'ti'


def test_classify_dual_opamp_splits_to_two() -> None:
    cls = RegexSpiceModelClassifier()
    results = cls.classify_all(_raw_from_fixture('dual_opamp_pair.lib'))
    assert len(results) == 2
    names = {r[0].name for r in results}
    assert names == {'OPAONE', 'OPATWO'}
    for _, classification in results:
        assert classification.category is ComponentCategory.OPAMP


def test_classify_encrypted_block_raises_content_rejected() -> None:
    from domain.spice_import import ContentRejectedError

    cls = RegexSpiceModelClassifier()
    with pytest.raises(ContentRejectedError, match='encrypted'):
        cls.classify_all(_raw_from_fixture('encrypted_block.lib'))


def test_classify_html_login_raises_content_rejected() -> None:
    from domain.spice_import import ContentRejectedError

    cls = RegexSpiceModelClassifier()
    with pytest.raises(ContentRejectedError, match='html|login'):
        cls.classify_all(_raw_from_fixture('html_login_page.lib'))


def test_classify_ambiguous_3pin_subckt() -> None:
    cls = RegexSpiceModelClassifier()
    with pytest.raises(ClassificationAmbiguousError, match='ambiguous|3-pin|UNKNOWN3'):
        cls.classify_all(_raw_from_fixture('ambiguous_3pin_subckt.lib'))


# === Inline synthetic decks: edge cases ===


def test_classify_empty_deck_returns_empty() -> None:
    cls = RegexSpiceModelClassifier()
    assert cls.classify_all(_raw_from_text('* just a comment\n')) == ()


def test_classify_model_continuation_lines_joined() -> None:
    text = (
        '.MODEL QFOO NPN (BF=200\n'
        '+ IS=1e-14\n'
        '+ VAF=70)\n'
    )
    cls = RegexSpiceModelClassifier()
    results = cls.classify_all(_raw_from_text(text))
    card, _ = results[0]
    assert card.name == 'QFOO'
    assert 'BF=200' in card.body
    assert 'IS=1e-14' in card.body
    assert 'VAF=70' in card.body


def test_classify_header_override_category_subcategory() -> None:
    text = (
        '* category: diode\n'
        '* subcategory: schottky\n'
        '.MODEL BAT85 D (IS=1e-9)\n'
    )
    cls = RegexSpiceModelClassifier()
    _, classification = cls.classify_all(_raw_from_text(text))[0]
    assert classification.category is ComponentCategory.DIODE
    assert classification.subcategory == 'schottky'


def test_classify_subckt_with_pmos_internals() -> None:
    text = (
        '.SUBCKT IRF9540 D G S\n'
        'M1 D G S S PMOS_INT\n'
        '.MODEL PMOS_INT PMOS\n'
        '.ENDS\n'
    )
    cls = RegexSpiceModelClassifier()
    results = cls.classify_all(_raw_from_text(text))
    # Должен classify-ить outer SUBCKT (PMOS внутренний model — частный
    # implementation detail outer wrapper'а).
    outer = next(r for r in results if r[0].name == 'IRF9540')
    assert outer[1].category is ComponentCategory.MOSFET
    assert outer[1].subcategory == 'pmos'


def test_classify_lowercase_model_keywords_supported() -> None:
    text = '.model qux pnp (BF=100)\n'
    cls = RegexSpiceModelClassifier()
    results = cls.classify_all(_raw_from_text(text))
    card, classification = results[0]
    assert card.name == 'QUX'  # normalized uppercase
    assert classification.category is ComponentCategory.BJT
    assert classification.subcategory == 'pnp'


def test_classify_2pin_subckt_with_d_card_is_diode() -> None:
    text = (
        '.SUBCKT MYDIODE A K\n'
        'D1 A K DMODEL\n'
        '.MODEL DMODEL D\n'
        '.ENDS\n'
    )
    cls = RegexSpiceModelClassifier()
    outer = next(
        r for r in cls.classify_all(_raw_from_text(text)) if r[0].name == 'MYDIODE'
    )
    assert outer[1].category is ComponentCategory.DIODE


def test_classify_5pin_subckt_with_opamp_names_is_opamp() -> None:
    text = (
        '.SUBCKT MYAMP V+ V- IN+ IN- OUT\n'
        'R1 IN+ IN- 1MEG\n'
        '.ENDS\n'
    )
    cls = RegexSpiceModelClassifier()
    _, classification = cls.classify_all(_raw_from_text(text))[0]
    assert classification.category is ComponentCategory.OPAMP
    assert classification.subcategory == 'full_vendor'
