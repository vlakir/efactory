"""Integration: FilesystemSpiceModelLibrary через tmp_path (T006)."""

from __future__ import annotations

from pathlib import Path

import pytest

from adapters.outbound.spice_models.conversion import (
    convert_pwrs_to_ngspice,
)
from adapters.outbound.spice_models.spice_library import (
    FilesystemSpiceModelLibrary,
)
from domain.spice_model import ModelSource, TubeType
from ports.outbound.spice_model_library import (
    SpiceModelLibraryDuplicateError,
    SpiceModelNotFoundError,
)

_TRIODE_LIB = """\
* Generic Koren-style triode model
* Pins: P (plate), G (grid), K (cathode)
.SUBCKT GENERIC_TRIODE P G K
Bp p 0 V=V(P,K)
.ENDS
"""

_PENTODE_INC = """\
* tube_type: pentode
* Generic Ayumi-style pentode using `^` exponent
.SUBCKT GENERIC_PENTODE P G2 G K
Bp p 0 V=(V(P,K)^1.5)/100
.ENDS
"""

_DUAL_LIB = """\
* tube_type: dual_triode
.SUBCKT TWIN_TRIODE P1 G1 K1 P2 G2 K2
Bp1 p1 0 V=V(P1,K1)
.ENDS
"""


def _seed(
    root: Path,
    source: ModelSource,
    filename: str,
    content: str,
    category: str = 'tubes',
) -> Path:
    """Создать файл по схеме `<root>/<category>/<source>/<filename>`."""
    target = root / category / source.value / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding='utf-8')
    return target


async def test_list_empty_when_root_missing(tmp_path: Path) -> None:
    repo = FilesystemSpiceModelLibrary(tmp_path / 'missing')

    assert await repo.list_all() == []


async def test_list_empty_when_no_source_dirs(tmp_path: Path) -> None:
    repo = FilesystemSpiceModelLibrary(tmp_path)

    assert await repo.list_all() == []


async def test_list_returns_models_sorted_by_id(tmp_path: Path) -> None:
    _seed(tmp_path, ModelSource.KOREN, 'GENERIC_TRIODE.lib', _TRIODE_LIB)
    _seed(tmp_path, ModelSource.AYUMI, 'GENERIC_PENTODE.inc', _PENTODE_INC)
    repo = FilesystemSpiceModelLibrary(tmp_path)

    models = await repo.list_all()

    assert [m.id for m in models] == ['GENERIC_PENTODE', 'GENERIC_TRIODE']
    assert models[0].source is ModelSource.AYUMI
    assert models[1].source is ModelSource.KOREN


async def test_list_detects_tube_type_from_header(tmp_path: Path) -> None:
    _seed(tmp_path, ModelSource.AYUMI, 'GENERIC_PENTODE.inc', _PENTODE_INC)
    repo = FilesystemSpiceModelLibrary(tmp_path)

    model = (await repo.list_all())[0]

    assert model.tube_type is TubeType.PENTODE


async def test_list_detects_tube_type_by_pin_count_fallback(tmp_path: Path) -> None:
    _seed(tmp_path, ModelSource.KOREN, 'GENERIC_TRIODE.lib', _TRIODE_LIB)
    _seed(tmp_path, ModelSource.CUSTOM, 'TWIN.lib', _DUAL_LIB)
    repo = FilesystemSpiceModelLibrary(tmp_path)

    models = {m.id: m for m in await repo.list_all()}

    assert models['GENERIC_TRIODE'].tube_type is TubeType.TRIODE
    assert models['TWIN'].tube_type is TubeType.DUAL_TRIODE


async def test_list_uses_filename_stem_as_id(tmp_path: Path) -> None:
    """C3: id = uppercase filename stem (не .SUBCKT name)."""
    _seed(
        tmp_path, ModelSource.KOREN, 'el34_koren.lib',
        '.SUBCKT EL34 P G2 G K\n.ENDS\n',
    )
    _seed(
        tmp_path, ModelSource.AYUMI, 'el34_ayumi.inc',
        '.SUBCKT EL34 P G2 G K\n.ENDS\n',
    )
    repo = FilesystemSpiceModelLibrary(tmp_path)

    ids = [m.id for m in await repo.list_all()]
    assert ids == ['EL34_AYUMI', 'EL34_KOREN']


