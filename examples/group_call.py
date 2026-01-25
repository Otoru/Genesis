import asyncio
import os

from genesis import Inbound, Channel
from genesis.types import ChannelState
from genesis.exceptions import TimeoutError

FS_HOST = os.getenv("FS_HOST", "127.0.0.1")
FS_PORT = int(os.getenv("FS_PORT", "8021"))
FS_PASSWORD = os.getenv("FS_PASSWORD", "ClueCon")


async def originate_multiple_simultaneous(
    client: Inbound,
    caller: str,
    callees: list[str],
    timeout: float = 30.0,
) -> tuple[Channel, Channel]:
    """Originate calls simultaneously and return first to answer."""
    # Originate the caller
    caller_ch = await Channel.create(client, caller)
    await caller_ch.wait(ChannelState.EXECUTE, timeout=timeout)

    # Originate the callees
    channels = []
    for callee in callees:
        ch = await Channel.create(client, callee)
        channels.append(ch)

    # Create tasks to wait for the callees to answer
    tasks = {}
    for ch in channels:
        task = asyncio.create_task(ch.wait(ChannelState.EXECUTE, timeout=timeout))
        tasks[task] = ch

    try:
        # Wait for the first callee to answer
        done, pending = await asyncio.wait(
            tasks.keys(), return_when=asyncio.FIRST_COMPLETED, timeout=timeout
        )

        # If no callee answered, raise an error
        if not done:
            raise TimeoutError("No destination answered")

        # Get the first callee to answer
        answered_task = done.pop()
        answered = tasks[answered_task]
        
        # Wait for the task to complete (may raise if it failed)
        await answered_task

        # All pending callee tasks are about to be cancelled and the rest of the channels will be hung up.
        for task in pending:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, TimeoutError):
                pass

        for ch in channels:
            if ch == answered:
                continue
            if ch.state >= ChannelState.HANGUP:
                continue
            try:
                await ch.hangup("NORMAL_CLEARING")
            except:
                pass

        return caller_ch, answered


    except Exception:
        for task in tasks:
            task.cancel()
        for ch in channels:
            if ch.state >= ChannelState.HANGUP:
                continue
            try:
                await ch.hangup("NORMAL_CLEARING")
            except:
                pass
        raise


async def main() -> None:
    caller = "user/1000"
    callees = ["user/1001", "user/1002", "user/1003"]

    async with Inbound(FS_HOST, FS_PORT, FS_PASSWORD) as client:
        # Originate the calls
        caller_ch, callee_ch = await originate_multiple_simultaneous(client, caller, callees)

        await caller_ch.bridge(callee_ch)

        # Do something with the call
        await asyncio.sleep(5)

        # Hang up the call
        await callee_ch.hangup()
        await caller_ch.hangup()


if __name__ == "__main__":
    asyncio.run(main())
