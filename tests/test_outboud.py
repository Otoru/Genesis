import pytest
from asyncio import create_task, Event
from typing import Awaitable

from genesis import Outbound, Session


@pytest.mark.skip("on development")
async def test_freeswitch_dial_to_outbound_application(host, port, dialplan):
    async def handler(session: Session) -> Awaitable[None]:
        ...

    address = [host(), port()]
    application = Outbound(*address, handler)
    dialplan.connect(*address)

    await application.stop()
