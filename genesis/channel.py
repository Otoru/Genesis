from __future__ import annotations

from typing import (
    Any,
    Mapping,
    Optional,
    Union,
    Dict,
    Literal,
    TYPE_CHECKING,
    Awaitable,
    Callable,
)
from collections.abc import Coroutine
import time
from asyncio import Event, wait_for, TimeoutError as AsyncioTimeoutError

from opentelemetry import trace, metrics

from genesis.protocol import Protocol
from genesis.session import Session
from genesis.inbound import Inbound
from genesis.protocol.parser import ESLEvent
from genesis.types import HangupCause, ChannelState, ContextType
from genesis.exceptions import ChannelError, TimeoutError
from genesis.observability import logger

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

# Span/attribute names (S1192: avoid duplicated literals)
ATTR_CHANNEL_UUID = "channel.uuid"
ATTR_CHANNEL_STATE = "channel.state"
ATTR_HANGUP_CAUSE = "hangup.cause"
ATTR_WAIT_TYPE = "wait.type"
ATTR_WAIT_RESULT = "wait.result"
ATTR_WAIT_DURATION = "wait.duration"


def _context_str(context: Mapping[str, Any], key: str) -> str:
    """Get a string value from context, normalizing list or non-string to str."""
    value = context.get(key, "")
    if isinstance(value, list):
        return value[0] if value else ""
    return value if isinstance(value, str) else ""


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

    def _state_handler(self, event: ESLEvent) -> None:
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
                span.set_attribute(ATTR_CHANNEL_UUID, self.uuid)

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
    def from_session(cls, session: "Session") -> "Channel":
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

        dial_path = _context_str(session.context, "Channel-Name")
        self = cls(session, dial_path)
        self.uuid = session.uuid
        self.context.update(session.context)

        channel_state = _context_str(session.context, "Channel-State")
        if channel_state:
            try:
                self._state = ChannelState.from_freeswitch(channel_state)
            except (KeyError, ValueError):
                pass

        # Register state handler for O(1) routing of CHANNEL_STATE for this channel
        self.protocol.register_channel_handler(
            self.uuid, "CHANNEL_STATE", self._state_handler
        )

        return self

    async def _wait_for_event(
        self,
        event_name: str,
        timeout: float,
    ) -> ESLEvent:
        """Wait for a specific event; raises TimeoutError if not received."""
        received_event: Optional[ESLEvent] = None
        event_ready = Event()

        def event_handler(event: ESLEvent) -> None:
            nonlocal received_event
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
            assert received_event is not None
            return received_event
        except AsyncioTimeoutError:
            raise TimeoutError(
                f"Event '{event_name}' not received within {timeout}s timeout"
            )
        finally:
            self.protocol.remove(event_name, event_handler)

    async def _wait_for_state(
        self,
        target_state: ChannelState,
        timeout: float,
    ) -> Optional[ESLEvent]:
        """Wait for channel to reach target state; raises TimeoutError if not reached."""
        state_event_received: Optional[ESLEvent] = None
        state_reached = Event()
        answer_received = Event() if target_state == ChannelState.EXECUTE else None

        def state_handler(event: ESLEvent) -> None:
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

        def answer_handler(event: ESLEvent) -> None:
            if event.get("Unique-ID") == self.uuid and answer_received:
                answer_received.set()
                if self.state == ChannelState.EXECUTE:
                    state_reached.set()

        self.protocol.on("CHANNEL_STATE", state_handler)
        if target_state == ChannelState.EXECUTE:
            self.protocol.on("CHANNEL_ANSWER", answer_handler)
        try:
            await wait_for(state_reached.wait(), timeout=timeout)
            return state_event_received if self.state == target_state else None
        except AsyncioTimeoutError:
            raise TimeoutError(
                f"Channel did not reach {target_state.name} state within {timeout}s"
            )
        finally:
            self.protocol.remove("CHANNEL_STATE", state_handler)
            if target_state == ChannelState.EXECUTE:
                self.protocol.remove("CHANNEL_ANSWER", answer_handler)

    def _record_wait_success(
        self,
        span: Any,
        start_time: float,
        wait_type: str,
    ) -> None:
        """Record successful wait in span and metrics."""
        duration = time.time() - start_time
        span.set_attribute(ATTR_WAIT_RESULT, "success")
        span.set_attribute(ATTR_WAIT_DURATION, duration)
        channel_operations_counter.add(
            1,
            attributes={
                "operation": "wait",
                ATTR_WAIT_TYPE: wait_type,
                "success": "true",
            },
        )

    def _record_wait_timeout(
        self,
        span: Any,
        start_time: float,
        wait_type: str,
        timeout_operation: str,
    ) -> None:
        """Record wait timeout in span and metrics."""
        duration = time.time() - start_time
        span.set_attribute(ATTR_WAIT_RESULT, "timeout")
        span.set_attribute(ATTR_WAIT_DURATION, duration)
        timeout_counter.add(
            1,
            attributes={
                "timeout.type": "wait",
                "timeout.operation": timeout_operation,
                "timeout.duration": duration,
            },
        )
        channel_operations_counter.add(
            1,
            attributes={
                "operation": "wait",
                ATTR_WAIT_TYPE: wait_type,
                "success": "false",
                "error": "TimeoutError",
            },
        )

    async def wait(
        self,
        target: Union[ChannelState, str],
        timeout: float = 30.0,
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
                ATTR_CHANNEL_UUID: self.uuid or "unknown",
                ATTR_CHANNEL_STATE: self.state.name,
                "wait.target": str(target),
                "wait.timeout": timeout,
                ATTR_WAIT_TYPE: wait_type,
                "operation": "wait",
            },
        ) as span:
            if isinstance(target, str):
                try:
                    result = await self._wait_for_event(target, timeout)
                    self._record_wait_success(span, start_time, wait_type)
                    return result
                except TimeoutError:
                    self._record_wait_timeout(
                        span, start_time, wait_type, f"wait.event.{target}"
                    )
                    raise

            target_state = target
            if self.state >= ChannelState.HANGUP or (
                self.state == target_state and target_state != ChannelState.EXECUTE
            ):
                span.set_attribute(ATTR_WAIT_RESULT, "already_reached")
                return None

            try:
                state_result = await self._wait_for_state(target_state, timeout)
                self._record_wait_success(span, start_time, wait_type)
                return state_result
            except TimeoutError:
                self._record_wait_timeout(
                    span, start_time, wait_type, f"wait.state.{target_state.name}"
                )
                raise

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

    def _get_peer_uuid(self, other: Union["Channel", "Session"]) -> Optional[str]:
        """Extract UUID from a Channel or Session for bridge/peer operations."""
        if hasattr(other, "uuid") and other.uuid:
            return other.uuid
        if hasattr(other, "context"):
            unique_id = other.context.get("Unique-ID")
            if isinstance(unique_id, list):
                return unique_id[0] if unique_id else None
            return unique_id if isinstance(unique_id, str) else None
        return None

    async def _execute_operation(
        self,
        operation: str,
        span_name: str,
        span_attributes: Dict[str, Any],
        get_result: Callable[[], Awaitable[ESLEvent]],
        extra_on_success: Optional[Callable[[Any, ESLEvent, float], None]] = None,
        extra_on_error: Optional[Callable[[Exception], None]] = None,
    ) -> ESLEvent:
        """Run a channel operation with tracing and metrics (single implementation)."""
        start_time = time.time()
        with tracer.start_as_current_span(
            span_name, attributes=span_attributes
        ) as span:
            try:
                result = await get_result()
                duration = time.time() - start_time
                success = result.get("Reply-Text", "").startswith("+OK")
                span.set_attribute(f"channel.{operation}.success", success)
                span.set_attribute(f"channel.{operation}.duration", duration)
                channel_operations_counter.add(
                    1,
                    attributes={"operation": operation, "success": str(success)},
                )
                channel_operation_duration.record(
                    duration, attributes={"operation": operation}
                )
                if extra_on_success:
                    extra_on_success(span, result, duration)
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
                if extra_on_error:
                    extra_on_error(e)
                raise

    async def answer(self) -> ESLEvent:
        """Answer the call associated with the channel."""
        return await self._execute_operation(
            "answer",
            "channel.answer",
            {
                ATTR_CHANNEL_UUID: self.uuid or "unknown",
                ATTR_CHANNEL_STATE: self.state.name,
                "operation": "answer",
            },
            lambda: self._sendmsg_or_send("execute", "answer"),
        )

    async def park(self) -> ESLEvent:
        """Move channel-associated call to park."""
        return await self._execute_operation(
            "park",
            "channel.park",
            {
                ATTR_CHANNEL_UUID: self.uuid or "unknown",
                ATTR_CHANNEL_STATE: self.state.name,
                "operation": "park",
            },
            lambda: self._sendmsg_or_send("execute", "park"),
        )

    async def hangup(self, cause: HangupCause = "NORMAL_CLEARING") -> ESLEvent:
        """Hang up the call associated with the channel."""
        call_duration = time.time() - self._created_at if self._created_at else None

        def on_success(span: Any, result: ESLEvent, duration: float) -> None:
            hangup_causes_counter.add(1, attributes={ATTR_HANGUP_CAUSE: cause})
            if call_duration is not None:
                span.set_attribute("call.duration", call_duration)
                call_duration_histogram.record(call_duration)

        def on_error(exc: Exception) -> None:
            hangup_causes_counter.add(
                1,
                attributes={ATTR_HANGUP_CAUSE: cause, "error": type(exc).__name__},
            )

        async def do_hangup() -> ESLEvent:
            if isinstance(self.protocol, Session):
                return await self._sendmsg_or_send("execute", "hangup", cause)
            if self.protocol is not None:
                return await self.protocol.send(f"api uuid_kill {self.uuid} {cause}")
            raise ChannelError("Protocol not connected")

        return await self._execute_operation(
            "hangup",
            "channel.hangup",
            {
                ATTR_CHANNEL_UUID: self.uuid or "unknown",
                ATTR_CHANNEL_STATE: self.state.name,
                ATTR_HANGUP_CAUSE: cause,
                "operation": "hangup",
            },
            do_hangup,
            extra_on_success=on_success,
            extra_on_error=on_error,
        )

    async def bridge(self, other: Union["Channel", "Session"]) -> ESLEvent:
        """
        Bridges this channel with another channel or session.

        Returns:
            The event response from FreeSWITCH.
        """
        if self.state >= ChannelState.HANGUP:
            raise ChannelError(f"Cannot bridge channel in state {self.state.name}")

        other_uuid = self._get_peer_uuid(other)
        if not self.uuid or not other_uuid:
            raise ChannelError("Both channels must have valid UUIDs to bridge.")

        def on_success(span: Any, result: ESLEvent, duration: float) -> None:
            success = result.get("Reply-Text", "").startswith("+OK")
            bridge_operations_counter.add(1, attributes={"success": str(success)})

        def on_error(exc: Exception) -> None:
            bridge_operations_counter.add(
                1, attributes={"success": "false", "error": type(exc).__name__}
            )

        async def do_bridge() -> ESLEvent:
            if isinstance(self.protocol, Session):
                return await self.protocol.sendmsg(
                    "execute", "bridge", f"uuid:{other_uuid}"
                )
            return await self.protocol.send(f"api uuid_bridge {self.uuid} {other_uuid}")

        return await self._execute_operation(
            "bridge",
            "channel.bridge",
            {
                ATTR_CHANNEL_UUID: self.uuid or "unknown",
                "channel.other_uuid": other_uuid or "unknown",
                ATTR_CHANNEL_STATE: self.state.name,
                "operation": "bridge",
            },
            do_bridge,
            extra_on_success=on_success,
            extra_on_error=on_error,
        )

    async def playback(
        self,
        path: str,
        block: bool = True,
        timeout: Optional[float] = None,
    ) -> ESLEvent:
        """Requests the freeswitch to play an audio."""
        return await self._execute_operation(
            "playback",
            "channel.playback",
            {
                ATTR_CHANNEL_UUID: self.uuid or "unknown",
                ATTR_CHANNEL_STATE: self.state.name,
                "playback.path": path,
                "playback.block": str(block),
                "operation": "playback",
            },
            lambda: self._sendmsg_or_send(
                "execute", "playback", path, block=block, timeout=timeout
            ),
        )

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
        if lang:
            module += f":{lang}"
        arguments = f"{module} {kind} {method} {gender} {text}"
        logger.debug(f"Arguments used in say command: {arguments}")

        return await self._execute_operation(
            "say",
            "channel.say",
            {
                ATTR_CHANNEL_UUID: self.uuid or "unknown",
                ATTR_CHANNEL_STATE: self.state.name,
                "say.module": module,
                "say.kind": kind,
                "say.method": method,
                "say.gender": gender,
                "operation": "say",
            },
            lambda: self._sendmsg_or_send(
                "execute", "say", arguments, block=block, timeout=timeout
            ),
        )

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
        arguments = " ".join(formatter(x) for x in ordered_arguments)
        logger.debug(f"Arguments used in play_and_get_digits command: {arguments}")

        return await self._execute_operation(
            "play_and_get_digits",
            "channel.play_and_get_digits",
            {
                ATTR_CHANNEL_UUID: self.uuid or "unknown",
                ATTR_CHANNEL_STATE: self.state.name,
                "play_and_get_digits.file": file,
                "play_and_get_digits.tries": str(tries),
                "play_and_get_digits.timeout": str(timeout),
                "play_and_get_digits.minimal": str(minimal),
                "play_and_get_digits.maximum": str(maximum),
                "operation": "play_and_get_digits",
            },
            lambda: self._sendmsg_or_send(
                "execute",
                "play_and_get_digits",
                arguments,
                block=block,
                timeout=sendmsg_timeout,
            ),
        )

    async def log(
        self,
        level: Literal[
            "CONSOLE", "ALERT", "CRIT", "ERR", "WARNING", "NOTICE", "INFO", "DEBUG"
        ],
        message: str,
    ) -> ESLEvent:
        """Log a message to FreeSWITCH using dp tools log."""
        return await self._sendmsg_or_send("execute", "log", f"{level} {message}")

    def on_dtmf(
        self, digit: Optional[str] = None
    ) -> Callable[[Callable[[str], Awaitable[None]]], Callable[[str], Awaitable[None]]]:
        """
        Decorator to register a handler for DTMF events.

        Args:
            digit: Optional specific digit to listen for (e.g., "1", "2", "*", "#").
                   If None, handler receives all DTMF digits.

        Example:
            @channel.on_dtmf("1")
            async def handle_option_one(dtmf: str):
                await channel.playback("/sounds/option_one.wav")

            @channel.on_dtmf()  # Receives all DTMF
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
                                ATTR_CHANNEL_UUID: self.uuid or "unknown",
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
