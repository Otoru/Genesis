"""
Queue example.

One extension calls another via the app: the caller is held (music or message)
until a queue slot is free, then we bridge them to the callee. Only one
bridge at a time so you keep control (e.g. one agent per queue).
"""

import asyncio
import os

from genesis import Outbound, Session, Queue, Channel
from genesis.types import ChannelState

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "9696"))
CALLEE = "user/1001"
# Sound to play while caller waits. Default: music on hold (project Docker has MOH).
# Alternative: ivr/8000/ivr-one_moment_please.wav (Callie voice)
HOLD_SOUND = os.getenv("HOLD_SOUND", "local_stream://moh")

queue = Queue()  # in-memory by default


async def handler(session: Session) -> None:
    if session.channel is None:
        return
    await session.channel.answer()

    # Start hold sound (block=False so it plays while we wait for a slot)
    await session.channel.playback(HOLD_SOUND, block=False)

    async with queue.slot("support"):
        callee = await Channel.create(session, CALLEE)
        await callee.wait(ChannelState.EXECUTE, timeout=30.0)
        await session.channel.bridge(callee)


async def main() -> None:
    server = Outbound(handler=handler, host=HOST, port=PORT)
    await server.start()


if __name__ == "__main__":
    asyncio.run(main())