async def test_list_skips_non_spice_extensions(tmp_path: Path) -> None:
    _seed(tmp_path, ModelSource.KOREN, 'GENERIC_TRIODE.lib', _TRIODE_LIB)
    (tmp_path / 'tubes' / 'koren' / 'README.md').write_text('not a model')
    (tmp_path / 'tubes' / 'koren' / '.gitkeep').write_text('')
    repo = FilesystemSpiceModelLibrary(tmp_path)

    models = await repo.list_all()
    assert [m.id for m in models] == ['GENERIC_TRIODE']


async def test_duplicate_id_raises(tmp_path: Path) -> None:
    """Resolved #9: fail-fast при дубликате id."""
    _seed(tmp_path, ModelSource.KOREN, 'XX.lib', '.SUBCKT XX P G K\n.ENDS\n')
    _seed(tmp_path, ModelSource.CUSTOM, 'XX.lib', '.SUBCKT XX P G K\n.ENDS\n')
    repo = FilesystemSpiceModelLibrary(tmp_path)

    with pytest.raises(SpiceModelLibraryDuplicateError):
        await repo.list_all()


async def test_get_by_id_returns_model(tmp_path: Path) -> None:
    _seed(tmp_path, ModelSource.KOREN, 'GENERIC_TRIODE.lib', _TRIODE_LIB)
    repo = FilesystemSpiceModelLibrary(tmp_path)

    model = await repo.get_by_id('GENERIC_TRIODE')

    assert model.name == 'GENERIC_TRIODE'
    assert model.subckt_pins == ('P', 'G', 'K')


async def test_get_by_id_missing_raises(tmp_path: Path) -> None:
    repo = FilesystemSpiceModelLibrary(tmp_path)

    with pytest.raises(SpiceModelNotFoundError):
        await repo.get_by_id('NONEXISTENT')


async def test_read_subckt_returns_block(tmp_path: Path) -> None:
    _seed(tmp_path, ModelSource.KOREN, 'GENERIC_TRIODE.lib', _TRIODE_LIB)
    repo = FilesystemSpiceModelLibrary(tmp_path)

    block = await repo.read_subckt('GENERIC_TRIODE')

    assert block.startswith('.SUBCKT GENERIC_TRIODE P G K')
    assert '.ENDS' in block
    assert '*' not in block.splitlines()[0]  # без комментариев в начале


async def test_read_subckt_ayumi_converts_caret_to_double_star(
    tmp_path: Path,
) -> None:
    """Resolved #4: Ayumi `^` → ngspice `**` на чтении."""
    _seed(tmp_path, ModelSource.AYUMI, 'GENERIC_PENTODE.inc', _PENTODE_INC)
    repo = FilesystemSpiceModelLibrary(tmp_path)

    block = await repo.read_subckt('GENERIC_PENTODE')

    assert '^' not in block
    assert '**1.5' in block


async def test_read_subckt_koren_is_not_converted(tmp_path: Path) -> None:
    text = '.SUBCKT XX P G K\nBp p 0 V=V(P,K)**2\n.ENDS\n'
    _seed(tmp_path, ModelSource.KOREN, 'XX.lib', text)
    repo = FilesystemSpiceModelLibrary(tmp_path)

    block = await repo.read_subckt('XX')

    assert '**2' in block  # без изменений


def test_convert_ayumi_replaces_caret_globally() -> None:
    from adapters.outbound.spice_models.conversion import convert_ayumi_to_ngspice

    assert convert_ayumi_to_ngspice('V=x^2 + y^3') == 'V=x**2 + y**3'
    assert convert_ayumi_to_ngspice('no caret') == 'no caret'
    assert convert_ayumi_to_ngspice('') == ''


# ---------- T102: PWRS → sgn()*pwr() конвертер ----------


def test_convert_pwrs_simple_call() -> None:
    """Простейший случай: PWRS(V(7),1.4) → sgn(V(7))*pwr(abs(V(7)),1.4)."""
    src = 'G1 P K VALUE={PWRS(V(7),1.4)/1060}'
    expected = 'G1 P K VALUE={sgn(V(7))*pwr(abs(V(7)),1.4)/1060}'
    assert convert_pwrs_to_ngspice(src) == expected


def test_convert_pwrs_nested_parens_in_arg() -> None:
    """Вложенные скобки в первом аргументе: PWRS(V(P,K),2) корректен."""
    src = 'V={PWRS(V(P,K),2)}'
    expected = 'V={sgn(V(P,K))*pwr(abs(V(P,K)),2)}'
    assert convert_pwrs_to_ngspice(src) == expected


