"""
Genesis Session (OOP)
----------------------

This module defines the Session class, which abstracts a session
established between the application and FreeSWITCH in an outbound context.
This is the enhanced OOP version supporting multi-channel management.
"""

from __future__ import annotations

from asyncio import StreamReader, StreamWriter, Queue, Event
from functools import partial
from pprint import pformat
from typing import Any, Callable, Dict, Literal, Optional, Tuple, Union
from uuid import uuid4

from genesis.exceptions import OperationInterruptedException, SessionGoneAway
from genesis.logger import logger
from genesis.parser import ESLEvent
from genesis.protocol import Protocol

from genesis.channels.bgapi import BackgroundAPI
from genesis.channels.channel import Channel
from genesis.channels.results import BackgroundJobResult, CommandResult


class Session(Protocol):
    """
    Session class (OOP version)
    ---------------------------

    Abstracts a session established between the application and FreeSWITCH.
    This version supports multi-channel management via the Channel abstraction.

    This session has nothing to do with the session in the FreeSWITCH context.

    Attributes:
        reader: StreamReader used to read incoming information.
        writer: StreamWriter used to send information to FreeSWITCH.
        context: The initial context variables received from FreeSWITCH upon connection.
        channels: A dictionary of channels associated with this session, keyed by UUID.
        channel_a: The channel that initiated this session (A-leg in outbound).
        fifo: A queue used internally for blocking commands.
        bgapi: BackgroundAPI instance for background command execution.
    """

    def __init__(
        self, reader: StreamReader, writer: StreamWriter, myevents: bool = False
    ) -> None:
        """
        Initialize the session with the provided StreamReader and StreamWriter.

        Args:
            reader: StreamReader used to read incoming information.
            writer: StreamWriter used to send information to FreeSWITCH.
            myevents: If true, ask FreeSWITCH to send us all events for this session.
        """
        super().__init__()
        self.context: Union[Dict[str, str], ESLEvent] = dict()
        self.reader = reader
        self.writer = writer
        self.fifo: Queue[ESLEvent] = Queue()
        self.channels: Dict[str, Channel] = {}
        self.myevents: bool = myevents
        self.linger: bool = True
        self.channel_a: Optional[Channel] = None
        self.bgapi = BackgroundAPI(self)

        # Register the dispatcher for all events
        self.on("*", self._dispatch_event_to_channels)

    async def __aenter__(self) -> "Session":
        await self.start()
        return self

    async def __aexit__(self, *args: Any, **kwargs: Any) -> None:
        await self.stop()

    async def _dispatch_event_to_channels(self, event: ESLEvent) -> None:
        """
        Dispatches incoming events to the appropriate managed Channel.
        If a CHANNEL_CREATE or CHANNEL_DATA event is received, a Channel is created.
        """
        target_channel_uuid: Optional[str] = event.get("Channel-Unique-ID")
        if not target_channel_uuid:
            target_channel_uuid = event.get("Unique-ID")

        logger.trace(
            f"Session._dispatch: Event Target UUID: {target_channel_uuid}, "
            f"Event-Name: {event.get('Event-Name')}, "
            f"Content-Type: {event.get('Content-Type')}. "
            f"Current self.channel_a: "
            f"{self.channel_a.uuid if self.channel_a else 'None'}"
        )

        if not target_channel_uuid:
            event_name_for_log = event.get("Event-Name") or event.get("Content-Type")
            logger.trace(
                f"Session._dispatch: Received non-channel specific event or "
                f"command reply: {event_name_for_log}. Returning."
            )
            return

        channel_instance: Optional[Channel] = self.channels.get(target_channel_uuid)

        if not channel_instance:
            # Event for an unknown channel

            # For Outbound ESL, the initial 'connect' reply (a command/reply event)
            # should establish channel_a. It has channel vars but isn't a
            # 'CHANNEL_CREATE' or 'CHANNEL_DATA' event by Event-Name.
            is_initial_connect_reply = (
                self.channel_a is None
                and event.get("Content-Type") == "command/reply"
                and "Channel-State" in event
                and target_channel_uuid is not None
            )
            logger.trace(
                f"Session._dispatch: Calculated is_initial_connect_reply = "
                f"{is_initial_connect_reply} "
                f"(self.channel_a is None: {self.channel_a is None}, "
                f"Content-Type is command/reply: "
                f"{event.get('Content-Type') == 'command/reply'}, "
                f"Channel-State in event: {'Channel-State' in event}, "
                f"target_channel_uuid is not None: {target_channel_uuid is not None})"
            )

            if (
                event.get("Event-Name") in ["CHANNEL_CREATE", "CHANNEL_DATA"]
                or is_initial_connect_reply
            ):
                logger.info(
                    f"Session._dispatch: CREATING new channel instance for UUID "
                    f"{target_channel_uuid} "
                    f"(Type: {event.get('Event-Name') or event.get('Content-Type')})."
                )

                channel_instance = Channel(uuid=target_channel_uuid, session=self)
                self.channels[target_channel_uuid] = channel_instance

                if not self.myevents:
                    try:
                        # Defer filtering for the initial A-leg
                        if not is_initial_connect_reply:
                            logger.debug(
                                f"Session._dispatch: Adding filter for new channel "
                                f"{target_channel_uuid} (myevents=False)."
                            )
                            await self.send(f"filter Unique-ID {target_channel_uuid}")
                    except Exception as e:
                        logger.error(
                            f"Session._dispatch: Failed to send filter command for "
                            f"new channel {target_channel_uuid}: {e}"
                        )

                if self.channel_a is None:
                    self.channel_a = channel_instance
                    logger.info(
                        f"Session._dispatch: Channel {target_channel_uuid} assigned "
                        f"as A-leg. self.channel_a is now "
                        f"{self.channel_a.uuid if self.channel_a else 'None'}."
                    )
                else:
                    logger.info(
                        f"Session._dispatch: Channel {target_channel_uuid} identified "
                        f"as B-leg (or subsequent leg). self.channel_a "
                        f"({self.channel_a.uuid if self.channel_a else 'None'}) "
                        f"already set."
                    )
            else:
                # Event for an unmanaged UUID that is not a designated creation trigger
                event_description = event.get(
                    "Event-Name", event.get("Content-Type", "Unknown Event")
                )
                logger.debug(
                    f"Session._dispatch: Received event '{event_description}' for "
                    f"unmanaged channel UUID '{target_channel_uuid}'. "
                    f"Not a designated creation trigger. Ignoring."
                )
                logger.warning(
                    f"Session._dispatch: Received event was not a creation trigger "
                    f"for unknown UUID. channel_instance is {channel_instance}. "
                    f"self.channel_a is "
                    f"{self.channel_a.uuid if self.channel_a else 'None'}."
                )
                return

        if channel_instance:  # Known channel
            await channel_instance._handle_event(event)
            logger.trace(
                f"Session._dispatch: Dispatched event "
                f"{event.get('Event-Name', 'N/A')} to channel {target_channel_uuid}."
            )

            # Handle channel destruction after it has processed its DESTROY event
            if event.get("Event-Name") == "CHANNEL_DESTROY":
                logger.info(
                    f"Session._dispatch: Channel {target_channel_uuid} destroyed. "
                    "Removing from session."
                )
                del self.channels[target_channel_uuid]
                if self.channel_a and self.channel_a.uuid == target_channel_uuid:
                    logger.info(
                        f"Session._dispatch: Channel A ({target_channel_uuid}) "
                        "was destroyed."
                    )
                    self.channel_a = None

    async def _awaitable_complete_command(
        self, event_uuid: str, channel_uuid: Optional[str], result: CommandResult
    ) -> Event:
        """
        Create an event that will be set when a command completes.

        If channel_uuid is provided, it also listens for hangup events on that
        channel and puts an OperationInterruptedException if hangup occurs first.

        Args:
            event_uuid: UUID to track the specific command execution
            channel_uuid: UUID of the channel the command is acting upon.
            result: CommandResult object to update when the command completes

        Returns:
            Event that will be set when command completes
        """
        semaphore = Event()

        async def _complete_handler(session: Session, event: ESLEvent) -> None:
            logger.debug(
                f"Received CHANNEL_EXECUTE_COMPLETE event for App-UUID {event_uuid}"
            )
            logger.trace(f"Event details: {pformat(event)}")
            if "Application-UUID" in event and event["Application-UUID"] == event_uuid:
                result.set_complete(event)
                semaphore.set()
                # Clean up both handlers
                self.remove("CHANNEL_EXECUTE_COMPLETE", bound_complete_handler)
                if channel_uuid:
                    self.remove("CHANNEL_HANGUP", bound_hangup_handler)
                    self.remove("CHANNEL_DESTROY", bound_hangup_handler)

        async def _hangup_handler(session: Session, event: ESLEvent) -> None:
            # Check if the hangup event is for the channel we are monitoring
            if event.get("Unique-ID") == channel_uuid:
                logger.warning(
                    f"Operation with App-UUID {event_uuid} on channel {channel_uuid} "
                    f"interrupted by {event.get('Event-Name')}."
                )
                exception_to_put = OperationInterruptedException(
                    f"Operation with App-UUID {event_uuid} on channel {channel_uuid} "
                    f"interrupted by {event.get('Event-Name')}",
                    event_uuid=event_uuid,
                    channel_uuid=channel_uuid,
                )
                result.set_exception(exception_to_put)
                semaphore.set()
                # Clean up both handlers
                self.remove("CHANNEL_EXECUTE_COMPLETE", bound_complete_handler)
                if channel_uuid:  # Should always be true in this handler path
                    self.remove("CHANNEL_HANGUP", bound_hangup_handler)
                    self.remove("CHANNEL_DESTROY", bound_hangup_handler)

        bound_complete_handler = partial(_complete_handler, self)
        bound_hangup_handler = partial(_hangup_handler, self)

        logger.debug(
            f"Registering CHANNEL_EXECUTE_COMPLETE handler for App-UUID: {event_uuid}"
        )
        self.on("CHANNEL_EXECUTE_COMPLETE", bound_complete_handler)

        if channel_uuid:
            logger.debug(
                f"Registering CHANNEL_HANGUP/DESTROY handler for channel: "
                f"{channel_uuid} during operation {event_uuid}"
            )
            self.on("CHANNEL_HANGUP", bound_hangup_handler)
            self.on("CHANNEL_DESTROY", bound_hangup_handler)

        return semaphore

    async def sendmsg(
        self,
        command: str,
        application: str,
        data: Optional[str] = None,
        lock: bool = False,
        uuid: Optional[str] = None,
        app_event_uuid: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> CommandResult:
        """
        Used to send commands from dialplan to session.

        Args:
            command: Command to send to FreeSWITCH (execute, hangup, etc.)
            application: Dialplan application to execute.
            data: Arguments to send to the application.
            lock: If true, lock the event.
            uuid: UUID of the call/session/channel to send the command.
            app_event_uuid: Adds a UUID to the execute command.
            headers: Additional headers to send with the command.

        Returns:
            CommandResult: An object representing the completed command execution.
        """
        if uuid:
            cmd = f"sendmsg {uuid}"
        else:
            cmd = "sendmsg"

        cmd += f"\ncall-command: {command}"

        if command == "execute":
            cmd += f"\nexecute-app-name: {application}"
            if data:
                cmd += f"\nexecute-app-arg: {data}"

            app_event_uuid = app_event_uuid or str(uuid4())
            cmd += f"\nEvent-UUID: {app_event_uuid}"

        if lock:
            cmd += "\nevent-lock: true"

        if command == "hangup":
            cmd += f"\nhangup-cause: {data}"

        if headers:
            for key, value in headers.items():
                cmd += f"\n{key}: {value}"

        logger.debug(
            f"Send command to FreeSWITCH: '{cmd}'. "
            f"Target channel UUID: {uuid}, App-UUID: {app_event_uuid}"
        )

        channel: Optional[Channel] = None
        if uuid and uuid in self.channels:
            channel = self.channels[uuid]

        result = CommandResult(
            initial_event=ESLEvent(),  # Will be replaced with actual response
            app_uuid=app_event_uuid,
            channel_uuid=uuid,
            channel=channel,
            command=command,
            application=application,
            data=data,
        )

        if command == "execute":
            assert app_event_uuid is not None  # Set via uuid4() above
            logger.debug(
                f"Waiting for command completion with Application-UUID: "
                f"{app_event_uuid} on channel {uuid}"
            )

            command_is_complete_or_interrupted = await self._awaitable_complete_command(
                app_event_uuid, uuid, result
            )
            response = await self.send(cmd)
            result.initial_event = response
            logger.debug(f"Received response of execute command: {pformat(response)}")
            await command_is_complete_or_interrupted.wait()

            # The result should now be complete (either success or exception)
            return result
        else:
            # For non-execute commands, just send command and complete with reply
            response = await self.send(cmd)
            result.initial_event = response
            result.set_complete(response)
            return result

    async def log(
        self,
        level: Literal[
            "CONSOLE", "ALERT", "CRIT", "ERR", "WARNING", "NOTICE", "INFO", "DEBUG"
        ],
        message: str,
    ) -> CommandResult:
        """Log a message to FreeSWITCH using dp tools log."""
        return await self.sendmsg("execute", "log", f"{level} {message}")

    async def answer(self) -> CommandResult:
        """Answer the call associated with the session."""
        return await self.sendmsg("execute", "answer")

    async def park(self) -> CommandResult:
        """Move session-associated call to park."""
        return await self.sendmsg("execute", "park")

    async def hangup(self, cause: str = "NORMAL_CLEARING") -> CommandResult:
        """Hang up the call associated with the session."""
        return await self.sendmsg("execute", "hangup", cause)

    async def playback(self, path: str) -> CommandResult:
        """
        Requests FreeSWITCH to play an audio and waits for it to complete.

        To play audio in the background without waiting for completion, use:
        `asyncio.create_task(session.playback(path))`

        Args:
            path: The path to the audio file.

        Returns:
            CommandResult: An object representing the completed command execution.
        """
        return await self.sendmsg("execute", "playback", path)

    async def say(
        self,
        text: str,
        module: str = "en",
        lang: Optional[str] = None,
        kind: str = "NUMBER",
        method: str = "pronounced",
        gender: str = "FEMININE",
    ) -> CommandResult:
        """
        The say application will use pre-recorded sound files to say things.
        This method waits for the operation to complete.

        Args:
            text: The text to be spoken.
            module: The say module to use (e.g., 'en').
            lang: The language within the module.
            kind: The type of text (e.g., 'NUMBER', 'TEXT').
            method: The method of saying (e.g., 'pronounced').
            gender: The gender of the voice.

        Returns:
            CommandResult: An object representing the completed command execution.
        """
        if lang:
            module += f":{lang}"

        arguments = f"{module} {kind} {method} {gender} {text}"
        logger.debug(f"Arguments used in say command: {arguments}")
        return await self.sendmsg("execute", "say", arguments)

    async def bridge(
        self,
        channel_a: Channel,
        target: str,
        call_variables: Optional[Dict[str, str]] = None,
    ) -> Tuple[CommandResult, Channel]:
        """
        Bridges channel_a to another target (e.g., endpoint, dialplan extension).
        This is a wrapper around Channel.bridge for backward compatibility.

        Args:
            channel_a: The A-leg channel to bridge from
            target: The bridge target string (e.g., 'user/1000').
            call_variables: Optional dictionary of variables for the B-leg.

        Returns:
            A tuple containing:
            - CommandResult: An object representing the command execution result.
            - The pre-created B-leg Channel object.
        """
        if channel_a.is_gone:
            raise SessionGoneAway(f"Channel {channel_a.uuid} has been destroyed.")

        logger.info(
            f"Session: Using Channel.bridge method for channel [{channel_a.uuid}]"
        )
        result = await channel_a.bridge(target, call_variables)
        # Bridge with string target returns (CommandResult, Channel)
        if isinstance(result, tuple):
            return result
        # Should not happen with string target, but handle gracefully
        raise TypeError("Unexpected return type from Channel.bridge")

    async def unbridge(
        self,
        channel: Union[str, Channel],
        destination: Optional[str] = None,
        park: bool = True,
    ) -> BackgroundJobResult:
        """
        Unbridges a channel from any connected channel and transfers it.

        This is a wrapper around Channel.unbridge for backward compatibility.

        Args:
            channel: The channel or channel UUID to unbridge
            destination: Optional destination for the channel after unbridging.
            park: If True, both channels will be parked after unbridging.

        Returns:
            BackgroundJobResult: An object that can be awaited for completion

        Raises:
            SessionGoneAway: If the channel has been destroyed
        """
        if isinstance(channel, str):
            if channel not in self.channels:
                raise SessionGoneAway(f"Channel {channel} not found in this session")
            channel_obj = self.channels[channel]
        elif isinstance(channel, Channel):
            channel_obj = channel
        else:
            raise TypeError("channel must be a string UUID or Channel object")

        logger.info(
            f"Session: Using Channel.unbridge method for channel [{channel_obj.uuid}]"
        )
        return await channel_obj.unbridge(destination=destination, park=park)

    async def play_and_get_digits(
        self,
        tries: int,
        timeout: int,
        terminators: str,
        file: str,
        minimal: int = 0,
        maximum: int = 128,
        regexp: Optional[str] = None,
        var_name: Optional[str] = None,
        invalid_file: Optional[str] = None,
        digit_timeout: Optional[int] = None,
        transfer_on_failure: Optional[str] = None,
    ) -> CommandResult:
        """
        Executes the 'play_and_get_digits' application and waits for completion.
        """
        formatter: Callable[[Any], str] = lambda value: (
            "" if value is None else str(value)
        )
        ordered_arguments = [
            minimal,
            maximum,
            tries,
            timeout,
            terminators,
            file,
            invalid_file,
            var_name,
            regexp,
            digit_timeout,
            transfer_on_failure,
        ]
        formated_ordered_arguments = map(formatter, ordered_arguments)
        arguments = " ".join(formated_ordered_arguments)
        logger.debug(f"Arguments used in play_and_get_digits command: {arguments}")

        return await self.sendmsg("execute", "play_and_get_digits", arguments)

    async def originate(
        self,
        destination: str,
        uuid: Optional[str] = None,
        variables: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        application_after: str = "park",
    ) -> Channel:
        """
        Create a new channel using FreeSWITCH's originate command.

        This is a convenience wrapper around Channel.originate.

        Args:
            destination: FreeSWITCH endpoint string for the origination target
            uuid: Optional UUID for the new channel.
            variables: Optional dictionary of variables to set for the call
            timeout: Optional timeout in seconds for call origination
            application_after: Application to execute after call is answered

        Returns:
            Channel: The newly created channel object

        Raises:
            OriginateError: If originate command fails
        """
        logger.info(f"Session: Originating new call to destination {destination}")
        return await Channel.originate(
            session=self,
            destination=destination,
            uuid=uuid,
            variables=variables,
            timeout=timeout,
            application_after=application_after,
        )

    async def bgapi_execute(
        self, cmd: str, job_uuid: Optional[str] = None
    ) -> BackgroundJobResult:
        """
        Execute a background API command.

        This is a convenience method that delegates to the BackgroundAPI instance.

        Args:
            cmd: The API command to execute (without 'bgapi' prefix)
            job_uuid: Optional custom Job-UUID.

        Returns:
            BackgroundJobResult: An object that can be awaited for completion

        Example:
            result = await session.bgapi_execute("originate sofia/gateway/mygw/1234 &park()")
            await result  # Wait for completion
            print(result.response)  # Get the result
        """
        return await self.bgapi.execute(cmd, job_uuid)
