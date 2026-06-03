"""T031 Phase 5 templates smoke (T175): materialize → kicad-cli netlist → ngspice .op.

Acceptance: оба template'а (6zh38p-if-amp, 6p13s-se-resistive) дают
operating point в expected range. Smoke validates end-to-end pipeline:
template materialization → kicad-cli SPICE netlist export → ngspice
.op → Ia op-point.

Skip когда KiCad или ngspice не установлены на CI runner — ловит
regression только на dev-машинах с tool-chain.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

from composition.main import build_cli_app

if TYPE_CHECKING:
    pass

_KICAD_AVAILABLE = shutil.which('kicad-cli') is not None
_NGSPICE_AVAILABLE = shutil.which('ngspice') is not None

needs_kicad = pytest.mark.skipif(
    not _KICAD_AVAILABLE, reason='kicad-cli not installed',
)
needs_ngspice = pytest.mark.skipif(
    not _NGSPICE_AVAILABLE, reason='ngspice not installed',
)

_ENV_VARS = ('EFACTORY_PROJECTS_ROOT', 'XDG_DATA_HOME')


def _setup_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Изолировать env + projects_root в tmp_path."""
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.setenv('EFACTORY_PROJECTS_ROOT', str(tmp_path / 'projects'))
    monkeypatch.chdir(tmp_path)
    return tmp_path / 'projects'


def _materialize_and_simulate(
    project_name: str, template_name: str, projects_root: Path
) -> Path:
    """Create project from template, design-to-sim op, return netlist path."""
    app = build_cli_app()
    runner = CliRunner()
    r = runner.invoke(
        app, ['project', 'create', '--name', project_name, '--template', template_name],
    )
    assert r.exit_code == 0, r.output
    r = runner.invoke(
        app,
        [
            'bridge', 'design-to-sim', 'op', project_name,
            '--schematic', f'{project_name}.kicad_sch',
        ],
    )
    assert r.exit_code == 0, r.output
    return projects_root / project_name / 'sim' / f'{project_name}.cir'


def _ngspice_op_probe(
    netlist: Path, *, prints: tuple[str, ...]
) -> dict[str, float]:
    """ngspice -b с .op + print statements, parse значения."""
    deck = (
        f'.include {netlist}\n'
        '.control\n'
        'op\n'
        f'print {" ".join(prints)}\n'
        'quit\n'
        '.endc\n'
    )
    with tempfile.NamedTemporaryFile(
        mode='w', suffix='.cir', delete=False, encoding='utf-8',
    ) as fh:
        fh.write(deck)
        deck_path = Path(fh.name)
    try:
        result = subprocess.run(
            ['ngspice', '-b', str(deck_path)],
            capture_output=True, text=True, check=False, timeout=60,
        )
    finally:
        deck_path.unlink(missing_ok=True)
    parsed: dict[str, float] = {}
    for line in result.stdout.splitlines():
        line = line.strip()
        if '=' not in line:
            continue
        name, sep, value = line.partition('=')
        if not sep:
            continue
        name = name.strip().lower()
        value = value.strip()
        try:
            parsed[name] = float(value)
        except ValueError:
            pass
    return parsed


# ============================== 6Ж38П IF amp ==============================


@needs_kicad
@needs_ngspice
def test_6zh38p_if_amp_op_point(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """6Ж38П IF amp materialize + .op smoke.

    Expected (per Phase 5 verification):
    - V(plate) in [80, 140] V (active region, well below Vbb=150).
    - Ia in [2.5, 5.0] mA (class A, self-bias Vgk_eff≈-2V).
    """
    projects_root = _setup_env(tmp_path, monkeypatch)
    netlist = _materialize_and_simulate(
        'p_6zh38p', '6zh38p-if-amp', projects_root,
    )

    probe = _ngspice_op_probe(
        netlist, prints=('v(/plate)', 'v(/cathode)', 'i(V1)'),
    )
    v_plate = probe['v(/plate)']
    i_v1 = probe['i(v1)']
    # I(V1) negative = current flowing out of Vbb = anode current Ia
    ia_ma = -i_v1 * 1000.0

    assert 80.0 < v_plate < 140.0, (
        f'V(plate)={v_plate:.1f}V outside [80,140]V active region'
    )
    assert 2.5 < ia_ma < 5.0, (
        f'Ia={ia_ma:.2f}mA outside [2.5,5.0]mA class A range'
    )


# ============================== 6П13С SE-amp ==============================


@needs_kicad
@needs_ngspice
def test_6p13s_se_resistive_op_point(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """6П13С SE-amp materialize + .op smoke.

    Expected (T173 refined bias, Rk=470Ω):
    - V(plate) in [40, 120] V (active region, well below Vbb=250).
    - Ia in [25, 50] mA (class A, self-bias Vgk_eff≈-15V).
    - Ig2 < 15 mA (screen dissipation < 4W max with Vg2=200V).
    """
    projects_root = _setup_env(tmp_path, monkeypatch)
    netlist = _materialize_and_simulate(
        'p_6p13s', '6p13s-se-resistive', projects_root,
    )

    probe = _ngspice_op_probe(
        netlist,
        prints=('v(/plate)', 'v(/cathode)', 'i(V1)', 'i(V2)'),
    )
    v_plate = probe['v(/plate)']
    ia_ma = -probe['i(v1)'] * 1000.0
    ig2_ma = -probe['i(v2)'] * 1000.0

    assert 40.0 < v_plate < 120.0, (
        f'V(plate)={v_plate:.1f}V outside [40,120]V active region'
    )
    assert 25.0 < ia_ma < 50.0, (
        f'Ia={ia_ma:.2f}mA outside [25,50]mA T173 refined bias range'
    )
    assert ig2_ma < 15.0, (
        f'Ig2={ig2_ma:.2f}mA exceeds 15mA — screen overload risk '
        f'(>15mA × 200V = 3W approaching Pg2_max=4W)'
    )