def test_convert_pwrs_multiple_in_one_expression() -> None:
    """Реальный паттерн из 6N1P: два PWRS в одном выражении."""
    src = 'G1 P K VALUE={(PWRS(V(7),1.4)+PWRS(V(7),1.4))/450}'
    expected = (
        'G1 P K VALUE={(sgn(V(7))*pwr(abs(V(7)),1.4)'
        '+sgn(V(7))*pwr(abs(V(7)),1.4))/450}'
    )
    assert convert_pwrs_to_ngspice(src) == expected


def test_convert_pwrs_no_pwrs_returned_as_is() -> None:
    """Текст без PWRS возвращается без изменений (no-op fast path)."""
    src = 'Bp p 0 V=V(P,K)\n.ENDS\n'
    assert convert_pwrs_to_ngspice(src) == src


def test_convert_pwrs_empty_string() -> None:
    assert convert_pwrs_to_ngspice('') == ''


def test_convert_pwrs_idempotent() -> None:
    """f(f(x)) == f(x): повторное применение ничего не меняет."""
    src = 'G1 P K VALUE={(PWRS(V(7),1.4)+PWRS(V(7),1.4))/1060}'
    once = convert_pwrs_to_ngspice(src)
    twice = convert_pwrs_to_ngspice(once)
    assert once == twice


def test_convert_pwrs_case_insensitive_match() -> None:
    """ngspice case-insensitive; PWRS / pwrs / Pwrs — все одинаково."""
    assert (
        convert_pwrs_to_ngspice('pwrs(x,2)') == 'sgn(x)*pwr(abs(x),2)'
    )
    assert (
        convert_pwrs_to_ngspice('Pwrs(x,2)') == 'sgn(x)*pwr(abs(x),2)'
    )


def test_convert_pwrs_does_not_match_identifier_suffix() -> None:
    """`mypwrs(` — не PWRS-вызов; не должен трогаться."""
    src = 'foo mypwrs(1,2) bar'
    assert convert_pwrs_to_ngspice(src) == src


def test_convert_pwrs_handles_whitespace_around_args() -> None:
    """`PWRS( V(7) , 1.4 )` — пробелы внутри скобок, аргументы strip'нуты."""
    src = 'PWRS( V(7) , 1.4 )'
    expected = 'sgn(V(7))*pwr(abs(V(7)),1.4)'
    assert convert_pwrs_to_ngspice(src) == expected


def test_convert_pwrs_recursive_nested_pwrs() -> None:
    """PWRS внутри PWRS обрабатывается рекурсивно (защита, не реальный кейс)."""
    src = 'PWRS(PWRS(x,2),3)'
    # внутренняя: sgn(x)*pwr(abs(x),2)
    # внешняя: sgn(<inner>)*pwr(abs(<inner>),3)
    expected = (
        'sgn(sgn(x)*pwr(abs(x),2))*pwr(abs(sgn(x)*pwr(abs(x),2)),3)'
    )
    assert convert_pwrs_to_ngspice(src) == expected


# ---------- User overlay (Q3 fix-up) ----------


async def test_user_overlay_adds_new_model(tmp_path: Path) -> None:
    """User-каталог добавляет модель, которой нет в built-in."""
    built_in = tmp_path / 'built_in'
    user = tmp_path / 'user'
    _seed(built_in, ModelSource.KOREN, 'GENERIC_TRIODE.lib', _TRIODE_LIB)
    _seed(
        user, ModelSource.CUSTOM, 'MY_TUBE.lib',
        '.SUBCKT MY_TUBE P G K\n.ENDS\n',
    )
    repo = FilesystemSpiceModelLibrary(built_in, user)

    models = {m.id: m for m in await repo.list_all()}

    assert set(models) == {'GENERIC_TRIODE', 'MY_TUBE'}
    assert models['GENERIC_TRIODE'].is_user is False
    assert models['MY_TUBE'].is_user is True


async def test_user_overlay_overrides_built_in_by_id(tmp_path: Path) -> None:
    """User-id с тем же именем перезаписывает built-in (overlay семантика)."""
    built_in = tmp_path / 'built_in'
    user = tmp_path / 'user'
    _seed(built_in, ModelSource.KOREN, 'GENERIC_TRIODE.lib', _TRIODE_LIB)
    user_content = '.SUBCKT MY_OWN_TRIODE P G K\n* tuned for my V12 stock\n.ENDS\n'
    _seed(user, ModelSource.CUSTOM, 'GENERIC_TRIODE.lib', user_content)
    repo = FilesystemSpiceModelLibrary(built_in, user)

    model = await repo.get_by_id('GENERIC_TRIODE')

    assert model.is_user is True
    assert model.source is ModelSource.CUSTOM
    # read_subckt возвращает user-файл, не built-in
    subckt = await repo.read_subckt('GENERIC_TRIODE')
    assert 'MY_OWN_TRIODE' in subckt


