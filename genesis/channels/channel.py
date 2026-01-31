"""
Channel Representation
----------------------

This module defines the Channel class, which represents and manages
the state and interactions of a single FreeSWITCH channel.
"""

from __future__ import annotations

from asyncio import create_task, iscoroutinefunction, to_thread
from typing import (
    TYPE_CHECKING,
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    Union,
)
from uuid import uuid4

from genesis.enums import CallState, ChannelState
from genesis.exceptions import OriginateError, SessionGoneAway
from genesis.logger import logger
from genesis.parser import ESLEvent
from genesis.utils import build_variable_string

from genesis.channels.results import BackgroundJobResult, CommandResult

if TYPE_CHECKING:
    from genesis.channels.session import Session


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

    def __init__(
        self,
        uuid: str,
        session: "Session",
        initial_state: ChannelState = ChannelState.NEW,
    ) -> None:
        """
        Initializes a Channel instance.

        Args:
            uuid: The Unique-ID of the channel.
            session: The Session instance this channel is associated with.
            initial_state: The initial state to set for the channel.
        """
        self.uuid: str = uuid
        self.session: "Session" = session
        self.state: ChannelState = initial_state
        self.call_state: CallState = CallState.DOWN
        self.variables: Dict[str, str] = {}
        self.is_gone: bool = False
        self.handlers: Dict[
            str, List[Callable[["Channel", ESLEvent], Union[None, Awaitable[None]]]]
        ] = {}
        logger.info(
            f"Channel {self.uuid} created in state: {self.state.name} "
            f"for session {self.session}"
        )

    def __repr__(self) -> str:
        return (
            f"<Channel uuid={self.uuid} state={self.state.name} "
            f"call_state={self.call_state.name}>"
        )

    def _check_if_gone(self) -> None:
        """Raises SessionGoneAway if the channel is marked as destroyed."""
        if self.is_gone:
            raise SessionGoneAway(f"Channel {self.uuid} has been destroyed.")

    def on(
        self,
        event_name: str,
        handler: Callable[["Channel", ESLEvent], Union[None, Awaitable[None]]],
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
        logger.debug(
            f"Channel {self.uuid} registering handler for event '{event_name}'."
        )
        self.handlers.setdefault(event_name, []).append(handler)

    def remove(
        self,
        event_name: str,
        handler: Callable[["Channel", ESLEvent], Union[None, Awaitable[None]]],
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
            if not self.handlers[event_name]:
                del self.handlers[event_name]

    async def _handle_event(self, event: ESLEvent) -> None:
        """
        Internal method to process an incoming event for this channel.
        It updates the channel state and invokes registered handlers.
        """
        self.update_state(event)

        event_name_header = event.get("Event-Name")
        effective_event_key = event_name_header

        if event_name_header == "CUSTOM":
            subclass = event.get("Event-Subclass")
            if subclass:
                effective_event_key = str(subclass).upper()
            else:
                effective_event_key = "CUSTOM"
        elif effective_event_key:
            effective_event_key = str(effective_event_key).upper()

        handlers_to_call: List[
            Callable[["Channel", ESLEvent], Union[None, Awaitable[None]]]
        ] = []
        if effective_event_key:
            handlers_to_call.extend(self.handlers.get(effective_event_key, []))

        if event_name_header == "CUSTOM" and effective_event_key != "CUSTOM":
            handlers_to_call.extend(self.handlers.get("CUSTOM", []))
        handlers_to_call.extend(self.handlers.get("*", []))

        unique_handlers = list(dict.fromkeys(handlers_to_call))

        if unique_handlers:
            logger.debug(
                f"Channel {self.uuid} invoking {len(unique_handlers)} handlers "
                f"for event (effective_key: '{effective_event_key}')."
            )
            for handler_func in unique_handlers:
                try:
                    if iscoroutinefunction(handler_func):
                        create_task(handler_func(self, event))
                    else:
                        await to_thread(handler_func, self, event)
                except Exception as e:
                    logger.error(
                        f"Channel {self.uuid} error in event handler for "
                        f"'{effective_event_key or event_name_header}': {e}",
                        exc_info=True,
                    )

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
                        f"Channel {self.uuid} received invalid channel state "
                        f"number: {new_state_num}"
                    )
            except (ValueError, TypeError):
                logger.warning(
                    f"Channel {self.uuid} received non-integer "
                    f"Channel-State-Number: {channel_state_num}"
                )

        call_state_str = event.get("Channel-Call-State")
        if call_state_str:
            old_call_state = self.call_state
            processed_call_state_str = str(call_state_str).upper()

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
                    f"Channel {self.uuid} received unknown "
                    f"Channel-Call-State: {call_state_str}"
                )

        if self.call_state == CallState.HANGUP or self.state == ChannelState.DESTROY:
            self.is_gone = True
            logger.debug(
                f"Channel {self.uuid} marked as gone "
                f"(call state: {self.call_state.name}, core state: {self.state.name})."
            )

        for key, value in event.items():
            if key.startswith("variable_"):
                var_name = key[len("variable_") :]
                if self.variables.get(var_name) != value:
                    self.variables[var_name] = str(value)
            elif key in [
                "Caller-Caller-ID-Number",
                "Caller-Caller-ID-Name",
                "Caller-Destination-Number",
                "Unique-ID",
                "Channel-Name",
            ]:
                if self.variables.get(key) != value:
                    self.variables[key] = str(value)

    async def _sendmsg(
        self,
        command: str,
        application: str,
        data: Optional[str] = None,
        lock: bool = False,
        app_event_uuid: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> CommandResult:
        """Internal helper to send commands via the associated session."""
        self._check_if_gone()
        return await self.session.sendmsg(
            command=command,
            application=application,
            data=data,
            lock=lock,
            uuid=self.uuid,
            app_event_uuid=app_event_uuid,
            headers=headers,
        )

    async def execute(
        self,
        application: str,
        data: Optional[str] = None,
        app_event_uuid: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> CommandResult:
        """
        Executes a dialplan application on this channel and waits for it to complete.

        Args:
            application: The application name (e.g., 'playback', 'bridge').
            data: Arguments for the application.
            app_event_uuid: Custom UUID for tracking execute events.
            headers: Additional ESL headers for the sendmsg command.

        Returns:
            CommandResult: An object representing the completed command execution.
        """
        return await self._sendmsg(
            command="execute",
            application=application,
            data=data,
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
        if self.state in [ChannelState.HANGUP, ChannelState.DESTROY] or self.is_gone:
            logger.info(
                f"Channel {self.uuid} already hanging up or gone. "
                "Skipping redundant hangup command."
            )
            result = CommandResult(
                initial_event=ESLEvent(
                    {"Reply-Text": "+OK Channel already hungup or gone"}
                ),
                channel_uuid=self.uuid,
                channel=self,
                command="hangup",
                application="",
                data=cause,
            )
            result.set_complete(result.initial_event)
            return result
        return await self._sendmsg(command="hangup", application="", data=cause)

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

        Returns:
            CommandResult: An object representing the command execution result.
        """
        logger.debug(f"Channel {self.uuid} parking")
        return await self.execute("park")

    async def bridge(
        self,
        target: Union[str, "Channel"],
        call_variables: Optional[Dict[str, str]] = None,
    ) -> Union[Tuple[CommandResult, "Channel"], BackgroundJobResult]:
        """
        Bridges this channel to another target.

        Args:
            target: The bridge target. Can be either:
                   - A string (e.g., 'user/1000', 'sofia/gateway/mygw/1234')
                   - A Channel object to bridge directly to this channel
            call_variables: Optional dictionary of variables to set for the B-leg.

        Returns:
            - When target is a string: Tuple[CommandResult, Channel]
            - When target is a Channel: BackgroundJobResult
        """
        self._check_if_gone()

        if isinstance(target, Channel):
            logger.info(
                f"Channel {self.uuid} bridging to existing channel "
                f"[{target.uuid}] using uuid_bridge bgapi"
            )
            bridge_cmd = f"uuid_bridge {self.uuid} {target.uuid}"
            result = await self.session.bgapi_execute(bridge_cmd)
            return result

        bleg_uuid = str(uuid4())
        bridge_app_uuid = str(uuid4())

        effective_call_vars = dict(call_variables or {})
        effective_call_vars["origination_uuid"] = bleg_uuid

        a_leg_cid_name = self.variables.get("Caller-Caller-ID-Name")
        a_leg_cid_num = self.variables.get("Caller-Caller-ID-Number")

        if "origination_caller_id_name" not in effective_call_vars and a_leg_cid_name:
            effective_call_vars["origination_caller_id_name"] = a_leg_cid_name
        if "origination_caller_id_number" not in effective_call_vars and a_leg_cid_num:
            effective_call_vars["origination_caller_id_number"] = a_leg_cid_num

        if (
            "origination_caller_id_name" in effective_call_vars
            and not effective_call_vars["origination_caller_id_name"]
        ):
            del effective_call_vars["origination_caller_id_name"]
        if (
            "origination_caller_id_number" in effective_call_vars
            and not effective_call_vars["origination_caller_id_number"]
        ):
            del effective_call_vars["origination_caller_id_number"]

        variable_string = build_variable_string(effective_call_vars)
        bridge_target_with_vars = f"{variable_string}{target}"

        logger.info(f"Channel {self.uuid} bridging to: {bridge_target_with_vars}")

        bleg_channel = Channel(
            uuid=bleg_uuid, session=self.session, initial_state=ChannelState.NEW
        )
        self.session.channels[bleg_uuid] = bleg_channel
        logger.info(
            f"Created B-leg Channel object [{bleg_uuid}] for bridge "
            f"from channel {self.uuid}."
        )

        try:
            await self.session.send(f"filter Unique-ID {bleg_uuid}")
            logger.debug(f"Added event filter for B-leg channel {bleg_uuid}")
        except Exception as e:
            logger.error(
                f"Failed to add event filter for B-leg channel {bleg_uuid}: {e}"
            )

        response = await self.execute(
            application="bridge",
            data=bridge_target_with_vars,
            app_event_uuid=bridge_app_uuid,
        )

        logger.debug(f"Bridge command completed with response: {response}")
        return response, bleg_channel

    async def playback(self, path: str) -> CommandResult:
        """
        Plays an audio file on the channel and waits for it to complete.

        Args:
            path: The path to the audio file (accessible by FreeSWITCH).

        Returns:
            CommandResult: An object representing the completed command execution.
        """
        return await self.execute("playback", path)

    async def silence(self, ms: int) -> CommandResult:
        """
        Play silence for a specified duration and wait for it to complete.

        Args:
            ms: Duration of silence in milliseconds.

        Returns:
            CommandResult: An object representing the completed command execution.
        """
        logger.debug(f"Channel {self.uuid} playing {ms}ms of silence")
        path = f"silence_stream://{ms}"
        return await self.playback(path)

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
        Uses the 'say' application to speak text and waits for completion.

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
        return await self.execute("say", arguments)

    async def play_and_get_digits(
        self,
        min_digits: int,
        max_digits: int,
        tries: int,
        timeout: int,
        terminators: str,
        file: str,
        invalid_file: Optional[str] = None,
        var_name: Optional[str] = None,
        regexp: Optional[str] = None,
        digit_timeout: Optional[int] = None,
        transfer_on_failure: Optional[str] = None,
    ) -> CommandResult:
        """
        Executes the 'play_and_get_digits' application and waits for completion.

        Returns:
            CommandResult: An object representing the command execution result.
        """
        formatter: Callable[[Any], str] = lambda value: (
            "" if value is None else str(value)
        )
        ordered_args = [
            min_digits,
            max_digits,
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
        arguments = " ".join(map(formatter, ordered_args)).strip()
        return await self.execute("play_and_get_digits", arguments)

    async def set_variable(self, name: str, value: str) -> CommandResult:
        """
        Sets a channel variable on this channel.

        Args:
            name: The name of the variable.
            value: The value to set.

        Returns:
            CommandResult: An object representing the command execution result.
        """
        return await self.execute("set", f"{name}={value}")

    async def get_variable(self, name: str) -> Optional[str]:
        """
        Gets a channel variable's value from local cache.

        Args:
            name: The name of the variable.

        Returns:
            The variable value, or None if not found locally.
        """
        self._check_if_gone()
        return self.variables.get(name)

    @classmethod
    async def originate(
        cls,
        session: "Session",
        destination: str,
        uuid: Optional[str] = None,
        variables: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        application_after: str = "park()",
    ) -> "Channel":
        """
        Create a new channel using FreeSWITCH's originate command.

        Args:
            session: Session object to use for the new channel
            destination: FreeSWITCH endpoint string for the origination target
            uuid: Optional UUID for the new channel
            variables: Optional dictionary of variables to set for the call
            timeout: Optional timeout in seconds for call origination
            application_after: Application to execute after call is answered

        Returns:
            Channel: The newly created channel object

        Raises:
            OriginateError: If originate command fails
        """
        new_uuid = uuid if uuid else str(uuid4())
        logger.debug(
            f"Creating new channel with UUID {new_uuid} to destination {destination}"
        )

        new_channel = cls(new_uuid, session, initial_state=ChannelState.NEW)

        vars_dict = variables or {}
        vars_dict["origination_uuid"] = new_uuid

        try:
            await session.send(f"filter Unique-ID {new_uuid}")

            full_destination = f"{destination} &{application_after}"
            timeout_str = f"timeout={timeout}" if timeout else ""
            originate_cmd = (
                f"originate {build_variable_string(vars_dict)}"
                f"{full_destination} {timeout_str}"
            )

            logger.debug(f"Executing bgapi originate command: {originate_cmd}")
            result = await session.bgapi_execute(originate_cmd)

            logger.debug(
                f"Waiting for bgapi originate completion for channel {new_uuid}"
            )
            await result

            if result.completion_event and result.response:
                response_body = result.response.strip()
                logger.debug(f"Originate bgapi response: {response_body}")

                if response_body.startswith("-ERR") or "ERROR" in response_body.upper():
                    error_msg = response_body
                    logger.error(f"Originate bgapi failed: {error_msg}")
                    raise OriginateError(
                        f"Originate command failed: {error_msg}",
                        destination,
                        vars_dict,
                    )

            session.channels[new_uuid] = new_channel
            logger.info(f"Successfully initiated new channel {new_uuid} via bgapi")

            if new_channel.is_gone:
                logger.error(
                    f"Channel {new_uuid} was created but disconnected immediately"
                )
                raise OriginateError(
                    f"Channel {new_uuid} disconnected immediately",
                    destination,
                    vars_dict,
                )

            return new_channel

        except OriginateError:
            if new_uuid in session.channels:
                del session.channels[new_uuid]
            raise
        except Exception as e:
            if new_uuid in session.channels:
                del session.channels[new_uuid]
            logger.error(f"Failed to create channel via bgapi: {str(e)}")
            raise OriginateError(
                f"Failed to create channel: {str(e)}",
                destination,
                vars_dict,
            )

    async def unbridge(
        self, destination: Optional[str] = None, park: bool = True
    ) -> BackgroundJobResult:
        """
        Unbridges this channel from any connected channel.

        Args:
            destination: Optional destination for the channel after unbridging.
            park: If True, both channels will be parked after unbridging.

        Returns:
            BackgroundJobResult: An object that can be awaited for completion

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

        return result
