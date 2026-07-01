"""
ESL lifecycle telemetry processors
----------------------------------

These processors run after the core protocol processors and emit OpenTelemetry
spans for the semantic FreeSWITCH channel lifecycle (``freeswitch.channel.*``)
and for CUSTOM subclasses (``sofia::``, ``callcenter::``, ``conference::``,
``valet_parking::``). They only enrich telemetry — they never consume events
that route to user handlers.

Correlation with the passive sniffer (Otoru/sniffer) is attribute-based:
every channel span carries ``sip.call_id`` (= ``variable_sip_call_id``), which
matches the sniffer's ``voip.call_id``. The join happens at the observability
backend (Grafana/Tempo), not in code. No sniffer changes are required.

Cardinality rule: UUIDs go on spans only; metric attributes use low-cardinality
enums/labels (channel.state, direction, hangup.cause, application.name, ...).
"""

import os
from typing import TYPE_CHECKING, Any, Dict, Optional

from opentelemetry import trace

from genesis.protocol.parser import ESLEvent
from genesis.protocol.metrics import (
    calls_active_counter,
    channel_bridge_events_counter,
    channel_codec_changes_counter,
    channel_transfers_counter,
    dialplan_applications_counter,
    events_without_sip_call_id_counter,
    hangup_q850_counter,
    safe_add,
)

if TYPE_CHECKING:
    from genesis.protocol.base import Protocol

tracer = trace.get_tracer(__name__)

# Feature flags (default on; opt-out via env). Reserved for future W3C
# propagation is intentionally NOT implemented here (out of scope).
_LIFECYCLE_ENABLED = os.environ.get("GENESIS_TRACE_ESL_LIFECYCLE", "1") != "0"
_CUSTOM_ENABLED = os.environ.get("GENESIS_TRACE_CUSTOM_SUBCLASSES", "1") != "0"


def _str(event: ESLEvent, key: str) -> Optional[str]:
    """Return a single string value for key (list-aware), or None."""
    value = event.get(key)
    if value is None:
        return None
    if isinstance(value, list):
        return value[0] if value else None
    return value if isinstance(value, str) else str(value)


def _set(attrs: Dict[str, Any], dst: str, event: ESLEvent, src: str) -> None:
    """Copy event[src] into attrs[dst] when present."""
    value = _str(event, src)
    if value:
        attrs[dst] = value


def _channel_attrs(event: ESLEvent) -> Dict[str, Any]:
    """Common channel attributes (uuid, call_uuid, direction, sip.call_id, other_leg)."""
    attrs: Dict[str, Any] = {}
    _set(attrs, "channel.uuid", event, "Unique-ID")
    _set(attrs, "channel.call_uuid", event, "Channel-Call-UUID")
    _set(attrs, "channel.direction", event, "Call-Direction")
    _set(attrs, "sip.call_id", event, "variable_sip_call_id")
    _set(attrs, "other_leg.uuid", event, "Other-Leg-Unique-ID")
    return attrs


def _record_sip_gap(event: ESLEvent, attrs: Dict[str, Any]) -> None:
    """Count channel events that lack the sniffer correlation key."""
    if "sip.call_id" not in attrs:
        safe_add(events_without_sip_call_id_counter, 1, attributes={})


# Event names handled by the lifecycle processor.
_LIFECYCLE_EVENTS = {
    "CHANNEL_CREATE",
    "CHANNEL_PROGRESS",
    "CHANNEL_PROGRESS_MEDIA",
    "CHANNEL_ANSWER",
    "CHANNEL_BRIDGE",
    "CHANNEL_UNBRIDGE",
    "CHANNEL_HANGUP",
    "CHANNEL_HANGUP_COMPLETE",
    "CHANNEL_DESTROY",
    "CHANNEL_EXECUTE",
    "CHANNEL_EXECUTE_COMPLETE",
    "CHANNEL_PARK",
    "CHANNEL_UNPARK",
    "CALL_UPDATE",
    "CODEC",
}