async def test_user_overlay_missing_dir_falls_back_to_built_in(
    tmp_path: Path,
) -> None:
    built_in = tmp_path / 'built_in'
    _seed(built_in, ModelSource.KOREN, 'GENERIC_TRIODE.lib', _TRIODE_LIB)
    repo = FilesystemSpiceModelLibrary(built_in, tmp_path / 'no_user_dir')

    models = await repo.list_all()
    assert [m.id for m in models] == ['GENERIC_TRIODE']
    assert models[0].is_user is False


async def test_duplicate_within_user_root_still_fails(tmp_path: Path) -> None:
    """Внутри user root duplicate id всё ещё fail-fast."""
    built_in = tmp_path / 'built_in'
    user = tmp_path / 'user'
    _seed(user, ModelSource.KOREN, 'XX.lib', '.SUBCKT XX P G K\n.ENDS\n')
    _seed(user, ModelSource.CUSTOM, 'XX.lib', '.SUBCKT XX P G K\n.ENDS\n')
    repo = FilesystemSpiceModelLibrary(built_in, user)

    with pytest.raises(SpiceModelLibraryDuplicateError):
        await repo.list_all()


async def test_user_overlay_none_argument_works(tmp_path: Path) -> None:
    """user_library_root=None — поведение как до fix-up (только built-in)."""
    _seed(tmp_path, ModelSource.KOREN, 'GENERIC_TRIODE.lib', _TRIODE_LIB)
    repo = FilesystemSpiceModelLibrary(tmp_path, None)

    models = await repo.list_all()
    assert [m.id for m in models] == ['GENERIC_TRIODE']
    assert models[0].is_user is False


# ---------- Rectifier support (expanded library) ----------

_RECTIFIER_LIB = """\
* 5AR4 — full-wave indirectly-heated rectifier.
* tube_type: rectifier
* Pins: A1, A2, K.
.SUBCKT TEST_RECT A1 A2 K
D1 A1 K DIODE_TEST
D2 A2 K DIODE_TEST
.MODEL DIODE_TEST D(IS=8m RS=75 N=2.0 BV=1500)
.ENDS TEST_RECT
"""

_HALF_WAVE_LIB = """\
* Half-wave rectifier (2 pin: anode + cathode).
.SUBCKT HALFWAVE A K
D1 A K DIODE_HW
.MODEL DIODE_HW D(IS=2m RS=200 N=2.0 BV=800)
.ENDS HALFWAVE
"""


async def test_rectifier_full_wave_detected_via_header(tmp_path: Path) -> None:
    """3-pin SUBCKT с `* tube_type: rectifier` header → RECTIFIER (не TRIODE)."""
    _seed(tmp_path, ModelSource.KOREN, 'TEST_RECT.lib', _RECTIFIER_LIB)
    repo = FilesystemSpiceModelLibrary(tmp_path)

    model = (await repo.list_all())[0]

    assert model.tube_type is TubeType.RECTIFIER
    assert model.subckt_pins == ('A1', 'A2', 'K')


async def test_rectifier_half_wave_detected_by_pin_count(tmp_path: Path) -> None:
    """2-pin SUBCKT → RECTIFIER (fallback heuristic, без header)."""
    _seed(tmp_path, ModelSource.KOREN, 'HALFWAVE.lib', _HALF_WAVE_LIB)
    repo = FilesystemSpiceModelLibrary(tmp_path)

    model = (await repo.list_all())[0]

    assert model.tube_type is TubeType.RECTIFIER
    assert model.subckt_pins == ('A', 'K')


async def test_rectifier_read_subckt_includes_model_directive(tmp_path: Path) -> None:
    _seed(tmp_path, ModelSource.KOREN, 'TEST_RECT.lib', _RECTIFIER_LIB)
    repo = FilesystemSpiceModelLibrary(tmp_path)

    block = await repo.read_subckt('TEST_RECT')

    assert '.SUBCKT TEST_RECT' in block
    assert '.MODEL DIODE_TEST' in block
    assert '.ENDS TEST_RECT' in block
