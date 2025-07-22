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
from genesis import Outbound, Session, CallState, ChannelState
from genesis.exceptions import OperationInterruptedException
from genesis.logger import logger


b_leg = os.environ.get("GENESIS_B_LEG", "sofia/gateway/sip1/50104")  # Modify as needed


async def handler(session: Session):
    session.channel_a.on("DTMF", on_dtmf_a_leg)
    try:
        await session.channel_a.answer()
        logger.info(f"Channel {session.channel_a.uuid} answered.")

        await session.channel_a.playback('ivr/ivr-welcome_to_freeswitch', block=True)
        logger.info(f"Channel {session.channel_a.uuid} finished playback: ivr-welcome_to_freeswitch")

        # When target is a string (dialstring), bridge returns a tuple of (result, channel)
        bridge_result, channel_b = await session.channel_a.bridge(b_leg, block=False)

        while channel_b.call_state == CallState.DOWN:
            await asyncio.sleep(0.1)  # Give FreeSWITCH time to create the channel and process the call state change

        # Set these so our b-leg channel will not hangup after the a-leg hangup
        await channel_b.set_variable("hangup_after_bridge", "false")
        await channel_b.set_variable("park_after_bridge", "true")


        while not bridge_result:
            # Alternative checks:
            # while not bridge_result.is_completed:
            # while bridge_result.is_completed is False:
            # while channel.state <= CallState.HANGUP:
            logger.info(f"#Channel {channel_b.uuid} is active. {channel_b.state.name}")
            logger.info("Hangup any channel to continue.")
            await asyncio.sleep(1.0)

        # Find which channel is still active after the bridge, so we can do the playback on it
        if channel_b and not channel_b.is_gone:
            active_channel = channel_b
            logger.info(f"B-leg channel {channel_b.uuid} is still active")
        else:
            active_channel = session.channel_a
            logger.info(f"A-leg channel {session.channel_a.uuid} is still active")

        playback = await active_channel.playback('ivr/ivr-you_are_number_one', block=False)
        while not playback.is_completed:
            logger.info("We wait for completion of playback in a loop.")
            await asyncio.sleep(1.0)

        logger.info("Lets do another playback, but this time we don't wait in a loop, we just wait with 'await playback'")
        playback2 = await active_channel.playback('ivr/ivr-nobody_got_time_for_that', block=False)
        await playback2

        logger.info(f"Channel {active_channel.uuid} finished playback: ivr-you_are_number_one")

        await active_channel.playback('ivr/ivr-oh_whatever', block=True)

        await active_channel.hangup()
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
