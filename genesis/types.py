from typing import Protocol, Any, runtime_checkable


@runtime_checkable
class WatcherProtocol(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def join(self) -> None: ...
    def schedule(
        self, event_handler: Any, path: str, recursive: bool = False
    ) -> Any: ...


from asyncio import StreamReader, StreamWriter
from typing import Awaitable, TYPE_CHECKING

if TYPE_CHECKING:
    from genesis.outbound import Session


class OutboundHandler(Protocol):
    def __call__(self, session: "Session") -> Awaitable[None]: ...
