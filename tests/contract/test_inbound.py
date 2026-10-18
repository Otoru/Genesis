"""Inbound ESL transport against the loopback simulator."""

import asyncio
from typing import Tuple
from unittest.mock import patch

import pytest

from genesis import Inbound
from genesis.exceptions import (
    AuthenticationError,
    ConnectionError,
    ConnectionTimeoutError,
    UnconnectedError,
)
from genesis.protocol.parser import ESLEvent

from tests.simulator.codec import ESLFrame
from tests.simulator.faults import Fault
from tests.simulator.server import Simulator

UNKNOWN_API = b"-ERR nope_research_cmd Command not found!\n"
UNICODE_UNIT = "café-研究"


def _api_frames(server: Simulator) -> Tuple[ESLFrame, ...]:
    frames = []
    for item in server.journal.events():
        if item.frame.header("Content-Type") == "api/response":
            frames.append(item.frame)
    return tuple(frames)


def _connection_id(server: Simulator, command: str) -> str:
    matched = [
        item.connection_id for item in server.journal.commands() if item.text == command
    ]
    assert matched
    return matched[-1]


async def test_send_requires_connection() -> None:
    client = Inbound("127.0.0.1", 8021, "lab-password")
    with pytest.raises(UnconnectedError):
        await client.send("uptime")


async def test_connect_refused() -> None:
    probe = await asyncio.start_server(lambda _r, _w: None, "127.0.0.1", 0)
    sockets = probe.sockets
    assert sockets is not None
    port = int(sockets[0].getsockname()[1])
    probe.close()
    await probe.wait_closed()
    with pytest.raises((ConnectionRefusedError, OSError)):
        async with Inbound("127.0.0.1", port, "lab-password"):
            pass


async def test_connect_times_out_before_the_socket_opens(
    esl_server: Simulator,
) -> None:
    """``timeout=0`` cancels ``open_connection`` before the socket is up.

    ``Inbound.start`` maps that ``TimeoutError`` to ``ConnectionTimeoutError``.
    It is not the stalled-auth case below.
    """
    with pytest.raises(ConnectionTimeoutError):
        async with Inbound(
            esl_server.host,
            esl_server.port,
            esl_server.password,
            timeout=0,
        ):
            pass


async def test_connect_times_out_when_auth_never_arrives(esl_server: Simulator) -> None:
    """The greeting is sent. The auth command is stalled, so no reply arrives.

    ``Inbound.timeout`` only bounds ``open_connection``. This wait is the
    stalled read, after the socket is already open.
    """
    caught = esl_server.arm_next(Fault.STALL_READS)
    client = Inbound(esl_server.host, esl_server.port, esl_server.password)
    start_task = asyncio.create_task(client.start())
    try:
        await asyncio.wait_for(caught.wait(), 1)
        assert not start_task.done()
        assert esl_server.connection_ids
        connection_id = esl_server.connection_ids[-1]
        assert esl_server.journal.commands(connection_id) == ()
        start_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await start_task
    finally:
        if not start_task.done():
            start_task.cancel()
        await client.stop()


async def test_invalid_password(esl_server: Simulator) -> None:
    with pytest.raises(AuthenticationError):
        async with Inbound(esl_server.host, esl_server.port, "invalid"):
            pass


async def test_api_command_ok(esl_server: Simulator) -> None:
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        response = await client.send("api eval alpha")
    assert response.get("Content-Type") == "api/response"
    assert response.body == "alpha"
    assert response.get("Reply-Text") is None
    frames = [frame for frame in _api_frames(esl_server) if frame.body == b"alpha"]
    assert frames
    assert frames[-1].header("Content-Length") == "5"


async def test_api_large_body(esl_server: Simulator) -> None:
    text = UNICODE_UNIT * 400
    encoded = text.encode("utf-8")
    assert len(encoded) != len(text)
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        response = await client.send("api eval %s" % text)
    assert response.body == text
    assert response.get("Content-Length") == str(len(encoded))
    assert int(str(response["Content-Length"])) != len(text)
    frames = [frame for frame in _api_frames(esl_server) if frame.body == encoded]
    assert frames
    assert frames[-1].header("Content-Length") == str(len(encoded))


async def test_heartbeat_handler(esl_server: Simulator) -> None:
    heard: asyncio.Future[ESLEvent] = asyncio.get_running_loop().create_future()

    def handler(event: ESLEvent) -> None:
        if not heard.done():
            heard.set_result(event)

    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        client.on("HEARTBEAT", handler)
        await client.send("event plain HEARTBEAT")
        await esl_server.emit(
            (
                ("Event-Name", "HEARTBEAT"),
                ("Event-Info", "System Ready"),
            )
        )
        event = await asyncio.wait_for(heard, 1)
    assert event.get("Event-Name") == "HEARTBEAT"
    assert event.get("Event-Info") == "System Ready"


