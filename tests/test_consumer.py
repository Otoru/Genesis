import asyncio
from typing import Any

try:
    from unittest.mock import AsyncMock, PropertyMock
except ImportError:
    from mock import AsyncMock, PropertyMock

import pytest

from genesis import filtrate, Consumer

cases = [
    {"decorator": ["key"], "expected": True, "event": {"key": "value"}},
    {"decorator": ["key"], "expected": False, "event": {"invalid_key": "value"}},
    {"decorator": ["key", "value"], "expected": True, "event": {"key": "value"}},
    {
        "decorator": ["key", "value"],
        "expected": False,
        "event": {"key": "another_value"},
    },
    {
        "decorator": ["key", "^[a-z]{5}$", True],
        "expected": True,
        "event": {"key": "value"},
    },
    {
        "decorator": ["key", "^[a-z]{3}$", True],
        "expected": False,
        "event": {"key": "value"},
    },
]


@pytest.mark.parametrize("content", cases)
@pytest.mark.filterwarnings("ignore: coroutine")
@pytest.mark.filterwarnings("ignore: There is no current event loop")
async def test_decorator_behavior(content):
    """Validates decorator behavior."""
    handler = AsyncMock()

    event = content["event"]
    expected = content["expected"]
    parameters = content["decorator"]

    decorator = filtrate(*parameters)
    assert callable(decorator), "The decorator result did not return a function"

    new_handler = decorator(handler)
    assert asyncio.iscoroutinefunction(
        new_handler
    ), "New handler is not a coroutine funcion"

    await new_handler(event)

    assert handler.called == expected, "The handler has stored the expected value"


async def test_decorator_not_change_behavior_of_funcion():
    app = Consumer("127.0.0.1", 8021, "ClueCon")

    @app.handle("sofia::register")
    async def handle(event):
        return "result"

    expected = "result"
    got = await handle(dict())

    assert got == expected, "The result of the function is not as expected"


async def test_consumer_with_heartbeat_event(freeswitch, heartbeat):
    async with freeswitch as server:
        server.events.append(heartbeat)
        server.oncommand(
            "filter Event-Name HEARTBEAT",
            "+OK filter added. [filter]=[Event-Name HEARTBEAT]",
        )

        semaphore = asyncio.Event()

        async def effect(*args, **kwargs):
            semaphore.set()

        handler = AsyncMock(side_effect=effect)
        app = Consumer(*freeswitch.address)
        app.handle("HEARTBEAT")(handler)

        future = asyncio.create_task(app.start())
        await semaphore.wait()

        await app.stop()
        future.cancel()

    assert handler.called, "The handler has stored the expected value"


async def test_consumer_with_register_custom_event(freeswitch, register):
    async with freeswitch as server:
        server.events.append(register)
        server.oncommand(
            "filter Event-Subclass sofia::register",
            "+OK filter added. [filter]=[Event-Subclass sofia::register]",
        )

        semaphore = asyncio.Event()

        async def effect(*args, **kwargs):
            semaphore.set()

        handler = AsyncMock(side_effect=effect)
        app = Consumer(*freeswitch.address)
        app.handle("sofia::register")(handler)

        future = asyncio.create_task(app.start())
        await semaphore.wait()

        await app.stop()
        future.cancel()

    assert handler.called, "The handler has stored the expected value"


async def test_consumer_wait_method_is_callend(freeswitch):
    semaphore = asyncio.Event()

    async with freeswitch as server:
        spider = AsyncMock(side_effect=semaphore.set)
        app = Consumer(*server.address)
        setattr(app, "wait", spider)

        future = asyncio.ensure_future(app.start())
        await semaphore.wait()

        assert spider.called, "the wait method was called successfully"

        await app.stop()
        future.cancel()


