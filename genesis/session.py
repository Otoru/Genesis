"""
Genesis Session
---------------

This module defines the Session class, which abstracts a session
established between the application and FreeSWITCH in an outbound context.
"""

from __future__ import annotations

from asyncio import StreamReader, StreamWriter, Queue, Event
from typing import Optional, Union, Dict, Literal, Tuple, Any, Coroutine
from functools import partial
from pprint import pformat
from uuid import uuid4
from genesis.exceptions import OperationInterruptedException, SessionGoneAway
from genesis.protocol import Protocol
from genesis.events import ESLEvent
from genesis.logger import logger
from genesis.channel import Channel
from genesis.results import CommandResult, BackgroundJobResult
from genesis.bgapi import BackgroundAPI


class Session(Protocol):
    """
    Session class
    -------------

    Abstracts a session established between the application and the freeswitch.

    This session has nothing to do with the session in the freeswitch context.

    Attributes:
    - reader: required
        StreamReader used to read incoming information.
    - writer: required
        StreamWriter used to send information to freeswitch.
    - context: Dict[str, str]
        The initial context variables received from FreeSWITCH upon connection.
    - channels: Dict[str, Channel]
        A dictionary of channels associated with this session, keyed by channel UUID.
    - channel_a: Optional[Channel]
        The channel that initiated this session (typically the A-leg in outbound).
    - fifo: Queue
        A queue used internally, for example, to hold results of blocking commands.
    """

    def __init__(self, reader: StreamReader, writer: StreamWriter, myevents: bool = False) -> None:
        """
        Initialize the session with the provided StreamReader and StreamWriter.

        Args:
            reader: StreamReader used to read incoming information.
            writer: StreamWriter used to send information to freeswitch.
            myevents: If true, ask freeswitch to send us all events associated with the session.
        """
        super().__init__()
        self.context: Union[Dict[str, str], ESLEvent] = dict()
        self.reader = reader
        self.writer = writer
        self.fifo = Queue()
        self.channels: Dict[str, 'Channel'] = {}
        self.myevents: bool = myevents
        self.linger: bool = True
        self.channel_a: Optional['Channel'] = None
        self.bgapi = BackgroundAPI(self)

        # Register the dispatcher for all events
        self.on("*", self._dispatch_event_to_channels)

    async def __aenter__(self) -> "Session":
        await self.start()
        return self

    async def __aexit__(self, *args, **kwargs) -> None:
        await self.stop()

    async def _dispatch_event_to_channels(self, event: ESLEvent) -> None:
        """
        Dispatches incoming events to the appropriate managed Channel.
        If a "CHANNEL_CREATE" or "CHANNEL_DATA" event is received, a Channel instance is created.
        """
        target_channel_uuid: Optional[str] = event.get("Channel-Unique-ID")
        if not target_channel_uuid:
            target_channel_uuid = event.get("Unique-ID")

        logger.trace(f"Session._dispatch: Event Target UUID: {target_channel_uuid}, Event-Name: {event.get('Event-Name')}, Content-Type: {event.get('Content-Type')}. Current self.channel_a: {self.channel_a.uuid if self.channel_a else 'None'}")

        if not target_channel_uuid:
            # Event is not related to a specific channel (e.g., general command reply, non-channel event)
            event_name_for_log = event.get("Event-Name") or event.get("Content-Type")
            logger.trace(
                f"Session._dispatch: Received non-channel specific event or command reply: {event_name_for_log}. Returning."
            )
            return

        channel_instance: Optional[Channel] = self.channels.get(target_channel_uuid)

        if not channel_instance:
            # Event for an unknown channel

            # For Outbound ESL, the initial 'connect' reply (a command/reply event)
            # should establish channel_a. It contains channel variables but isn't a
            # 'CHANNEL_CREATE' or 'CHANNEL_DATA' event by Event-Name.
            is_initial_connect_reply = (
                self.channel_a is None and  # No A-leg established yet
                event.get("Content-Type") == "command/reply" and  # It's a command reply
                "Channel-State" in event and # It contains channel information (heuristic)
                target_channel_uuid is not None # It has a UUID
            )
            logger.trace(f"Session._dispatch: Calculated is_initial_connect_reply = {is_initial_connect_reply} (self.channel_a is None: {self.channel_a is None}, Content-Type is command/reply: {event.get('Content-Type') == 'command/reply'}, Channel-State in event: {'Channel-State' in event}, target_channel_uuid is not None: {target_channel_uuid is not None})")

            if event.get("Event-Name") in ["CHANNEL_CREATE", "CHANNEL_DATA"] or is_initial_connect_reply:
                logger.info(f"Session._dispatch: CREATING new channel instance for UUID {target_channel_uuid} (Type: {event.get('Event-Name') or event.get('Content-Type')}).")

                channel_instance = Channel(uuid=target_channel_uuid, session=self)
                self.channels[target_channel_uuid] = channel_instance

                if not self.myevents:
                    try:
                        # Defer filtering for the initial A-leg; Outbound.handler manages its event subscriptions.
                        if not is_initial_connect_reply:
                            logger.debug(f"Session._dispatch: Adding filter for new channel {target_channel_uuid} (myevents=False).")
                            await self.send(f"filter Unique-ID {target_channel_uuid}")
                    except Exception as e:
                        logger.error(f"Session._dispatch: Failed to send filter command for new channel {target_channel_uuid}: {e}")

                if self.channel_a is None:
                    self.channel_a = channel_instance
                    logger.info(
                        f"Session._dispatch: Channel {target_channel_uuid} assigned as A-leg. self.channel_a is now {self.channel_a.uuid if self.channel_a else 'None'}."
                    )
                else:
                    logger.info(
                        f"Session._dispatch: Channel {target_channel_uuid} identified as B-leg (or subsequent leg). self.channel_a ({self.channel_a.uuid if self.channel_a else 'None'}) already set."
                    )
            else:
                # Event for an unmanaged UUID that is not a designated creation trigger.
                event_description = event.get('Event-Name', event.get('Content-Type', 'Unknown Event'))
                logger.debug(
                    f"Session._dispatch: Received event '{event_description}' for unmanaged channel UUID '{target_channel_uuid}'. "
                    f"Not a designated creation trigger. Ignoring for channel creation."
                )
                logger.warn(f"Session._dispatch: Received event was not a creation trigger for unknown UUID. channel_instance is {channel_instance}. self.channel_a is {self.channel_a.uuid if self.channel_a else 'None'}.")
                return

        if channel_instance: # Known channel
            await channel_instance._handle_event(event)
            logger.trace(
                f"Session._dispatch: Dispatched event {event.get('Event-Name', 'N/A')} to channel {target_channel_uuid}."
            )

            # Handle channel destruction after it has processed its own DESTROY event
            if event.get("Event-Name") == "CHANNEL_DESTROY":
                logger.info(f"Session._dispatch: Channel {target_channel_uuid} destroyed. Removing from session.")
                del self.channels[target_channel_uuid]
                if self.channel_a and self.channel_a.uuid == target_channel_uuid:
                    logger.info(f"Session._dispatch: Channel A ({target_channel_uuid}) was destroyed.")
                    self.channel_a = None

    async def _awaitable_complete_command(self, event_uuid: str, channel_uuid: Optional[str], result: CommandResult) -> Event:
        """
        Create an event that will be set when a command completes.
        If channel_uuid is provided, it also listens for hangup events on that channel
        and puts an OperationInterruptedException on the fifo if hangup occurs first.

        Args:
            event_uuid: UUID to track the specific command execution
            channel_uuid: UUID of the channel the command is acting upon.
            result: CommandResult object to update when the command completes

        Returns:
            Event that will be set when command completes
        """
        semaphore = Event()

        async def _complete_handler(session: Session, event: ESLEvent):
            logger.debug(f"Received CHANNEL_EXECUTE_COMPLETE event for App-UUID {event_uuid}")
            logger.trace(f"Event details: {pformat(event)}")
            if "Application-UUID" in event and event["Application-UUID"] == event_uuid:
                result.set_complete(event)
                semaphore.set()
                # Clean up both handlers
                self.remove("CHANNEL_EXECUTE_COMPLETE", bound_complete_handler)
                if channel_uuid:
                    self.remove("CHANNEL_HANGUP", bound_hangup_handler)
                    self.remove("CHANNEL_DESTROY", bound_hangup_handler)

        async def _hangup_handler(session: Session, event: ESLEvent):
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
                    channel_uuid=channel_uuid
                )
                result.set_exception(exception_to_put)
                semaphore.set()
                # Clean up both handlers
                self.remove("CHANNEL_EXECUTE_COMPLETE", bound_complete_handler)
                if channel_uuid: # Should always be true if we are in this handler path
                    self.remove("CHANNEL_HANGUP", bound_hangup_handler)
                    self.remove("CHANNEL_DESTROY", bound_hangup_handler)

        bound_complete_handler = partial(_complete_handler, self)
        bound_hangup_handler = partial(_hangup_handler, self)

        logger.debug(f"Registering CHANNEL_EXECUTE_COMPLETE handler for App-UUID: {event_uuid}")
        self.on("CHANNEL_EXECUTE_COMPLETE", bound_complete_handler)

        if channel_uuid:
            logger.debug(f"Registering CHANNEL_HANGUP/DESTROY handler for channel: {channel_uuid} during operation {event_uuid}")
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
            command: required
                Command to send to freeswitch. One of: execute, hangup, unicast, nomedia, xferext
            application: required
                Dialplan application to execute.
            data: optional
                Arguments to send to the application. If the command is 'hangup', this is the cause.
            lock: optional
                If true, lock the event.
            uuid: optional
                UUID of the call/session/channel to send the command.
            app_event_uuid: optional
                Adds a UUID to the execute command. In the corresponding events (CHANNEL_EXECUTE and
                CHANNEL_EXECUTE_COMPLETE), the UUID will be in the Application-UUID header.
            headers: optional
                Additional headers to send with the command.
        
        Returns:
            CommandResult: An object representing the completed command execution.
            To run a command in the background, use `asyncio.create_task()`.
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
            cmd += f"\nevent-lock: true"

        if command == "hangup":
            cmd += f"\nhangup-cause: {data}"

        if headers:
            for key, value in headers.items():
                cmd += f"\n{key}: {value}"

        logger.debug(f"Send command to freeswitch: '{cmd}'. Target channel UUID: {uuid}, App-UUID: {app_event_uuid}")

        channel = None
        if uuid and uuid in self.channels:
            channel = self.channels[uuid]

        result = CommandResult(
            initial_event=ESLEvent(),  # Will be replaced with actual response
            app_uuid=app_event_uuid,
            channel_uuid=uuid,
            channel=channel,
            command=command,
            application=application,
            data=data
        )

        if command == "execute":
            logger.debug(
                f"Waiting for command completion with Application-UUID: {app_event_uuid} on channel {uuid}"
            )

            command_is_complete_or_interrupted = await self._awaitable_complete_command(app_event_uuid, uuid, result)
            response = await self.send(cmd)
            result.initial_event = response
            logger.debug(
                f"Received response of execute command: {pformat(response)}"
            )
            await command_is_complete_or_interrupted.wait()

            # The result should now be complete (either success or exception)
            return result
        else:
            # For non-execute commands, just send the command and complete the result with the command/reply
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
        Requests the freeswitch to play an audio and waits for it to complete.

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
        module="en",
        lang: Optional[str] = None,
        kind: str = "NUMBER",
        method: str = "pronounced",
        gender: str = "FEMININE",
    ) -> CommandResult:
        """
        The say application will use the pre-recorded sound files to read or say things.
        This method waits for the operation to complete.

        To run this in the background, use `asyncio.create_task()`.

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
        This is now a wrapper around Channel.bridge for backward compatibility.
        This method waits for the bridge to complete. To run in the background, use `asyncio.create_task()`.

        Args:
            channel_a: The A-leg channel to bridge from
            target: The bridge target string (e.g., 'user/1000', 'sofia/gateway/mygw/1234').
            call_variables: Optional dictionary of variables to set for the B-leg.
                            'origination_uuid' will be automatically added/overridden.

        Returns:
            A tuple containing:
            - CommandResult: An object representing the command execution result.
            - The pre-created B-leg Channel object.
        """
        if channel_a.is_gone:
            raise SessionGoneAway(f"Channel {channel_a.uuid} has been destroyed.")
            
        logger.info(f"Session: Using Channel.bridge method for channel [{channel_a.uuid}]")
        return await channel_a.bridge(target, call_variables)
        
    async def unbridge(self, channel: Union[str, Channel], destination: Optional[str] = None, park: bool = True) -> BackgroundJobResult:
        """
        Unbridges a channel from any connected channel and transfers it to a destination.
        
        This is a wrapper around Channel.unbridge for backward compatibility.
        
        Args:
            channel: The channel or channel UUID to unbridge
            destination: Optional destination for the channel after unbridging.
                       If park=True, this is ignored.
                       If park=False and no destination provided, just unbridges without transferring.
            park: If True, both channels will be parked after unbridging (default: True)
        
        Returns:
            CommandResult: An object representing the command execution result
            
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
        
        logger.info(f"Session: Using Channel.unbridge method for channel [{channel_obj.uuid}]")
        return await channel_obj.unbridge(destination=destination, park=park)

    async def play_and_get_digits(
        self,
        tries,
        timeout,
        terminators,
        file,
        minimal=0,
        maximum=128,
        regexp: Optional[str] = None,
        var_name: Optional[str] = None,
        invalid_file: Optional[str] = None,
        digit_timeout: Optional[int] = None,
        transfer_on_failure: Optional[str] = None,
    ) -> CommandResult:
        """
        Executes the 'play_and_get_digits' application and waits for completion.

        To run this in the background, use `asyncio.create_task()`.
        """
        formatter = lambda value: "" if value is None else str(value)
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

        return await self.sendmsg(
            "execute", "play_and_get_digits", arguments
        )
        
    async def originate(
        self,
        destination: str,
        uuid: Optional[str] = None,
        variables: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        application_after: str = "park"
    ) -> Channel:
        """
        Create a new channel using FreeSWITCH's originate command.
        
        This is a convenience wrapper around Channel.originate.
        
        Args:
            destination: FreeSWITCH endpoint string for the origination target
            uuid: Optional UUID for the new channel. If not provided, one will be generated
            variables: Optional dictionary of variables to set for the call
            timeout: Optional timeout in seconds for call origination
            application_after: Application to execute after call is answered (default: park)
            
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
            application_after=application_after
        )
        
    async def bgapi_execute(self, cmd: str, job_uuid: Optional[str] = None):
        """
        Execute a background API command.
        
        This is a convenience method that delegates to the BackgroundAPI instance.
        
        Args:
            cmd: The API command to execute (without 'bgapi' prefix)
            job_uuid: Optional custom Job-UUID. If not provided, one will be generated
            
        Returns:
            BackgroundJobResult: An object that can be awaited for completion
            
        Example:
            result = await session.bgapi_execute("originate sofia/gateway/mygw/1234 &park()")
            await result  # Wait for completion
            print(result.response)  # Get the result
        """
        return await self.bgapi.execute(cmd, job_uuid)
