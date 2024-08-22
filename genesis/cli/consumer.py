from typing import Annotated, Union
from pathlib import Path
import importlib
import logging
import asyncio

import typer
from rich import print
from rich.panel import Panel
from rich.padding import Padding

from genesis.cli import watcher
from genesis.logger import logger
from genesis.consumer import Consumer
from genesis.cli.exceptions import CLIExcpetion
from genesis.cli.utils import complete_log_levels
from genesis.cli.discover import get_import_string

consumer = typer.Typer(rich_markup_mode="rich")


async def _run_with_reload(app: Consumer, path: Path) -> None:
    loop = asyncio.get_running_loop()
    queue = asyncio.Queue()

    async def consume(queue: asyncio.Queue) -> None:
        await app.start()
        async for event in watcher.EventIterator(queue):
            if event:
                logger.info(f"File changed: {event.src_path}")
                await app.stop()
                logger.info("App stopped, restarting...")
                await app.start()

    observer = watcher.factory(path, queue, loop)

    observer.start()
    asyncio.run_coroutine_threadsafe(queue.put(None), loop)

    try:
        await consume(queue)
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        observer.stop()


def _run(
    path: Union[Path, None] = None,
    host: str = "127.0.0.1",
    port: int = 8021,
    reload: bool = True,
    app: Union[str, None] = None,
    loglevel: str = "info",
    password: str = "ClueCon",
) -> None:
    try:
        import_string = get_import_string(Consumer, path=path, app_name=app)

        panel = Panel(
            f"[dim]ESL dial address:[/dim] [link]esl://{host}:{port}[/link]",
            title="Genesis Consumer app",
            expand=False,
            padding=(1, 2),
            style="black on yellow" if reload else "green",
        )

        print(Padding(panel, 1))

        module_str, attr_str = import_string.split(":")
        module = importlib.import_module(module_str)
        app: Consumer = getattr(module, attr_str)

        app.host = host
        app.port = port
        app.password = password

        logger.info(f"Setting log level to [bold]{loglevel.upper()}[/bold]")
        levels = logging.getLevelNamesMapping()
        logger.setLevel(levels.get(loglevel.upper(), logging.INFO))

        if reload:
            asyncio.run(_run_with_reload(app, path))
        else:
            asyncio.run(app.start())

    except CLIExcpetion as e:
        logger.error(e)
        raise typer.Exit(1)


@consumer.command()
def dev(
    path: Annotated[
        Path,
        typer.Argument(
            help="A path to a Python file or package directory.", metavar="PATH"
        ),
    ],
    *,
    host: Annotated[
        str,
        typer.Option(help="The host to connect on.", envvar="ESL_HOST"),
    ] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option(help="The port to connect on.", envvar="ESL_PORT"),
    ] = 8021,
    password: Annotated[
        str,
        typer.Option(
            help="The password to authenticate on host.", envvar="ESL_PASSWORD"
        ),
    ] = "ClueCon",
    app: Annotated[
        Union[str, None],
        typer.Option(
            help="Variable that contains the [bold]Consumer[/bold] app in the imported module or package.",
            envvar="ESL_APP_NAME",
        ),
    ] = None,
    loglevel: Annotated[
        str,
        typer.Option(
            help="The log level to use.",
            envvar="ESL_LOG_LEVEL",
            show_default=True,
            case_sensitive=False,
            autocompletion=complete_log_levels,
        ),
    ] = "info",
):
    """
    Run a [bold]Consumer[/bold] genesis app in [yellow]development[/yellow] mode. 🧪

    It automatically detects the Python module or package that needs to be imported based on the file or directory path passed.

    It detects the [bold]Consumer[/bold] app object to use based on the app name passed.
    By default it looks in the module or package for an object named [blue]app[/blue].
    Otherwise, it uses the first [bold]Consumer[/bold] app found in the imported module or package.
    """
    _run(
        path=path,
        host=host,
        port=port,
        password=password,
        app=app,
        reload=True,
        loglevel=loglevel,
    )


@consumer.command()
def run(
    path: Annotated[
        Path,
        typer.Argument(
            help="A path to a Python file or package directory.", metavar="PATH"
        ),
    ],
    *,
    host: Annotated[
        str,
        typer.Option(help="The host to connect on.", envvar="ESL_HOST"),
    ] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option(help="The port to connect on.", envvar="ESL_PORT"),
    ] = 8021,
    password: Annotated[
        str,
        typer.Option(
            help="The password to authenticate on host.", envvar="ESL_PASSWORD"
        ),
    ] = "ClueCon",
    app: Annotated[
        Union[str, None],
        typer.Option(
            help="Variable that contains the [bold]Consumer[/bold] app in the imported module or package.",
            envvar="ESL_APP_NAME",
        ),
    ] = None,
    loglevel: Annotated[
        str,
        typer.Option(
            help="The log level to use.",
            envvar="ESL_LOG_LEVEL",
            show_default=True,
            case_sensitive=False,
            autocompletion=complete_log_levels,
        ),
    ] = "info",
):
    """
    Run a [bold]Consumer[/bold] genesis app in [green]production[/green] mode. 🚀

    It automatically detects the Python module or package that needs to be imported based on the file or directory path passed.

    It detects the [bold]Consumer[/bold] app object to use based on the app name passed.
    By default it looks in the module or package for an object named [blue]app[/blue].
    Otherwise, it uses the first [bold]Consumer[/bold] app found in the imported module or package.
    """
    _run(
        path=path,
        host=host,
        port=port,
        password=password,
        app=app,
        reload=False,
        loglevel=loglevel,
    )
