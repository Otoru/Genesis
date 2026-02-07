"""
Genesis inbound
---------------
ESL implementation used for incoming connections on freeswitch.
"""

from __future__ import annotations

from asyncio import TimeoutError, open_connection, wait_for

from opentelemetry import metrics, trace

from genesis.exceptions import AuthenticationError, ConnectionTimeoutError
from genesis.observability import logger
from genesis.protocol import Protocol

tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)

active_connections_counter = meter.create_up_down_counter(
    "genesis.connections.active",
    description="Number of active connections",
    unit="1",
)
connection_errors_counter = meter.create_counter(
    "genesis.connections.errors",
    description="Number of connection errors",
    unit="1",
)


def _safe_connection_metric(counter: object, *args: object, **kwargs: object) -> None:
    """Add to a counter, swallowing OTel/metrics errors."""
    try:
        getattr(counter, "add")(*args, **kwargs)
    except Exception:
        pass


class Inbound(Protocol):
    """
    Inbound class
    -------------

    Given a valid set of information, establish a connection to a freeswitch server.

    Attributes:
    - host: required
        IP address associated with the connection destination server.
    - port: required
        Network port where ESL module is listening.
    - password: required
        Password used for authentication on freeswitch.
    - timeout: optional
        Maximum time we wait to initiate a connection.
    """

    def __init__(self, host: str, port: int, password: str, timeout: int = 5) -> None:
        super().__init__()
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout

    async def __aenter__(self) -> Inbound:
        """Interface used to implement a context manager."""
        await self.start()
        return self

    async def __aexit__(self, *args: object, **kwargs: object) -> None:
        """Interface used to implement a context manager."""
        await self.stop()

    async def _connect(self) -> None:
        """Open TCP connection to host:port; sets self.reader and self.writer."""
        promise = open_connection(self.host, self.port)
        self.reader, self.writer = await wait_for(promise, self.timeout)

    async def authenticate(self) -> None:
        """Authenticates to the freeswitch server. Raises an exception on failure."""
        await self.authentication_event.wait()
        logger.debug("Send command to authenticate inbound ESL connection.")
        response = await self.send(f"auth {self.password}")

        if response["Reply-Text"] != "+OK accepted":
            logger.debug("Freeswitch said the passed password is incorrect.")
            _safe_connection_metric(
                connection_errors_counter,
                1,
                attributes={"error": "authentication_failed", "type": "inbound"},
            )
            raise AuthenticationError("Invalid password")

    async def start(self) -> None:
        """Initiates an authenticated connection to a freeswitch server."""
        try:
            try:
                with tracer.start_as_current_span(
                    "inbound_connect",
                    attributes={
                        "net.peer.name": self.host,
                        "net.peer.port": self.port,
                    },
                ):
                    await self._connect()
            except Exception as e:
                if "tracer" not in str(e).lower():
                    raise
                await self._connect()
        except TimeoutError:
            logger.debug("A timeout occurred when trying to connect to the freeswitch.")
            _safe_connection_metric(
                connection_errors_counter,
                1,
                attributes={"error": "timeout", "type": "inbound"},
            )
            raise ConnectionTimeoutError() from None

        await super().start()
        try:
            _safe_connection_metric(
                active_connections_counter, 1, attributes={"type": "inbound"}
            )
            await self.authenticate()
        except Exception:
            await self.stop()
            raise

    async def stop(self) -> None:
        """Terminates the connection."""
        await super().stop()
        _safe_connection_metric(
            active_connections_counter, -1, attributes={"type": "inbound"}
        )
