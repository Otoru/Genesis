from __future__ import annotations
from typing import Optional, Union, Dict, Literal, TYPE_CHECKING, Awaitable, Callable
from collections.abc import Coroutine
import asyncio
import time
from asyncio import Event, wait_for, TimeoutError as AsyncioTimeoutError
from uuid import uuid4

from opentelemetry import trace, metrics

from genesis.protocol import Protocol
from genesis.outbound import Session
from genesis.inbound import Inbound
from genesis.parser import ESLEvent
from genesis.types import HangupCause, ChannelState, ContextType
from genesis.exceptions import ChannelError, TimeoutError

tracer = trace.get_tracer(__name__)
meter = metrics.get_meter(__name__)

# Define metrics here to avoid circular imports
channel_operations_counter = meter.create_counter(
    "genesis.channel.operations",
    description="Number of channel operations",
    unit="1",
)

channel_operation_duration = meter.create_histogram(
    "genesis.channel.operation.duration",
    description="Duration of channel operations",
    unit="s",
)

hangup_causes_counter = meter.create_counter(
    "genesis.channel.hangup.causes",
    description="Hangup causes",
    unit="1",
)

bridge_operations_counter = meter.create_counter(
    "genesis.channel.bridge.operations",
    description="Bridge operations",
    unit="1",
)

dtmf_received_counter = meter.create_counter(
    "genesis.channel.dtmf.received",
    description="DTMF digits received",
    unit="1",
)

call_duration_histogram = meter.create_histogram(
    "genesis.call.duration",
    description="Total call duration from creation to hangup",
    unit="s",
)

timeout_counter = meter.create_counter(
    "genesis.timeouts",
    description="Number of timeouts",
    unit="1",
)