async def test_custom_subclass_handler(esl_server: Simulator) -> None:
    heard: asyncio.Future[ESLEvent] = asyncio.get_running_loop().create_future()

    def handler(event: ESLEvent) -> None:
        if not heard.done():
            heard.set_result(event)

    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        client.on("sofia::register", handler)
        await client.send("event plain CUSTOM sofia::register")
        await esl_server.emit(
            (
                ("Event-Name", "CUSTOM"),
                ("Event-Subclass", "sofia::register"),
                ("from-user", "1000"),
            )
        )
        event = await asyncio.wait_for(heard, 1)
    assert event.get("Event-Subclass") == "sofia::register"
    assert event.get("from-user") == "1000"


async def test_remove_handler() -> None:
    async def handler(event: ESLEvent) -> None:
        del event

    client = Inbound("127.0.0.1", 8021, "lab-password")
    client.on("MESSAGE", handler)
    assert handler in client.handlers["MESSAGE"]
    client.remove("MESSAGE", handler)
    assert handler not in client.handlers["MESSAGE"]


async def test_send_raises_when_the_writer_is_closed(esl_server: Simulator) -> None:
    """Closing the writer is ``ConnectionError``, not an API error body."""
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        assert client.writer is not None
        client.writer.close()
        with pytest.raises(ConnectionError):
            await client.send("api eval alpha")


async def test_unknown_api_error(esl_server: Simulator) -> None:
    async with Inbound(esl_server.host, esl_server.port, esl_server.password) as client:
        response = await client.send("api nope_research_cmd")
    assert response.get("Content-Type") == "api/response"
    assert response.body == UNKNOWN_API.decode("utf-8")
    assert response.get("Reply-Text") is None
    frames = [frame for frame in _api_frames(esl_server) if frame.body == UNKNOWN_API]
    assert frames
    assert frames[-1].header("Content-Length") == "42"


async def test_metrics_error_on_start(esl_server: Simulator) -> None:
    with patch(
        "genesis.inbound.connections_active_counter.add",
        side_effect=Exception("Metrics error"),
    ):
        async with Inbound(
            esl_server.host, esl_server.port, esl_server.password
        ) as client:
            assert client.is_connected


async def test_metrics_error_on_stop(esl_server: Simulator) -> None:
    client = Inbound(esl_server.host, esl_server.port, esl_server.password)
    await client.start()
    assert client.is_connected
    with patch(
        "genesis.inbound.connections_active_counter.add",
        side_effect=Exception("Metrics error"),
    ):
        await client.stop()
    assert not client.is_connected


async def test_connect_error_metrics(esl_server: Simulator) -> None:
    with patch(
        "genesis.inbound.connection_errors_counter.add",
        side_effect=Exception("Metrics error"),
    ):
        with pytest.raises(ConnectionTimeoutError):
            async with Inbound(
                esl_server.host,
                esl_server.port,
                esl_server.password,
                timeout=0,
            ):
                pass


async def test_subscriptions_and_filters_stay_on_one_connection(
    esl_server: Simulator,
) -> None:
    alpha_hit: asyncio.Event = asyncio.Event()
    beta_hit: asyncio.Event = asyncio.Event()

    def on_alpha(event: ESLEvent) -> None:
        if event.get("Event-Subclass") == "esl.research.a":
            alpha_hit.set()

    def on_beta(event: ESLEvent) -> None:
        del event
        beta_hit.set()

    async with Inbound(
        esl_server.host, esl_server.port, esl_server.password
    ) as alpha, Inbound(esl_server.host, esl_server.port, esl_server.password) as beta:
        alpha.on("esl.research.a", on_alpha)
        beta.on("esl.research.b", on_beta)
        await alpha.send("event plain CUSTOM esl.research.a")
        await alpha.send("filter Event-Subclass esl.research.a")
        await beta.send("event plain CUSTOM esl.research.b")
        await beta.send("filter Event-Subclass esl.research.b")
        await esl_server.emit(
            (
                ("Event-Name", "CUSTOM"),
                ("Event-Subclass", "esl.research.a"),
                ("research-note", "only-a"),
            )
        )
        await asyncio.wait_for(alpha_hit.wait(), 1)
        drained = await beta.send("api eval beta-drain")
    assert drained.body == "beta-drain"
    assert not beta_hit.is_set()
    alpha_id = _connection_id(esl_server, "filter Event-Subclass esl.research.a")
    beta_id = _connection_id(esl_server, "filter Event-Subclass esl.research.b")
    assert alpha_id != beta_id
    assert any(
        b"esl.research.a" in item.frame.body
        for item in esl_server.journal.events(alpha_id)
    )
    assert not any(
        b"esl.research.a" in item.frame.body
        for item in esl_server.journal.events(beta_id)
    )
