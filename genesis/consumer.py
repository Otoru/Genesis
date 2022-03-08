"""
Consumer Module
---------------

Simple abstraction used to put some syntactic sugar into freeswitch event consumption.
"""
from typing import Optional, Awaitable, NoReturn, Callable
from asyncio import sleep, Task, create_task, sleep
import functools
import logging
import re

from .inbound import Inbound


def filtrate(key: str, value: str = None, regex: bool = False):
    """
    Method that allows to filter the events accordingto a set 'key', 'value'.
    Parameters
    ----------
    - key: required
        Key to be searched in the event.
    - value: optional
        Value needed in the last key.
    - regex: optional
        Tells whether 'value' is a regular expression.
    """

    def decorator(function: Awaitable):
        @functools.wraps(function)
        async def wrapper(message):
            if isinstance(message, dict):
                if key in message:
                    content = message[key]

                    if value is None:
                        return function(message)

                    if not regex and content == value:
                        return function(message)

                    if regex and re.match(value, content):
                        return function(message)

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

    def __init__(self, host: str, port: int, password: str, timeout: int = 5) -> None:
        self.protocol: Inbound = Inbound(host, port, password, timeout)

    def handle(self, event: str) -> Callable:
        """Decorator that allows the registration of new handlers.

        Parameters
        ----------
        - event: required
            Name of the event to be parsed.
        """

        def decorator(function: Awaitable):
            self.protocol.on(event, function)

            @functools.wraps(function)
            async def wrapper(*args, **kwargs):
                return await function(*args, **kwargs)

            return wrapper

        return decorator

    async def start(self) -> Awaitable[NoReturn]:
        """Method called to request the freeswitch to start sending us the appropriate events."""
        try:
            async with self.protocol as protocol:
                logging.debug("Asking freeswitch to send us all events.")
                await protocol.send("events plain ALL")

                for event in protocol.handlers.keys():
                    logging.debug(
                        f"Requesting freeswitch to filter events of type '{event}'."
                    )

                    if event.isupper():
                        logging.debug(
                            f"Send command to filtrate events with name: '{event}'."
                        )
                        await protocol.send(f"filter Event-Name {event}")
                    else:
                        logging.debug(
                            f"Send command to filtrate events with subclass: '{event}'."
                        )
                        await protocol.send(f"filter Event-Subclass {event}")

                while self.protocol.is_connected:
                    await sleep(1)

        except:
            await self.stop()
            raise

    async def stop(self) -> Awaitable[NoReturn]:
        return await self.protocol.stop()
