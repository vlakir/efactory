"""E2E: bridge edit-value + design-to-sim (T004b) на RC-фильтре.

Acceptance: после изменения R1 с 1k на 10k через CLI `bridge edit`,
повторный `bridge design-to-sim op` показывает other V(/out) или
operating-point значения (sanity: R1 изменился, лампа netlist'а
содержит новый value).

T021 (Phase B) — добавлены тесты `bridge edit-and-resim` с
автосравнением метрик до/после.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from composition.main import build_cli_app

_KICAD_AVAILABLE = (
    any(
        (Path.home() / 'kicad').glob('kicad*.AppImage'),
    )
    or shutil.which('kicad-cli') is not None
)
_NGSPICE_AVAILABLE = shutil.which('ngspice') is not None

needs_kicad = pytest.mark.skipif(
    not _KICAD_AVAILABLE,
    reason='KiCad not installed',
)

needs_kicad_and_ngspice = pytest.mark.skipif(
    not (_KICAD_AVAILABLE and _NGSPICE_AVAILABLE),
    reason='KiCad and/or ngspice not installed',
)


def _setup_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Path:
    projects_root = tmp_path / 'projects'
    monkeypatch.setenv('EFACTORY_PROJECTS_ROOT', str(projects_root))
    monkeypatch.setenv('EFACTORY_SESSION_ROOT', str(tmp_path / 'sessions'))
    return projects_root


@needs_kicad
def test_bridge_edit_changes_value_in_schematic(
    rc_filter_schematic_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """bridge edit меняет value R1 в существующем .kicad_sch."""
    projects_root = _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()
    create_result = runner.invoke(
        build_cli_app(),
        ['project', 'create', '--name', 'editor_test'],
    )
    assert create_result.exit_code == 0, create_result.output

    project_path = projects_root / 'editor_test'
    schematic_dir = project_path / 'schematic'
    schematic_dir.mkdir(parents=True, exist_ok=True)
    target = schematic_dir / 'rc_filter.kicad_sch'
    shutil.copy(rc_filter_schematic_path, target)

    # Verify pre-edit value
    pre_text = target.read_text(encoding='utf-8')
    assert '(property "Value" "1k"' in pre_text

    result = runner.invoke(
        build_cli_app(),
        [
            'bridge',
            'edit',
            'editor_test',
            '--schematic',
            'schematic/rc_filter.kicad_sch',
            '--set',
            'R1=10k',
        ],
    )
    assert result.exit_code == 0, result.output
    assert "R1: '1k' → '10k'" in result.output

    # File теперь содержит value="10k" для R1 (был "1k").
    post_text = target.read_text(encoding='utf-8')
    assert post_text.count('(property "Value" "10k"') == 1
    assert '(property "Value" "1k"' not in post_text


@needs_kicad
def test_bridge_edit_unknown_reference_exits_1(
    rc_filter_schematic_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """bridge edit падает с exit 1 если ref не найден."""
    projects_root = _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()
    runner.invoke(
        build_cli_app(),
        ['project', 'create', '--name', 'editor_test'],
    )
    project_path = projects_root / 'editor_test'
    schematic_dir = project_path / 'schematic'
    schematic_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(rc_filter_schematic_path, schematic_dir / 'rc_filter.kicad_sch')

    result = runner.invoke(
        build_cli_app(),
        [
            'bridge',
            'edit',
            'editor_test',
            '--schematic',
            'schematic/rc_filter.kicad_sch',
            '--set',
            'R999=10k',
        ],
    )
    assert result.exit_code == 1
    assert 'R999' in result.output


@needs_kicad
def test_bridge_edit_invalid_set_format_exits_2(
    rc_filter_schematic_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projects_root = _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()
    runner.invoke(
        build_cli_app(),
        ['project', 'create', '--name', 'editor_test'],
    )
    project_path = projects_root / 'editor_test'
    schematic_dir = project_path / 'schematic'
    schematic_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(rc_filter_schematic_path, schematic_dir / 'rc_filter.kicad_sch')

    result = runner.invoke(
        build_cli_app(),
        [
            'bridge',
            'edit',
            'editor_test',
            '--schematic',
            'schematic/rc_filter.kicad_sch',
            '--set',
            'no_equals_sign',
        ],
    )
    assert result.exit_code == 2
    assert 'REF=VALUE' in result.output


# ====================================================================
# T021: bridge edit-and-resim (Phase B).
# ====================================================================


def _prepare_project_with_rc(
    rc_filter_schematic_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: str = 'editor_test',
) -> Path:
    """Создать проект `name`, скопировать RC-фильтр в его schematic/."""
    projects_root = _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()
    runner.invoke(build_cli_app(), ['project', 'create', '--name', name])
    project_path = projects_root / name
    schematic_dir = project_path / 'schematic'
    schematic_dir.mkdir(parents=True, exist_ok=True)
    target = schematic_dir / 'rc_filter.kicad_sch'
    shutil.copy(rc_filter_schematic_path, target)
    return projects_root


def test_bridge_edit_and_resim_invalid_set_format_exits_2(
    rc_filter_schematic_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--set` без `=` → exit 2 ещё до резолва проекта."""
    _prepare_project_with_rc(rc_filter_schematic_path, tmp_path, monkeypatch)
    runner = CliRunner()
    result = runner.invoke(
        build_cli_app(),
        [
            'bridge',
            'edit-and-resim',
            'editor_test',
            '--schematic',
            'schematic/rc_filter.kicad_sch',
            '--set',
            'no_equals',
            '--measure',
            'gain',
            '--freq',
            '1k',
        ],
    )
    assert result.exit_code == 2, result.output
    assert 'REF=VALUE' in result.output