async def test_consumer_wait_method_behavior(host, port, password, monkeypatch):
    spider = AsyncMock()
    monkeypatch.setattr(asyncio, "sleep", spider)

    address = (host(), port(), password())
    app = Consumer(*address)

    app.protocol.is_connected = PropertyMock()
    app.protocol.is_connected.side_effect = [True, True, False]
    app.protocol.is_connected.__bool__ = lambda self: self()

    await app.wait()

    message = "The consumer stopped when the connection was closed."
    assert spider.call_count == 2, message


async def test_receive_background_job_event(freeswitch, background_job):
    async with freeswitch as server:
        server.events.append(background_job)
        server.oncommand(
            "filter Event-Name BACKGROUND_JOB",
            "+OK filter added. [filter]=[Event-Name BACKGROUND_JOB]",
        )

        buffer: asyncio.Queue[Any] = asyncio.Queue()
        app = Consumer(*server.address)

        @app.handle("BACKGROUND_JOB")
        async def handler(event):
            await buffer.put(event)

        future = asyncio.ensure_future(app.start())
        event = await buffer.get()

        assert event == {
            "Content-Type": "text/event-plain",
            "Core-UUID": "42bdf272-16e6-11dd-b7a0-db4edd065621",
            "Event-Date-GMT": "Thu, 01 May 2008 23:37:03 GMT",
            "Event-Date-Local": "2008-05-02 07:37:03",
            "Event-Date-timestamp": "1209685023894968",
            "Event-Name": "BACKGROUND_JOB",
            "FreeSWITCH-Hostname": "ser",
            "FreeSWITCH-IPv4": "192.168.1.104",
            "FreeSWITCH-IPv6": "127.0.0.1",
            "Job-Command": "originate",
            "Job-Command-Arg": "sofia/default/1005 '&park'",
            "Job-UUID": "7f4db78a-17d7-11dd-b7a0-db4edd065621",
            "Event-Calling-File": "mod_event_socket.c",
            "Event-Calling-Function": "api_exec",
            "Event-Calling-Line-Number": "609",
            "Content-Length": "40",
        }, "The header parsing did not go as expected."

        assert (
            event.body == "+OK 7f4de4bc-17d7-11dd-b7a0-db4edd065621"
        ), "The body parsing did not go as expected."

        await app.stop()
        future.cancel()


