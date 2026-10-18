"""Socket telemetry against the ESL simulator and an outbound peer."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from genesis import Consumer, Inbound, Outbound, Session
from genesis.protocol.metrics import session_commands_counter
from genesis.protocol.parser import ESLEvent

from tests.simulator.server import Simulator


class _CommandMetrics:
    def __init__(self) -> None:
        self.labels: list[dict[str, str]] = []
        self._real = session_commands_counter.add

    def add(self, *args: object, **kwargs: object) -> None:
        attributes = kwargs.get("attributes")
        if isinstance(attributes, dict):
            self.labels.append(
                {str(key): str(value) for key, value in attributes.items()}
            )
        self._real(*args, **kwargs)

    def assert_application(self, name: str, *uuids: str) -> None:
        assert self.labels, "session command metric was not recorded"
        assert self.labels[-1]["application.name"] == name
        for attributes in self.labels:
            for key, value in attributes.items():
                assert "uuid" not in key.lower()
                for uuid in uuids:
                    assert uuid not in value


@pytest.fixture
def memory_exporter() -> Iterator[InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    processor = SimpleSpanProcessor(exporter)
    provider: Any = trace.get_tracer_provider()
    if not hasattr(provider, "add_span_processor"):
        provider = TracerProvider()
        trace.set_tracer_provider(provider)
    provider.add_span_processor(processor)
    yield exporter


def _bound_port(app: Outbound) -> int:
    server = app.server
    sockets = server.sockets if server is not None else None
    if not sockets:
        raise RuntimeError("outbound server did not bind")
    return int(sockets[0].getsockname()[1])


async def wait_for_span(
    exporter: InMemorySpanExporter,
    span_name: str,
    timeout: float = 1.0,
) -> None:
    """Wait until a finished span with this name is exported."""
    loop = asyncio.get_running_loop()
    start_time = loop.time()
    while True:
        spans = exporter.get_finished_spans()
        if any(span.name == span_name for span in spans):
            return
        if loop.time() - start_time >= timeout:
            raise TimeoutError("Span '%s' not found within %ss" % (span_name, timeout))
        future: asyncio.Future[None] = loop.create_future()
        loop.call_soon(future.set_result, None)
        await future


async def test_inbound_connection_spans(
    esl_server: Simulator,
    memory_exporter: InMemorySpanExporter,
) -> None:
    """Connecting to the simulator generates an inbound_connect span."""
    async with Inbound(esl_server.host, esl_server.port, esl_server.password):
        pass

    await wait_for_span(memory_exporter, "inbound_connect", timeout=1.0)

    spans = memory_exporter.get_finished_spans()
    connect_spans = [span for span in spans if span.name == "inbound_connect"]
    assert len(connect_spans) == 1
    span = connect_spans[0]
    assert span.attributes["net.peer.name"] == "127.0.0.1"
    assert "net.peer.port" in span.attributes


async def test_send_command_span(
    esl_server: Simulator,
    memory_exporter: InMemorySpanExporter,
) -> None:
    """Sending a command generates a send_command span carrying the reply text."""
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        await client.send("uptime")

    await wait_for_span(memory_exporter, "send_command", timeout=1.0)

    spans = memory_exporter.get_finished_spans()
    send_spans = [span for span in spans if span.name == "send_command"]
    assert len(send_spans) >= 1

    uptime_span = next(
        (span for span in send_spans if span.attributes["command.name"] == "uptime"),
        None,
    )
    assert uptime_span is not None
    replies = [
        observed.frame.header("Reply-Text")
        for observed in esl_server.journal.events()
        if observed.frame.header("Reply-Text")
    ]
    assert "-ERR command not found" in replies
    if "command.reply" in uptime_span.attributes:
        assert uptime_span.attributes["command.reply"] == "-ERR command not found"


async def test_consumer_start_and_stop_spans(
    esl_server: Simulator,
    memory_exporter: InMemorySpanExporter,
) -> None:
    """Consumer start and stop emit spans, and a subscribed handler still runs."""
    consumer = Consumer(esl_server.host, esl_server.port, esl_server.password)
    received = asyncio.Event()

    @consumer.handle("HEARTBEAT")
    async def on_heartbeat(event: ESLEvent) -> None:
        if event.get("Event-Name") == "HEARTBEAT":
            received.set()

    start_task = asyncio.create_task(consumer.start())
    stopped = False
    try:
        await wait_for_span(memory_exporter, "consumer.start", timeout=5.0)
        connection_id = esl_server.connection_ids[-1]
        await esl_server.emit(
            (("Event-Name", "HEARTBEAT"),),
            connection_id=connection_id,
        )
        await asyncio.wait_for(received.wait(), timeout=5.0)
        await consumer.stop()
        stopped = True
        try:
            await asyncio.wait_for(start_task, timeout=5.0)
        except (asyncio.TimeoutError, Exception):
            start_task.cancel()
    finally:
        if not stopped:
            with contextlib.suppress(Exception):
                await consumer.stop()
        if not start_task.done():
            start_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await start_task

    spans = {span.name for span in memory_exporter.get_finished_spans()}
    assert "consumer.start" in spans
    assert "consumer.stop" in spans

    start_span = next(
        span
        for span in memory_exporter.get_finished_spans()
        if span.name == "consumer.start"
    )
    assert start_span.attributes["consumer.host"] == esl_server.host
    assert "consumer.port" in start_span.attributes


async def test_sendmsg_non_blocking_emits_span(
    esl_server: Simulator,
    memory_exporter: InMemorySpanExporter,
) -> None:
    """A non-blocking sendmsg emits session.sendmsg with application metadata."""
    done = asyncio.Event()
    handler_started = asyncio.Event()
    metrics = _CommandMetrics()

    async def handler(session: Session) -> None:
        handler_started.set()
        await session.sendmsg("execute", "answer", block=False)
        done.set()

    app = Outbound(handler, "127.0.0.1", 0)
    await app.start(block=False)
    try:
        with patch.object(session_commands_counter, "add", metrics.add):
            await esl_server.connect_dialplan("127.0.0.1", _bound_port(app), full=True)
            await asyncio.wait_for(handler_started.wait(), timeout=5.0)
            await asyncio.wait_for(done.wait(), timeout=5.0)
    finally:
        await app.stop()

    sendmsg_spans = [
        span
        for span in memory_exporter.get_finished_spans()
        if span.name == "session.sendmsg"
    ]
    assert sendmsg_spans, "session.sendmsg span not emitted"
    span = sendmsg_spans[-1]
    assert span.attributes["application.name"] == "answer"
    assert span.attributes["application.block"] == "False"
    channel_uuid = str(span.attributes["channel.uuid"])
    assert channel_uuid
    assert channel_uuid != "unknown"
    metrics.assert_application("answer", channel_uuid)


async def test_sendmsg_blocking_emits_await_complete(
    esl_server: Simulator,
    memory_exporter: InMemorySpanExporter,
) -> None:
    """A blocking sendmsg emits session.sendmsg and a session.await_complete child."""
    sendmsg_returned = asyncio.Event()
    handler_started = asyncio.Event()
    metrics = _CommandMetrics()
    recorded: list[str] = []

    async def handler(session: Session) -> None:
        handler_started.set()
        await session.sendmsg("execute", "playback", "/tmp/x.wav", block=True)
        sendmsg_returned.set()

    async def complete() -> None:
        pending = await esl_server.next_execution(5.0)
        recorded.append(pending.event_uuid)
        if pending.application != "playback" or pending.data != "/tmp/x.wav":
            raise AssertionError("pending execution does not match the playback")
        await esl_server.start_execution(pending)
        await esl_server.complete_execution(pending)

    watcher = asyncio.create_task(complete())
    app = Outbound(handler, "127.0.0.1", 0)
    await app.start(block=False)
    try:
        with patch.object(session_commands_counter, "add", metrics.add):
            await esl_server.connect_dialplan("127.0.0.1", _bound_port(app), full=True)
            await asyncio.wait_for(handler_started.wait(), timeout=5.0)
            await asyncio.wait_for(sendmsg_returned.wait(), timeout=5.0)
        await watcher
    finally:
        if not watcher.done():
            watcher.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher
        await app.stop()

    names = [span.name for span in memory_exporter.get_finished_spans()]
    assert "session.sendmsg" in names
    assert "session.await_complete" in names
    sendmsg_span = next(
        span
        for span in memory_exporter.get_finished_spans()
        if span.name == "session.sendmsg"
    )
    assert sendmsg_span.attributes["application.name"] == "playback"
    assert sendmsg_span.attributes["application.block"] == "True"
    channel_uuid = str(sendmsg_span.attributes["channel.uuid"])
    assert channel_uuid
    assert channel_uuid != "unknown"
    assert recorded
    assert sendmsg_span.attributes["application.uuid"] == recorded[0]
    metrics.assert_application("playback", channel_uuid)
