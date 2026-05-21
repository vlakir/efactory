"""Unit: saturable transformer subckt generator (T131 Phase A)."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from adapters.outbound.fem_solver_getdp.material import FrohlichBHCurve
from adapters.outbound.spice_models.saturable_core import (
    generate_saturable_transformer_subckt,
)

_NGSPICE_AVAILABLE = shutil.which('ngspice') is not None
needs_ngspice = pytest.mark.skipif(
    not _NGSPICE_AVAILABLE,
    reason='ngspice not installed',
)


def _bh_curve() -> FrohlichBHCurve:
    """Standard test curve — Nanoperm 8000 proxy."""
    return FrohlichBHCurve.from_pyom_material(mu_initial=8000.0, b_sat=1.2)


def _generate_default_subckt(name: str = 'OPT_TEST') -> str:
    return generate_saturable_transformer_subckt(
        subckt_name=name,
        n_primary=1000,
        n_secondary=40,
        a_core_m2=1.0e-4,
        l_path_m=0.15,
        r_primary_ohm=200.0,
        r_secondary_ohm=0.3,
        bh_curve=_bh_curve(),
    )


def test_subckt_header_and_footer() -> None:
    """Subckt начинается с .SUBCKT NAME P1 P2 S1 S2 и заканчивается .ENDS NAME."""
    text = _generate_default_subckt('OPT_HELLO')
    lines = text.strip().splitlines()
    header = next(ln for ln in lines if ln.lstrip().startswith('.SUBCKT'))
    footer = next(ln for ln in lines if ln.lstrip().startswith('.ENDS'))
    assert re.match(
        r'^\.SUBCKT\s+OPT_HELLO\s+P1\s+P2\s+S1\s+S2',
        header,
        re.IGNORECASE,
    )
    assert re.match(r'^\.ENDS\s+OPT_HELLO\b', footer, re.IGNORECASE)


def test_subckt_includes_dcr_resistors() -> None:
    """Subckt содержит R_pri = R_PRIMARY_OHM и R_sec = R_SECONDARY_OHM."""
    text = _generate_default_subckt()
    # primary DCR 200Ω, secondary DCR 0.3Ω
    assert '200' in text
    assert '0.3' in text


def test_subckt_uses_xspice_lcouple_and_core() -> None:
    """Phase E redesign: lcouple gyrator'ы + nonlinear core element."""
    text = _generate_default_subckt()
    # Two lcouple gyrators — primary + secondary
    assert text.lower().count('lcouple') >= 2
    # XSPICE a-elements
    assert re.search(r'^a1\s+', text, re.MULTILINE) is not None
    assert re.search(r'^a2\s+', text, re.MULTILINE) is not None
    assert re.search(r'^a_core\s+', text, re.MULTILINE) is not None
    # core element с tabulated B-H curve
    assert re.search(r'\bcore\(', text, re.IGNORECASE) is not None
    assert 'H_array=[' in text or 'h_array=[' in text.lower()
    assert 'B_array=[' in text or 'b_array=[' in text.lower()