async def test_receive_mod_audio_stream_play(freeswitch, mod_audio_stream_play):
    async with freeswitch as server:
        server.events.append(mod_audio_stream_play)

        server.oncommand(
            "filter Event-Subclass mod_audio_stream::play",
            "+OK filter added. [filter]=[Event-Name mod_audio_stream::play]",
        )

        buffer: asyncio.Queue[Any] = asyncio.Queue()
        app = Consumer(*server.address)

        @app.handle("mod_audio_stream::play")
        async def handler(event):
            await buffer.put(event)

        future = asyncio.ensure_future(app.start())
        event = await buffer.get()

        assert event == {
            "Event-Subclass": "mod_audio_stream::play",
            "Event-Name": "CUSTOM",
            "Core-UUID": "5f1c2da2-9958-44b2-ae1b-bce99d38f971",
            "FreeSWITCH-Hostname": "freeswitch-01",
            "FreeSWITCH-Switchname": "freeswitch-01",
            "FreeSWITCH-IPv4": "10.10.10.23",
            "FreeSWITCH-IPv6": "::1",
            "Event-Date-Local": "2024-08-16 13:46:02",
            "Event-Date-GMT": "Fri, 16 Aug 2024 16:46:02 GMT",
            "Event-Date-Timestamp": "1723826762670076",
            "Event-Calling-File": "mod_audio_stream.c",
            "Event-Calling-Function": "responseHandler",
            "Event-Calling-Line-Number": "16",
            "Event-Sequence": "5642",
            "Channel-State": "CS_EXECUTE",
            "Channel-Call-State": "ACTIVE",
            "Channel-State-Number": "4",
            "Channel-Name": "sofia/internal/1000@10.10.10.23",
            "Unique-ID": "84e7dad0-dc1e-4234-8c56-5688e2069d99",
            "Call-Direction": "inbound",
            "Presence-Call-Direction": "inbound",
            "Channel-HIT-Dialplan": "true",
            "Channel-Presence-ID": "1000@10.10.10.23",
            "Channel-Call-UUID": "84e7dad0-dc1e-4234-8c56-5688e2069d99",
            "Answer-State": "answered",
            "Channel-Read-Codec-Name": "opus",
            "Channel-Read-Codec-Rate": "48000",
            "Channel-Read-Codec-Bit-Rate": "0",
            "Channel-Write-Codec-Name": "opus",
            "Channel-Write-Codec-Rate": "48000",
            "Channel-Write-Codec-Bit-Rate": "0",
            "Caller-Direction": "inbound",
            "Caller-Logical-Direction": "inbound",
            "Caller-Username": "1000",
            "Caller-Dialplan": "XML",
            "Caller-Caller-ID-Name": "1000",
            "Caller-Caller-ID-Number": "1000",
            "Caller-Orig-Caller-ID-Name": "1000",
            "Caller-Orig-Caller-ID-Number": "1000",
            "Caller-Network-Addr": "10.10.10.4",
            "Caller-ANI": "1000",
            "Caller-Destination-Number": "4001",
            "Caller-Unique-ID": "84e7dad0-dc1e-4234-8c56-5688e2069d99",
            "Caller-Source": "mod_sofia",
            "Caller-Context": "default",
            "Caller-Channel-Name": "sofia/internal/1000@10.10.10.23",
            "Caller-Profile-Index": "1",
            "Caller-Profile-Created-Time": "1723826754130221",
            "Caller-Channel-Created-Time": "1723826754130221",
            "Caller-Channel-Answered-Time": "1723826754130221",
            "Caller-Channel-Progress-Time": "0",
            "Caller-Channel-Progress-Media-Time": "1723826754130221",
            "Caller-Channel-Hangup-Time": "0",
            "Caller-Channel-Transfer-Time": "0",
            "Caller-Channel-Resurrect-Time": "0",
            "Caller-Channel-Bridged-Time": "0",
            "Caller-Channel-Last-Hold": "0",
            "Caller-Channel-Hold-Accum": "0",
            "Caller-Screen-Bit": "true",
            "Caller-Privacy-Hide-Name": "false",
            "Caller-Privacy-Hide-Number": "false",
            "variable_direction": "inbound",
            "variable_uuid": "84e7dad0-dc1e-4234-8c56-5688e2069d99",
            "variable_session_id": "46",
            "variable_sip_from_user": "1000",
            "variable_sip_from_uri": "1000@10.10.10.23",
            "variable_sip_from_host": "10.10.10.23",
            "variable_video_media_flow": "disabled",
            "variable_text_media_flow": "disabled",
            "variable_channel_name": "sofia/internal/1000@10.10.10.23",
            "variable_sip_call_id": "nRVIux7E3nnbt4PrQw63Ir8tVRew3rTJ",
            "variable_sip_local_network_addr": "170.247.5.105",
            "variable_sip_network_ip": "10.10.10.4",
            "variable_sip_network_port": "65154",
            "variable_sip_invite_stamp": "1723826754130221",
            "variable_sip_received_ip": "10.10.10.4",
            "variable_sip_received_port": "65154",
            "variable_sip_via_protocol": "udp",
            "variable_sip_authorized": "true",
            "variable_Event-Name": "REQUEST_PARAMS",
            "variable_Core-UUID": "5f1c2da2-9958-44b2-ae1b-bce99d38f971",
            "variable_FreeSWITCH-Hostname": "freeswitch-01",
            "variable_FreeSWITCH-Switchname": "freeswitch-01",
            "variable_FreeSWITCH-IPv4": "10.10.10.23",
            "variable_FreeSWITCH-IPv6": "::1",
            "variable_Event-Date-Local": "2024-08-16 13:45:54",
            "variable_Event-Date-GMT": "Fri, 16 Aug 2024 16:45:54 GMT",
            "variable_Event-Date-Timestamp": "1723826754130221",
            "variable_Event-Calling-File": "sofia.c",
            "variable_Event-Calling-Function": "sofia_handle_sip_i_invite",
            "variable_Event-Calling-Line-Number": "10723",
            "variable_Event-Sequence": "5591",
            "variable_sip_number_alias": "1000",
            "variable_sip_auth_username": "1000",
            "variable_sip_auth_realm": "10.10.10.23",
            "variable_number_alias": "1000",
            "variable_requested_user_name": "1000",
            "variable_requested_domain_name": "10.10.10.23",
            "variable_record_stereo": "true",
            "variable_default_gateway": "example.com",
            "variable_default_areacode": "918",
            "variable_transfer_fallback_extension": "operator",
            "variable_toll_allow": "domestic,international,local",
            "variable_accountcode": "1000",
            "variable_user_context": "default",
            "variable_effective_caller_id_name": "Extension 1000",
            "variable_effective_caller_id_number": "1000",
            "variable_outbound_caller_id_name": "FreeSWITCH",
            "variable_outbound_caller_id_number": "0000000000",
            "variable_callgroup": "techsupport",
            "variable_user_name": "1000",
            "variable_domain_name": "10.10.10.23",
            "variable_sip_from_user_stripped": "1000",
            "variable_sip_from_tag": "ctd4Q7kZX1X-ymiaOZW75CCNoctiyssB",
            "variable_sofia_profile_name": "internal",
            "variable_sofia_profile_url": "sip:mod_sofia@170.247.5.105:5060",
            "variable_recovery_profile_name": "internal",
            "variable_sip_full_via": "SIP/2.0/UDP 10.10.10.4:65154;rport=65154;branch=z9hG4bKPjUtX7iY.6-KV2faycxhzseZiQy-KTpp9v",
            "variable_sip_from_display": "1000",
            "variable_sip_full_from": '"1000" <sip:1000@10.10.10.23>;tag=ctd4Q7kZX1X-ymiaOZW75CCNoctiyssB',
            "variable_sip_full_to": "sip:4001@10.10.10.23",
            "variable_sip_allow": "PRACK, INVITE, ACK, BYE, CANCEL, UPDATE, INFO, SUBSCRIBE, NOTIFY, REFER, MESSAGE, OPTIONS",
            "variable_sip_req_user": "4001",
            "variable_sip_req_uri": "4001@10.10.10.23",
            "variable_sip_req_host": "10.10.10.23",
            "variable_sip_to_user": "4001",
            "variable_sip_to_uri": "4001@10.10.10.23",
            "variable_sip_to_host": "10.10.10.23",
            "variable_sip_contact_params": "ob",
            "variable_sip_contact_user": "1000",
            "variable_sip_contact_port": "65154",
            "variable_sip_contact_uri": "1000@10.10.10.4:65154",
            "variable_sip_contact_host": "10.10.10.4",
            "variable_sip_user_agent": "Telephone 1.6",
            "variable_sip_via_host": "10.10.10.4",
            "variable_sip_via_port": "65154",
            "variable_sip_via_rport": "65154",
            "variable_max_forwards": "70",
            "variable_presence_id": "1000@10.10.10.23",
            "variable_switch_r_sdp": "v=0\r\no=- 3932815554 3932815554 IN IP4 10.10.10.4\r\ns=pjmedia\r\nb=AS:117\r\nt=0 0\r\na=X-nat:0\r\nm=audio 4004 RTP/AVP 96 9 8 0 101 102\r\nc=IN IP4 10.10.10.4\r\nb=TIAS:96000\r\na=rtpmap:96 opus/48000/2\r\na=fmtp:96 useinbandfec=1\r\na=rtpmap:9 G722/8000\r\na=rtpmap:8 PCMA/8000\r\na=rtpmap:0 PCMU/8000\r\na=rtpmap:101 telephone-event/48000\r\na=fmtp:101 0-16\r\na=rtpmap:102 telephone-event/8000\r\na=fmtp:102 0-16\r\na=rtcp:4005 IN IP4 10.10.10.4\r\na=ssrc:1491843177 cname:242da6923112cdcc\r\n",
            "variable_ep_codec_string": "mod_opus.opus@48000h@20i@2c,mod_spandsp.G722@8000h@20i@64000b,CORE_PCM_MODULE.PCMA@8000h@20i@64000b,CORE_PCM_MODULE.PCMU@8000h@20i@64000b",
            "variable_DP_MATCH": "ARRAY::DELAYED NEGOTIATION|:DELAYED NEGOTIATION",
            "variable_call_uuid": "84e7dad0-dc1e-4234-8c56-5688e2069d99",
            "variable_open": "true",
            "variable_RFC2822_DATE": "Fri, 16 Aug 2024 13:45:54 -0300",
            "variable_export_vars": "RFC2822_DATE",
            "variable_rtp_use_codec_string": "OPUS,G722,PCMU,PCMA,H264,VP8",
            "variable_remote_video_media_flow": "inactive",
            "variable_remote_text_media_flow": "inactive",
            "variable_remote_audio_media_flow": "sendrecv",
            "variable_audio_media_flow": "sendrecv",
            "variable_rtp_remote_audio_rtcp_port": "4005",
            "variable_rtp_audio_recv_pt": "96",
            "variable_rtp_use_codec_name": "opus",
            "variable_rtp_use_codec_fmtp": "useinbandfec=1",
            "variable_rtp_use_codec_rate": "48000",
            "variable_rtp_use_codec_ptime": "20",
            "variable_rtp_use_codec_channels": "1",
            "variable_rtp_last_audio_codec_string": "opus@48000h@20i@1c",
            "variable_read_codec": "opus",
            "variable_original_read_codec": "opus",
            "variable_read_rate": "48000",
            "variable_original_read_rate": "48000",
            "variable_write_codec": "opus",
            "variable_write_rate": "48000",
            "variable_dtmf_type": "rfc2833",
            "variable_local_media_ip": "10.10.10.23",
            "variable_local_media_port": "19072",
            "variable_advertised_media_ip": "10.10.10.23",
            "variable_rtp_use_timer_name": "soft",
            "variable_rtp_use_pt": "96",
            "variable_rtp_use_ssrc": "3539919802",
            "variable_rtp_2833_send_payload": "101",
            "variable_rtp_2833_recv_payload": "101",
            "variable_remote_media_ip": "10.10.10.4",
            "variable_remote_media_port": "4004",
            "variable_rtp_local_sdp_str": "v=0\r\no=FreeSWITCH 1723807682 1723807683 IN IP4 10.10.10.23\r\ns=FreeSWITCH\r\nc=IN IP4 10.10.10.23\r\nt=0 0\r\nm=audio 19072 RTP/AVP 96 101\r\na=rtpmap:96 opus/48000/2\r\na=fmtp:96 useinbandfec=1\r\na=rtpmap:101 telephone-event/48000\r\na=fmtp:101 0-15\r\na=ptime:20\r\na=sendrecv\r\na=rtcp:19073 IN IP4 10.10.10.23\r\n",
            "variable_endpoint_disposition": "ANSWER",
            "variable_send_silence_when_idle": "-1",
            "variable_hangup_after_bridge": "false",
            "variable_park_after_bridge": "true",
            "variable_playback_terminators": "none",
            "variable_STREAM_BUFFER_SIZE": "100",
            "variable_current_application_data": "127.0.0.1:9000 async full",
            "variable_current_application": "socket",
            "variable_socket_host": "127.0.0.1",
            "Content-Length": "103",
        }, "The header parsing did not go as expected."

        assert (
            event.body
            == '{"audioDataType":"raw","sampleRate":16000,"file":"/tmp/84e7dad0-dc1e-4234-8c56-5688e2069d99_0.tmp.r16"}'
        ), "The body parsing did not go as expected."

        await app.stop()
        future.cancel()