def test_bridge_edit_and_resim_unknown_metric_exits_2(
    rc_filter_schematic_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--measure foobar` → exit 2 с понятным сообщением."""
    _prepare_project_with_rc(rc_filter_schematic_path, tmp_path, monkeypatch)
    runner = CliRunner()
    result = runner.invoke(
        build_cli_app(),
        [
            'bridge',
            'edit-and-resim',
            'editor_test',
            '--schematic',
            'schematic/rc_filter.kicad_sch',
            '--set',
            'R1=10k',
            '--measure',
            'foobar',
            '--freq',
            '1k',
        ],
    )
    assert result.exit_code == 2, result.output
    assert 'foobar' in result.output
    assert 'gain' in result.output  # allowed list shown


def test_bridge_edit_and_resim_missing_freq_for_gain_exits_2(
    rc_filter_schematic_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--measure gain` без `--freq` → EditAndResimConfig validation."""
    _prepare_project_with_rc(rc_filter_schematic_path, tmp_path, monkeypatch)
    runner = CliRunner()
    result = runner.invoke(
        build_cli_app(),
        [
            'bridge',
            'edit-and-resim',
            'editor_test',
            '--schematic',
            'schematic/rc_filter.kicad_sch',
            '--set',
            'R1=10k',
            '--measure',
            'gain',
        ],
    )
    assert result.exit_code == 2, result.output
    assert 'frequency_hz' in result.output


@needs_kicad_and_ngspice
def test_bridge_edit_and_resim_rc_filter_bandwidth_changes(
    rc_filter_schematic_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RC-corner 159 Hz @ R1=1k → 16 Hz @ R1=10k; bandwidth уменьшается."""
    _prepare_project_with_rc(rc_filter_schematic_path, tmp_path, monkeypatch)
    runner = CliRunner()
    result = runner.invoke(
        build_cli_app(),
        [
            'bridge',
            'edit-and-resim',
            'editor_test',
            '--schematic',
            'schematic/rc_filter.kicad_sch',
            '--set',
            'R1=10k',
            '--measure',
            'bandwidth',
            '--f-low',
            '1',
            '--f-high',
            '100k',
            '--output-signal',
            'v(/out)',
            '--output',
            'json',
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload['project'] == 'editor_test'
    assert any(
        edit == ['R1', '10k'] or tuple(edit) == ('R1', '10k')
        for edit in payload['edits']
    )
    deltas = payload['deltas']
    assert len(deltas) == 1
    bw = deltas[0]
    assert bw['metric_field'] == 'bandwidth_hz'
    assert bw['delta_absolute'] is not None
    # Corner понизился ~10× → bandwidth ~ 16 Hz vs 159 Hz, дельта < 0.
    assert bw['delta_absolute'] < 0
    assert bw['after']['bandwidth_hz'] < bw['before']['bandwidth_hz']
