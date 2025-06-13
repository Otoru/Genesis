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
from genesis.exceptions import OperationInterruptedException, OriginateError
from genesis.logger import logger


b_leg_destination = os.environ.get("GENESIS_B_LEG", "sofia/gateway/sip1/50104")  # Modify as needed


async def handler(session: Session):
    """Handler for the incoming session"""
    try:
        channel_a = session.channel_a

        # A-Leg is the incoming call
        # Answer the incoming call
        await channel_a.answer()
        logger.info(f"Incoming call (A-Leg) with UUID {channel_a.uuid} answered")

        # Play welcome message
        await channel_a.playback('ivr/ivr-welcome_to_freeswitch', block=True)
        logger.info("Welcome message played to A-Leg")

        # While wait music is playing: Originate B-Leg
        try:
            logger.info(f"Attempting to originate B-Leg to {b_leg_destination}")
            channel_b = await session.originate(
                destination=b_leg_destination,
                variables={
                    "origination_caller_id_name": "Forwarded",
                    "origination_caller_id_number": channel_a.variables.get("Caller-Caller-ID-Number", "1000")
                },
                timeout=10
            )
            
            # Check explicitly if the channel was successfully created
            if channel_b is None or channel_b.is_gone:
                raise RuntimeError("B-Leg channel was not properly created or was destroyed immediately")
        except OriginateError as e:
            logger.error(f"Error originating B-Leg to '{e.destination}': {e}", exc_info=True)
            logger.debug(f"Originate variables: {e.variables}")
            # Inform A-Leg about the error
            await channel_a.playback('ivr/ivr-call_cannot_be_completed_as_dialed', block=True)
            await channel_a.hangup()

        # Wait for B-Leg to answer
        start_time = asyncio.get_event_loop().time()
        while channel_b.call_state != CallState.ACTIVE:
            if channel_b.is_gone or channel_b.call_state == CallState.HANGUP:
                raise RuntimeError(f"B-Leg channel hung up before it was answered")

            # Check timeout after 30 seconds
            if asyncio.get_event_loop().time() - start_time > 30:
                await channel_b.hangup()
                raise TimeoutError("Timeout waiting for B-Leg to answer")

            await asyncio.sleep(0.1)

        logger.info(f"B-Leg channel with UUID {channel_b.uuid} answered")

        # Welcome message for B-Leg
        await channel_b.playback('ivr/ivr-welcome_to_freeswitch', block=True)
        logger.info("Welcome message played to B-Leg")

        # Bridge A-Leg and B-Leg together
        logger.info(f"Connecting A-Leg ({channel_a.uuid}) with B-Leg ({channel_b.uuid})")

        # Set these so our channels will not hangup after the bridge, and we can reconnect them later
        await channel_a.set_variable("hangup_after_bridge", "false")
        await channel_b.set_variable("hangup_after_bridge", "false")

        await channel_a.bridge(channel_b, block=False)

        logger.info("Channels are bridged. Starting 10-second countdown before unbridging...")
        for i in range(10, 0, -1):
            logger.info(f"Unbridging in {i} seconds...")
            await asyncio.sleep(1) # Wait for 1 second if playback fails, to keep timing somewhat

        logger.info("10 seconds passed. Unbridging channels...")
        await channel_a.unbridge(park=True)
        logger.info("Channels unbridged and parked")

        logger.info("Playing different audio files on each channel")
        playback_a = await channel_a.playback('ivr/ivr-you_are_number_one', block=False)
        playback_b = await channel_b.playback('ivr/ivr-oh_whatever', block=False)

        while not (playback_a.is_completed and playback_b.is_completed):
            logger.info("Waiting for both playbacks to complete...")
            await asyncio.sleep(1)

        logger.info(f"Both playbacks completed.")

        logger.info(f"Reconnecting channel_a ({channel_a.uuid}) with channel_b ({channel_b.uuid})")
        await channel_a.bridge(channel_b, block=False)

        logger.info("Channels re-bridged")

        while not (channel_a.is_gone or channel_b.is_gone):
            logger.info("Waiting for one of the channels to disconnect...")
            await asyncio.sleep(1.0)
        logger.info(f"Bridge has ended")
        
    except OperationInterruptedException as e:
        logger.warning(
            f"Operation on channel {e.channel_uuid} (App-UUID: {e.event_uuid}) was interrupted: {e}"
        )
    except Exception as e:
        logger.error(f"Unexpected error in handler for channel {session.channel_a.uuid}: {e}", exc_info=True)


async def on_dtmf_a_leg(self, event):
    logger.info("User on channel A pressed DTMF: %s", event["DTMF-Digit"])


app = Outbound(host="127.0.0.1", port=5000, handler=handler)

if __name__ == "__main__":
    try:
        asyncio.run(app.start())
    except KeyboardInterrupt:
        logger.info("Application shutting down...")
