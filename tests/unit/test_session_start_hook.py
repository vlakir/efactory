"""Unit tests для SessionStart hook (T016 Phase A).

Hook живёт в `scripts/session_start_hook.py` (standalone stdlib-only
скрипт, запускается Claude Code из settings.json). Логика — чистые
функции, тестируем напрямую через sys.path-инъекцию scripts/ в импорт.
"""

from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS_DIR = REPO_ROOT / 'scripts'
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import session_start_hook as hook  # type: ignore[import-not-found]

if TYPE_CHECKING:
    pass


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Эмулирует контейнерный `/workspace/`."""
    ws = tmp_path / 'workspace'
    ws.mkdir()
    return ws


class TestResolveProjectRoot:
    def test_cwd_is_workspace_root_returns_none(self, workspace: Path) -> None:
        assert hook.resolve_project_root(workspace, workspace_root=workspace) is None

    def test_cwd_is_project_root(self, workspace: Path) -> None:
        project = workspace / 'foo'
        project.mkdir()
        assert hook.resolve_project_root(project, workspace_root=workspace) == project

    def test_cwd_is_nested_in_project(self, workspace: Path) -> None:
        project = workspace / 'foo'
        (project / 'sub' / 'deep').mkdir(parents=True)
        cwd = project / 'sub' / 'deep'
        assert hook.resolve_project_root(cwd, workspace_root=workspace) == project

    def test_cwd_outside_workspace_returns_none(
        self, tmp_path: Path, workspace: Path
    ) -> None:
        outside = tmp_path / 'elsewhere'
        outside.mkdir()
        assert hook.resolve_project_root(outside, workspace_root=workspace) is None

    def test_cwd_is_hidden_project_returns_none(self, workspace: Path) -> None:
        hidden = workspace / '.hidden'
        hidden.mkdir()
        assert hook.resolve_project_root(hidden, workspace_root=workspace) is None


class TestScanProjectFiles:
    def test_empty_project(self, workspace: Path) -> None:
        project = workspace / 'foo'
        project.mkdir()
        result = hook.scan_project_files(project)
        assert all(v == [] for v in result.values())

    def test_groups_files_by_category(self, workspace: Path) -> None:
        project = workspace / 'foo'
        project.mkdir()
        (project / 'amp.kicad_pro').touch()
        (project / 'amp.kicad_sch').touch()
        (project / 'tubes.cir').touch()
        (project / 'core.FCStd').touch()
        (project / 'mesh.geo').touch()
        result = hook.scan_project_files(project)
        kicad_names = {p.name for p in result['KiCad']}
        assert kicad_names == {'amp.kicad_pro', 'amp.kicad_sch'}
        assert [p.name for p in result['SPICE']] == ['tubes.cir']
        assert [p.name for p in result['FreeCAD']] == ['core.FCStd']
        assert [p.name for p in result['FEM']] == ['mesh.geo']

    def test_includes_one_subdir_level(self, workspace: Path) -> None:
        project = workspace / 'foo'
        sub = project / 'models'
        sub.mkdir(parents=True)
        (sub / 'tube.subckt').touch()
        result = hook.scan_project_files(project)
        spice_rels = [p.relative_to(project) for p in result['SPICE']]
        assert Path('models/tube.subckt') in spice_rels

    def test_ignores_hidden_files_and_dirs(self, workspace: Path) -> None:
        project = workspace / 'foo'
        project.mkdir()
        (project / '.efactory').mkdir()
        (project / '.efactory' / 'cache.cir').touch()
        (project / '.hidden.kicad_sch').touch()
        result = hook.scan_project_files(project)
        assert result['KiCad'] == []
        assert result['SPICE'] == []

    def test_soft_cap_applies(self, workspace: Path) -> None:
        project = workspace / 'foo'
        project.mkdir()
        for i in range(25):
            (project / f'sheet_{i:02d}.kicad_sch').touch()
        result = hook.scan_project_files(project, max_per_category=20)
        assert len(result['KiCad']) == 20

    def test_non_existent_root_safe(self, workspace: Path) -> None:
        result = hook.scan_project_files(workspace / 'ghost')
        assert all(v == [] for v in result.values())


class TestScanSimResults:
    def test_no_sim_results_dir(self, workspace: Path) -> None:
        project = workspace / 'foo'
        project.mkdir()
        assert hook.scan_sim_results(project) == []

    def test_returns_latest_by_filename_desc(self, workspace: Path) -> None:
        project = workspace / 'foo'
        sim_dir = project / '.efactory' / 'sim-results'
        sim_dir.mkdir(parents=True)
        for ts in ['2026-05-20T10-00-00Z', '2026-05-21T11-00-00Z', '2026-05-22T12-00-00Z']:
            (sim_dir / f'{ts}-tran.json').write_text(
                json.dumps(
                    {
                        'schema_version': 1,
                        'timestamp': ts.replace('-', ':', 2).replace('T', 'T'),
                        'analysis_type': 'tran',
                        'tool': 'ngspice',
                        'source_file': 'amp.cir',
                        'summary': f'sim at {ts}',
                    }
                )
            )
        result = hook.scan_sim_results(project, max_results=2)
        assert len(result) == 2
        assert result[0]['filename'].startswith('2026-05-22')
        assert result[1]['filename'].startswith('2026-05-21')

    def test_broken_json_skipped(self, workspace: Path) -> None:
        project = workspace / 'foo'
        sim_dir = project / '.efactory' / 'sim-results'
        sim_dir.mkdir(parents=True)
        (sim_dir / '2026-05-22T12-00-00Z-bad.json').write_text('{not json')
        (sim_dir / '2026-05-22T13-00-00Z-good.json').write_text(
            json.dumps(
                {
                    'schema_version': 1,
                    'timestamp': '2026-05-22T13:00:00Z',
                    'analysis_type': 'op',
                    'tool': 'ngspice',
                    'source_file': 'amp.cir',
                    'summary': 'op point',
                }
            )
        )
        result = hook.scan_sim_results(project)
        assert len(result) == 1
        assert result[0]['analysis_type'] == 'op'

    def test_non_dict_json_skipped(self, workspace: Path) -> None:
        project = workspace / 'foo'
        sim_dir = project / '.efactory' / 'sim-results'
        sim_dir.mkdir(parents=True)
        (sim_dir / '2026-05-22T12-00-00Z-list.json').write_text('[1, 2, 3]')
        result = hook.scan_sim_results(project)
        assert result == []


class TestListWorkspaceProjects:
    def test_lists_subdirs_sorted(self, workspace: Path) -> None:
        for name in ['zebra', 'alpha', 'middle']:
            (workspace / name).mkdir()
        assert hook.list_workspace_projects(workspace) == ['alpha', 'middle', 'zebra']

    def test_ignores_files_and_hidden(self, workspace: Path) -> None:
        (workspace / 'foo').mkdir()
        (workspace / '.hidden').mkdir()
        (workspace / 'README.md').touch()
        assert hook.list_workspace_projects(workspace) == ['foo']

    def test_missing_workspace_safe(self, tmp_path: Path) -> None:
        assert hook.list_workspace_projects(tmp_path / 'ghost') == []


class TestRenderContext:
    def test_no_project_lists_available(self, workspace: Path) -> None:
        (workspace / 'foo').mkdir()
        (workspace / 'bar').mkdir()
        text = hook.render_context(
            project_root=None, cwd=workspace, workspace_root=workspace
        )
        assert 'No active project' in text
        assert 'bar' in text and 'foo' in text
        assert 'efactory-up --agent' in text

    def test_no_project_empty_workspace(self, workspace: Path) -> None:
        text = hook.render_context(
            project_root=None, cwd=workspace, workspace_root=workspace
        )
        assert 'No active project' in text
        assert 'Workspace empty' in text or 'empty' in text.lower()

    def test_with_project_renders_name_and_files(self, workspace: Path) -> None:
        project = workspace / 'se-amp'
        project.mkdir()
        (project / 'se_amp.kicad_pro').touch()
        (project / 'se_amp.kicad_sch').touch()
        text = hook.render_context(
            project_root=project, cwd=project, workspace_root=workspace
        )
        assert '**se-amp**' in text
        assert 'se_amp.kicad_sch' in text
        assert 'KiCad' in text

    def test_with_project_no_files_message(self, workspace: Path) -> None:
        project = workspace / 'empty-proj'
        project.mkdir()
        text = hook.render_context(
            project_root=project, cwd=project, workspace_root=workspace
        )
        assert 'empty-proj' in text
        assert 'empty project' in text.lower() or 'no kicad' in text.lower()

    def test_with_sim_results_section(self, workspace: Path) -> None:
        project = workspace / 'foo'
        sim_dir = project / '.efactory' / 'sim-results'
        sim_dir.mkdir(parents=True)
        (sim_dir / '2026-05-22T13-00-00Z-thd.json').write_text(
            json.dumps(
                {
                    'schema_version': 1,
                    'timestamp': '2026-05-22T13:00:00Z',
                    'analysis_type': 'thd',
                    'tool': 'ngspice',
                    'source_file': 'amp.kicad_sch',
                    'summary': 'THD=9.6% @ 1 kHz / 1 W',
                }
            )
        )
        text = hook.render_context(
            project_root=project, cwd=project, workspace_root=workspace
        )
        assert 'thd' in text.lower()
        assert 'THD=9.6%' in text

    def test_with_project_no_sim_results_message(self, workspace: Path) -> None:
        project = workspace / 'foo'
        project.mkdir()
        text = hook.render_context(
            project_root=project, cwd=project, workspace_root=workspace
        )
        assert 'no sim results' in text.lower() or 'sim-results' in text.lower()

    def test_pending_staged_warning_when_present(self, workspace: Path) -> None:
        """T026: SessionStart hook отмечает pending .kicad_sch.staged."""
        project = workspace / 'pending-proj'
        project.mkdir()
        (project / 'se_amp.kicad_sch').touch()
        (project / 'se_amp.kicad_sch.staged').write_text('x', encoding='utf-8')
        text = hook.render_context(
            project_root=project, cwd=project, workspace_root=workspace
        )
        assert 'Pending staged' in text or 'pending staged' in text.lower()
        assert 'se_amp.kicad_sch.staged' in text
        assert '/schematic-apply' in text

    def test_pending_staged_absent_when_clean(self, workspace: Path) -> None:
        project = workspace / 'clean-proj'
        project.mkdir()
        (project / 'se_amp.kicad_sch').touch()
        text = hook.render_context(
            project_root=project, cwd=project, workspace_root=workspace
        )
        assert 'pending staged' not in text.lower()

    def test_pending_staged_multi_sheet(self, workspace: Path) -> None:
        project = workspace / 'multi-proj'
        sub = project / 'subsheets'
        sub.mkdir(parents=True)
        (project / 'root.kicad_sch.staged').write_text('x', encoding='utf-8')
        (sub / 'amp.kicad_sch.staged').write_text('x', encoding='utf-8')
        text = hook.render_context(
            project_root=project, cwd=project, workspace_root=workspace
        )
        assert '**2**' in text  # count
        assert 'root.kicad_sch.staged' in text
        assert 'subsheets/amp.kicad_sch.staged' in text


class TestMain:
    def test_emits_valid_session_start_json(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = workspace / 'demo'
        project.mkdir()
        (project / 'demo.kicad_sch').touch()
        monkeypatch.setenv('CLAUDE_PROJECT_DIR', str(project))
        monkeypatch.setattr(hook, 'WORKSPACE_ROOT', workspace)
        monkeypatch.setattr(sys, 'stdin', io.StringIO(''))
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = hook.main()
        assert rc == 0
        payload = json.loads(buf.getvalue())
        assert payload['hookSpecificOutput']['hookEventName'] == 'SessionStart'
        assert 'demo' in payload['hookSpecificOutput']['additionalContext']

    def test_falls_back_to_getcwd_when_env_missing(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        project = workspace / 'fallback-demo'
        project.mkdir()
        monkeypatch.delenv('CLAUDE_PROJECT_DIR', raising=False)
        monkeypatch.setattr(hook, 'WORKSPACE_ROOT', workspace)
        monkeypatch.chdir(project)
        monkeypatch.setattr(sys, 'stdin', io.StringIO(''))
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = hook.main()
        assert rc == 0
        payload = json.loads(buf.getvalue())
        assert 'fallback-demo' in payload['hookSpecificOutput']['additionalContext']

    def test_no_project_safe(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv('CLAUDE_PROJECT_DIR', str(workspace))
        monkeypatch.setattr(hook, 'WORKSPACE_ROOT', workspace)
        monkeypatch.setattr(sys, 'stdin', io.StringIO(''))
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = hook.main()
        assert rc == 0
        payload = json.loads(buf.getvalue())
        assert payload['hookSpecificOutput']['hookEventName'] == 'SessionStart'
        assert 'No active project' in payload['hookSpecificOutput']['additionalContext']


# ---------------------------- T134 Knowledge Base section ----------------


def _write_kb_md(directory: Path, slug: str, *, description: str, body: str = 'Body.') -> None:
    directory.mkdir(parents=True, exist_ok=True)
    content = (
        '---\n'
        f'topic: {slug}\n'
        f'description: {description}\n'
        '---\n'
        f'{body}\n'
    )
    (directory / f'{slug}.md').write_text(content, encoding='utf-8')


def test_render_kb_section_empty_returns_empty_string(tmp_path: Path) -> None:
    """Empty KB → секция skip (Analyze A4)."""
    result = hook.render_kb_section(
        built_in_dir=tmp_path / 'built-in',
        host_mutated_dir=tmp_path / 'host-mutated',
    )
    assert result == ''


def test_render_kb_section_groups_by_namespace(tmp_path: Path) -> None:
    _write_kb_md(tmp_path / 'built-in', 'spice.saturable', description='XSPICE gyrator-cap')
    _write_kb_md(tmp_path / 'built-in', 'magnetics.leakage', description='Erickson sandwich')
    _write_kb_md(tmp_path / 'built-in', 'agent.command-routing', description='Map request to command')

    result = hook.render_kb_section(
        built_in_dir=tmp_path / 'built-in',
        host_mutated_dir=tmp_path / 'host-mutated',
    )

    assert '## Agent Knowledge Base' in result
    assert '### agent' in result
    assert '### magnetics' in result
    assert '### spice' in result
    assert 'spice.saturable' in result
    assert 'XSPICE gyrator-cap' in result
    # Namespaces sorted alphabetically: agent < magnetics < spice.
    assert result.index('### agent') < result.index('### magnetics') < result.index('### spice')


def test_render_kb_section_host_wins(tmp_path: Path) -> None:
    _write_kb_md(tmp_path / 'built-in', 'spice.saturable', description='Built-in desc')
    _write_kb_md(tmp_path / 'host-mutated', 'spice.saturable', description='Host desc')

    result = hook.render_kb_section(
        built_in_dir=tmp_path / 'built-in',
        host_mutated_dir=tmp_path / 'host-mutated',
    )

    assert 'Host desc' in result
    assert 'Built-in desc' not in result


def test_render_kb_section_count_in_intro(tmp_path: Path) -> None:
    _write_kb_md(tmp_path / 'built-in', 'spice.saturable', description='x')
    _write_kb_md(tmp_path / 'built-in', 'magnetics.leakage', description='y')

    result = hook.render_kb_section(
        built_in_dir=tmp_path / 'built-in',
        host_mutated_dir=tmp_path / 'host-mutated',
    )

    assert '2 topic(s) available' in result


def test_render_kb_section_missing_dirs_safe(tmp_path: Path) -> None:
    """Несуществующие директории → пустая KB, не error."""
    result = hook.render_kb_section(
        built_in_dir=tmp_path / 'nonexistent-built-in',
        host_mutated_dir=tmp_path / 'nonexistent-host',
    )
    assert result == ''


def test_parse_kb_frontmatter_minimal_extracts_topic_and_description() -> None:
    content = (
        '---\n'
        'topic: foo.bar\n'
        'description: My description\n'
        'tags:\n'
        '  - one\n'
        '  - two\n'
        '---\n'
        'body\n'
    )
    fields = hook._parse_kb_frontmatter_minimal(content)
    assert fields == {'topic': 'foo.bar', 'description': 'My description'}


def test_parse_kb_frontmatter_minimal_no_frontmatter() -> None:
    assert hook._parse_kb_frontmatter_minimal('body only\n') == {}


def test_parse_kb_frontmatter_minimal_unclosed() -> None:
    assert hook._parse_kb_frontmatter_minimal('---\ntopic: x\n# no close\n') == {}


def test_parse_kb_frontmatter_minimal_quoted_values_unwrapped() -> None:
    content = '---\ntopic: "spice.saturable"\ndescription: \'XSPICE\'\n---\nbody\n'
    fields = hook._parse_kb_frontmatter_minimal(content)
    assert fields['topic'] == 'spice.saturable'
    assert fields['description'] == 'XSPICE'
