"""
CLI module for Genesis.
------------------------

This module contains the CLI commands for Genesis.
"""

import importlib.metadata
from typing import Annotated, Union

import typer
from rich import print

from genesis.cli.consumer import consumer
from genesis.cli.outbound import outbound


app = typer.Typer(rich_markup_mode="rich")
app.add_typer(consumer, name="consumer", short_help="Run you ESL events consumer.")
app.add_typer(outbound, name="outbound", short_help="Run you outbound services.")


def version(show: bool) -> None:
    """Show the version and exit."""
    if show:
        version = importlib.metadata.version("genesis")
        print(f"Genesis version: [green]{version}[/green]")
        raise typer.Exit()


@app.callback()
def callback(
    version: Annotated[
        Union[bool, None],
        typer.Option("--version", help="Show the version and exit.", callback=version),
    ] = None,
) -> None:
    """
    Genesis - [blue]FreeSWITCH Event Socket protocol[/blue] implementation with [bold]asyncio[/bold].

    Run yours freeswitch apps without any external dependencies.

    ℹ️ Read more in the docs: [link]https://github.com/Otoru/Genesis/wiki[/link].
    """
