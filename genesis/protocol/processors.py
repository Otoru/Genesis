"""
Event processors (adapters)
----------------------------

Processors run for each event before routing. Use them to add protocol-level
behavior (auth, command reply, disconnect) or to plug in use-case adapters.
"""

from typing import TYPE_CHECKING, List, Callable, Awaitable, Union

from genesis.protocol.parser import ESLEvent
from genesis.protocol.lifecycle import (
    channel_lifecycle_processor,
    custom_subclass_processor,
)

if TYPE_CHECKING:
    from genesis.protocol.base import Protocol

# Type for a processor: sync or async (protocol, event) -> None
EventProcessor = Callable[["Protocol", ESLEvent], Union[None, Awaitable[None]]]


def auth_request_processor(protocol: "Protocol", event: ESLEvent) -> None:
    """Signal that auth/request was received (e.g. for Inbound authenticate())."""
    if event.get("Content-Type") == "auth/request":
        protocol.authentication_event.set()


async def command_reply_processor(protocol: "Protocol", event: ESLEvent) -> None:
    """Enqueue command/reply so send() can return the response."""
    if event.get("Content-Type") == "command/reply":
        await protocol.commands.put(event)


async def api_response_processor(protocol: "Protocol", event: ESLEvent) -> None:
    """Enqueue api/response so send() can return the response."""
    if event.get("Content-Type") == "api/response":
        await protocol.commands.put(event)


async def disconnect_processor(protocol: "Protocol", event: ESLEvent) -> None:
    """Stop connection on rude-rejection or disconnect-notice unless lingering."""
    if event.get("Content-Type") in [
        "text/rude-rejection",
        "text/disconnect-notice",
    ] and not (
        "Content-Disposition" in event and event.get("Content-Disposition") == "linger"
    ):
        await protocol.stop()


def default_processors() -> List[EventProcessor]:
    """Return the default list of event processors (order matters).

    Lifecycle/CUSTOM processors run last so they never interfere with the
    core protocol adapters (auth, command reply, disconnect). They only emit
    telemetry — they do not consume events routed to user handlers.
    """
    return [
        auth_request_processor,
        command_reply_processor,
        api_response_processor,
        disconnect_processor,
        channel_lifecycle_processor,
        custom_subclass_processor,
    ]