class Channel:
    """
    Channel class
    -------------

    Abstracts a FreeSWITCH channel (leg) creation and management.
    """

    def __init__(self, protocol: Protocol, dial_path: str) -> None:
        self.protocol = protocol
        self.dial_path = dial_path
        self.uuid: Optional[str] = None
        self._state: ChannelState = ChannelState.NEW
        self.context: ContextType = {}
        self._created_at: Optional[float] = None
        self._state_changes: Dict[ChannelState, float] = {}

    @property
    def state(self) -> ChannelState:
        """Read-only channel state, updated by FreeSWITCH events."""
        return self._state

    async def _state_handler(self, event: ESLEvent) -> None:
        """Updates internal state based on CHANNEL_STATE events."""
        if event.get("Unique-ID") == self.uuid:
            state_str = event.get("Channel-State")
            if state_str:
                new_state = ChannelState.from_freeswitch(state_str)
                if new_state != self._state:
                    # Track state change timestamp
                    self._state_changes[new_state] = time.time()
                self._state = new_state
            self.context.update(event)

    @classmethod
    async def create(
        cls,
        protocol: Protocol,
        dial_path: str,
        variables: Optional[Dict[str, str]] = None,
    ) -> "Channel":
        """
        Factory method to create and initialize a channel.

        Args:
            protocol: Protocol instance (Inbound or Session)
            dial_path: Destination to call (e.g., "user/1000")
            variables: Optional dictionary of custom variables for originate
        """
        start_time = time.time()
        self = cls(protocol, dial_path)
        self._created_at = start_time

        with tracer.start_as_current_span(
            "channel.create",
            attributes={
                "channel.dial_path": dial_path,
                "channel.has_variables": str(variables is not None),
            },
        ) as span:
            try:
                if isinstance(protocol, Inbound):
                    await self.protocol.send("events plain ALL")

                response = await self.protocol.send("api create_uuid")
                if not response.body:
                    raise ChannelError("Failed to retrieve UUID from FreeSWITCH")
                self.uuid = response.body.strip()
                span.set_attribute("channel.uuid", self.uuid)

                self.protocol.on("CHANNEL_STATE", self._state_handler)
                await self.protocol.send(f"filter Unique-ID {self.uuid}")

                default_variables = {
                    "origination_uuid": self.uuid,
                    "return_ring_ready": "true",
                }

                if variables:
                    for key, value in variables.items():
                        if key not in default_variables:
                            default_variables[key] = value

                options = [f"{key}={value}" for key, value in default_variables.items()]
                cmd = f"api originate {{{','.join(options)}}}{self.dial_path} &park()"
                await self.protocol.send(cmd)

                duration = time.time() - start_time
                span.set_attribute("channel.create.duration", duration)
                channel_operations_counter.add(1, attributes={"operation": "create"})
                channel_operation_duration.record(
                    duration, attributes={"operation": "create"}
                )

                return self
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                raise

    @classmethod
    async def from_session(cls, session: "Session") -> "Channel":
        """
        Factory method to create a Channel from an existing Session (outbound mode).

        This wraps an existing channel that was already created by FreeSWITCH
        when the Session was established.

        Args:
            session: Session instance with an existing channel

        Returns:
            Channel instance representing the session's channel

        Raises:
            ChannelError: If session doesn't have a valid UUID in context
        """
        if not session.uuid:
            raise ChannelError(
                "Session does not have a valid UUID. Ensure session context is initialized."
            )

        # Extract dial_path from context if available, otherwise use empty string
        dial_path = session.context.get("Channel-Name", "")
        if isinstance(dial_path, list):
            dial_path = dial_path[0] if dial_path else ""
        elif not isinstance(dial_path, str):
            dial_path = ""

        self = cls(session, dial_path)
        self.uuid = session.uuid
        self.context.update(session.context)

        # Initialize state from context if available
        channel_state = session.context.get("Channel-State")
        if channel_state:
            if isinstance(channel_state, list):
                channel_state = channel_state[0]
            if isinstance(channel_state, str):
                try:
                    self._state = ChannelState.from_freeswitch(channel_state)
                except (KeyError, ValueError):
                    # If state parsing fails, start with NEW
                    pass

        # Register state handler to track channel state changes
        self.protocol.on("CHANNEL_STATE", self._state_handler)

        return self

    async def wait(
        self, target: Union[ChannelState, str], timeout: float = 30.0
    ) -> Optional[ESLEvent]:
        """
        Wait for the channel to reach a target state or receive a specific event.

        When waiting for a state (ChannelState):
        - For EXECUTE state, also waits for CHANNEL_ANSWER event to ensure call is actually answered.

        When waiting for an event (str):
        - Waits for a specific event name (e.g., "DTMF", "CHANNEL_HANGUP").

        Args:
            target: Either a ChannelState to wait for, or a string event name
            timeout: Maximum time to wait in seconds. Default: 30.0

        Returns:
            The event received, or None if timeout or channel destroyed

        Raises:
            TimeoutError: If timeout is reached and target was not reached

        Example:
            # Wait for state
            await channel.wait(ChannelState.EXECUTE, timeout=10.0)

            # Wait for event
            event = await channel.wait("DTMF", timeout=10.0)
            digit = event.get("DTMF-Digit")
        """
        start_time = time.time()
        wait_type = "event" if isinstance(target, str) else "state"

        with tracer.start_as_current_span(
            "channel.wait",
            attributes={
                "channel.uuid": self.uuid or "unknown",
                "channel.state": self.state.name,
                "wait.target": str(target),
                "wait.timeout": timeout,
                "wait.type": wait_type,
                "operation": "wait",
            },
        ) as span:
            # Handle event name (string)
            if isinstance(target, str):
                event_name = target
                received_event: Optional[ESLEvent] = None
                event_ready = Event()

                async def event_handler(event: ESLEvent) -> None:
                    nonlocal received_event
                    # Filter by channel UUID only for channel-specific events
                    # Events like DTMF, CHANNEL_HANGUP, etc. may not have matching UUID
                    # Only filter for events that are definitely channel-specific
                    channel_specific_events = {
                        "CHANNEL_STATE",
                        "CHANNEL_ANSWER",
                        "CHANNEL_HANGUP_COMPLETE",
                    }
                    if (
                        event_name in channel_specific_events
                        and self.uuid
                        and event.get("Unique-ID") != self.uuid
                    ):
                        return
                    received_event = event
                    event_ready.set()

                self.protocol.on(event_name, event_handler)

                try:
                    await wait_for(event_ready.wait(), timeout=timeout)
                    duration = time.time() - start_time
                    span.set_attribute("wait.result", "success")
                    span.set_attribute("wait.duration", duration)
                    channel_operations_counter.add(
                        1,
                        attributes={
                            "operation": "wait",
                            "wait.type": wait_type,
                            "success": "true",
                        },
                    )
                    return received_event
                except AsyncioTimeoutError:
                    duration = time.time() - start_time
                    self.protocol.remove(event_name, event_handler)
                    span.set_attribute("wait.result", "timeout")
                    span.set_attribute("wait.duration", duration)
                    timeout_counter.add(
                        1,
                        attributes={
                            "timeout.type": "wait",
                            "timeout.operation": f"wait.event.{event_name}",
                            "timeout.duration": duration,
                        },
                    )
                    channel_operations_counter.add(
                        1,
                        attributes={
                            "operation": "wait",
                            "wait.type": wait_type,
                            "success": "false",
                            "error": "TimeoutError",
                        },
                    )
                    raise TimeoutError(
                        f"Event '{event_name}' not received within {timeout}s timeout"
                    )
                finally:
                    self.protocol.remove(event_name, event_handler)

            # Handle state (ChannelState)
            target_state = target
            if self.state >= ChannelState.HANGUP or (
                self.state == target_state and target_state != ChannelState.EXECUTE
            ):
                span.set_attribute("wait.result", "already_reached")
                return None

            state_event_received: Optional[ESLEvent] = None
            state_reached = Event()
            answer_received = Event() if target_state == ChannelState.EXECUTE else None

            async def state_handler(event: ESLEvent) -> None:
                nonlocal state_event_received
                if event.get("Unique-ID") != self.uuid:
                    return

                state_str = event.get("Channel-State")
                if not state_str:
                    return

                event_state = ChannelState.from_freeswitch(state_str)
                if event_state == target_state or event_state >= ChannelState.HANGUP:
                    self._state = event_state
                    self.context.update(event)
                    state_event_received = event
                    if target_state != ChannelState.EXECUTE or (
                        answer_received and answer_received.is_set()
                    ):
                        state_reached.set()

            async def answer_handler(event: ESLEvent) -> None:
                if event.get("Unique-ID") == self.uuid and answer_received:
                    answer_received.set()
                    if self.state == ChannelState.EXECUTE:
                        state_reached.set()

            self.protocol.on("CHANNEL_STATE", state_handler)
            if target_state == ChannelState.EXECUTE:
                self.protocol.on("CHANNEL_ANSWER", answer_handler)

            try:
                await wait_for(state_reached.wait(), timeout=timeout)
                duration = time.time() - start_time
                span.set_attribute("wait.result", "success")
                span.set_attribute("wait.duration", duration)
                channel_operations_counter.add(
                    1,
                    attributes={
                        "operation": "wait",
                        "wait.type": wait_type,
                        "success": "true",
                    },
                )
                return state_event_received if self.state == target_state else None
            except AsyncioTimeoutError:
                duration = time.time() - start_time
                span.set_attribute("wait.result", "timeout")
                span.set_attribute("wait.duration", duration)
                timeout_counter.add(
                    1,
                    attributes={
                        "timeout.type": "wait",
                        "timeout.operation": f"wait.state.{target_state.name}",
                        "timeout.duration": duration,
                    },
                )
                channel_operations_counter.add(
                    1,
                    attributes={
                        "operation": "wait",
                        "wait.type": wait_type,
                        "success": "false",
                        "error": "TimeoutError",
                    },
                )
                raise TimeoutError(
                    f"Channel did not reach {target_state.name} state within {timeout}s"
                )
            finally:
                self.protocol.remove("CHANNEL_STATE", state_handler)
                if target_state == ChannelState.EXECUTE:
                    self.protocol.remove("CHANNEL_ANSWER", answer_handler)

    async def _sendmsg_or_send(
        self,
        command: str,
        application: str,
        data: Optional[str] = None,
        block: bool = False,
        timeout: Optional[float] = None,
    ) -> ESLEvent:
        """Helper to use sendmsg if available (Session) or send with api (Inbound)."""
        if isinstance(self.protocol, Session):
            return await self.protocol.sendmsg(
                command, application, data, block=block, timeout=timeout
            )
        else:
            # For Inbound, use api commands
            if command == "execute":
                if data:
                    cmd = f"api uuid_execute {self.uuid} {application} {data}"
                else:
                    cmd = f"api uuid_execute {self.uuid} {application}"
            elif command == "hangup":
                cause = data or "NORMAL_CLEARING"
                cmd = f"api uuid_kill {self.uuid} {cause}"
            else:
                raise ChannelError(
                    f"Command {command} not supported for Inbound protocol"
                )
            return await self.protocol.send(cmd)

    async def answer(self) -> ESLEvent:
        """Answer the call associated with the channel."""
        start_time = time.time()
        operation = "answer"

        with tracer.start_as_current_span(
            "channel.answer",
            attributes={
                "channel.uuid": self.uuid or "unknown",
                "channel.state": self.state.name,
                "operation": operation,
            },
        ) as span:
            try:
                result = await self._sendmsg_or_send("execute", "answer")
                duration = time.time() - start_time

                success = result.get("Reply-Text", "").startswith("+OK")
                span.set_attribute("channel.answer.success", success)
                span.set_attribute("channel.answer.duration", duration)

                channel_operations_counter.add(
                    1,
                    attributes={
                        "operation": operation,
                        "success": str(success),
                    },
                )
                channel_operation_duration.record(
                    duration,
                    attributes={
                        "operation": operation,
                    },
                )

                return result
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                channel_operations_counter.add(
                    1,
                    attributes={
                        "operation": operation,
                        "success": "false",
                        "error": type(e).__name__,
                    },
                )
                raise

    async def park(self) -> ESLEvent:
        """Move channel-associated call to park."""
        start_time = time.time()
        operation = "park"

        with tracer.start_as_current_span(
            "channel.park",
            attributes={
                "channel.uuid": self.uuid or "unknown",
                "channel.state": self.state.name,
                "operation": operation,
            },
        ) as span:
            try:
                result = await self._sendmsg_or_send("execute", "park")
                duration = time.time() - start_time

                success = result.get("Reply-Text", "").startswith("+OK")
                span.set_attribute("channel.park.success", success)
                span.set_attribute("channel.park.duration", duration)

                channel_operations_counter.add(
                    1,
                    attributes={
                        "operation": operation,
                        "success": str(success),
                    },
                )
                channel_operation_duration.record(
                    duration,
                    attributes={
                        "operation": operation,
                    },
                )

                return result
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                channel_operations_counter.add(
                    1,
                    attributes={
                        "operation": operation,
                        "success": "false",
                        "error": type(e).__name__,
                    },
                )
                raise

    async def hangup(self, cause: HangupCause = "NORMAL_CLEARING") -> ESLEvent:
        """Hang up the call associated with the channel."""
        start_time = time.time()
        operation = "hangup"

        # Calculate call duration if channel was created
        call_duration = None
        if self._created_at:
            call_duration = time.time() - self._created_at

        with tracer.start_as_current_span(
            "channel.hangup",
            attributes={
                "channel.uuid": self.uuid or "unknown",
                "channel.state": self.state.name,
                "hangup.cause": cause,
                "operation": operation,
            },
        ) as span:
            try:
                if isinstance(self.protocol, Session):
                    result = await self._sendmsg_or_send("execute", "hangup", cause)
                else:
                    # For Inbound, use api uuid_kill directly
                    result = await self.protocol.send(
                        f"api uuid_kill {self.uuid} {cause}"
                    )

                duration = time.time() - start_time
                success = result.get("Reply-Text", "").startswith("+OK")

                span.set_attribute("channel.hangup.success", success)
                span.set_attribute("channel.hangup.duration", duration)
                if call_duration is not None:
                    span.set_attribute("call.duration", call_duration)
                    call_duration_histogram.record(call_duration)

                hangup_causes_counter.add(1, attributes={"hangup.cause": cause})
                channel_operations_counter.add(
                    1,
                    attributes={
                        "operation": operation,
                        "success": str(success),
                        "hangup.cause": cause,
                    },
                )
                channel_operation_duration.record(
                    duration,
                    attributes={
                        "operation": operation,
                    },
                )

                return result
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                hangup_causes_counter.add(
                    1, attributes={"hangup.cause": cause, "error": type(e).__name__}
                )
                channel_operations_counter.add(
                    1,
                    attributes={
                        "operation": operation,
                        "success": "false",
                        "error": type(e).__name__,
                    },
                )
                raise

    async def bridge(self, other: Union["Channel", "Session"]) -> ESLEvent:
        """
        Bridges this channel with another channel or session.

        Returns:
            The event response from FreeSWITCH.
        """
        start_time = time.time()
        operation = "bridge"

        if self.state >= ChannelState.HANGUP:
            raise ChannelError(f"Cannot bridge channel in state {self.state.name}")

        other_uuid = None

        if hasattr(other, "uuid"):
            other_uuid = other.uuid
        elif hasattr(other, "context"):  # Session
            unique_id = other.context.get("Unique-ID")
            if isinstance(unique_id, list):
                other_uuid = unique_id[0]
            else:
                other_uuid = unique_id

        if not self.uuid or not other_uuid:
            raise ChannelError("Both channels must have valid UUIDs to bridge.")

        with tracer.start_as_current_span(
            "channel.bridge",
            attributes={
                "channel.uuid": self.uuid or "unknown",
                "channel.other_uuid": other_uuid or "unknown",
                "channel.state": self.state.name,
                "operation": operation,
            },
        ) as span:
            try:
                if isinstance(self.protocol, Session):
                    result = await self.protocol.sendmsg(
                        "execute", "bridge", f"uuid:{other_uuid}"
                    )
                else:
                    result = await self.protocol.send(
                        f"api uuid_bridge {self.uuid} {other_uuid}"
                    )

                duration = time.time() - start_time
                success = result.get("Reply-Text", "").startswith("+OK")

                span.set_attribute("channel.bridge.success", success)
                span.set_attribute("channel.bridge.duration", duration)

                bridge_operations_counter.add(
                    1,
                    attributes={
                        "success": str(success),
                    },
                )
                channel_operations_counter.add(
                    1,
                    attributes={
                        "operation": operation,
                        "success": str(success),
                    },
                )
                channel_operation_duration.record(
                    duration,
                    attributes={
                        "operation": operation,
                    },
                )

                return result
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                bridge_operations_counter.add(
                    1,
                    attributes={
                        "success": "false",
                        "error": type(e).__name__,
                    },
                )
                channel_operations_counter.add(
                    1,
                    attributes={
                        "operation": operation,
                        "success": "false",
                        "error": type(e).__name__,
                    },
                )
                raise

    async def playback(
        self, path: str, block: bool = True, timeout: Optional[float] = None
    ) -> ESLEvent:
        """Requests the freeswitch to play an audio."""
        start_time = time.time()
        operation = "playback"

        with tracer.start_as_current_span(
            "channel.playback",
            attributes={
                "channel.uuid": self.uuid or "unknown",
                "channel.state": self.state.name,
                "playback.path": path,
                "playback.block": str(block),
                "operation": operation,
            },
        ) as span:
            try:
                result = await self._sendmsg_or_send(
                    "execute", "playback", path, block=block, timeout=timeout
                )
                duration = time.time() - start_time

                success = result.get("Reply-Text", "").startswith("+OK")
                span.set_attribute("channel.playback.success", success)
                span.set_attribute("channel.playback.duration", duration)

                channel_operations_counter.add(
                    1,
                    attributes={
                        "operation": operation,
                        "success": str(success),
                    },
                )
                channel_operation_duration.record(
                    duration,
                    attributes={
                        "operation": operation,
                    },
                )

                return result
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                channel_operations_counter.add(
                    1,
                    attributes={
                        "operation": operation,
                        "success": "false",
                        "error": type(e).__name__,
                    },
                )
                raise

    async def say(
        self,
        text: str,
        module: str = "en",
        lang: Optional[str] = None,
        kind: str = "NUMBER",
        method: str = "pronounced",
        gender: str = "FEMININE",
        block: bool = True,
        timeout: Optional[float] = None,
    ) -> ESLEvent:
        """The say application will use the pre-recorded sound files to read or say things."""
        start_time = time.time()
        operation = "say"

        if lang:
            module += f":{lang}"

        arguments = f"{module} {kind} {method} {gender} {text}"
        from genesis.logger import logger

        logger.debug(f"Arguments used in say command: {arguments}")

        with tracer.start_as_current_span(
            "channel.say",
            attributes={
                "channel.uuid": self.uuid or "unknown",
                "channel.state": self.state.name,
                "say.module": module,
                "say.kind": kind,
                "say.method": method,
                "say.gender": gender,
                "operation": operation,
            },
        ) as span:
            try:
                result = await self._sendmsg_or_send(
                    "execute", "say", arguments, block=block, timeout=timeout
                )
                duration = time.time() - start_time

                success = result.get("Reply-Text", "").startswith("+OK")
                span.set_attribute("channel.say.success", success)
                span.set_attribute("channel.say.duration", duration)

                channel_operations_counter.add(
                    1,
                    attributes={
                        "operation": operation,
                        "success": str(success),
                    },
                )
                channel_operation_duration.record(
                    duration,
                    attributes={
                        "operation": operation,
                    },
                )

                return result
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                channel_operations_counter.add(
                    1,
                    attributes={
                        "operation": operation,
                        "success": "false",
                        "error": type(e).__name__,
                    },
                )
                raise

    async def play_and_get_digits(
        self,
        tries: int,
        timeout: int,
        terminators: str,
        file: str,
        minimal: int = 0,
        maximum: int = 128,
        block: bool = True,
        regexp: Optional[str] = None,
        var_name: Optional[str] = None,
        invalid_file: Optional[str] = None,
        digit_timeout: Optional[int] = None,
        transfer_on_failure: Optional[str] = None,
        sendmsg_timeout: Optional[float] = None,
    ) -> ESLEvent:
        """Play a file and collect digits from the caller."""
        start_time = time.time()
        operation = "play_and_get_digits"

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
        from genesis.logger import logger

        logger.debug(f"Arguments used in play_and_get_digits command: {arguments}")

        with tracer.start_as_current_span(
            "channel.play_and_get_digits",
            attributes={
                "channel.uuid": self.uuid or "unknown",
                "channel.state": self.state.name,
                "play_and_get_digits.file": file,
                "play_and_get_digits.tries": tries,
                "play_and_get_digits.timeout": timeout,
                "play_and_get_digits.minimal": minimal,
                "play_and_get_digits.maximum": maximum,
                "operation": operation,
            },
        ) as span:
            try:
                result = await self._sendmsg_or_send(
                    "execute",
                    "play_and_get_digits",
                    arguments,
                    block=block,
                    timeout=sendmsg_timeout,
                )
                duration = time.time() - start_time

                success = result.get("Reply-Text", "").startswith("+OK")
                span.set_attribute("channel.play_and_get_digits.success", success)
                span.set_attribute("channel.play_and_get_digits.duration", duration)

                channel_operations_counter.add(
                    1,
                    attributes={
                        "operation": operation,
                        "success": str(success),
                    },
                )
                channel_operation_duration.record(
                    duration,
                    attributes={
                        "operation": operation,
                    },
                )

                return result
            except Exception as e:
                span.record_exception(e)
                span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                channel_operations_counter.add(
                    1,
                    attributes={
                        "operation": operation,
                        "success": "false",
                        "error": type(e).__name__,
                    },
                )
                raise

    async def log(
        self,
        level: Literal[
            "CONSOLE", "ALERT", "CRIT", "ERR", "WARNING", "NOTICE", "INFO", "DEBUG"
        ],
        message: str,
    ) -> ESLEvent:
        """Log a message to FreeSWITCH using dp tools log."""
        return await self._sendmsg_or_send("execute", "log", f"{level} {message}")

    def onDTMF(
        self, digit: Optional[str] = None
    ) -> Callable[[Callable[[str], Awaitable[None]]], Callable[[str], Awaitable[None]]]:
        """
        Decorator to register a handler for DTMF events.

        Args:
            digit: Optional specific digit to listen for (e.g., "1", "2", "*", "#").
                   If None, handler receives all DTMF digits.

        Example:
            @channel.onDTMF("1")
            async def handle_option_one(dtmf: str):
                await channel.playback("/sounds/option_one.wav")

            @channel.onDTMF()  # Receives all DTMF
            async def handle_any_dtmf(dtmf: str):
                logger.info(f"Received DTMF: {dtmf}")
        """

        def decorator(
            func: Callable[[str], Awaitable[None]]
        ) -> Callable[[str], Awaitable[None]]:
            async def dtmf_handler(event: ESLEvent) -> None:
                dtmf_digit = event.get("DTMF-Digit")
                if dtmf_digit:
                    # If specific digit filter is set, only call handler for that digit
                    if digit is None or dtmf_digit == digit:
                        with tracer.start_as_current_span(
                            "channel.dtmf.received",
                            attributes={
                                "channel.uuid": self.uuid or "unknown",
                                "dtmf.digit": dtmf_digit,
                            },
                        ) as span:
                            try:
                                dtmf_received_counter.add(
                                    1, attributes={"dtmf.digit": dtmf_digit}
                                )
                                await func(dtmf_digit)
                                span.set_attribute("dtmf.handled", True)
                            except Exception as e:
                                span.record_exception(e)
                                span.set_status(
                                    trace.Status(trace.StatusCode.ERROR, str(e))
                                )
                                raise

            # Register the handler for DTMF events
            self.protocol.on("DTMF", dtmf_handler)
            return func

        return decorator
