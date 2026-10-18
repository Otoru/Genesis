from __future__ import annotations

import contextlib
import re
import time
from asyncio import (
    FIRST_COMPLETED,
    AbstractEventLoop,
    CancelledError,
    Event,
    Task,
    create_task,
    get_running_loop,
    wait,
    wait_for,
    TimeoutError as AsyncioTimeoutError,
)
from collections.abc import Coroutine
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    List,
    Literal,
    Mapping,
    Optional,
    TypeVar,
    Union,
    cast,
    TYPE_CHECKING,
)

from opentelemetry import trace

from genesis.protocol import Protocol
from genesis.session import (
    Session,
    _build_sendmsg_cmd,
    _install_execution_wait,
    _rejected,
)
from genesis.inbound import Inbound
from genesis.protocol.parser import ESLEvent, parse_headers
from genesis.protocol.metrics import (
    channel_operations_counter,
    channel_operation_duration,
    hangup_causes_counter,
    bridge_operations_counter,
    dtmf_received_counter,
    call_duration_histogram,
    timeout_counter,
    safe_add,
    safe_record,
    ObservingSpan,
)
from genesis.protocol.subscriptions import EventLease, ensure_channel_events
from genesis.types import HangupCause, ChannelState, ContextType
from genesis.exceptions import (
    ChannelError,
    ChannelNotFound,
    CommandStage,
    SessionGoneAway,
    TimeoutError,
)
from genesis.observability import logger

tracer = trace.get_tracer(__name__)

# Span/attribute names (S1192: avoid duplicated literals)
ATTR_CHANNEL_UUID = "channel.uuid"
ATTR_CHANNEL_CALL_UUID = "channel.call_uuid"
ATTR_SIP_CALL_ID = "sip.call_id"
ATTR_CHANNEL_STATE = "channel.state"
ATTR_HANGUP_CAUSE = "hangup.cause"
ATTR_HANGUP_CAUSE_Q850 = "hangup.cause.q850"
ATTR_WAIT_TYPE = "wait.type"
ATTR_WAIT_RESULT = "wait.result"
ATTR_WAIT_DURATION = "wait.duration"
ATTR_GET_CHANNEL_RESULT = "get_channel.result"

_CHANNEL_UUID = re.compile(
    r"\A[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\Z"
)
_TERMINAL_EVENTS = frozenset(
    {"CHANNEL_HANGUP", "CHANNEL_HANGUP_COMPLETE", "CHANNEL_DESTROY"}
)
_TERMINAL_STATES = frozenset({"CS_HANGUP", "CS_DESTROY", "CS_REPORTING"})
_T = TypeVar("_T")


def require_channel_uuid(value: Optional[str]) -> str:
    """Reject a uuid that could inject another ESL command."""
    if value is None or _CHANNEL_UUID.fullmatch(value) is None:
        raise ChannelError("invalid channel uuid: %r" % (value,))
    return value


def _context_str(context: Mapping[str, Any], key: str) -> str:
    """Get a string value from context, normalizing list or non-string to str."""
    value = context.get(key, "")
    if isinstance(value, list):
        return value[0] if value else ""
    return value if isinstance(value, str) else ""


def _header(event: Mapping[str, Any], key: str) -> Optional[str]:
    value = event.get(key)
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, str):
        return value
    return None


def _sequence(value: Any) -> Optional[int]:
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _copy_context(headers: Mapping[str, Any]) -> ContextType:
    copied: ContextType = {}
    for key, value in headers.items():
        if isinstance(key, str) and isinstance(value, list):
            copied[key] = [str(item) for item in value]
        elif isinstance(key, str) and isinstance(value, str):
            copied[key] = value
    return copied


def _api_body(event: ESLEvent) -> str:
    return (event.body or "").strip()


def _terminal(event: ESLEvent) -> bool:
    if _header(event, "Event-Name") in _TERMINAL_EVENTS:
        return True
    return _header(event, "Channel-State") in _TERMINAL_STATES


def _invalid_session(event: ESLEvent) -> bool:
    reply = _header(event, "Reply-Text") or ""
    return "invalid session id" in reply