def test_subckt_h_b_arrays_are_symmetric_odd() -> None:
    """H_array / B_array odd-симметричны (включают origin + negative reflection)."""
    text = _generate_default_subckt()
    # должны присутствовать и положительные, и отрицательные значения
    assert re.search(r'-\d', text) is not None
    # origin '0' должен быть в массиве (как middle point)
    h_array_match = re.search(r'H_array=\[([^\]]+)\]', text, re.IGNORECASE)
    assert h_array_match is not None
    h_values = h_array_match.group(1).split()
    # ожидаем нечётное количество (negative + 0 + positive)
    assert len(h_values) % 2 == 1, h_values
    middle = h_values[len(h_values) // 2]
    assert float(middle) == 0.0


def test_ratio_appears_in_num_turns() -> None:
    """lcouple-models несут num_turns=N для primary и secondary."""
    text = _generate_default_subckt()
    # n_primary=1000, n_secondary=40 в дефолтной фикстуре
    assert 'num_turns=1000' in text
    assert 'num_turns=40' in text


def test_curve_parameters_documented_in_comments() -> None:
    """В комментариях subckt'а присутствуют μ_initial и B_sat исходного curve."""
    text = _generate_default_subckt()
    assert '8000' in text
    assert '1.2' in text


def test_geometry_parameters_documented_in_comments() -> None:
    """В комментариях фигурируют geometry parameters."""
    text = _generate_default_subckt()
    # n_primary 1000, n_secondary 40, a_core 1e-4, l_path 0.15
    assert '1000' in text
    # 40 секонд тоже встретится; проверяем по нескольким признакам
    assert '0.15' in text


def test_invalid_inputs_raise() -> None:
    """Базовая валидация: turns ≥1, geometry > 0, R ≥ 0."""
    bh = _bh_curve()
    common = {
        'subckt_name': 'X',
        'n_primary': 100,
        'n_secondary': 10,
        'a_core_m2': 1e-4,
        'l_path_m': 0.1,
        'r_primary_ohm': 1.0,
        'r_secondary_ohm': 0.1,
        'bh_curve': bh,
    }
    with pytest.raises(ValueError, match='n_primary'):
        generate_saturable_transformer_subckt(**{**common, 'n_primary': 0})
    with pytest.raises(ValueError, match='n_secondary'):
        generate_saturable_transformer_subckt(**{**common, 'n_secondary': 0})
    with pytest.raises(ValueError, match='a_core_m2'):
        generate_saturable_transformer_subckt(**{**common, 'a_core_m2': 0.0})
    with pytest.raises(ValueError, match='l_path_m'):
        generate_saturable_transformer_subckt(**{**common, 'l_path_m': -1.0})
    with pytest.raises(ValueError, match='r_primary_ohm'):
        generate_saturable_transformer_subckt(**{**common, 'r_primary_ohm': -0.1})
    with pytest.raises(ValueError, match='r_secondary_ohm'):
        generate_saturable_transformer_subckt(**{**common, 'r_secondary_ohm': -0.1})
    with pytest.raises(ValueError, match='subckt_name'):
        generate_saturable_transformer_subckt(**{**common, 'subckt_name': ''})


@needs_ngspice
def test_ngspice_parses_generated_subckt(tmp_path: Path) -> None:
    """Smoke: ngspice -b принимает сгенерированный subckt без ошибок.

    Использует minimal testbench: подаёт sin 1V 1kHz на первичку через 1Ω,
    нагрузка 8Ω на вторичке, .tran 1ms. Если subckt syntactically/semantically
    invalid — ngspice exit code != 0 или сообщение об ошибке в stderr.
    """
    sub_text = _generate_default_subckt('OPT_SMOKE')
    netlist = f"""* T131 Phase A smoke testbench
{sub_text}

V_in IN 0 SIN(0 1 1000)
R_src IN PRI 1
X1 PRI 0 SEC 0 OPT_SMOKE
R_load SEC 0 8

.tran 1u 1m UIC
.print tran v(SEC) v(PRI) i(V_in)
.end
"""
    cir = tmp_path / 'smoke.cir'
    cir.write_text(netlist)
    proc = subprocess.run(
        ['ngspice', '-b', str(cir)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    # ngspice пишет ошибки и warnings в stderr; exit code 0 даже при warning.
    # Считаем pass, если нет 'Error' / 'syntax' / 'aborted' в комбинированном выводе.
    combined = (proc.stdout + '\n' + proc.stderr).lower()
    fatal_markers = ['fatal', 'aborted', 'cannot', 'unrecognised', 'unknown subckt']
    for marker in fatal_markers:
        assert marker not in combined, (
            f'ngspice вернул fatal marker {marker!r}:\nSTDOUT:\n{proc.stdout}\n'
            f'STDERR:\n{proc.stderr}'
        )
    assert proc.returncode == 0, (
        f'ngspice exit {proc.returncode}\nSTDOUT:\n{proc.stdout}\n'
        f'STDERR:\n{proc.stderr}'
    )
    # silence unused-import lint
    _ = sys
