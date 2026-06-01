"""E2E: `efactory project list-templates` (T027 Phase E)."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from composition.main import build_cli_app


def test_list_templates_human_readable_lists_all_shipping_templates() -> None:
    """Human-readable table mode: список всех baked templates с summary."""
    runner = CliRunner()
    app = build_cli_app()

    result = runner.invoke(app, ['project', 'list-templates'])

    assert result.exit_code == 0, result.output
    output = result.output
    # T027 baked templates — all 8 должны присутствовать.
    expected_names = {
        'se-amp',
        'nfb-se-amp',
        'op-amp-inverting',
        'bjt-ce-nfb',
        'tube-pp-amp',
        'tube-line-preamp',
        'tube-phono-riaa',
        'active-lpf-sallen-key',
    }
    for name in expected_names:
        assert name in output, f'template {name!r} missing in output: {output}'


def test_list_templates_json_mode_returns_array_of_objects() -> None:
    """--json flag: machine-readable JSON array."""
    runner = CliRunner()
    app = build_cli_app()

    result = runner.invoke(app, ['project', 'list-templates', '--json'])

    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert isinstance(parsed, list)
    # Each entry — dict с name + summary.
    assert all('name' in entry and 'summary' in entry for entry in parsed)
    names = {entry['name'] for entry in parsed}
    # Same 8 expected templates.
    assert 'se-amp' in names
    assert 'tube-pp-amp' in names
    assert 'active-lpf-sallen-key' in names
    # Summary should be non-empty for shipping templates.
    se_amp_summary = next(e['summary'] for e in parsed if e['name'] == 'se-amp')
    assert se_amp_summary, 'se-amp summary should be non-empty'