async def channel_lifecycle_processor(protocol: "Protocol", event: ESLEvent) -> None:
    """Emit ``freeswitch.channel.*`` spans for channel lifecycle events."""
    if not _LIFECYCLE_ENABLED:
        return

    name = _str(event, "Event-Name")
    if not name or name not in _LIFECYCLE_EVENTS:
        return

    attrs = _channel_attrs(event)
    _record_sip_gap(event, attrs)

    if name == "CHANNEL_CREATE":
        _emit_create(event, attrs)
    elif name == "CHANNEL_PROGRESS":
        _emit_progress(event, attrs)
    elif name == "CHANNEL_PROGRESS_MEDIA":
        _emit_progress_media(event, attrs)
    elif name == "CHANNEL_ANSWER":
        _emit_answer(event, attrs)
    elif name == "CHANNEL_BRIDGE":
        _emit_bridge(event, attrs)
    elif name == "CHANNEL_UNBRIDGE":
        _emit_unbridge(event, attrs)
    elif name == "CHANNEL_HANGUP":
        _emit_hangup(event, attrs)
    elif name == "CHANNEL_HANGUP_COMPLETE":
        _emit_hangup_complete(event, attrs)
    elif name == "CHANNEL_DESTROY":
        _emit_destroy(event, attrs)
    elif name == "CHANNEL_EXECUTE":
        _emit_execute(event, attrs)
    elif name == "CHANNEL_EXECUTE_COMPLETE":
        _emit_execute_complete(event, attrs)
    elif name in ("CHANNEL_PARK", "CHANNEL_UNPARK"):
        _emit_state_span(event, attrs, f"freeswitch.channel.{name.lower()[8:]}")
    elif name == "CALL_UPDATE":
        _emit_call_update(event, attrs)
    elif name == "CODEC":
        _emit_codec(event, attrs)


def _emit_create(event: ESLEvent, attrs: Dict[str, Any]) -> None:
    _set(attrs, "channel.name", event, "Channel-Name")
    _set(attrs, "channel.destination_number", event, "Caller-Destination-Number")
    _set(attrs, "channel.context", event, "Caller-Context")
    _set(attrs, "channel.dialplan", event, "Caller-Dialplan")
    _set(attrs, "channel.caller_id_number", event, "Caller-Caller-ID-Number")
    _set(attrs, "channel.caller_id_name", event, "Caller-Caller-ID-Name")
    _set(attrs, "channel.network_addr", event, "Caller-Network-Addr")
    with tracer.start_as_current_span("freeswitch.channel.create", attributes=attrs):
        safe_add(
            calls_active_counter,
            1,
            attributes={
                "channel.state": _str(event, "Channel-State") or "CS_INIT",
                "direction": _str(event, "Call-Direction") or "unknown",
            },
        )


def _emit_progress(event: ESLEvent, attrs: Dict[str, Any]) -> None:
    _set(attrs, "channel.state", event, "Channel-State")
    attrs["answer.state"] = _str(event, "Answer-State") or "ringing"
    with tracer.start_as_current_span("freeswitch.channel.progress", attributes=attrs):
        pass


def _emit_progress_media(event: ESLEvent, attrs: Dict[str, Any]) -> None:
    attrs["answer.state"] = _str(event, "Answer-State") or "early"
    _set(attrs, "channel.read_codec", event, "Channel-Read-Codec-Name")
    _set(attrs, "channel.write_codec", event, "Channel-Write-Codec-Name")
    with tracer.start_as_current_span(
        "freeswitch.channel.progress_media", attributes=attrs
    ):
        pass


def _emit_answer(event: ESLEvent, attrs: Dict[str, Any]) -> None:
    _set(attrs, "channel.state", event, "Channel-State")
    attrs["answer.state"] = "answered"
    _set(attrs, "channel.read_codec", event, "Channel-Read-Codec-Name")
    _set(attrs, "channel.write_codec", event, "Channel-Write-Codec-Name")
    with tracer.start_as_current_span("freeswitch.channel.answer", attributes=attrs):
        pass


