"""
Your dialplan should have an entry similar to this:

<extension name="out socket">
   <condition>
      <action application="socket" data="127.0.0.1:5000 async full"/>
   </condition>
</extension>
"""

import os
import asyncio
from genesis import Outbound, Session, Channel
from genesis.exceptions import OperationInterruptedException
from genesis.logger import logger

os.environ["GENESIS_LOG_LEVEL"] = "DEBUG"

# Todo: originate
# Todo: update tests
# Todo: Update cli tools


async def handler(session: Session):
    session.channel_a.on("DTMF", on_dtmf_a_leg)
    try:
        await session.channel_a.answer()
        logger.info(f"Channel {session.channel_a} answered.")

        await session.channel_a.playback('ivr/ivr-welcome_to_freeswitch', block=True)
        logger.info(f"Channel {session.channel_a} finished playback: ivr-welcome_to_freeswitch")

        await session.channel_a.playback('ivr/ivr-you_are_number_one', block=True)
        logger.info(f"Channel {session.channel_a} finished playback: ivr-you_are_number_one")

    except OperationInterruptedException as e:
        logger.warning(
            f"Playback on channel {e.channel_uuid} (App-UUID: {e.event_uuid}) was interrupted: {e}"
        )
    except Exception as e:
        logger.error(f"An unexpected error occurred in handler for channel {session.channel_a.uuid}: {e}", exc_info=True)
    finally:
        if session.channel_a and not session.channel_a.is_gone:
            logger.info(f"Channel {session.channel_a.uuid} ensuring hangup.")
            await session.channel_a.hangup()
        else:
            logger.info(f"Channel {session.channel_a.uuid if session.channel_a else 'N/A'} was already gone or not set, skipping final hangup.")

async def on_dtmf_a_leg(self, event):
    logger.info("User on channel A pressed DTMF: %s", event["DTMF-Digit"])


app = Outbound(host="127.0.0.1", port=5000, handler=handler)

if __name__ == "__main__":
    try:
        asyncio.run(app.start())
    except KeyboardInterrupt:
        logger.info("Application shutting down...")