class _LookupWatch:
    """Events seen while ``uuid_dump`` is still the newer observation.

    Frames processed before that reply stay in ``early`` and are not
    applied. Frames processed after it are later state, including a
    hangup that means the lookup missed a live channel.
    """

    def __init__(self, channel_uuid: str) -> None:
        self.channel_uuid = channel_uuid
        self.expect_dump = False
        self.dump_noted = False
        self.terminal = False
        self.early: List[ESLEvent] = []
        self.later: List[ESLEvent] = []

    def note(self, _protocol: Protocol, event: ESLEvent) -> None:
        if (
            self.expect_dump
            and not self.dump_noted
            and event.get("Content-Type") == "api/response"
        ):
            self.dump_noted = True
            return
        if _header(event, "Unique-ID") != self.channel_uuid:
            return
        if self.dump_noted:
            self.later.append(event)
            return
        self.early.append(event)

    def apply_later(self, channel: "Channel") -> None:
        snapshot = _sequence(channel.context.get("Event-Sequence"))
        for event in self.later:
            if _terminal(event):
                self.terminal = True
                return
            event_sequence = _sequence(event.get("Event-Sequence"))
            if (
                snapshot is not None
                and event_sequence is not None
                and event_sequence <= snapshot
            ):
                continue
            channel._state_handler(event)


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
        self._state_listening = False
        self._destroy_listening = False
        self._event_lease: Optional[EventLease] = None
        self._loop: Optional[AbstractEventLoop] = None
        self._release_tasks: set[Task[None]] = set()

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
            if self._state == ChannelState.DESTROY:
                self._schedule_release()

    def _arm_state_listener(self) -> None:
        # ``register_channel_handler`` stops routing, so a user observer of
        # the same event would never run. Global handlers both receive it.
        if self._state_listening:
            return
        self.protocol.on("CHANNEL_STATE", self._state_handler)
        self._state_listening = True

    def _on_destroy(self, event: ESLEvent) -> None:
        if _header(event, "Unique-ID") != self.uuid:
            return
        self._schedule_release()

    def attach_lease(self, lease: EventLease) -> None:
        self._event_lease = lease

    def arm_observed_state(self) -> None:
        """Listen for later state. The lease ends when the channel is destroyed."""
        self._loop = get_running_loop()
        self._arm_state_listener()
        if not self._destroy_listening:
            self.protocol.on("CHANNEL_DESTROY", self._on_destroy)
            self._destroy_listening = True
        if self._state == ChannelState.DESTROY:
            self._schedule_release()

    def _drop_listener(self) -> None:
        if self._state_listening:
            self.protocol.remove("CHANNEL_STATE", self._state_handler)
            self._state_listening = False
        if self._destroy_listening:
            self.protocol.remove("CHANNEL_DESTROY", self._on_destroy)
            self._destroy_listening = False

    def _schedule_release(self) -> None:
        lease = self._event_lease
        loop = self._loop
        if lease is None or loop is None:
            return
        self._event_lease = None

        def _kick() -> None:
            task = create_task(self._finish_release(lease))
            self._release_tasks.add(task)
            task.add_done_callback(self._release_done)

        loop.call_soon_threadsafe(_kick)

    def _release_done(self, task: Task[None]) -> None:
        self._release_tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            logger.error(f"Channel event lease release failed: {error}")

    async def _finish_release(self, lease: EventLease) -> None:
        self._drop_listener()
        await lease.release(self.protocol)

    @classmethod
    def from_snapshot(cls, protocol: Protocol, snapshot: ESLEvent) -> "Channel":
        """A new channel whose context is only this dump. No handlers are copied."""
        unique = require_channel_uuid(_header(snapshot, "Unique-ID"))
        state_name = _header(snapshot, "Channel-State") or ""
        if state_name.startswith("["):
            raise ChannelError("uuid_dump plain format is not a channel snapshot")
        self = cls(protocol, _header(snapshot, "Channel-Name") or "")
        self.uuid = unique
        self.context = _copy_context(snapshot)
        if state_name:
            self._state = ChannelState.from_freeswitch(state_name)
        return self

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
                # channel.call_uuid groups a-leg/b-leg within the Genesis trace;
                # at originate time it equals the origination UUID.
                span.set_attribute(ATTR_CHANNEL_CALL_UUID, self.uuid)
                # sip.call_id is the standard SIP Call-ID and the cross-system
                # join key. It is usually not known yet at originate; attach when present.
                sip_call_id = _context_str(self.context, "variable_sip_call_id")
                if sip_call_id:
                    span.set_attribute(ATTR_SIP_CALL_ID, sip_call_id)

                self._arm_state_listener()
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

    def _is_state_reached(
        self,
        target_state: ChannelState,
        answer_received: Optional[Event],
    ) -> bool:
        if target_state != ChannelState.EXECUTE:
            return True
        return answer_received is not None and answer_received.is_set()

    def _on_answer_received(
        self,
        event: ESLEvent,
        answer_received: Optional[Event],
        state_reached: Event,
    ) -> None:
        if event.get("Unique-ID") != self.uuid or not answer_received:
            return
        answer_received.set()
        if self.state == ChannelState.EXECUTE:
            state_reached.set()

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
            if event_state != target_state and event_state < ChannelState.HANGUP:
                return
            self._state = event_state
            self.context.update(event)
            state_event_received = event
            if self._is_state_reached(target_state, answer_received):
                state_reached.set()

        def answer_handler(event: ESLEvent) -> None:
            self._on_answer_received(event, answer_received, state_reached)

        self.protocol.on("CHANNEL_STATE", state_handler)
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
        safe_add(
            channel_operations_counter,
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
        safe_add(
            timeout_counter,
            1,
            attributes={
                "timeout.type": "wait",
                "timeout.operation": timeout_operation,
                "timeout.duration": duration,
            },
        )
        safe_add(
            channel_operations_counter,
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
        target: ChannelState | str,
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
            ConnectionLost: The connection is already gone, or it drops while
                this wait is pending. A pure wait accepts no command, so the
                stage is ``NOT_SENT``: ``write()`` was not called for the wait.

        Example:
            # Wait for state
            await channel.wait(ChannelState.EXECUTE, timeout=10.0)

            # Wait for event
            event = await channel.wait("DTMF", timeout=10.0)
            digit = event.get("DTMF-Digit")
        """
        start_time = time.time()
        wait_type = "event" if isinstance(target, str) else "state"

        opened = ObservingSpan.open(
            "channel.wait",
            {
                ATTR_CHANNEL_UUID: self.uuid or "unknown",
                ATTR_CHANNEL_STATE: self.state.name,
                "wait.target": str(target),
                "wait.timeout": timeout,
                ATTR_WAIT_TYPE: wait_type,
                "operation": "wait",
            },
        )
        try:
            # NOT_SENT: this wait does not write a command, so ACCEPTED would
            # claim an ack that never happened.
            self.protocol.raise_if_lost(CommandStage.NOT_SENT)
            if isinstance(target, str):
                try:
                    result = await self._race_loss(
                        self._wait_for_event(target, timeout),
                        CommandStage.NOT_SENT,
                    )
                    self._record_wait_success(opened, start_time, wait_type)
                    return result
                except TimeoutError:
                    self._record_wait_timeout(
                        opened, start_time, wait_type, f"wait.event.{target}"
                    )
                    raise

            target_state = target
            if self.state >= ChannelState.HANGUP or (
                self.state == target_state and target_state != ChannelState.EXECUTE
            ):
                opened.set_attribute(ATTR_WAIT_RESULT, "already_reached")
                return None

            try:
                state_result = await self._race_loss(
                    self._wait_for_state(target_state, timeout),
                    CommandStage.NOT_SENT,
                )
                self._record_wait_success(opened, start_time, wait_type)
                return state_result
            except TimeoutError:
                self._record_wait_timeout(
                    opened, start_time, wait_type, f"wait.state.{target_state.name}"
                )
                raise
        finally:
            opened.close()

    async def _race_loss(self, operation: Awaitable[_T], stage: CommandStage) -> _T:
        """Finish ``operation`` or raise ``ConnectionLost(stage)`` when the link drops."""
        inner: Task[_T] = create_task(cast(Any, operation))
        lost: Task[None] = create_task(self.protocol.wait_lost(stage))
        try:
            done, _pending = await wait(
                {inner, lost},
                return_when=FIRST_COMPLETED,
            )
            if inner in done:
                return inner.result()
            await lost
            raise AssertionError("connection loss did not fail the wait")
        finally:
            if not lost.done():
                lost.cancel()
                with contextlib.suppress(CancelledError):
                    await lost
            elif not lost.cancelled():
                lost.exception()
            if not inner.done():
                inner.cancel()
                with contextlib.suppress(CancelledError):
                    await inner

    async def _await_execution(self, execution: Any) -> ESLEvent:
        """Wait for this execute after ``+OK``. Loss here is ``ACCEPTED``."""
        lost: Task[None] = create_task(self.protocol.wait_lost(CommandStage.ACCEPTED))
        try:
            done, _pending = await wait(
                cast(List[Any], [execution.future, lost]),
                return_when=FIRST_COMPLETED,
            )
            if execution.future in done:
                return cast(ESLEvent, execution.future.result())
            await lost
            raise AssertionError("connection loss did not fail the completion wait")
        finally:
            if not lost.done():
                lost.cancel()
                with contextlib.suppress(CancelledError):
                    await lost
            elif not lost.cancelled():
                lost.exception()

    async def _inbound_execute(
        self,
        application: str,
        data: Optional[str],
        block: bool,
        completion_timeout: Optional[float],
    ) -> ESLEvent:
        """``sendmsg`` execute. ``block`` waits for this Event-UUID, not the ack.

        ``completion_timeout`` is a relative duration in seconds, the same bound
        as the public ``timeout`` argument. It limits only the wait for
        ``CHANNEL_EXECUTE_COMPLETE`` after the command is accepted. ``None``
        waits without a limit. The send itself is outside this bound, so the
        caller cannot wrap the whole method. ``asyncio.wait_for`` applies the
        duration; Python 3.10 has no ``asyncio.timeout``.
        """
        require_channel_uuid(self.uuid)
        _cmd, event_uuid = _build_sendmsg_cmd(
            "execute",
            application,
            data,
            uuid=self.uuid,
        )
        if not block or event_uuid is None:
            result = await self.protocol.send(_cmd)
            if _invalid_session(result):
                raise ChannelNotFound(self.uuid or "")
            return result
        self.protocol.raise_if_lost(CommandStage.NOT_SENT)
        self.protocol.subscriptions.require_completion_visible(self.uuid or "")
        execution = _install_execution_wait(self.protocol, event_uuid, None, self.uuid)
        try:
            result = await self.protocol.send(_cmd)
            if _invalid_session(result):
                raise ChannelNotFound(self.uuid or "")
            if _rejected(result):
                return result
            completion = self._await_execution(execution)
            if completion_timeout is None:
                return await completion
            return await wait_for(completion, completion_timeout)
        finally:
            execution.abandon()

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
        if command == "execute":
            return await self._inbound_execute(application, data, block, timeout)
        if command == "hangup":
            require_channel_uuid(self.uuid)
            cause = data or "NORMAL_CLEARING"
            return await self.protocol.send("api uuid_kill %s %s" % (self.uuid, cause))
        raise ChannelError("Command %s not supported for Inbound protocol" % command)

    def _get_peer_uuid(self, other: Channel | Session) -> Optional[str]:
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
        opened = ObservingSpan.open(span_name, span_attributes)
        try:
            try:
                result = await get_result()
            except Exception as exc:
                opened.record_exception(exc)
                opened.set_status(trace.Status(trace.StatusCode.ERROR, str(exc)))
                safe_add(
                    channel_operations_counter,
                    1,
                    attributes={
                        "operation": operation,
                        "success": "false",
                        "error": type(exc).__name__,
                    },
                )
                try:
                    if extra_on_error:
                        extra_on_error(exc)
                except Exception:
                    logger.debug("channel operation error telemetry failed")
                raise
            duration = time.time() - start_time
            try:
                success = result.get("Reply-Text", "").startswith("+OK")
                opened.set_attribute(f"channel.{operation}.success", success)
                opened.set_attribute(f"channel.{operation}.duration", duration)
                safe_add(
                    channel_operations_counter,
                    1,
                    attributes={"operation": operation, "success": str(success)},
                )
                safe_record(
                    channel_operation_duration,
                    duration,
                    attributes={"operation": operation},
                )
                if extra_on_success:
                    extra_on_success(opened, result, duration)
            except Exception:
                logger.debug("channel operation telemetry failed")
            return result
        finally:
            opened.close()

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
            # Q.850 code (authoritative) when FreeSWITCH exposed it on the leg.
            q850 = _context_str(self.context, "variable_hangup_cause_q850")
            if q850:
                span.set_attribute(ATTR_HANGUP_CAUSE_Q850, q850)
            # call.duration recorded with low-cardinality attrs so it can be
            # partitioned by cause/direction (NO UUID: cardinality rule).
            if call_duration is not None:
                span.set_attribute("call.duration", call_duration)
                direction = _context_str(self.context, "Call-Direction") or "unknown"
                call_duration_histogram.record(
                    call_duration,
                    attributes={ATTR_HANGUP_CAUSE: cause, "direction": direction},
                )
            # Mark the command-side hangup span; the authoritative marker comes
            # from CHANNEL_HANGUP_COMPLETE (see channel_lifecycle_processor).
            span.add_event(
                "hangup.command_issued",
                attributes={ATTR_HANGUP_CAUSE: cause},
            )

        def on_error(exc: Exception) -> None:
            hangup_causes_counter.add(
                1,
                attributes={ATTR_HANGUP_CAUSE: cause, "error": type(exc).__name__},
            )

        async def do_hangup() -> ESLEvent:
            if isinstance(self.protocol, Session):
                return await self._sendmsg_or_send("execute", "hangup", cause)
            require_channel_uuid(self.uuid)
            return await self.protocol.send("api uuid_kill %s %s" % (self.uuid, cause))

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

    async def bridge(self, other: Channel | Session) -> ESLEvent:
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
        require_channel_uuid(self.uuid)
        require_channel_uuid(other_uuid)

        def on_success(span: Any, result: ESLEvent, duration: float) -> None:
            success = result.get("Reply-Text", "").startswith("+OK")
            bridge_operations_counter.add(1, attributes={"success": str(success)})
            # Correlation attrs: a/b leg UUIDs let the backend cross the two
            # SIP dialogs of a bridged call (each leg has its own sip.call_id).
            span.set_attribute("bridge.a_uuid", self.uuid or "unknown")
            span.set_attribute("bridge.b_uuid", other_uuid or "unknown")
            call_uuid = _context_str(self.context, "Channel-Call-UUID") or (
                self.uuid or "unknown"
            )
            span.set_attribute(ATTR_CHANNEL_CALL_UUID, call_uuid)
            sip_call_id = _context_str(self.context, "variable_sip_call_id")
            if sip_call_id:
                span.set_attribute(ATTR_SIP_CALL_ID, sip_call_id)
            span.add_event(
                "bridge.command_issued",
                attributes={
                    "bridge.a_uuid": self.uuid or "unknown",
                    "bridge.b_uuid": other_uuid or "unknown",
                },
            )

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
            func: Callable[[str], Awaitable[None]],
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
                                safe_add(
                                    dtmf_received_counter,
                                    1,
                                    attributes={"dtmf.digit": dtmf_digit},
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


async def get_inbound_channel(protocol: Inbound, channel_uuid: str) -> Channel:
    """Observe one live channel. Events from before the dump do not replace it."""
    started = time.perf_counter()
    outcome = "error"
    try:
        require_channel_uuid(channel_uuid)
        protocol.raise_if_lost(CommandStage.NOT_SENT)
        opened = ObservingSpan.open(
            "get_channel",
            {"channel.uuid": channel_uuid},
        )
        try:
            watch = _LookupWatch(channel_uuid)
            lease: Optional[EventLease] = None
            protocol.event_processors.append(watch.note)
            try:
                lease = await ensure_channel_events(protocol, channel_uuid)
                exists = await protocol.send("api uuid_exists %s" % channel_uuid)
                exists_body = _api_body(exists)
                if exists_body == "false" or exists_body.startswith(
                    "-ERR No such channel"
                ):
                    raise ChannelNotFound(channel_uuid)
                if exists_body != "true":
                    raise ChannelError("unexpected uuid_exists reply")
                watch.expect_dump = True
                dumped = await protocol.send("api uuid_dump %s" % channel_uuid)
                dump_body = dumped.body or ""
                if dump_body.startswith("-ERR No such channel"):
                    raise ChannelNotFound(channel_uuid)
                if dump_body.startswith(("-ERR", "-USAGE")):
                    raise ChannelError(dump_body.strip())
                snapshot = parse_headers(dump_body)
                if _header(snapshot, "Unique-ID") != channel_uuid:
                    raise ChannelNotFound(channel_uuid)
                channel = Channel.from_snapshot(protocol, snapshot)
                watch.apply_later(channel)
                if watch.terminal:
                    raise ChannelNotFound(channel_uuid)
                channel.attach_lease(lease)
                lease = None
                channel.arm_observed_state()
                outcome = "found"
                opened.set_attribute(ATTR_GET_CHANNEL_RESULT, "found")
                return channel
            except ChannelNotFound:
                outcome = "not_found"
                opened.set_attribute(ATTR_GET_CHANNEL_RESULT, "not_found")
                raise
            except Exception as exc:
                outcome = "error"
                opened.record_exception(exc)
                opened.set_status(trace.Status(trace.StatusCode.ERROR, str(exc)))
                opened.set_attribute(ATTR_GET_CHANNEL_RESULT, "error")
                raise
            finally:
                if watch.note in protocol.event_processors:
                    protocol.event_processors.remove(watch.note)
                if lease is not None:
                    await lease.release(protocol)
        finally:
            opened.close()
    finally:
        safe_add(
            channel_operations_counter,
            1,
            attributes={"operation": "get_channel", "result": outcome},
        )
        safe_record(
            channel_operation_duration,
            time.perf_counter() - started,
            attributes={"operation": "get_channel", "result": outcome},
        )