def _emit_bridge(event: ESLEvent, attrs: Dict[str, Any]) -> None:
    _set(attrs, "bridge.a_uuid", event, "Bridge-A-Unique-ID")
    _set(attrs, "bridge.b_uuid", event, "Bridge-B-Unique-ID")
    _set(attrs, "other_leg.type", event, "Other-Type")
    _set(attrs, "other_leg.destination_number", event, "Other-Leg-Destination-Number")
    _set(attrs, "other_leg.caller_id_number", event, "Other-Leg-Caller-ID-Number")
    with tracer.start_as_current_span(
        "freeswitch.channel.bridge", attributes=attrs
    ) as span:
        a = attrs.get("bridge.a_uuid", "unknown")
        b = attrs.get("bridge.b_uuid", "unknown")
        span.add_event(
            "bridge.established",
            attributes={"bridge.a_uuid": a, "bridge.b_uuid": b},
        )
        safe_add(
            channel_bridge_events_counter,
            1,
            attributes={"bridge.result": "established"},
        )


def _emit_unbridge(event: ESLEvent, attrs: Dict[str, Any]) -> None:
    _set(attrs, "bridge.a_uuid", event, "Bridge-A-Unique-ID")
    # CHANNEL_UNBRIDGE may carry Other-Leg-Unique-ID instead of Bridge-B.
    if "bridge.b_uuid" not in attrs:
        _set(attrs, "bridge.b_uuid", event, "Other-Leg-Unique-ID")
    _set(attrs, "hangup.cause", event, "Hangup-Cause")
    with tracer.start_as_current_span(
        "freeswitch.channel.unbridge", attributes=attrs
    ) as span:
        span.add_event(
            "bridge.torn_down",
            attributes={
                "bridge.a_uuid": attrs.get("bridge.a_uuid", "unknown"),
                "bridge.b_uuid": attrs.get("bridge.b_uuid", "unknown"),
            },
        )
        metric_attrs: Dict[str, Any] = {"bridge.result": "unbridged"}
        cause = attrs.get("hangup.cause")
        if cause:
            metric_attrs["hangup.cause"] = cause
        safe_add(channel_bridge_events_counter, 1, attributes=metric_attrs)


def _emit_hangup(event: ESLEvent, attrs: Dict[str, Any]) -> None:
    _set(attrs, "hangup.cause", event, "Hangup-Cause")
    _set(attrs, "channel.state", event, "Channel-State")
    attrs["answer.state"] = "hangup"
    cause = _str(event, "Hangup-Cause") or "unknown"
    normalized = cause.lower().replace(" ", "_")
    with tracer.start_as_current_span(
        "freeswitch.channel.hangup", attributes=attrs
    ) as span:
        span.add_event(f"hangup.cause.{normalized}", attributes={"hangup.cause": cause})


def _emit_hangup_complete(event: ESLEvent, attrs: Dict[str, Any]) -> None:
    _set(attrs, "hangup.cause", event, "Hangup-Cause")
    _set(attrs, "hangup.cause.q850", event, "variable_hangup_cause_q850")
    _set(attrs, "channel.name", event, "Channel-Name")
    with tracer.start_as_current_span(
        "freeswitch.channel.hangup_complete", attributes=attrs
    ) as span:
        span.add_event(
            "call.finalized",
            attributes={"hangup.cause": attrs.get("hangup.cause", "unknown")},
        )
        q850 = _str(event, "variable_hangup_cause_q850")
        if q850:
            safe_add(
                hangup_q850_counter,
                1,
                attributes={"hangup.cause.q850": q850},
            )


def _emit_destroy(event: ESLEvent, attrs: Dict[str, Any]) -> None:
    with tracer.start_as_current_span("freeswitch.channel.destroy", attributes=attrs):
        safe_add(
            calls_active_counter,
            -1,
            attributes={
                "channel.state": "CS_DESTROY",
                "direction": _str(event, "Call-Direction") or "unknown",
            },
        )


