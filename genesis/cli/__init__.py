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
from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

from genesis.cli.consumer import consumer
from genesis.cli.outbound import outbound
from genesis.observability import reconfigure_logger, logger
from genesis.observability.otel_config import (
    create_resource,
    get_otel_exporter_otlp_metrics_endpoint,
    get_otel_exporter_otlp_traces_endpoint,
    is_otel_sdk_disabled,
)


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
        # Setup OpenTelemetry (honors OTEL_SDK_DISABLED, OTEL_* env vars)
        if not is_otel_sdk_disabled():
            resource = create_resource()
            metric_readers: list = [PrometheusMetricReader()]
            if get_otel_exporter_otlp_metrics_endpoint():
                metric_readers.append(
                    PeriodicExportingMetricReader(
                        OTLPMetricExporter(),
                        export_interval_millis=60_000,
                    )
                )
            metrics.set_meter_provider(
                MeterProvider(resource=resource, metric_readers=metric_readers)
            )
            if get_otel_exporter_otlp_traces_endpoint():
                tracer_provider = TracerProvider(resource=resource)
                tracer_provider.add_span_processor(
                    BatchSpanProcessor(OTLPSpanExporter())
                )
                trace.set_tracer_provider(tracer_provider)
    except Exception as e:
        logger.warning(f"Failed to setup OpenTelemetry: {e}")

    """
    Genesis - [blue]FreeSWITCH Event Socket protocol[/blue] implementation with [bold]asyncio[/bold].

    Run yours freeswitch apps without any external dependencies.

    ℹ️ Read more in the docs: [link]https://otoru.github.io/Genesis/[/link].
    """
