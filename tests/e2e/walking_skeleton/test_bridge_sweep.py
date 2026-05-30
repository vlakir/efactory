"""E2E: bridge sweep + edit-model (T004b/T005 Phase 1)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from composition.main import build_cli_app

_KICAD_AVAILABLE = any(
    (Path.home() / 'kicad').glob('kicad*.AppImage'),
) or shutil.which('kicad-cli') is not None
_NGSPICE_AVAILABLE = shutil.which('ngspice') is not None

needs_kicad = pytest.mark.skipif(
    not _KICAD_AVAILABLE, reason='KiCad not installed',
)
needs_ngspice = pytest.mark.skipif(
    not _NGSPICE_AVAILABLE, reason='ngspice not installed',
)


def _setup_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    projects_root = tmp_path / 'projects'
    monkeypatch.setenv('EFACTORY_PROJECTS_ROOT', str(projects_root))
    monkeypatch.setenv(
        'EFACTORY_DATABASE_URL',
        f'sqlite+aiosqlite:///{tmp_path / "efactory.sqlite"}',
    )
    monkeypatch.setenv('EFACTORY_SESSION_ROOT', str(tmp_path / 'sessions'))
    return projects_root


def _seed_rc_project(
    rc_filter_schematic_path: Path,
    projects_root: Path,
    runner: CliRunner,
    project_name: str = 'sweep_test',
) -> Path:
    create_result = runner.invoke(
        build_cli_app(), ['project', 'create', '--name', project_name],
    )
    assert create_result.exit_code == 0, create_result.output
    project_path = projects_root / project_name
    schematic_dir = project_path / 'schematic'
    schematic_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(rc_filter_schematic_path, schematic_dir / 'rc_filter.kicad_sch')
    return project_path


@needs_kicad
@needs_ngspice
def test_bridge_sweep_two_param_combinations(
    rc_filter_schematic_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """bridge sweep --param R1=1k,10k --param C1=100n,1u → 4 combinations.

    T022 Phase C new format: aligned tabular output. Header = `R1 C1 <op
    nodes...>`, далее 4 строки с значениями. Заменяет старый
    `[R1=X C1=Y] op_voltages` (A2).
    """
    projects_root = _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()
    _seed_rc_project(rc_filter_schematic_path, projects_root, runner)

    result = runner.invoke(
        build_cli_app(),
        [
            'bridge', 'sweep',
            'sweep_test',
            '--schematic', 'schematic/rc_filter.kicad_sch',
            '--param', 'R1=1k,10k',
            '--param', 'C1=1u,10u',
        ],
    )

    assert result.exit_code == 0, result.output
    assert 'Sweep complete: 4 combinations' in result.output
    # Tabular header содержит параметры sweep'а первой колонкой.
    lines = result.output.splitlines()
    header_idx = next(
        (i for i, ln in enumerate(lines) if ln.startswith('R1')),
        None,
    )
    assert header_idx is not None, (
        f'No header line starting with R1 found:\n{result.output}'
    )
    header = lines[header_idx]
    assert 'R1' in header
    assert 'C1' in header
    # ≥4 строк после header'а с данными (один на combination).
    data_lines = [
        ln for ln in lines[header_idx + 1 :]
        if ln.strip() and not ln.startswith('Sweep')
    ]
    assert len(data_lines) >= 4, (
        f'Expected ≥4 data rows after header, got {len(data_lines)}:\n'
        f'{result.output}'
    )
    # Каждая ожидаемая combination присутствует в одной из data row'ов
    # (parameter values как column entries, не bracket-prefix).
    for r1 in ('1k', '10k'):
        for c1 in ('1u', '10u'):
            matching = [
                ln for ln in data_lines
                if r1 in ln.split() and c1 in ln.split()
            ]
            assert matching, (
                f'Combination R1={r1} C1={c1} not in any data row:\n'
                f'{chr(10).join(data_lines)}'
            )


@needs_kicad
def test_bridge_sweep_invalid_param_format_exits_2(
    rc_filter_schematic_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    projects_root = _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()
    _seed_rc_project(rc_filter_schematic_path, projects_root, runner)

    result = runner.invoke(
        build_cli_app(),
        [
            'bridge', 'sweep',
            'sweep_test',
            '--schematic', 'schematic/rc_filter.kicad_sch',
            '--param', 'no_equals',
        ],
    )
    assert result.exit_code == 2
    assert 'REF=v1' in result.output


@needs_kicad
def test_bridge_edit_atomic_rollback_on_failure(
    rc_filter_schematic_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T004b P1: multi-edit с failure посередине → весь batch откатывается."""
    projects_root = _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()
    _seed_rc_project(rc_filter_schematic_path, projects_root, runner)
    target = projects_root / 'sweep_test' / 'schematic' / 'rc_filter.kicad_sch'

    pre_text = target.read_text(encoding='utf-8')

    # R1 success, R999 missing → весь batch откатывается
    result = runner.invoke(
        build_cli_app(),
        [
            'bridge', 'edit',
            'sweep_test',
            '--schematic', 'schematic/rc_filter.kicad_sch',
            '--set', 'R1=42k',          # valid
            '--set', 'R999=100',        # missing → fail
        ],
    )
    assert result.exit_code == 1
    assert 'Rollback' in result.output

    # Файл должен совпадать с pre_text — R1 НЕ изменён, потому что rollback
    post_text = target.read_text(encoding='utf-8')
    assert post_text == pre_text


