import logging

from rich.logging import RichHandler

logger = logging.getLogger("genesis")

handler = RichHandler(
    show_time=False,
    rich_tracebacks=True,
    tracebacks_show_locals=True,
    markup=True,
    show_path=False,
)

handler.setFormatter(logging.Formatter("%(message)s"))
logger.setLevel(logging.DEBUG)
logger.propagate = False
