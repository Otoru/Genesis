from typing import Annotated, Union
from pathlib import Path
import importlib
import logging
import asyncio

import typer

from genesis.cli import watcher
from genesis.logger import logger
from genesis.consumer import Consumer
from genesis.cli.exceptions import CLIExcpetion
from genesis.cli.utils import complete_log_levels, get_log_level_map
from genesis.cli.discover import get_import_string
from genesis.types import WatcherProtocol

consumer = typer.Typer(rich_markup_mode="rich")


async def _run_with_reload(app: Consumer, path: Path) -> None:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    async def consume(queue: asyncio.Queue) -> None:
        await app.start()
        async for event in watcher.EventIterator(queue):
            if event:
                logger.info(f"File changed: {event.src_path}")
                await app.stop()
                logger.info("App stopped, restarting...")
                await app.start()

    observer: WatcherProtocol = watcher.factory(path, queue, loop)

    observer.start()
    asyncio.run_coroutine_threadsafe(queue.put(None), loop)

    try:
        await consume(queue)
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        observer.stop()


def _run(
    path: Path,
    host: str = "127.0.0.1",
    port: int = 8021,
    reload: bool = True,
    app: Union[str, None] = None,
    loglevel: str = "info",
    password: str = "ClueCon",
) -> None:
    try:
        import_string = get_import_string(Consumer, path=path, app_name=app)

        logger.info(f"Consumer started - Host: {host}, Port: {port}")

        module_str, attr_str = import_string.split(":")
        module = importlib.import_module(module_str)
        consumer_app: Consumer = getattr(module, attr_str)

        consumer_app.host = host
        consumer_app.port = port
        consumer_app.password = password

        logger.info(f"Setting log level to [bold]{loglevel.upper()}[/bold]")
        levels = get_log_level_map()
        logger.setLevel(levels.get(loglevel.upper(), logging.INFO))

        if reload:
            asyncio.run(_run_with_reload(consumer_app, path))
        else:
            asyncio.run(consumer_app.start())

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
            shell_complete=complete_log_levels,
        ),
    ] = "info",
) -> None:
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
            shell_complete=complete_log_levels,
        ),
    ] = "info",
) -> None:
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