# ────────── T022 Phase C: новые CLI флаги ──────────


import json


@needs_kicad
@needs_ngspice
def test_bridge_sweep_output_csv_to_file_writes_csv(
    rc_filter_schematic_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--output csv --output-file` → файл создан, 1-line stdout summary."""
    projects_root = _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()
    _seed_rc_project(rc_filter_schematic_path, projects_root, runner)

    csv_file = tmp_path / 'sweep.csv'
    result = runner.invoke(
        build_cli_app(),
        [
            'bridge', 'sweep', 'sweep_test',
            '--schematic', 'schematic/rc_filter.kicad_sch',
            '--param', 'R1=1k,10k',
            '--output', 'csv',
            '--output-file', str(csv_file),
        ],
    )

    assert result.exit_code == 0, result.output
    # 1-line summary в stdout (Q-F → b).
    assert 'rows →' in result.output
    assert csv_file.exists()
    csv_content = csv_file.read_text()
    # CSV header содержит R1 + хотя бы один op-сигнал.
    header = csv_content.strip().splitlines()[0]
    assert 'R1' in header
    # 2 data rows + header = 3 lines.
    assert len(csv_content.strip().splitlines()) == 3


@needs_kicad
@needs_ngspice
def test_bridge_sweep_output_json_returns_parseable_json(
    rc_filter_schematic_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--output json` → stdout содержит valid JSON list."""
    projects_root = _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()
    _seed_rc_project(rc_filter_schematic_path, projects_root, runner)

    result = runner.invoke(
        build_cli_app(),
        [
            'bridge', 'sweep', 'sweep_test',
            '--schematic', 'schematic/rc_filter.kicad_sch',
            '--param', 'R1=1k,10k',
            '--output', 'json',
        ],
    )

    assert result.exit_code == 0, result.output
    # JSON начинается после 'Sweep complete: N combinations.' header строки.
    json_start = result.output.index('[')
    parsed = json.loads(result.output[json_start:])
    assert isinstance(parsed, list)
    assert len(parsed) == 2
    r1_values = {row['R1'] for row in parsed}
    assert r1_values == {'1k', '10k'}


@needs_kicad
def test_bridge_sweep_n_over_hard_cap_exits_2(
    rc_filter_schematic_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """N=121 > default cap 100 без --max-combinations → exit 2."""
    projects_root = _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()
    _seed_rc_project(rc_filter_schematic_path, projects_root, runner)

    # 11 × 11 = 121 > 100
    values_str = ','.join(f'{i}k' for i in range(1, 12))
    result = runner.invoke(
        build_cli_app(),
        [
            'bridge', 'sweep', 'sweep_test',
            '--schematic', 'schematic/rc_filter.kicad_sch',
            '--param', f'R1={values_str}',
            '--param', f'C1={values_str}',
        ],
    )

    assert result.exit_code == 2
    assert 'combinations' in result.output.lower()


@needs_kicad
def test_bridge_sweep_incompatible_metric_analysis_exits_2(
    rc_filter_schematic_path: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--metric op --analysis ac` → exit 2 (Analyze A1)."""
    projects_root = _setup_env(tmp_path, monkeypatch)
    runner = CliRunner()
    _seed_rc_project(rc_filter_schematic_path, projects_root, runner)

    result = runner.invoke(
        build_cli_app(),
        [
            'bridge', 'sweep', 'sweep_test',
            '--schematic', 'schematic/rc_filter.kicad_sch',
            '--param', 'R1=1k',
            '--metric', 'op',
            '--analysis', 'ac',
        ],
    )

    assert result.exit_code == 2
    assert 'incompatible' in result.output.lower()