def _emit_execute(event: ESLEvent, attrs: Dict[str, Any]) -> None:
    _set(attrs, "application.name", event, "Application")
    _set(attrs, "application.uuid", event, "Application-UUID")
    _set(attrs, "application.data", event, "Application-Data")
    with tracer.start_as_current_span("freeswitch.channel.execute", attributes=attrs):
        app = _str(event, "Application") or "unknown"
        safe_add(
            dialplan_applications_counter,
            1,
            attributes={"application.name": app, "application.result": "started"},
        )


def _emit_execute_complete(event: ESLEvent, attrs: Dict[str, Any]) -> None:
    _set(attrs, "application.name", event, "Application")
    _set(attrs, "application.uuid", event, "Application-UUID")
    _set(attrs, "application.response", event, "Application-Response")
    app = _str(event, "Application") or "unknown"
    response = _str(event, "Application-Response") or ""
    result = "success" if response and not response.startswith("-ERR") else "fail"
    with tracer.start_as_current_span(
        "freeswitch.channel.execute_complete", attributes=attrs
    ) as span:
        span.add_event(
            f"app.{app}.done",
            attributes={"application.name": app, "application.result": result},
        )
        safe_add(
            dialplan_applications_counter,
            1,
            attributes={"application.name": app, "application.result": result},
        )


def _emit_state_span(event: ESLEvent, attrs: Dict[str, Any], span_name: str) -> None:
    _set(attrs, "channel.state", event, "Channel-State")
    with tracer.start_as_current_span(span_name, attributes=attrs):
        pass


def _emit_call_update(event: ESLEvent, attrs: Dict[str, Any]) -> None:
    _set(attrs, "bridged.to", event, "Bridged-To")
    _set(attrs, "caller.transfer_source", event, "Caller-Transfer-Source")
    _set(attrs, "caller.orig_caller_id_number", event, "Caller-Orig-Caller-ID-Number")
    with tracer.start_as_current_span(
        "freeswitch.call.update", attributes=attrs
    ) as span:
        span.add_event("caller_id.mutated", attributes={})


def _emit_codec(event: ESLEvent, attrs: Dict[str, Any]) -> None:
    _set(attrs, "channel.read_codec.name", event, "Channel-Read-Codec-Name")
    _set(attrs, "channel.read_codec.rate", event, "Channel-Read-Codec-Rate")
    _set(attrs, "channel.write_codec.name", event, "Channel-Write-Codec-Name")
    _set(attrs, "channel.write_codec.rate", event, "Channel-Write-Codec-Rate")
    read_codec = _str(event, "Channel-Read-Codec-Name") or "unknown"
    write_codec = _str(event, "Channel-Write-Codec-Name") or "unknown"
    with tracer.start_as_current_span("freeswitch.channel.codec", attributes=attrs):
        safe_add(
            channel_codec_changes_counter,
            1,
            attributes={
                "channel.read_codec": read_codec,
                "channel.write_codec": write_codec,
            },
        )


# ---------------------------------------------------------------------------
# CUSTOM subclass processor
# ---------------------------------------------------------------------------
_CUSTOM_MAP = {
    "sofia::transferor": "transferor",
    "sofia::transferee": "transferee",
    "sofia::reinvite": "reinvite",
    "sofia::replaced": "replaced",
    "sofia::register": "register",
    "sofia::unregister": "register",
    "sofia::expire": "register",
    "sofia::gateway_state": "register",
    "callcenter::info": "callcenter",
    "conference::maintenance": "conference",
    "conference::cdr": "conference",
    "valet_parking::info": "valet",
}


async def custom_subclass_processor(protocol: "Protocol", event: ESLEvent) -> None:
    """Emit spans for CUSTOM subclasses (sofia/callcenter/conference/valet)."""
    if not _CUSTOM_ENABLED:
        return
    if _str(event, "Event-Name") != "CUSTOM":
        return
    subclass = _str(event, "Event-Subclass")
    if not subclass or subclass not in _CUSTOM_MAP:
        return

    attrs = _channel_attrs(event)
    kind = _CUSTOM_MAP[subclass]

    if kind in ("transferor", "transferee"):
        _emit_transfer(event, attrs, kind)
    elif kind in ("reinvite", "replaced"):
        _emit_reinvite(event, attrs, kind)
    elif kind == "register":
        _emit_register(event, attrs, subclass)
    elif kind == "callcenter":
        _emit_callcenter(event, attrs)
    elif kind == "conference":
        _emit_conference(event, attrs, subclass)
    elif kind == "valet":
        _emit_valet(event, attrs)


