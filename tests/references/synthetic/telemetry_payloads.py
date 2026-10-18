"""Synthetic ESL text for lifecycle telemetry tests.

``channel_create`` and ``heartbeat`` keep only the headers those tests
assert. They are not FreeSWITCH captures, and this module does not import
the Genesis parser.
"""

from textwrap import dedent

UUID_A: str = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
UUID_B: str = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
SIP_CALL_ID: str = "test-sip-call-id-123"

heartbeat: str = dedent("""\
    Event-Name: HEARTBEAT
    """)

channel_create: str = dedent("""\
    Event-Name: CHANNEL_CREATE
    Channel-State: CS_INIT
    Unique-ID: d0b1da34-a727-11e4-9728-6f83a2e5e50a
    Channel-Call-UUID: d0b1da34-a727-11e4-9728-6f83a2e5e50a
    Call-Direction: inbound
    Caller-Destination-Number: 101
    variable_sip_call_id: 6bG.Hj5UCe8pDFEy1R9FO8EIfHtKrZ3H
    """)

_channel_common: str = dedent("""\
    Unique-ID: {uuid_a}
    Channel-Call-UUID: {uuid_a}
    Call-Direction: inbound
    variable_sip_call_id: {sip_call_id}
    """)

channel_bridge: str = _channel_common.format(
    uuid_a=UUID_A, sip_call_id=SIP_CALL_ID
) + dedent(
    """\
    Event-Name: CHANNEL_BRIDGE
    Bridge-A-Unique-ID: {uuid_a}
    Bridge-B-Unique-ID: {uuid_b}
    Other-Leg-Unique-ID: {uuid_b}
    Other-Type: bride
    Other-Leg-Destination-Number: 1002
    Other-Leg-Caller-ID-Number: 1002
    """.format(uuid_a=UUID_A, uuid_b=UUID_B)
)

channel_unbridge: str = _channel_common.format(
    uuid_a=UUID_A, sip_call_id=SIP_CALL_ID
) + dedent(
    """\
    Event-Name: CHANNEL_UNBRIDGE
    Bridge-A-Unique-ID: {uuid_a}
    Other-Leg-Unique-ID: {uuid_b}
    Hangup-Cause: NORMAL_CLEARING
    """.format(uuid_a=UUID_A, uuid_b=UUID_B)
)

channel_hangup_complete: str = _channel_common.format(
    uuid_a=UUID_A, sip_call_id=SIP_CALL_ID
) + dedent(
    """\
    Event-Name: CHANNEL_HANGUP_COMPLETE
    Hangup-Cause: NORMAL_CLEARING
    variable_hangup_cause_q850: 16
    Channel-Name: sofia/internal/100@192.168.50.4
    """
)

channel_destroy: str = _channel_common.format(
    uuid_a=UUID_A, sip_call_id=SIP_CALL_ID
) + dedent(
    """\
    Event-Name: CHANNEL_DESTROY
    Channel-State: CS_DESTROY
    """
)

channel_execute: str = _channel_common.format(
    uuid_a=UUID_A, sip_call_id=SIP_CALL_ID
) + dedent(
    """\
    Event-Name: CHANNEL_EXECUTE
    Application: playback
    Application-UUID: app-uuid-1
    Application-Data: /tmp/hello.wav
    """
)

channel_execute_complete: str = _channel_common.format(
    uuid_a=UUID_A, sip_call_id=SIP_CALL_ID
) + dedent(
    """\
    Event-Name: CHANNEL_EXECUTE_COMPLETE
    Application: playback
    Application-UUID: app-uuid-1
    Application-Response: FILE PLAYED
    """
)

codec: str = _channel_common.format(uuid_a=UUID_A, sip_call_id=SIP_CALL_ID) + dedent(
    """\
    Event-Name: CODEC
    Channel-Read-Codec-Name: opus
    Channel-Read-Codec-Rate: 48000
    Channel-Write-Codec-Name: opus
    Channel-Write-Codec-Rate: 48000
    """
)

call_update: str = _channel_common.format(
    uuid_a=UUID_A, sip_call_id=SIP_CALL_ID
) + dedent(
    """\
    Event-Name: CALL_UPDATE
    Bridged-To: {uuid_b}
    Caller-Transfer-Source: transfer_src
    Caller-Orig-Caller-ID-Number: 100
    """.format(uuid_b=UUID_B)
)

sofia_transferor: str = _channel_common.format(
    uuid_a=UUID_A, sip_call_id=SIP_CALL_ID
) + dedent(
    """\
    Event-Name: CUSTOM
    Event-Subclass: sofia::transferor
    variable_sofia_profile_name: internal
    """
)

sofia_transferee: str = _channel_common.format(
    uuid_a=UUID_A, sip_call_id=SIP_CALL_ID
) + dedent(
    """\
    Event-Name: CUSTOM
    Event-Subclass: sofia::transferee
    variable_sofia_profile_name: internal
    """
)

callcenter_info: str = _channel_common.format(
    uuid_a=UUID_A, sip_call_id=SIP_CALL_ID
) + dedent(
    """\
    Event-Name: CUSTOM
    Event-Subclass: callcenter::info
    CC-Queue: sales
    CC-Action: agent-state-change
    CC-Agent: agent-1001
    CC-Member-UUID: member-uuid-1
    CC-Count: 1
    CC-Selection: round-robin
    """
)

conference_maintenance: str = _channel_common.format(
    uuid_a=UUID_A, sip_call_id=SIP_CALL_ID
) + dedent(
    """\
    Event-Name: CUSTOM
    Event-Subclass: conference::maintenance
    Conference-Name: 3000
    Conference-Profile: default
    Action: add-member
    Member-ID: 1
    Old-Member-ID: 0
    """
)

valet_info: str = _channel_common.format(
    uuid_a=UUID_A, sip_call_id=SIP_CALL_ID
) + dedent(
    """\
    Event-Name: CUSTOM
    Event-Subclass: valet_parking::info
    Valet-Lot-Name: default
    Valet-Extension: 4100
    Action: bridge
    Bridge-To-UUID: {uuid_b}
    """.format(uuid_b=UUID_B)
)

channel_create_no_sip: str = dedent("""\
    Event-Name: CHANNEL_CREATE
    Channel-State: CS_INIT
    Unique-ID: {uuid_a}
    Channel-Call-UUID: {uuid_a}
    Call-Direction: outbound
    Caller-Destination-Number: 1002
    Caller-Context: default
    """).format(uuid_a=UUID_A)
