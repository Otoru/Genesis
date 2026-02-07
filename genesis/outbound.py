"""
Genesis outbound
----------------

ESL implementation used for outgoing connections on freeswitch.
"""

from __future__ import annotations

import asyncio
import socket
from asyncio import (
    CancelledError,
    StreamReader,
    StreamWriter,
    Task,
    current_task,
    start_server,
)
from functools import partial
from collections.abc import Callable
from typing import Any, Awaitable, Optional

from opentelemetry import metrics, trace

from genesis.observability import logger, observability
from genesis.channel import Channel
from genesis.session import Session

tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)

active_connections_counter = meter.create_up_down_counter(
    "genesis.connections.active",
    description="Number of active connections",
    unit="1",
)


def _safe_connection_metric(counter: object, *args: object, **kwargs: object) -> None:
    """Add to a counter, swallowing OTel/metrics errors."""
    try:
        getattr(counter, "add")(*args, **kwargs)
    except Exception:
        pass


async def _setup_session(session: Session, server: "Outbound") -> None:
    """Configure session: connect context, events, linger, and optional Channel."""
    logger.debug("Send command to start handle a call")
    session.context = dict(await session.send("connect"))

    if server.myevents:
        logger.debug("Send command to receive all call events")
        await session.send(f"filter Unique-ID {session.uuid}")
        await session.send("event plain all")

    if server.linger:
        logger.debug("Send linger command to freeswitch")
        await session.send("linger")
        session.is_lingering = True

    if session.uuid:

        try:
            session.channel = await Channel.from_session(session)
            logger.debug("Channel initialized for session: %s", session.channel.uuid)
        except Exception as e:
            logger.warning("Failed to initialize channel for session: %s", e)
            session.channel = None

    logger.debug("Start server session handler")


class Outbound:
    """
    Outbound class
    -------------

    Given a valid set of information, start an ESL server that processes calls.

    Attributes:
    - host: required
        IP address the server should listen on.
    - port: required
        Network port the server should listen on.
    - handler: required
        Function that will take a session as an argument and will actually process the call.
    - events: optional
        If true, ask freeswitch to send us all events associated with the session.
    - linger: optional
        If true, asks that the events associated with the session come even after the call hangup.
    """

    def __init__(
        self,
        handler: Callable[[Session], Awaitable[None]],
        host: str = "127.0.0.1",
        port: int = 9000,
        events: bool = True,
        linger: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.app = handler
        self.myevents = events
        self.linger = linger
        self.server: Optional[asyncio.AbstractServer] = None
        self.tasks: set[Task[Any]] = set()

    async def start(self, block: bool = True) -> None:
        """Start the application server."""
        handler = partial(self.handler, self)
        self.server = await start_server(
            handler, self.host, self.port, family=socket.AF_INET
        )

        if block:
            observability.set_outbound_ready(True)
            await self.server.serve_forever()
        else:
            await self.server.start_serving()
            observability.set_outbound_ready(True)

    async def stop(self) -> None:
        """Terminate the application server."""
        observability.set_outbound_ready(False)
        if self.server:
            logger.debug("Shutdown application server.")
            self.server.close()
            await self.server.wait_closed()

        for task in list(self.tasks):
            await self._cancel_connection_task(task)

    async def _cancel_connection_task(self, task: Task[Any]) -> None:
        """Cancel a connection task and wait for it; swallow CancelledError."""
        if task.done():
            return
        task.cancel()
        try:
            await task
        except (Exception, CancelledError):
            pass

    @staticmethod
    async def handler(
        server: Outbound, reader: StreamReader, writer: StreamWriter
    ) -> None:
        """Method used to process new connections."""
        task = current_task()
        if task:
            server.tasks.add(task)

        try:
            with tracer.start_as_current_span(
                "outbound_handle_connection",
                attributes={
                    "net.peer.name": server.host,
                    "net.peer.port": server.port,
                },
            ):
                _safe_connection_metric(
                    active_connections_counter,
                    1,
                    attributes={"type": "outbound"},
                )
                try:
                    async with Session(reader, writer) as session:
                        await _setup_session(session, server)
                        await server.app(session)
                finally:
                    _safe_connection_metric(
                        active_connections_counter,
                        -1,
                        attributes={"type": "outbound"},
                    )
        finally:
            if task:
                server.tasks.discard(task)
