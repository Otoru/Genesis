---
title: IVR
weight: 20
parent: Examples
---

Simple IVR (Interactive Voice Response) system using Outbound mode with DTMF interaction.

## Example Code

```python {filename="examples/ivr.py" base_url="https://github.com/Otoru/Genesis/blob/main"}
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
```

## How It Works

This example demonstrates Outbound Socket mode, where FreeSWITCH connects to your application when a call matches a dialplan entry. The IVR system:

1. Answers incoming calls
2. Plays a welcome message with menu options
3. Listens for DTMF (touch-tone) input
4. Responds based on the selected option
5. Handles timeouts and invalid inputs

## Running the Example

{{% steps %}}

### 1. Start FreeSWITCH

Make sure FreeSWITCH is running in Docker (see [Examples environment]({{< relref "../Examples/_index.md" >}})).

### 2. Start the IVR Server

In a terminal, run the IVR example:

```bash
python examples/ivr.py
```

The server will start listening on `0.0.0.0:9696` and wait for FreeSWITCH to connect.

### 3. Make a Test Call

In another terminal, use FreeSWITCH CLI to originate a call to the IVR:

```bash
docker exec -it genesis-freeswitch fs_cli -x "originate user/1000 9999"
```

This command:
- Creates a call from user `1000` (a test user configured in the Docker environment)
- Routes it to number `9999` (configured in the dialplan to connect to your outbound socket)

### 4. Interact with the IVR

Once the call is connected:
- You'll hear the welcome message
- Press `1`, `2`, or `3` to select an option
- The IVR will respond to your selection

### 5. View Logs

To see what's happening in FreeSWITCH:

```bash
docker exec -it genesis-freeswitch fs_cli -x "show channels"
docker logs genesis-freeswitch -f
```

{{% /steps %}}

## Testing with a SIP Client

You can also test using a SIP client (like Linphone, Zoiper, or X-Lite):

1. Configure your SIP client to connect to FreeSWITCH:
   - **Server:** `127.0.0.1:5060`
   - **Username:** `1000` or `1001`
   - **Password:** `1000` or `1001` (same as username)
   - **Domain:** `127.0.0.1`

2. Register the SIP client

3. Make a call to `9999`

4. The call will be routed to your IVR application

## Dialplan Configuration

The Docker environment includes a dialplan entry that routes calls to `9999` to your outbound socket:

```xml
<extension name="outbound_socket_test">
  <condition field="destination_number" expression="^(9999)$">
    <action application="socket" data="127.0.0.1:9696 async full"/>
  </condition>
</extension>
```

This means any call to `9999` will trigger FreeSWITCH to connect to your application at `127.0.0.1:9696`.
