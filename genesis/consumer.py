"""
Consumer Module
---------------
Simple abstraction used to put some syntactic sugar into freeswitch event consumption.
"""

import asyncio
import functools
import re
from typing import Any, Callable, Optional

from genesis.inbound import Inbound
from genesis.observability import logger, observability


async def _invoke_maybe_coro(func: Callable[..., Any], message: Any) -> Any:
    """Invoke handler and await if it returns a coroutine."""
    result = func(message)
    if asyncio.iscoroutine(result):
        return await result
    return result


def _content_matches(content: Any, value: Optional[str], regex: bool) -> bool:
    """True if value is None, or content matches value (literal or regex)."""
    if value is None:
        return True
    if content is None:
        return False
    text = content[0] if isinstance(content, list) else str(content)
    if not regex:
        return text == value
    return bool(re.match(value, text))


def filtrate(
    key: str, value: Optional[str] = None, regex: bool = False
) -> Callable[..., Any]:
    """
    Method that allows to filter the events according to a set 'key', 'value'.

    Parameters
    ----------
    - key: required
        Key to be searched in the event.
    - value: optional
        Value needed in the last key.
    - regex: optional
        Tells whether 'value' is a regular expression.
    """

    def decorator(function: Any) -> Any:
        @functools.wraps(function)
        async def wrapper(message: Any) -> Any:
            if not isinstance(message, dict) or key not in message:
                return None
            content = message[key]
            if not _content_matches(content, value, regex):
                return None
            return await _invoke_maybe_coro(function, message)

        return wrapper

    return decorator


class Consumer:
    """
    Consumer class
    --------------
    Abstraction used to create valid event consumers.

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

    host: str
    port: int
    password: str
    protocol: Inbound

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8021,
        password: str = "ClueCon",
        timeout: int = 5,
    ) -> None:
        self.host = host
        self.port = port
        self.password = password
        self.protocol = Inbound(self.host, self.port, self.password, timeout)

    def handle(self, event: str) -> Callable[..., Any]:
        """Decorator that allows the registration of new handlers.

        Parameters
        ----------
        - event: required
            Name of the event to be parsed.
        """

        def decorator(function: Callable[..., Any]) -> Callable[..., Any]:
            self.protocol.on(event, function)
            return function

        return decorator

    async def wait(self) -> None:
        """Block until the protocol disconnects."""
        while self.protocol.is_connected:
            logger.debug("Wait to receive new events...")
            await asyncio.sleep(1)

    def _filter_command(self, event: str) -> str:
        """Build filter command for an event name (Event-Name vs Event-Subclass)."""
        if event.isupper():
            return f"filter Event-Name {event}"
        return f"filter Event-Subclass {event}"

    async def start(self) -> None:
        """Method called to request the freeswitch to start sending us the appropriate events."""
        try:
            self.protocol.on("HEARTBEAT", observability.record_heartbeat)

            async with self.protocol as protocol:
                logger.debug("Asking freeswitch to send us all events.")
                await protocol.send("events plain ALL")

                for event in protocol.handlers.keys():
                    logger.debug(
                        "Requesting freeswitch to filter events of type '%s'.",
                        event,
                    )
                    await protocol.send(self._filter_command(event))

                await self.wait()

        except Exception:
            await self.stop()
            raise

    async def stop(self) -> None:
        await self.protocol.stop()
