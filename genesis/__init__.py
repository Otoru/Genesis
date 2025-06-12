import importlib.metadata

try:
    __version__ = importlib.metadata.version(__package__ or __name__)
except importlib.metadata.PackageNotFoundError:  # pragma: no cover - fallback for local usage
    __version__ = "0.0.0"

from .consumer import Consumer, filtrate
from .outbound import Outbound, Session, ESLEvent
from .inbound import Inbound

__all__ = ["Inbound", "Consumer", "filtrate", "Outbound", "Session", "ESLEvent"]
