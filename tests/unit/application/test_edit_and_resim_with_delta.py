"""edit_and_resim_with_delta — use case-агрегатор (T021 Phase A.3)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from application.edit_and_resim_with_delta import (
    BaselineFailedError,
    EditAndResimConfig,
    EditAndResimReport,
    edit_and_resim_with_delta,
)
from application.edit_component_value import (
    ComponentNotFoundError,
    MultipleMatchesError,
)
from domain.measurement import (
    BandwidthMeasurement,
    GainMeasurement,
    ThdMeasurement,
)
from domain.measurement_delta import (
    BandwidthDelta,
    GainDelta,
    ThdDelta,
)
from ports.outbound.schematic_exporter import SchematicExportError
from ports.outbound.simulator import SimulationFailedError

if TYPE_CHECKING:
    from domain.simulation import AnalysisSpec, SimulationResult


# --------------------------------------------------------------- Fakes / fixtures ----


class FakeExporter:
    def __init__(self, fail: bool = False) -> None:
        self.calls: list[tuple[Path, Path]] = []
        self._fail = fail

    async def export_spice_netlist(
        self,
        schematic: Path,
        output: Path,
    ) -> Path:
        self.calls.append((schematic, output))
        if self._fail:
            msg = 'simulated export failure'
            raise SchematicExportError(msg)
        output.write_text('* fake netlist\n.end\n')
        return output


class FailingAfterExporter:
    """Первый вызов успешен (baseline), второй — fail (after-edit)."""

    def __init__(self) -> None:
        self.calls: list[tuple[Path, Path]] = []

    async def export_spice_netlist(
        self,
        schematic: Path,
        output: Path,
    ) -> Path:
        self.calls.append((schematic, output))
        if len(self.calls) >= 2:
            msg = 'after-export failed'
            raise SchematicExportError(msg)
        output.write_text('* baseline netlist\n.end\n')
        return output


class _DummySimulator:
    """Use case никогда не вызывает simulator напрямую (через measure_*),
    но DI требует, чтобы port был передан."""

    async def run(
        self,
        netlist: Path,
        analysis: AnalysisSpec,
        *,
        timeout_seconds: float = 60.0,
    ) -> SimulationResult:
        msg = "should not be called — measure_* mock'ed"
        raise AssertionError(msg)


class _DummyNetlistEditor:
    """То же — use case не использует напрямую."""

    def find_top_level_v_sources(self, netlist_text: str) -> tuple[str, ...]:
        return ('V1',)

    def ensure_ac_modifier(
        self,
        netlist_text: str,
        *,
        source_ref: str,
        ac_magnitude: float = 1.0,
    ) -> str:
        return netlist_text

    def set_sin_source_amplitude(
        self,
        netlist_text: str,
        *,
        source_ref: str,
        amplitude_peak: float,
        frequency_hz: float,
        offset: float = 0.0,
    ) -> str:
        return netlist_text

    def substitute_subckt_library(
        self,
        netlist_text: str,
        target_subckt_name: str,
        new_subckt_text: str,
    ) -> str:
        return netlist_text


@pytest.fixture
def schematic_path(tmp_path: Path) -> Path:
    path = tmp_path / 'demo.kicad_sch'
    path.write_text('(kicad_sch (version 20231120) ; baseline)\n')
    return path


def _gain(**overrides: object) -> GainMeasurement:
    defaults: dict[str, object] = {
        'value_db': 20.0,
        'value_linear': 10.0,
        'frequency_hz': 1000.0,
        'mode': 'small',
        'input_signal': 'v(in)',
        'output_signal': 'v(load)',
    }
    defaults.update(overrides)
    return GainMeasurement(**defaults)  # type: ignore[arg-type]


def _bandwidth(**overrides: object) -> BandwidthMeasurement:
    defaults: dict[str, object] = {
        'f_low_hz': 20.0,
        'f_high_hz': 20000.0,
        'bandwidth_hz': 19980.0,
        'ref_db': -3.0,
        'midpoint_db': 20.0,
        'midpoint_source': 'auto',
        'passband_signal': 'v(load)',
        'input_signal': 'v(in)',
    }
    defaults.update(overrides)
    return BandwidthMeasurement(**defaults)  # type: ignore[arg-type]


def _thd(**overrides: object) -> ThdMeasurement:
    defaults: dict[str, object] = {
        'thd_percent': 2.5,
        'fundamental_hz': 1000.0,
        'v_in_peak': 0.1,
        'measured_power_w': 0.8,
        'dominant_harmonic_n': 2,
        'dominant_harmonic_percent': 2.0,
        'signal': 'v(load)',
        'n_harmonics': 10,
    }
    defaults.update(overrides)
    return ThdMeasurement(**defaults)  # type: ignore[arg-type]


def _seq_measure(results: list[object]) -> Callable[..., object]:
    """Возвращает async-callable, отдающий из `results` по очереди."""

    calls = {'n': 0}

    async def _runner(**_kwargs: object) -> object:
        idx = calls['n']
        calls['n'] += 1
        if idx >= len(results):
            msg = f'_seq_measure exhausted at call #{idx + 1}'
            raise RuntimeError(msg)
        value = results[idx]
        if isinstance(value, Exception):
            raise value
        return value

    return _runner


def _seq_edit(fail_at: int | None = None) -> Callable[[Path, str, str], str]:
    """Sync mock для edit_component_value: возвращает old value, или raise."""

    counter = {'n': 0}

    def _editor(path: Path, ref: str, value: str) -> str:
        idx = counter['n']
        counter['n'] += 1
        if fail_at is not None and idx == fail_at:
            msg = f'simulated edit failure at index {idx} for ref={ref}'
            raise ComponentNotFoundError(msg)
        text = path.read_text() + f'\n; edit {ref}={value}\n'
        path.write_text(text)
        return f'old-{ref}'

    return _editor


def _patch_measures(
    monkeypatch: pytest.MonkeyPatch,
    *,
    gain: Callable[..., object] | None = None,
    bandwidth: Callable[..., object] | None = None,
    thd: Callable[..., object] | None = None,
) -> None:
    if gain is not None:
        monkeypatch.setattr(
            'application.edit_and_resim_with_delta.measure_gain',
            gain,
        )
    if bandwidth is not None:
        monkeypatch.setattr(
            'application.edit_and_resim_with_delta.measure_bandwidth',
            bandwidth,
        )
    if thd is not None:
        monkeypatch.setattr(
            'application.edit_and_resim_with_delta.measure_thd',
            thd,
        )


def _patch_edit(
    monkeypatch: pytest.MonkeyPatch,
    editor: Callable[[Path, str, str], str],
) -> None:
    monkeypatch.setattr(
        'application.edit_and_resim_with_delta.edit_component_value',
        editor,
    )


def _run(coro: object) -> object:
    return asyncio.run(coro)  # type: ignore[arg-type]


# --------------------------------------------------------------- EditAndResimConfig ----


def test_config_requires_non_empty_metrics() -> None:
    with pytest.raises(ValueError, match='metrics'):
        EditAndResimConfig(metrics=[])


def test_config_gain_requires_frequency() -> None:
    with pytest.raises(ValueError, match='frequency_hz'):
        EditAndResimConfig(metrics=['gain'])


def test_config_thd_requires_frequency_and_v_in_peak() -> None:
    with pytest.raises(ValueError, match='v_in_peak'):
        EditAndResimConfig(metrics=['thd'], frequency_hz=1000.0)


def test_config_gain_large_mode_requires_v_in_peak() -> None:
    with pytest.raises(ValueError, match='v_in_peak'):
        EditAndResimConfig(metrics=['gain'], frequency_hz=1000.0, mode='large')


def test_config_bandwidth_has_default_f_band() -> None:
    cfg = EditAndResimConfig(metrics=['bandwidth'])
    assert cfg.f_low_hz > 0
    assert cfg.f_high_hz > cfg.f_low_hz


def test_config_silently_dedupes_metrics() -> None:
    cfg = EditAndResimConfig(metrics=['gain', 'gain', 'bandwidth'], frequency_hz=1000.0)
    assert cfg.metrics == ['gain', 'bandwidth']


# ----------------------------------------------------------------------- Use case ----


def test_happy_path_single_metric_gain_small(
    monkeypatch: pytest.MonkeyPatch,
    schematic_path: Path,
) -> None:
    _patch_measures(
        monkeypatch,
        gain=_seq_measure([_gain(value_db=20.0), _gain(value_db=23.0)]),
    )
    _patch_edit(monkeypatch, _seq_edit())

    cfg = EditAndResimConfig(metrics=['gain'], frequency_hz=1000.0)
    report = _run(
        edit_and_resim_with_delta(
            schematic=schematic_path,
            edits=[('R1', '10k')],
            config=cfg,
            exporter=FakeExporter(),
            simulator=_DummySimulator(),
            netlist_editor=_DummyNetlistEditor(),
        )
    )
    assert isinstance(report, EditAndResimReport)
    assert len(report.deltas) == 1
    delta = report.deltas[0]
    assert isinstance(delta, GainDelta)
    assert delta.delta_absolute == pytest.approx(3.0)
    assert delta.delta_relative_percent == pytest.approx(15.0)


def test_happy_path_all_three_metrics(
    monkeypatch: pytest.MonkeyPatch,
    schematic_path: Path,
) -> None:
    _patch_measures(
        monkeypatch,
        gain=_seq_measure([_gain(value_db=20.0), _gain(value_db=18.0)]),
        bandwidth=_seq_measure(
            [
                _bandwidth(f_high_hz=20000.0, bandwidth_hz=19980.0),
                _bandwidth(f_high_hz=40000.0, bandwidth_hz=39980.0),
            ]
        ),
        thd=_seq_measure([_thd(thd_percent=2.5), _thd(thd_percent=1.0)]),
    )
    _patch_edit(monkeypatch, _seq_edit())

    cfg = EditAndResimConfig(
        metrics=['gain', 'bandwidth', 'thd'],
        frequency_hz=1000.0,
        v_in_peak=0.1,
    )
    report = _run(
        edit_and_resim_with_delta(
            schematic=schematic_path,
            edits=[('R5', '2k')],
            config=cfg,
            exporter=FakeExporter(),
            simulator=_DummySimulator(),
            netlist_editor=_DummyNetlistEditor(),
        )
    )
    kinds = {type(d) for d in report.deltas}
    assert kinds == {GainDelta, BandwidthDelta, ThdDelta}


def test_multiple_edits_applied_in_order(
    monkeypatch: pytest.MonkeyPatch,
    schematic_path: Path,
) -> None:
    seen: list[tuple[str, str]] = []

    def recording_editor(path: Path, ref: str, value: str) -> str:
        seen.append((ref, value))
        return 'old'

    _patch_measures(
        monkeypatch,
        gain=_seq_measure([_gain(), _gain(value_db=22.0)]),
    )
    _patch_edit(monkeypatch, recording_editor)

    cfg = EditAndResimConfig(metrics=['gain'], frequency_hz=1000.0)
    _run(
        edit_and_resim_with_delta(
            schematic=schematic_path,
            edits=[('R1', '10k'), ('R2', '20k'), ('C3', '470n')],
            config=cfg,
            exporter=FakeExporter(),
            simulator=_DummySimulator(),
            netlist_editor=_DummyNetlistEditor(),
        )
    )
    assert seen == [('R1', '10k'), ('R2', '20k'), ('C3', '470n')]


def test_baseline_failure_raises_before_edits_applied(
    monkeypatch: pytest.MonkeyPatch,
    schematic_path: Path,
) -> None:
    original_text = schematic_path.read_text()
    edits_called: list[tuple[str, str]] = []

    def recording_editor(path: Path, ref: str, value: str) -> str:
        edits_called.append((ref, value))
        return 'old'

    _patch_measures(
        monkeypatch,
        gain=_seq_measure([SimulationFailedError('baseline gain diverged')]),
    )
    _patch_edit(monkeypatch, recording_editor)

    cfg = EditAndResimConfig(metrics=['gain'], frequency_hz=1000.0)
    with pytest.raises(BaselineFailedError, match='baseline gain'):
        _run(
            edit_and_resim_with_delta(
                schematic=schematic_path,
                edits=[('R1', '10k')],
                config=cfg,
                exporter=FakeExporter(),
                simulator=_DummySimulator(),
                netlist_editor=_DummyNetlistEditor(),
            )
        )
    assert edits_called == []
    assert schematic_path.read_text() == original_text


def test_edit_failure_rolls_back_schematic(
    monkeypatch: pytest.MonkeyPatch,
    schematic_path: Path,
) -> None:
    original_text = schematic_path.read_text()

    _patch_measures(
        monkeypatch,
        gain=_seq_measure([_gain()]),  # baseline OK, after не должен случиться
    )
    _patch_edit(monkeypatch, _seq_edit(fail_at=1))  # 1-й edit OK, 2-й fail

    cfg = EditAndResimConfig(metrics=['gain'], frequency_hz=1000.0)
    with pytest.raises(ComponentNotFoundError):
        _run(
            edit_and_resim_with_delta(
                schematic=schematic_path,
                edits=[('R1', '10k'), ('R2', '20k')],
                config=cfg,
                exporter=FakeExporter(),
                simulator=_DummySimulator(),
                netlist_editor=_DummyNetlistEditor(),
            )
        )
    # SchematicSnapshot должен был откатить.
    assert schematic_path.read_text() == original_text


def test_after_measure_failure_records_failed_reason(
    monkeypatch: pytest.MonkeyPatch,
    schematic_path: Path,
) -> None:
    _patch_measures(
        monkeypatch,
        gain=_seq_measure(
            [
                _gain(value_db=20.0),
                SimulationFailedError('after gain diverged'),
            ]
        ),
    )
    _patch_edit(monkeypatch, _seq_edit())

    cfg = EditAndResimConfig(metrics=['gain'], frequency_hz=1000.0)
    report = _run(
        edit_and_resim_with_delta(
            schematic=schematic_path,
            edits=[('R1', '10k')],
            config=cfg,
            exporter=FakeExporter(),
            simulator=_DummySimulator(),
            netlist_editor=_DummyNetlistEditor(),
        )
    )
    assert len(report.deltas) == 1
    delta = report.deltas[0]
    assert isinstance(delta, GainDelta)
    assert delta.after is None
    assert delta.failed_reason is not None
    assert 'after gain diverged' in delta.failed_reason


def test_partial_after_failure_mixed_deltas(
    monkeypatch: pytest.MonkeyPatch,
    schematic_path: Path,
) -> None:
    _patch_measures(
        monkeypatch,
        gain=_seq_measure([_gain(value_db=20.0), _gain(value_db=22.0)]),
        bandwidth=_seq_measure(
            [
                _bandwidth(),
                SimulationFailedError('after ac sweep diverged'),
            ]
        ),
    )
    _patch_edit(monkeypatch, _seq_edit())

    cfg = EditAndResimConfig(
        metrics=['gain', 'bandwidth'],
        frequency_hz=1000.0,
    )
    report = _run(
        edit_and_resim_with_delta(
            schematic=schematic_path,
            edits=[('R1', '10k')],
            config=cfg,
            exporter=FakeExporter(),
            simulator=_DummySimulator(),
            netlist_editor=_DummyNetlistEditor(),
        )
    )
    by_type = {type(d): d for d in report.deltas}
    assert by_type[GainDelta].after is not None
    assert by_type[BandwidthDelta].after is None
    assert by_type[BandwidthDelta].failed_reason is not None


def test_after_export_failure_marks_all_metrics_failed(
    monkeypatch: pytest.MonkeyPatch,
    schematic_path: Path,
) -> None:
    _patch_measures(
        monkeypatch,
        gain=_seq_measure([_gain()]),  # только baseline нужен
        bandwidth=_seq_measure([_bandwidth()]),
    )
    _patch_edit(monkeypatch, _seq_edit())

    cfg = EditAndResimConfig(
        metrics=['gain', 'bandwidth'],
        frequency_hz=1000.0,
    )
    report = _run(
        edit_and_resim_with_delta(
            schematic=schematic_path,
            edits=[('R1', '10k')],
            config=cfg,
            exporter=FailingAfterExporter(),
            simulator=_DummySimulator(),
            netlist_editor=_DummyNetlistEditor(),
        )
    )
    assert all(d.after is None for d in report.deltas)
    assert all(
        d.failed_reason is not None and 'export' in d.failed_reason
        for d in report.deltas
    )


def test_empty_edits_raises_value_error(
    monkeypatch: pytest.MonkeyPatch,
    schematic_path: Path,
) -> None:
    cfg = EditAndResimConfig(metrics=['gain'], frequency_hz=1000.0)
    with pytest.raises(ValueError, match='edits'):
        _run(
            edit_and_resim_with_delta(
                schematic=schematic_path,
                edits=[],
                config=cfg,
                exporter=FakeExporter(),
                simulator=_DummySimulator(),
                netlist_editor=_DummyNetlistEditor(),
            )
        )


def test_duplicate_metrics_silently_deduped_in_use_case(
    monkeypatch: pytest.MonkeyPatch,
    schematic_path: Path,
) -> None:
    """Если config дедуплицировал — use case вызывает measure_gain только дважды."""
    counter = {'n': 0}

    async def gain_counter(**_kwargs: object) -> GainMeasurement:
        counter['n'] += 1
        return _gain(value_db=20.0 + counter['n'])

    _patch_measures(monkeypatch, gain=gain_counter)
    _patch_edit(monkeypatch, _seq_edit())

    cfg = EditAndResimConfig(
        metrics=['gain', 'gain'],
        frequency_hz=1000.0,
    )
    _run(
        edit_and_resim_with_delta(
            schematic=schematic_path,
            edits=[('R1', '10k')],
            config=cfg,
            exporter=FakeExporter(),
            simulator=_DummySimulator(),
            netlist_editor=_DummyNetlistEditor(),
        )
    )
    assert counter['n'] == 2  # baseline + after, не 4


def test_soft_warn_edits_constant_is_exported() -> None:
    """Use case экспортит порог константой; soft-warn печатает CLI слой
    (паттерн T022 `SOFT_WARN_COMBINATIONS`)."""
    from application.edit_and_resim_with_delta import SOFT_WARN_EDITS

    assert SOFT_WARN_EDITS == 10


def test_report_includes_schematic_path_and_edits(
    monkeypatch: pytest.MonkeyPatch,
    schematic_path: Path,
) -> None:
    _patch_measures(
        monkeypatch,
        gain=_seq_measure([_gain(), _gain(value_db=22.0)]),
    )
    _patch_edit(monkeypatch, _seq_edit())

    cfg = EditAndResimConfig(metrics=['gain'], frequency_hz=1000.0)
    edits = [('R1', '10k'), ('R2', '20k')]
    report = _run(
        edit_and_resim_with_delta(
            schematic=schematic_path,
            edits=edits,
            config=cfg,
            exporter=FakeExporter(),
            simulator=_DummySimulator(),
            netlist_editor=_DummyNetlistEditor(),
        )
    )
    assert report.schematic == str(schematic_path)
    assert report.edits == edits


def test_multiple_matches_error_also_triggers_rollback(
    monkeypatch: pytest.MonkeyPatch,
    schematic_path: Path,
) -> None:
    """MultipleMatchesError тоже должен откатить SchematicSnapshot."""
    original_text = schematic_path.read_text()

    def editor_multiple_matches(path: Path, ref: str, value: str) -> str:
        msg = f'multiple symbols for ref={ref}'
        raise MultipleMatchesError(msg)

    _patch_measures(monkeypatch, gain=_seq_measure([_gain()]))
    _patch_edit(monkeypatch, editor_multiple_matches)

    cfg = EditAndResimConfig(metrics=['gain'], frequency_hz=1000.0)
    with pytest.raises(MultipleMatchesError):
        _run(
            edit_and_resim_with_delta(
                schematic=schematic_path,
                edits=[('R1', '10k')],
                config=cfg,
                exporter=FakeExporter(),
                simulator=_DummySimulator(),
                netlist_editor=_DummyNetlistEditor(),
            )
        )
    assert schematic_path.read_text() == original_text
