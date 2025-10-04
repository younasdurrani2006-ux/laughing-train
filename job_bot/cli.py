"""Command line interface for the job automation bot."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from .bot import JobApplicationBot, JobAutomationError
from .config import load_config

app = typer.Typer(add_completion=False, help="Automate job application workflows")


@app.command()
def run(
    config: Path = typer.Argument(..., exists=True, readable=True, help="Path to the YAML configuration file"),
    headless: Optional[bool] = typer.Option(
        None,
        "--headless/--no-headless",
        help="Override the headless mode defined in the configuration",
    ),
    dry_run: bool = typer.Option(False, help="Print the actions without running the browser"),
) -> None:
    """Execute all jobs defined in the configuration file."""

    try:
        automation_config = load_config(config)
    except Exception as exc:
        raise typer.BadParameter(str(exc)) from exc

    bot = JobApplicationBot(automation_config, headless=headless)
    try:
        bot.run(dry_run=dry_run)
    except JobAutomationError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":  # pragma: no cover
    app()
