from typing import Annotated, Union
from pathlib import Path
import importlib
import asyncio

import typer
from rich import print
from rich.panel import Panel
from rich.padding import Padding

from genesis.logger import logger
from genesis.outbound import Outbound
from genesis.cli.discover import get_import_string
from genesis.cli.exceptions import CLIExcpetion

outbound = typer.Typer(rich_markup_mode="rich")


@outbound.command()
def dev(
    path: Annotated[
        Union[Path, None],
        typer.Argument(help="A path to a Python file or package directory."),
    ] = None,
    *,
    host: Annotated[
        str,
        typer.Option(help="The host to serve on."),
    ] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option(help="The port to serve on."),
    ] = 9000,
    app: Annotated[
        Union[str, None],
        typer.Option(
            help="The name of the variable that contains the [bold]Outbound[/bold] genesis app in the imported module or package."
        ),
    ] = None,
):
    """
    Run a [bold]Outbound[/bold] genesis app in [yellow]development[/yellow] mode. 🧪

    It automatically detects the Python module or package that needs to be imported based on the file or directory path passed.

    It detects the [bold]Outbound[/bold] app object to use based on the app name passed.
    By default it looks in the module or package for an object named [blue]app[/blue].
    Otherwise, it uses the first [bold]Outbound[/bold] app found in the imported module or package.
    """
    _run(path=path, host=host, port=port, app=app, reload=True)


@outbound.command()
def run(
    path: Annotated[
        Union[Path, None],
        typer.Argument(help="A path to a Python file or package directory."),
    ] = None,
    *,
    host: Annotated[
        str,
        typer.Option(help="The host to serve on."),
    ] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option(help="The port to serve on."),
    ] = 9000,
    app: Annotated[
        Union[str, None],
        typer.Option(
            help="The name of the variable that contains the [bold]Outbound[/bold] genesis app in the imported module or package."
        ),
    ] = None,
):
    """
    Run a [bold]Outbound[/bold] genesis app in [green]production[/green] mode. 🚀

    It automatically detects the Python module or package that needs to be imported based on the file or directory path passed.

    It detects the [bold]Outbound[/bold] app object to use based on the app name passed.
    By default it looks in the module or package for an object named [blue]app[/blue].
    Otherwise, it uses the first [bold]Outbound[/bold] app found in the imported module or package.
    """
    _run(path=path, host=host, port=port, app=app, reload=False)


def _run(
    path: Union[Path, None] = None,
    host: str = "127.0.0.1",
    port: int = 9000,
    reload: bool = True,
    app: Union[str, None] = None,
) -> None:
    try:
        import_string = get_import_string(Outbound, path=path, app_name=app)

        panel = Panel(
            f"[dim]Application address:[/dim] [link]esl://{host}:{port}[/link]",
            title="Genesis Outbound app",
            expand=False,
            padding=(1, 2),
            style="black on yellow" if reload else "green",
        )

        print(Padding(panel, 1))

        module_str, attr_str = import_string.split(":")
        module = importlib.import_module(module_str)
        app: Outbound = getattr(module, attr_str)

        app.host = host
        app.port = port
        asyncio.run(app.start())

    except CLIExcpetion as e:
        logger.error(e)
        raise typer.Exit(1)
