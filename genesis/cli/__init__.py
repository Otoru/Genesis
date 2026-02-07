"""
CLI module for Genesis.
------------------------

This module contains the CLI commands for Genesis.
"""

import importlib.metadata
import os
from typing import Annotated, Union

import typer
from rich import print
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from prometheus_client import start_http_server

from genesis.cli.consumer import consumer
from genesis.cli.outbound import outbound
from genesis.observability import reconfigure_logger, logger


app = typer.Typer(rich_markup_mode="rich")
app.add_typer(consumer, name="consumer", short_help="Run you ESL events consumer.")
app.add_typer(outbound, name="outbound", short_help="Run you outbound services.")


def version(show: bool) -> None:
    """Show the version and exit."""
    if show:
        version = importlib.metadata.version("genesis")
        logger.info(f"Genesis version: {version}")
        raise typer.Exit()


@app.callback()
def callback(
    version: Annotated[
        Union[bool, None],
        typer.Option("--version", help="Show the version and exit.", callback=version),
    ] = None,
    json: Annotated[
        bool,
        typer.Option("--json", help="Output logs in JSON format."),
    ] = False,
) -> None:
    reconfigure_logger(json)

    try:
        # Setup OpenTelemetry
        metric_reader = PrometheusMetricReader()
        provider = MeterProvider(
            resource=Resource.create({"service.name": "genesis"}),
            metric_readers=[metric_reader],
        )
        metrics.set_meter_provider(provider)

    except Exception as e:
        logger.warning(f"Failed to setup OpenTelemetry: {e}")

    """
    Genesis - [blue]FreeSWITCH Event Socket protocol[/blue] implementation with [bold]asyncio[/bold].

    Run yours freeswitch apps without any external dependencies.

    ℹ️ Read more in the docs: [link]https://otoru.github.io/Genesis/[/link].
    """
