import asyncio
import os
import logging

from genesis import Outbound, Session
from genesis.exceptions import TimeoutError

logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "9696"))


async def play(channel, filename: str) -> None:
    """Helper function to play a sound file."""
    await channel.playback(f"ivr/8000/{filename}")


async def handler(session: Session) -> None:
    logger.info(f"New call received - Channel UUID: {session.channel.uuid}")

    @session.channel.onDTMF()
    async def on_dtmf(digit: str) -> None:
        logger.info(f"DTMF pressed: {digit}")
        await session.channel.say(digit, lang="en", kind="NUMBER")

    await session.channel.answer()

    # Welcome message
    await play(session.channel, "ivr-welcome_to_freeswitch.wav")

    # Wait 30 seconds then hangup
    await asyncio.sleep(30)
    await session.channel.hangup()


async def main() -> None:
    logger.info(f"Starting IVR server on {HOST}:{PORT}")
    server = Outbound(handler=handler, host=HOST, port=PORT)

    logger.info("IVR server is ready and waiting for connections...")
    await server.start()


if __name__ == "__main__":
    asyncio.run(main())
