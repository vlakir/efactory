"""KicadCliErcRunner integration tests against real kicad-cli."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from adapters.outbound.erc_kicad_cli.runner import KicadCliErcRunner
from domain.erc import KiCadCliUnavailableError, SchematicParseError

_KICAD_CLI = shutil.which('kicad-cli')

needs_kicad_cli = pytest.mark.skipif(
    _KICAD_CLI is None, reason='kicad-cli not in PATH',
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_TEMPLATES = _REPO_ROOT / 'data' / 'templates'


def _stage_template(name: str, tmp_path: Path) -> Path:
    """
    Copy a baked template into a tmp dir so kicad-cli's `.kicad_prl` and
    other session-state writes don't pollute the source tree.
    """
    src_dir = _TEMPLATES / name
    dst_dir = tmp_path / name
    shutil.copytree(src_dir, dst_dir)
    return dst_dir / '{{PROJECT_NAME}}.kicad_sch'


@needs_kicad_cli
async def test_runner_returns_clean_report_on_se_amp(tmp_path: Path) -> None:
    """`se-amp` template ships ERC-clean (0 errors, ≤1 warning)."""
    sch = _stage_template('se-amp', tmp_path)
    runner = KicadCliErcRunner()
    report = await runner.run(sch, timeout_seconds=30.0)

    assert report.error_count == 0
    assert report.kicad_version.startswith('10.')


@needs_kicad_cli
async def test_runner_raises_on_missing_binary(tmp_path: Path) -> None:
    sch = _stage_template('se-amp', tmp_path)
    runner = KicadCliErcRunner(binary='kicad-cli-does-not-exist')
    with pytest.raises(KiCadCliUnavailableError):
        await runner.run(sch, timeout_seconds=10.0)


@needs_kicad_cli
async def test_runner_raises_schematic_parse_error_on_garbage(
    tmp_path: Path,
) -> None:
    bad = tmp_path / 'bad.kicad_sch'
    bad.write_text('not a real kicad schematic\n', encoding='utf-8')

    runner = KicadCliErcRunner()
    with pytest.raises(SchematicParseError):
        await runner.run(bad, timeout_seconds=30.0)