def _emit_transfer(event: ESLEvent, attrs: Dict[str, Any], role: str) -> None:
    attrs["transfer.role"] = role
    # Heuristic: transferee only occurs in attended transfers; a lone
    # transferor is typically a blind transfer.
    attrs["transfer.type"] = "attended" if role == "transferee" else "blind"
    _set(attrs, "sofia.profile", event, "variable_sofia_profile_name")
    with tracer.start_as_current_span(
        "freeswitch.sofia.transfer", attributes=attrs
    ) as span:
        span.add_event(
            "transfer.initiated",
            attributes={"transfer.role": role, "transfer.type": attrs["transfer.type"]},
        )
        safe_add(
            channel_transfers_counter,
            1,
            attributes={
                "transfer.type": attrs["transfer.type"],
                "transfer.role": role,
            },
        )


def _emit_reinvite(event: ESLEvent, attrs: Dict[str, Any], kind: str) -> None:
    _set(attrs, "sofia.profile", event, "variable_sofia_profile_name")
    with tracer.start_as_current_span(
        f"freeswitch.sofia.{kind}", attributes=attrs
    ) as span:
        span.add_event("media.renegotiated", attributes={})


def _emit_register(event: ESLEvent, attrs: Dict[str, Any], subclass: str) -> None:
    from_user = _str(event, "from-user")
    from_host = _str(event, "from-host")
    if from_user and from_host:
        attrs["register.aor"] = f"{from_user}@{from_host}"
    _set(attrs, "register.contact_ip", event, "contact")
    _set(attrs, "register.expires_s", event, "expires")
    _set(attrs, "register.response_code", event, "status")
    _set(attrs, "gateway.name", event, "Gateway-Name")
    _set(attrs, "gateway.state", event, "State")
    attrs["register.action"] = subclass.split("::")[1]
    with tracer.start_as_current_span("freeswitch.sofia.register", attributes=attrs):
        pass


def _emit_callcenter(event: ESLEvent, attrs: Dict[str, Any]) -> None:
    _set(attrs, "cc.queue", event, "CC-Queue")
    _set(attrs, "cc.action", event, "CC-Action")
    _set(attrs, "cc.agent", event, "CC-Agent")
    _set(attrs, "cc.member_uuid", event, "CC-Member-UUID")
    _set(attrs, "cc.count", event, "CC-Count")
    _set(attrs, "cc.selection", event, "CC-Selection")
    with tracer.start_as_current_span("freeswitch.callcenter.info", attributes=attrs):
        pass


def _emit_conference(event: ESLEvent, attrs: Dict[str, Any], subclass: str) -> None:
    _set(attrs, "conference.name", event, "Conference-Name")
    _set(attrs, "conference.profile", event, "Conference-Profile")
    _set(attrs, "conference.action", event, "Action")
    _set(attrs, "conference.member_id", event, "Member-ID")
    _set(attrs, "old.member_id", event, "Old-Member-ID")
    span_name = (
        "freeswitch.conference.cdr"
        if subclass == "conference::cdr"
        else "freeswitch.conference.maintenance"
    )
    with tracer.start_as_current_span(span_name, attributes=attrs):
        pass


def _emit_valet(event: ESLEvent, attrs: Dict[str, Any]) -> None:
    _set(attrs, "valet.lot", event, "Valet-Lot-Name")
    _set(attrs, "valet.extension", event, "Valet-Extension")
    _set(attrs, "valet.action", event, "Action")
    _set(attrs, "bridge.to_uuid", event, "Bridge-To-UUID")
    with tracer.start_as_current_span("freeswitch.valet.info", attributes=attrs):
        pass
