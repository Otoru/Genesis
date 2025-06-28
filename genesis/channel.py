"""
Channel Representation
----------------------

This module defines the Channel class, which represents and manages
the state and interactions of a single FreeSWITCH channel.
"""
from __future__ import annotations

from asyncio import iscoroutinefunction, create_task, to_thread
from typing import TYPE_CHECKING, Optional, Dict, Literal, Union, Awaitable, List, Callable, Tuple
from uuid import uuid4

from .enums import ChannelState, CallState
from .events import ESLEvent
from .exceptions import SessionGoneAway, OriginateError
from .logger import logger
from .utils import build_variable_string
from .command import CommandResult

if TYPE_CHECKING:
    from .session import Session

class Channel:
    """
    Represents a FreeSWITCH channel, tracking its state and providing command methods.

    Attributes:
        uuid: The unique identifier of this channel.
        session: The Session instance this channel belongs to.
        state: The current core state (ChannelState) of the channel.
        call_state: The current call state (CallState) of the channel.
        variables: A dictionary holding known channel variables.
        is_gone: Flag indicating if the channel has been destroyed.
        handlers: Dictionary for event-specific handlers on this channel.
    """

    def __init__(self, uuid: str, session: 'Session', initial_state: ChannelState = ChannelState.NEW):
        """
        Initializes a Channel instance.

        Args:
            uuid: The Unique-ID of the channel.
            session: The Session instance this channel is associated with.
            initial_state: The initial state to set for the channel.
        """
        self.uuid: str = uuid
        self.session: 'Session' = session # Changed from protocol to session
        self.state: ChannelState = initial_state
        self.call_state: CallState = CallState.DOWN # Initial call state
        self.variables: Dict[str, str] = {}
        self.is_gone: bool = False
        self.handlers: Dict[
            str, List[Callable[[Channel, ESLEvent], Union[None, Awaitable[None]]]]
        ] = {}
        logger.info(f"Channel {self.uuid} created in state: {self.state.name} for session {self.session}")

    def __repr__(self) -> str:
        return f"<Channel uuid={self.uuid} state={self.state.name} call_state={self.call_state.name}>"

    def _check_if_gone(self) -> None:
        """Raises SessionGoneAway if the channel is marked as destroyed."""
        if self.is_gone:
            raise SessionGoneAway(f"Channel {self.uuid} has been destroyed.")

    def on(
        self,
        event_name: str,
        handler: Callable[[Channel, ESLEvent], Union[None, Awaitable[None]]],
    ) -> None:
        """
        Registers an event handler for a specific event on this channel.

        Args:
            event_name: The name of the event (e.g., "DTMF", "CHANNEL_ANSWER", "*").
            handler: The callable to execute when the event occurs.
                     It will receive the Channel instance and the ESLEvent.
        """
        event_name = event_name.upper()
        if not callable(handler):
            raise TypeError("Handler must be callable.")
        logger.debug(f"Channel {self.uuid} registering handler for event '{event_name}'.")
        self.handlers.setdefault(event_name, []).append(handler)

    def remove(
        self,
        event_name: str,
        handler: Callable[[Channel, ESLEvent], Union[None, Awaitable[None]]],
    ) -> None:
        """
        Removes a previously registered event handler.

        Args:
            event_name: The name of the event.
            handler: The specific handler callable to remove.
        """
        event_name = event_name.upper()
        logger.debug(f"Channel {self.uuid} removing handler for event '{event_name}'.")
        if event_name in self.handlers and handler in self.handlers[event_name]:
            self.handlers[event_name].remove(handler)
            if not self.handlers[event_name]: # Clean up if list is empty
                del self.handlers[event_name]

    async def _handle_event(self, event: ESLEvent) -> None:
        """
        Internal method to process an incoming event for this channel.
        It updates the channel state and invokes registered handlers.
        """
        self.update_state(event)  # Update state first

        event_name_header = event.get("Event-Name")
        effective_event_key = event_name_header

        if event_name_header == "CUSTOM":
            subclass = event.get("Event-Subclass")
            if subclass: # e.g., "DTMF"
                effective_event_key = subclass.upper() # Normalize subclass name
            else: # Generic CUSTOM event
                effective_event_key = "CUSTOM"
        elif effective_event_key:
            effective_event_key = effective_event_key.upper() # Normalize other event names

        handlers_to_call = []
        if effective_event_key:
            handlers_to_call.extend(self.handlers.get(effective_event_key, []))
        # If it was a CUSTOM event with a specific subclass, also check for generic "CUSTOM" handlers
        if event_name_header == "CUSTOM" and effective_event_key != "CUSTOM":
            handlers_to_call.extend(self.handlers.get("CUSTOM", []))
        handlers_to_call.extend(self.handlers.get("*", []))

        unique_handlers = list(dict.fromkeys(handlers_to_call))

        if unique_handlers:
            logger.trace(f"Channel {self.uuid} invoking {len(unique_handlers)} handlers for event (effective_key: '{effective_event_key}', name: '{event_name_header}').")
            for handler_func in unique_handlers:
                try:
                    if iscoroutinefunction(handler_func):
                        # For async handlers, ensure they are awaited or run as tasks
                        create_task(handler_func(self, event))
                    else:
                        # For sync handlers, run in a thread to avoid blocking the event loop
                        await to_thread(handler_func, self, event)
                except Exception as e:
                    logger.error(f"Channel {self.uuid} error in event handler for '{effective_event_key or event_name_header}': {e}", exc_info=True)

    def update_state(self, event: ESLEvent) -> None:
        """
        Updates the channel's state based on an incoming event.

        Args:
            event: The ESLEvent received for this channel.
        """
        channel_state_num = event.get("Channel-State-Number")
        if channel_state_num is not None:
            try:
                old_state = self.state
                new_state_num = int(channel_state_num)
                
                try:
                    self.state = ChannelState(new_state_num)
                    if old_state != self.state:
                        logger.debug(
                            f"Channel {self.uuid} state change: "
                            f"{old_state.name}({int(old_state)}) -> "
                            f"{self.state.name}({int(self.state)})"
                        )
                except ValueError:
                    logger.warning(
                        f"Channel {self.uuid} received invalid channel state number: {new_state_num}"
                    )
            except (ValueError, TypeError):
                logger.warning(
                    f"Channel {self.uuid} received non-integer Channel-State-Number: {channel_state_num}"
                )

        call_state_str = event.get("Channel-Call-State")
        if call_state_str:
            old_call_state = self.call_state
            processed_call_state_str = call_state_str.upper()
            
            # Special case mapping
            if processed_call_state_str == "EARLY_MEDIA":
                processed_call_state_str = "EARLY"
                
            try:
                self.call_state = CallState[processed_call_state_str]
                if old_call_state != self.call_state:
                    logger.debug(
                        f"Channel {self.uuid} CallState change: "
                        f"{old_call_state.name}({int(old_call_state)}) -> "
                        f"{self.call_state.name}({int(self.call_state)})"
                    )
            except KeyError:
                logger.warning(
                    f"Channel {self.uuid} received unknown Channel-Call-State: {call_state_str}"
                )
        
        # Mark channel as gone if it's in a terminal state
        if self.call_state == CallState.HANGUP or self.state == ChannelState.DESTROY:
            self.is_gone = True
            logger.debug(f"Channel {self.uuid} marked as gone (call state: {self.call_state.name}, core state: {self.state.name}).")
            if self.state == ChannelState.HANGUP:
                logger.info(f"Channel {self.uuid} is in HANGUP state, marking as gone.")

        # Update channel variables from the event
        for key, value in event.items():
            if key.startswith("variable_"):
                var_name = key[len("variable_"):]
                if self.variables.get(var_name) != value:
                     logger.trace(f"Channel {self.uuid} variable update: {var_name}={value}")
                     self.variables[var_name] = value
            elif key in ["Caller-Caller-ID-Number", "Caller-Caller-ID-Name", "Caller-Destination-Number", "Unique-ID", "Channel-Name"]:
                 if self.variables.get(key) != value:
                     logger.trace(f"Channel {self.uuid} variable update: {key}={value}")
                     self.variables[key] = value

    async def _sendmsg(
        self,
        command: str,
        application: str,
        data: Optional[str] = None,
        lock: bool = False,
        app_event_uuid: Optional[str] = None,
        block: bool = False,
        headers: Optional[Dict[str, str]] = None,
    ) -> CommandResult:
        """Internal helper to send commands via the associated protocol."""
        self._check_if_gone()
        return await self.session.sendmsg(
            command=command,
            application=application,
            data=data,
            lock=lock,
            uuid=self.uuid,
            app_event_uuid=app_event_uuid,
            block=block,
            headers=headers,
        )

    async def execute(
        self,
        application: str,
        data: Optional[str] = None,
        block: bool = False,
        app_event_uuid: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> CommandResult:
        """
        Executes a dialplan application on this channel.

        Args:
            application: The application name (e.g., 'playback', 'bridge').
            data: Arguments for the application.
            block: If True, wait for CHANNEL_EXECUTE_COMPLETE before returning.
                   Only fully supported for Outbound sessions.
            app_event_uuid: Custom UUID for tracking execute events.
            headers: Additional ESL headers for the sendmsg command.

        Returns:
            CommandResult: An object representing the command execution result.
            For blocking calls, the result will already be complete.
            For non-blocking calls, the result can be awaited later.
        """
        return await self._sendmsg(
            command="execute",
            application=application,
            data=data,
            block=block,
            app_event_uuid=app_event_uuid,
            headers=headers,
        )

    async def hangup(self, cause: str = "NORMAL_CLEARING") -> CommandResult:
        """
        Hangs up this channel.

        Args:
            cause: The hangup cause string (see FreeSWITCH hangup causes).

        Returns:
            CommandResult: An object representing the command execution result.
        """
        # If already in HANGUP or DESTROY state, or marked as gone, don't send again
        if self.state in [ChannelState.HANGUP, ChannelState.DESTROY] or self.is_gone:
            logger.info(f"Channel {self.uuid} already hanging up or gone. Skipping redundant hangup command.")
            # Create a synthetic CommandResult for already hung up channels
            result = CommandResult(
                initial_event=ESLEvent({"Reply-Text": "+OK Channel already hungup or gone"}),
                channel_uuid=self.uuid,
                channel=self,
                command="hangup",
                application="",
                data=cause
            )
            result.set_complete(result.initial_event)
            return result
        return await self._sendmsg(command="hangup", application="", data=cause) # application is empty for hangup command

    async def answer(self) -> CommandResult:
        """
        Answers the channel.
        
        Returns:
            CommandResult: An object representing the command execution result.
        """
        return await self.execute("answer")
        
    async def park(self) -> CommandResult:
        """
        Parks the channel.
        
        This places the channel in a holding state where it will hear silence
        and stay connected until another operation is performed.
        
        Returns:
            CommandResult: An object representing the command execution result.
        """
        logger.debug(f"Channel {self.uuid} parking")
        return await self.execute("park")

    async def bridge(
        self,
        target: Union[str, 'Channel'],
        call_variables: Optional[Dict[str, str]] = None,
        block: bool = True,
    ) -> Union[Tuple[CommandResult, Channel], CommandResult]:
        """
        Bridges this channel to another target (e.g., endpoint, dialplan extension) or directly to another Channel.
        Creates a B-leg channel and sets up proper event filtering when target is a dialstring.

        Args:
            target: The bridge target. Can be either:
                   - A string (e.g., 'user/1000', 'sofia/gateway/mygw/1234')
                   - A Channel object to bridge directly to this channel
            call_variables: Optional dictionary of variables to set for the B-leg.
                            'origination_uuid' will be automatically added/overridden.
                            Only used when target is a string (dialstring).
            block: If True, wait for the bridge to complete (or fail).
                   This typically means waiting for CHANNEL_EXECUTE_COMPLETE for the bridge app.

        Returns:
            - When target is a string: Tuple[CommandResult, Channel] with the command result and the newly created B-leg channel
            - When target is a Channel: Just the CommandResult, as no new channel is created
        """
        self._check_if_gone()
        
        # Handle the case where target is already a Channel object
        if isinstance(target, Channel):
            # Bridge to an existing channel using uuid_bridge bgapi command
            logger.info(f"Channel {self.uuid} bridging to existing channel [{target.uuid}] using uuid_bridge bgapi")

            bridge_cmd = f"uuid_bridge {self.uuid} {target.uuid}"
            result = await self.session.bgapi_execute(bridge_cmd)
            
            # Wait for the background job to complete
            await result
            
            # Only return the CommandResult when target is a Channel
            return result

        bleg_uuid = str(uuid4())
        bridge_app_uuid = str(uuid4())  # UUID for the bridge application itself
        
        # Prepare variables for the B-leg dialstring
        effective_call_vars = dict(call_variables or {})
        effective_call_vars["origination_uuid"] = bleg_uuid

        # Carry over caller ID from A-leg if not specified for B-leg
        a_leg_cid_name = self.variables.get("Caller-Caller-ID-Name")
        a_leg_cid_num = self.variables.get("Caller-Caller-ID-Number")

        if "origination_caller_id_name" not in effective_call_vars and a_leg_cid_name:
            effective_call_vars["origination_caller_id_name"] = a_leg_cid_name
        if "origination_caller_id_number" not in effective_call_vars and a_leg_cid_num:
            effective_call_vars["origination_caller_id_number"] = a_leg_cid_num

        # Ensure that we don't pass empty strings as caller ID if they were not set
        if "origination_caller_id_name" in effective_call_vars and not effective_call_vars["origination_caller_id_name"]:
            del effective_call_vars["origination_caller_id_name"]
        if "origination_caller_id_number" in effective_call_vars and not effective_call_vars["origination_caller_id_number"]:
            del effective_call_vars["origination_caller_id_number"]

        variable_string = build_variable_string(effective_call_vars)
        bridge_target_with_vars = f"{variable_string}{target}"

        logger.info(f"Channel {self.uuid} bridging to: {bridge_target_with_vars}")

        # Create B-leg channel object
        bleg_channel = Channel(uuid=bleg_uuid, session=self.session, initial_state=ChannelState.NEW)
        self.session.channels[bleg_uuid] = bleg_channel
        logger.info(f"Created B-leg Channel object [{bleg_uuid}] for bridge from channel {self.uuid}.")

        # Add filter for the B-leg channel's events
        try:
            await self.session.send(f"filter Unique-ID {bleg_uuid}")
            logger.debug(f"Added event filter for B-leg channel {bleg_uuid}")
        except Exception as e:
            logger.error(f"Failed to add event filter for B-leg channel {bleg_uuid}: {e}")
            # Continue anyway, as the bridge might still work

        # Execute the bridge command
        response = await self.execute(
            application="bridge",
            data=bridge_target_with_vars,
            block=block,
            app_event_uuid=bridge_app_uuid
        )
        
        logger.debug(f"Bridge command completed with response: {response}")
        # Return a tuple with CommandResult and new Channel when target is a dialstring
        return response, bleg_channel

    async def playback(self, path: str, block: bool = True) -> CommandResult:
        """
        Plays an audio file on the channel.

        Args:
            path: The path to the audio file (accessible by FreeSWITCH).
            block: If True, wait for playback to complete.

        Returns:
            CommandResult: An object representing the command execution result.
            For blocking calls, the result will already be complete.
            For non-blocking calls, the result can be awaited later.
        """
        return await self.execute("playback", path, block=block)
        
    async def silence(self, ms: int, block: bool = True) -> CommandResult:
        """
        Play silence for specified duration.

        Args:
            ms: Duration of silence in milliseconds
            block: If True, wait for playback completion before returning

        Returns:
            CommandResult: An object representing the command execution result.
            For blocking calls, the result will already be complete.
            For non-blocking calls, the result can be awaited later.

        Examples:
            # Play 2 seconds of silence
            await channel.silence(2000)

            # Play silence without blocking
            await channel.silence(1000, block=False)
        """
        logger.debug(f"Channel {self.uuid} playing {ms}ms of silence (block={block})")
        path = f"silence_stream://{ms}"
        return await self.playback(path, block=block)

    async def say(
        self,
        text: str,
        module="en",
        lang: Optional[str] = None,
        kind: str = "NUMBER",
        method: str = "pronounced",
        gender: str = "FEMININE",
        block=True,
    ) -> CommandResult:
        """
        Uses the 'say' application to speak text.
        
        Returns:
            CommandResult: An object representing the command execution result.
        """
        if lang:
            module += f":{lang}"
        arguments = f"{module} {kind} {method} {gender} {text}"
        return await self.execute("say", arguments, block=block)

    async def play_and_get_digits(
        self,
        min_digits: int,
        max_digits: int,
        tries: int,
        timeout: int, # Inter-digit timeout
        terminators: str,
        file: str,
        invalid_file: Optional[str] = None,
        var_name: Optional[str] = None, # Variable to store digits
        regexp: Optional[str] = None, # Regex to validate input
        digit_timeout: Optional[int] = None, # Timeout after last digit
        transfer_on_failure: Optional[str] = None,
        block: bool = True,
    ) -> CommandResult:
        """
        Executes the 'play_and_get_digits' application.
        
        Returns:
            CommandResult: An object representing the command execution result.
        """
        formatter = lambda value: "" if value is None else str(value)
        # Order matters for play_and_get_digits!
        ordered_args = [
            min_digits, max_digits, tries, timeout, terminators, file,
            invalid_file, var_name, regexp, digit_timeout, transfer_on_failure
        ]
        arguments = " ".join(map(formatter, ordered_args)).strip()
        return await self.execute("play_and_get_digits", arguments, block=block)

    async def set_variable(self, name: str, value: str) -> CommandResult:
        """
        Sets a channel variable on this channel.

        Args:
            name: The name of the variable.
            value: The value to set.

        Returns:
            CommandResult: An object representing the command execution result.
        """
        return await self.execute("set", f"{name}={value}", block=False)

    async def get_variable(self, name: str) -> Optional[str]:
        """
        Gets a channel variable's value.

        Note: This attempts to retrieve the value locally first. If not found,
        it sends a `uuid_getvar` command. Local updates depend on receiving
        events with `variable_` prefixes.

        Args:
            name: The name of the variable.

        Returns:
            The variable value, or None if not found locally and API call fails/returns empty.
        """
        self._check_if_gone()
        if name in self.variables:
            return self.variables[name]
        else:
            return None
            
    @classmethod
    async def originate(cls, session: 'Session', destination: str, uuid: Optional[str] = None,
                                variables: Optional[Dict[str, str]] = None,
                                timeout: Optional[int] = None, application_after: str = "park()") -> 'Channel':
        """
        Create a new channel using FreeSWITCH's originate command.

        Args:
            session: Session object to use for the new channel
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
        new_uuid = uuid if uuid else str(uuid4())
        logger.debug(f"Creating new channel with UUID {new_uuid} to destination {destination}")

        new_channel = cls(new_uuid, session, initial_state=ChannelState.NEW)

        vars_dict = variables or {}
        vars_dict['origination_uuid'] = new_uuid

        try:
            await session.send(f"filter Unique-ID {new_uuid}")

            full_destination = f"{destination} &{application_after}"

            timeout_str = f"timeout={timeout}" if timeout else ""
            originate_cmd = f"originate {build_variable_string(vars_dict)}{full_destination} {timeout_str}"
            
            # Use bgapi instead of api for non-blocking originate
            logger.debug(f"Executing bgapi originate command: {originate_cmd}")
            result = await session.bgapi_execute(originate_cmd)
            
            # Wait for the background job to complete
            logger.debug(f"Waiting for bgapi originate completion for channel {new_uuid}")
            await result
            
            # Check for errors in the completion event
            if result.completion_event and result.response:
                response_body = result.response.strip()
                logger.debug(f"Originate bgapi response: {response_body}")
                
                if response_body.startswith("-ERR") or "ERROR" in response_body.upper():
                    error_msg = response_body
                    logger.error(f"Originate bgapi failed: {error_msg}")
                    raise OriginateError(f"Originate command failed: {error_msg}", destination, vars_dict)
                elif not response_body.startswith("+OK"):
                    logger.warning(f"Unexpected originate bgapi response: {response_body}")
                    # Don't fail here as some responses might be valid but not start with +OK
            
            session.channels[new_uuid] = new_channel
            logger.info(f"Successfully initiated new channel {new_uuid} via bgapi")
            
            if new_channel.is_gone:
                logger.error(f"Channel {new_uuid} was created but disconnected immediately")
                raise OriginateError(f"Channel {new_uuid} disconnected immediately", destination, vars_dict)
            
            return new_channel

        except Exception as e:
            if new_uuid in session.channels:
                del session.channels[new_uuid]
            
            if isinstance(e, OriginateError):
                raise
                
            logger.error(f"Failed to create channel via bgapi: {str(e)}")
            raise OriginateError(f"Failed to create channel: {str(e)}", destination, vars_dict)
            
    async def unbridge(self, destination: Optional[str] = None, park: bool = True) -> CommandResult:
        """
        Unbridges this channel from any connected channel and transfers it to a destination.
        
        Args:
            destination: Optional destination for the channel after unbridging.
                       If park=True, this is ignored.
                       If park=False and no destination provided, just unbridges without transferring.
            park: If True, both channels will be parked after unbridging (default: True)
        
        Returns:
            CommandResult: An object representing the command execution result
            
        Raises:
            SessionGoneAway: If the channel has been destroyed
        """
        self._check_if_gone()
        
        transfer_target = "park:" if park else (destination or "")
        both_flag = "-both" if park else ""
        
        log_msg = f"Channel {self.uuid} unbridging"
        if park:
            log_msg += " and parking both legs"
        elif destination:
            log_msg += f" and transferring to '{destination}'"
        else:
            log_msg += " without transfer"
        
        logger.info(log_msg)

        transfer_cmd = f"uuid_transfer {self.uuid} {both_flag} {transfer_target} inline"
        result = await self.session.bgapi_execute(transfer_cmd)
        
        # Wait for the background job to complete
        await result
        
        return result
