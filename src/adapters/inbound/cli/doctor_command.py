"""
Регистрация `efactory doctor` subcommand (T036).

Маленький модуль для уменьшения размера `app.py`; вызывается из
`build_app` после создания root typer.Typer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

import typer

from adapters.inbound.cli.doctor_renderer import render_doctor_report
from application.run_doctor import run_doctor
from domain.doctor import CheckStatus

if TYPE_CHECKING:
    from ports.outbound.system_probe import SystemProbe


def register_doctor_command(
    app: typer.Typer,
    *,
    system_probe: SystemProbe,
) -> None:
    @app.command('doctor')
    def doctor(
        *,
        no_gui: Annotated[
            bool,
            typer.Option(
                '--no-gui',
                help='Пропустить GUI passthrough probe (headless контекст).',
            ),
        ] = False,
    ) -> None:
        """Диагностика тулчейна efactory:linux (T036)."""
        report = run_doctor(system_probe, include_gui=not no_gui)
        typer.echo(render_doctor_report(report))
        if report.worst_status == CheckStatus.FAIL:
            raise typer.Exit(1)


__all__ = ['register_doctor_command']
