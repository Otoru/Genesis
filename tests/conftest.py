from __future__ import annotations

import asyncio
from asyncio import (
    get_event_loop_policy,
    open_connection,
    ensure_future,
    StreamReader,
    StreamWriter,
    start_server,
    Future,
    sleep,
    CancelledError,
    TimeoutError as AsyncioTimeoutError
)
from typing import Awaitable, Callable, Optional, Dict, Union, List
from asyncio.base_events import Server
from abc import ABC, abstractmethod
from contextlib import closing
from functools import partial
from textwrap import dedent
from random import choices
from copy import copy
import string
import socket

from genesis.logger import logger as conftest_logger
conftest_logger.setLevel("DEBUG")

import pytest


@pytest.fixture
def mod_audio_stream_play() -> str:
    event = dedent(
        """\
        Event-Subclass: mod_audio_stream::play
        Event-Name: CUSTOM
        Core-UUID: 5f1c2da2-9958-44b2-ae1b-bce99d38f971
        FreeSWITCH-Hostname: freeswitch-01
        FreeSWITCH-Switchname: freeswitch-01
        FreeSWITCH-IPv4: 10.10.10.23
        FreeSWITCH-IPv6: ::1
        Event-Date-Local: 2024-08-16%2013:46:02
        Event-Date-GMT: Fri,%2016%20Aug%202024%2016:46:02%20GMT
        Event-Date-Timestamp: 1723826762670076
        Event-Calling-File: mod_audio_stream.c
        Event-Calling-Function: responseHandler
        Event-Calling-Line-Number: 16
        Event-Sequence: 5642
        Channel-State: CS_EXECUTE
        Channel-Call-State: ACTIVE
        Channel-State-Number: 4
        Channel-Name: sofia/internal/1000%4010.10.10.23
        Unique-ID: 84e7dad0-dc1e-4234-8c56-5688e2069d99
        Call-Direction: inbound
        Presence-Call-Direction: inbound
        Channel-HIT-Dialplan: true
        Channel-Presence-ID: 1000%4010.10.10.23
        Channel-Call-UUID: 84e7dad0-dc1e-4234-8c56-5688e2069d99
        Answer-State: answered
        Channel-Read-Codec-Name: opus
        Channel-Read-Codec-Rate: 48000
        Channel-Read-Codec-Bit-Rate: 0
        Channel-Write-Codec-Name: opus
        Channel-Write-Codec-Rate: 48000
        Channel-Write-Codec-Bit-Rate: 0
        Caller-Direction: inbound
        Caller-Logical-Direction: inbound
        Caller-Username: 1000
        Caller-Dialplan: XML
        Caller-Caller-ID-Name: 1000
        Caller-Caller-ID-Number: 1000
        Caller-Orig-Caller-ID-Name: 1000
        Caller-Orig-Caller-ID-Number: 1000
        Caller-Network-Addr: 10.10.10.4
        Caller-ANI: 1000
        Caller-Destination-Number: 4001
        Caller-Unique-ID: 84e7dad0-dc1e-4234-8c56-5688e2069d99
        Caller-Source: mod_sofia
        Caller-Context: default
        Caller-Channel-Name: sofia/internal/1000%4010.10.10.23
        Caller-Profile-Index: 1
        Caller-Profile-Created-Time: 1723826754130221
        Caller-Channel-Created-Time: 1723826754130221
        Caller-Channel-Answered-Time: 1723826754130221
        Caller-Channel-Progress-Time: 0
        Caller-Channel-Progress-Media-Time: 1723826754130221
        Caller-Channel-Hangup-Time: 0
        Caller-Channel-Transfer-Time: 0
        Caller-Channel-Resurrect-Time: 0
        Caller-Channel-Bridged-Time: 0
        Caller-Channel-Last-Hold: 0
        Caller-Channel-Hold-Accum: 0
        Caller-Screen-Bit: true
        Caller-Privacy-Hide-Name: false
        Caller-Privacy-Hide-Number: false
        variable_direction: inbound
        variable_uuid: 84e7dad0-dc1e-4234-8c56-5688e2069d99
        variable_session_id: 46
        variable_sip_from_user: 1000
        variable_sip_from_uri: 1000%4010.10.10.23
        variable_sip_from_host: 10.10.10.23
        variable_video_media_flow: disabled
        variable_text_media_flow: disabled
        variable_channel_name: sofia/internal/1000%4010.10.10.23
        variable_sip_call_id: nRVIux7E3nnbt4PrQw63Ir8tVRew3rTJ
        variable_sip_local_network_addr: 170.247.5.105
        variable_sip_network_ip: 10.10.10.4
        variable_sip_network_port: 65154
        variable_sip_invite_stamp: 1723826754130221
        variable_sip_received_ip: 10.10.10.4
        variable_sip_received_port: 65154
        variable_sip_via_protocol: udp
        variable_sip_authorized: true
        variable_Event-Name: REQUEST_PARAMS
        variable_Core-UUID: 5f1c2da2-9958-44b2-ae1b-bce99d38f971
        variable_FreeSWITCH-Hostname: freeswitch-01
        variable_FreeSWITCH-Switchname: freeswitch-01
        variable_FreeSWITCH-IPv4: 10.10.10.23
        variable_FreeSWITCH-IPv6: ::1
        variable_Event-Date-Local: 2024-08-16%2013:45:54
        variable_Event-Date-GMT: Fri,%2016%20Aug%202024%2016:45:54%20GMT
        variable_Event-Date-Timestamp: 1723826754130221
        variable_Event-Calling-File: sofia.c
        variable_Event-Calling-Function: sofia_handle_sip_i_invite
        variable_Event-Calling-Line-Number: 10723
        variable_Event-Sequence: 5591
        variable_sip_number_alias: 1000
        variable_sip_auth_username: 1000
        variable_sip_auth_realm: 10.10.10.23
        variable_number_alias: 1000
        variable_requested_user_name: 1000
        variable_requested_domain_name: 10.10.10.23
        variable_record_stereo: true
        variable_default_gateway: example.com
        variable_default_areacode: 918
        variable_transfer_fallback_extension: operator
        variable_toll_allow: domestic,international,local
        variable_accountcode: 1000
        variable_user_context: default
        variable_effective_caller_id_name: Extension%201000
        variable_effective_caller_id_number: 1000
        variable_outbound_caller_id_name: FreeSWITCH
        variable_outbound_caller_id_number: 0000000000
        variable_callgroup: techsupport
        variable_user_name: 1000
        variable_domain_name: 10.10.10.23
        variable_sip_from_user_stripped: 1000
        variable_sip_from_tag: ctd4Q7kZX1X-ymiaOZW75CCNoctiyssB
        variable_sofia_profile_name: internal
        variable_sofia_profile_url: sip:mod_sofia%40170.247.5.105:5060
        variable_recovery_profile_name: internal
        variable_sip_full_via: SIP/2.0/UDP%2010.10.10.4:65154%3Brport%3D65154%3Bbranch%3Dz9hG4bKPjUtX7iY.6-KV2faycxhzseZiQy-KTpp9v
        variable_sip_from_display: 1000
        variable_sip_full_from: %221000%22%20%3Csip:1000%4010.10.10.23%3E%3Btag%3Dctd4Q7kZX1X-ymiaOZW75CCNoctiyssB
        variable_sip_full_to: sip:4001%4010.10.10.23
        variable_sip_allow: PRACK,%20INVITE,%20ACK,%20BYE,%20CANCEL,%20UPDATE,%20INFO,%20SUBSCRIBE,%20NOTIFY,%20REFER,%20MESSAGE,%20OPTIONS
        variable_sip_req_user: 4001
        variable_sip_req_uri: 4001%4010.10.10.23
        variable_sip_req_host: 10.10.10.23
        variable_sip_to_user: 4001
        variable_sip_to_uri: 4001%4010.10.10.23
        variable_sip_to_host: 10.10.10.23
        variable_sip_contact_params: ob
        variable_sip_contact_user: 1000
        variable_sip_contact_port: 65154
        variable_sip_contact_uri: 1000%4010.10.10.4:65154
        variable_sip_contact_host: 10.10.10.4
        variable_sip_user_agent: Telephone%201.6
        variable_sip_via_host: 10.10.10.4
        variable_sip_via_port: 65154
        variable_sip_via_rport: 65154
        variable_max_forwards: 70
        variable_presence_id: 1000%4010.10.10.23
        variable_switch_r_sdp: v%3D0%0D%0Ao%3D-%203932815554%203932815554%20IN%20IP4%2010.10.10.4%0D%0As%3Dpjmedia%0D%0Ab%3DAS:117%0D%0At%3D0%200%0D%0Aa%3DX-nat:0%0D%0Am%3Daudio%204004%20RTP/AVP%2096%209%208%200%20101%20102%0D%0Ac%3DIN%20IP4%2010.10.10.4%0D%0Ab%3DTIAS:96000%0D%0Aa%3Drtpmap:96%20opus/48000/2%0D%0Aa%3Dfmtp:96%20useinbandfec%3D1%0D%0Aa%3Drtpmap:9%20G722/8000%0D%0Aa%3Drtpmap:8%20PCMA/8000%0D%0Aa%3Drtpmap:0%20PCMU/8000%0D%0Aa%3Drtpmap:101%20telephone-event/48000%0D%0Aa%3Dfmtp:101%200-16%0D%0Aa%3Drtpmap:102%20telephone-event/8000%0D%0Aa%3Dfmtp:102%200-16%0D%0Aa%3Drtcp:4005%20IN%20IP4%2010.10.10.4%0D%0Aa%3Dssrc:1491843177%20cname:242da6923112cdcc%0D%0A
        variable_ep_codec_string: mod_opus.opus%4048000h%4020i%402c,mod_spandsp.G722%408000h%4020i%4064000b,CORE_PCM_MODULE.PCMA%408000h%4020i%4064000b,CORE_PCM_MODULE.PCMU%408000h%4020i%4064000b
        variable_DP_MATCH: ARRAY::DELAYED%20NEGOTIATION%7C:DELAYED%20NEGOTIATION
        variable_call_uuid: 84e7dad0-dc1e-4234-8c56-5688e2069d99
        variable_open: true
        variable_RFC2822_DATE: Fri,%2016%20Aug%202024%2013:45:54%20-0300
        variable_export_vars: RFC2822_DATE
        variable_rtp_use_codec_string: OPUS,G722,PCMU,PCMA,H264,VP8
        variable_remote_video_media_flow: inactive
        variable_remote_text_media_flow: inactive
        variable_remote_audio_media_flow: sendrecv
        variable_audio_media_flow: sendrecv
        variable_rtp_remote_audio_rtcp_port: 4005
        variable_rtp_audio_recv_pt: 96
        variable_rtp_use_codec_name: opus
        variable_rtp_use_codec_fmtp: useinbandfec%3D1
        variable_rtp_use_codec_rate: 48000
        variable_rtp_use_codec_ptime: 20
        variable_rtp_use_codec_channels: 1
        variable_rtp_last_audio_codec_string: opus%4048000h%4020i%401c
        variable_read_codec: opus
        variable_original_read_codec: opus
        variable_read_rate: 48000
        variable_original_read_rate: 48000
        variable_write_codec: opus
        variable_write_rate: 48000
        variable_dtmf_type: rfc2833
        variable_local_media_ip: 10.10.10.23
        variable_local_media_port: 19072
        variable_advertised_media_ip: 10.10.10.23
        variable_rtp_use_timer_name: soft
        variable_rtp_use_pt: 96
        variable_rtp_use_ssrc: 3539919802
        variable_rtp_2833_send_payload: 101
        variable_rtp_2833_recv_payload: 101
        variable_remote_media_ip: 10.10.10.4
        variable_remote_media_port: 4004
        variable_rtp_local_sdp_str: v%3D0%0D%0Ao%3DFreeSWITCH%201723807682%201723807683%20IN%20IP4%2010.10.10.23%0D%0As%3DFreeSWITCH%0D%0Ac%3DIN%20IP4%2010.10.10.23%0D%0At%3D0%200%0D%0Am%3Daudio%2019072%20RTP/AVP%2096%20101%0D%0Aa%3Drtpmap:96%20opus/48000/2%0D%0Aa%3Dfmtp:96%20useinbandfec%3D1%0D%0Aa%3Drtpmap:101%20telephone-event/48000%0D%0Aa%3Dfmtp:101%200-15%0D%0Aa%3Dptime:20%0D%0Aa%3Dsendrecv%0D%0Aa%3Drtcp:19073%20IN%20IP4%2010.10.10.23%0D%0A
        variable_endpoint_disposition: ANSWER
        variable_send_silence_when_idle: -1
        variable_hangup_after_bridge: false
        variable_park_after_bridge: true
        variable_playback_terminators: none
        variable_STREAM_BUFFER_SIZE: 100
        variable_current_application_data: 127.0.0.1:9000%20async%20full
        variable_current_application: socket
        variable_socket_host: 127.0.0.1
        Content-Length: 103

        {"audioDataType":"raw","sampleRate":16000,"file":"/tmp/84e7dad0-dc1e-4234-8c56-5688e2069d99_0.tmp.r16"}"""
    )

    return event


@pytest.fixture
def heartbeat() -> str:
    event = dedent(
        """\
            Event-Name: HEARTBEAT
            Core-UUID: cb2d5146-9a99-11e4-9291-092b1a87b375
            FreeSWITCH-Hostname: evoluxdev
            FreeSWITCH-Switchname: freeswitch
            FreeSWITCH-IPv4: 172.16.7.47
            FreeSWITCH-IPv6: ::1
            Event-Date-Local: 2015-01-19%2012:06:19
            Event-Date-GMT: Mon,%2019%20Jan%202015%2015:06:19%20GMT
            Event-Date-Timestamp: 1421679979428652
            Event-Calling-File: switch_core.c
            Event-Calling-Function: send_heartbeat
            Event-Calling-Line-Number: 70
            Event-Sequence: 23910
            Event-Info: System%20Ready
            Up-Time: 0%20years,%201%20day,%2016%20hours,%2053%20minutes,%2014%20seconds,%20552%20milliseconds,%2035%20microseconds
            FreeSWITCH-Version: 1.5.15b%2Bgit~20141226T052811Z~0a66db6f12~64bit
            Uptime-msec: 147194552
            Session-Count: 0
            Max-Sessions: 1000
            Session-Per-Sec: 30
            Session-Per-Sec-Max: 2
            Session-Per-Sec-FiveMin: 0
            Session-Since-Startup: 34
            Session-Peak-Max: 4
            Session-Peak-FiveMin: 0
            Idle-CPU: 98.700000"""
    )

    return event


@pytest.fixture
def channel() -> Dict[str, str]:
    events = dict()

    events["create"] = dedent(
        """\
        Event-Name: CHANNEL_CREATE
        Core-UUID: ed56dab6-a6fc-11e4-960f-6f83a2e5e50a
        FreeSWITCH-Hostname: evoluxdev
        FreeSWITCH-Switchname: evoluxdev
        FreeSWITCH-IPv4: 172.16.7.69
        FreeSWITCH-IPv6: ::1
        Event-Date-Local: 2015-01-28 15:00:44
        Event-Date-GMT: Wed, 28 Jan 2015 18:00:44 GMT
        Event-Date-Timestamp: 1422468044671081
        Event-Calling-File: switch_core_state_machine.c
        Event-Calling-Function: switch_core_session_run
        Event-Calling-Line-Number: 509
        Event-Sequence: 3372
        Channel-State: CS_INIT
        Channel-Call-State: DOWN
        Channel-State-Number: 2
        Channel-Name: sofia/internal/100@192.168.50.4
        Unique-ID: d0b1da34-a727-11e4-9728-6f83a2e5e50a
        Call-Direction: inbound
        Presence-Call-Direction: inbound
        Channel-HIT-Dialplan: true
        Channel-Presence-ID: 100@192.168.50.4
        Channel-Call-UUID: d0b1da34-a727-11e4-9728-6f83a2e5e50a
        Answer-State: ringing
        Caller-Direction: inbound
        Caller-Logical-Direction: inbound
        Caller-Username: 100
        Caller-Dialplan: XML
        Caller-Caller-ID-Name: edev - 100
        Caller-Caller-ID-Number: 100
        Caller-Orig-Caller-ID-Name: edev - 100
        Caller-Orig-Caller-ID-Number: 100
        Caller-Network-Addr: 192.168.50.1
        Caller-ANI: 100
        Caller-Destination-Number: 101
        Caller-Unique-ID: d0b1da34-a727-11e4-9728-6f83a2e5e50a
        Caller-Source: mod_sofia
        Caller-Context: out-extensions
        Caller-Channel-Name: sofia/internal/100@192.168.50.4
        Caller-Profile-Index: 1
        Caller-Profile-Created-Time: 1422468044671081
        Caller-Channel-Created-Time: 1422468044671081
        Caller-Channel-Answered-Time: 0
        Caller-Channel-Progress-Time: 0
        Caller-Channel-Progress-Media-Time: 0
        Caller-Channel-Hangup-Time: 0
        Caller-Channel-Transfer-Time: 0
        Caller-Channel-Resurrect-Time: 0
        Caller-Channel-Bridged-Time: 0
        Caller-Channel-Last-Hold: 0
        Caller-Channel-Hold-Accum: 0
        Caller-Screen-Bit: true
        Caller-Privacy-Hide-Name: false
        Caller-Privacy-Hide-Number: false
        variable_direction: inbound
        variable_uuid: d0b1da34-a727-11e4-9728-6f83a2e5e50a
        variable_call_uuid: d0b1da34-a727-11e4-9728-6f83a2e5e50a
        variable_session_id: 9
        variable_sip_from_user: 100
        variable_sip_from_uri: 100@192.168.50.4
        variable_sip_from_host: 192.168.50.4
        variable_channel_name: sofia/internal/100@192.168.50.4
        variable_sip_call_id: 6bG.Hj5UCe8pDFEy1R9FO8EIfHtKrZ3H
        variable_ep_codec_string: GSM@8000h@20i@13200b,PCMU@8000h@20i@64000b,PCMA@8000h@20i@64000b,G722@8000h@20i@64000b
        variable_sip_local_network_addr: 192.168.50.4
        variable_sip_network_ip: 192.168.50.1
        variable_sip_network_port: 58588
        variable_sip_received_ip: 192.168.50.1
        variable_sip_received_port: 58588
        variable_sip_via_protocol: udp
        variable_sip_authorized: true
        variable_Event-Name: REQUEST_PARAMS
        variable_Core-UUID: ed56dab6-a6fc-11e4-960f-6f83a2e5e50a
        variable_FreeSWITCH-Hostname: evoluxdev
        variable_FreeSWITCH-Switchname: evoluxdev
        variable_FreeSWITCH-IPv4: 172.16.7.69
        variable_FreeSWITCH-IPv6: ::1
        variable_Event-Date-Local: 2015-01-28 15:00:44
        variable_Event-Date-GMT: Wed, 28 Jan 2015 18:00:44 GMT
        variable_Event-Date-Timestamp: 1422468044671081
        variable_Event-Calling-File: sofia.c
        variable_Event-Calling-Function: sofia_handle_sip_i_invite
        variable_Event-Calling-Line-Number: 8539
        variable_Event-Sequence: 3368
        variable_sip_number_alias: 100
        variable_sip_auth_username: 100
        variable_sip_auth_realm: 192.168.50.4
        variable_number_alias: 100
        variable_requested_domain_name: 192.168.50.4
        variable_record_stereo: true
        variable_transfer_fallback_extension: operator
        variable_toll_allow: celular_ddd,celular_local,fixo_ddd,fixo_local,ligar_para_outro_ramal,ramais_evolux_office
        variable_evolux_cc_position: 100
        variable_user_context: out-extensions
        variable_accountcode: dev
        variable_callgroup: dev
        variable_effective_caller_id_name: Evolux 100
        variable_effective_caller_id_number: 100
        variable_outbound_caller_id_name: Dev
        variable_outbound_caller_id_number: 0000000000
        variable_user_name: 100
        variable_domain_name: 192.168.50.4
        variable_sip_from_user_stripped: 100
        variable_sip_from_tag: ocZZPAo1FTdXA10orlmCaYeqc4mzYem1
        variable_sofia_profile_name: internal
        variable_recovery_profile_name: internal
        variable_sip_full_via: SIP/2.0/UDP 172.16.7.70:58588;rport=58588;branch=z9hG4bKPj-0Wi47Dyiq1mz3t.Bm8aluRrPEHF7-6C;received=192.168.50.1
        variable_sip_from_display: edev - 100
        variable_sip_full_from: "edev - 100" <sip:100@192.168.50.4>;tag=ocZZPAo1FTdXA10orlmCaYeqc4mzYem1
        variable_sip_full_to: <sip:101@192.168.50.4>
        variable_sip_req_user: 101
        variable_sip_req_uri: 101@192.168.50.4
        variable_sip_req_host: 192.168.50.4
        variable_sip_to_user: 101
        variable_sip_to_uri: 101@192.168.50.4
        variable_sip_to_host: 192.168.50.4
        variable_sip_contact_params: ob
        variable_sip_contact_user: 100
        variable_sip_contact_port: 58588
        variable_sip_contact_uri: 100@192.168.50.1:58588
        variable_sip_contact_host: 192.168.50.1
        variable_rtp_use_codec_string: G722,PCMA,PCMU,GSM,G729
        variable_sip_user_agent: Telephone 1.1.4
        variable_sip_via_host: 172.16.7.70
        variable_sip_via_port: 58588
        variable_sip_via_rport: 58588
        variable_max_forwards: 70
        variable_presence_id: 100@192.168.50.4
        variable_switch_r_sdp: v=0
        o=- 3631463817 3631463817 IN IP4 172.16.7.70
        s=pjmedia
        b=AS:84
        t=0 0
        a=X-nat:0
        m=audio 4016 RTP/AVP 103 102 104 109 3 0 8 9 101
        c=IN IP4 172.16.7.70
        b=AS:64000
        a=rtpmap:103 speex/16000
        a=rtpmap:102 speex/8000
        a=rtpmap:104 speex/32000
        a=rtpmap:109 iLBC/8000
        a=fmtp:109 mode=30
        a=rtpmap:3 GSM/8000
        a=rtpmap:0 PCMU/8000
        a=rtpmap:8 PCMA/8000
        a=rtpmap:9 G722/8000
        a=rtpmap:101 telephone-event/8000
        a=fmtp:101 0-15
        a=rtcp:4017 IN IP4 172.16.7.70

        variable_endpoint_disposition: DELAYED NEGOTIATION"""
    )

    return events


@pytest.fixture
def background_job() -> str:
    event = dedent(
        """\
        Content-Length: 582
        Content-Type: text/event-plain

        Job-UUID: 7f4db78a-17d7-11dd-b7a0-db4edd065621
        Job-Command: originate
        Job-Command-Arg: sofia/default/1005%20'%26park'
        Event-Name: BACKGROUND_JOB
        Core-UUID: 42bdf272-16e6-11dd-b7a0-db4edd065621
        FreeSWITCH-Hostname: ser
        FreeSWITCH-IPv4: 192.168.1.104
        FreeSWITCH-IPv6: 127.0.0.1
        Event-Date-Local: 2008-05-02%2007%3A37%3A03
        Event-Date-GMT: Thu,%2001%20May%202008%2023%3A37%3A03%20GMT
        Event-Date-timestamp: 1209685023894968
        Event-Calling-File: mod_event_socket.c
        Event-Calling-Function: api_exec
        Event-Calling-Line-Number: 609
        Content-Length: 40
        
        +OK 7f4de4bc-17d7-11dd-b7a0-db4edd065621"""
    )
    return event


@pytest.fixture
def custom() -> str:
    event = dedent(
        """\
        Event-Name: RELOADXML
        Core-UUID: 6c6def18-9562-de11-a8e0-001fc6ab49e2
        FreeSWITCH-Hostname: localhost.localdomain
        FreeSWITCH-IPv4: 10.0.1.250
        FreeSWITCH-IPv6: ::1
        Event-Date-Local: 2009-06-26%2017:06:33
        Event-Date-GMT: Fri,%2026%20Jun%202009%2021:06:33%20GMT
        Event-Date-Timestamp: 1246050393884782
        Event-Calling-File: switch_xml.c
        Event-Calling-Function: switch_xml_open_root
        Event-Calling-Line-Number: 1917
        Content-Length: 41
        Content-Length: 42
        Content-Length: 43
        """
    )
    return event


@pytest.fixture
def register() -> str:
    event = dedent(
        """\
        Event-Subclass: sofia::register
        Event-Name: CUSTOM
        Core-UUID: 662db344-5ecc-4eaa-9002-9992b7ab7c4d
        FreeSWITCH-Hostname: DEV-CS2
        FreeSWITCH-IPv4: 192.168.1.15
        FreeSWITCH-IPv6: ::1
        Event-Date-Local: 2009-06-16%2018:15:46
        Event-Date-GMT: Tue,%2016%20Jun%202009%2022:15:46%20GMT
        Event-Date-Timestamp: 1245190546126571
        Event-Calling-File: sofia_reg.c
        Event-Calling-Function: sofia_reg_handle_register
        Event-Calling-Line-Number: 1113
        profile-name: internal
        from-user: 1000
        from-host: 192.168.1.15
        presence-hosts: 192.168.1.15
        contact: %221000%22%20%3Csip:1000%40192.168.1.23:5060%3Bfs_nat%3Dyes%3Bfs_path%3Dsip%253A1000%2540192.168.1.23%253A5060%3E
        call-id: 002D61B2-5F3A-DD11-BF4B-00132019B750%40192.168.1.23
        rpid: unknown
        statusd: Registered(UDP-NAT)
        expires: 900
        to-user: 1000
        to-host: dev-cs2.fusedsolutions.com
        network-ip: 192.168.1.23
        network-port: 5060
        username: 1000
        realm: dev-cs2.fusedsolutions.com
        user-agent: SIPPER%20for%20PhonerLite"""
    )
    return event


@pytest.fixture
def connect() -> str:
    event = dedent(
        """\
        Channel-Username: 1001
        Channel-Dialplan: XML
        Channel-Caller-ID-Name: 1001
        Channel-Caller-ID-Number: 1001
        Channel-Network-Addr: 10.0.1.241
        Channel-Destination-Number: 886
        Channel-Unique-ID: 40117b0a-186e-11dd-bbcd-7b74b6b4d31e
        Channel-Source: mod_sofia
        Channel-Context: default
        Channel-Channel-Name: sofia/default/1001%4010.0.1.100
        Channel-Profile-Index: 1
        Channel-Channel-Created-Time: 1209749769132614
        Channel-Channel-Answered-Time: 0
        Channel-Channel-Hangup-Time: 0
        Channel-Channel-Transfer-Time: 0
        Channel-Screen-Bit: yes
        Channel-Privacy-Hide-Name: no
        Channel-Privacy-Hide-Number: no
        Channel-State: CS_EXECUTE
        Channel-State-Number: 4
        Channel-Name: sofia/default/1001%4010.0.1.100
        Unique-ID: 40117b0a-186e-11dd-bbcd-7b74b6b4d31e
        Call-Direction: inbound
        Answer-State: early
        Channel-Read-Codec-Name: G722
        Channel-Read-Codec-Rate: 16000
        Channel-Write-Codec-Name: G722
        Channel-Write-Codec-Rate: 16000
        Caller-Username: 1001
        Caller-Dialplan: XML
        Caller-Caller-ID-Name: 1001
        Caller-Caller-ID-Number: 1001
        Caller-Network-Addr: 10.0.1.241
        Caller-Destination-Number: 886
        Caller-Unique-ID: 40117b0a-186e-11dd-bbcd-7b74b6b4d31e
        Caller-Source: mod_sofia
        Caller-Context: default
        Caller-Channel-Name: sofia/default/1001%4010.0.1.100
        Caller-Profile-Index: 1
        Caller-Channel-Created-Time: 1209749769132614
        Caller-Channel-Answered-Time: 0
        Caller-Channel-Hangup-Time: 0
        Caller-Channel-Transfer-Time: 0
        Caller-Screen-Bit: yes
        Caller-Privacy-Hide-Name: no
        Caller-Privacy-Hide-Number: no
        variable_sip_authorized: true
        variable_sip_mailbox: 1001
        variable_sip_auth_username: 1001
        variable_sip_auth_realm: 10.0.1.100
        variable_mailbox: 1001
        variable_user_name: 1001
        variable_domain_name: 10.0.1.100
        variable_accountcode: 1001
        variable_user_context: default
        variable_effective_caller_id_name: Extension%201001
        variable_effective_caller_id_number: 1001
        variable_sip_from_user: 1001
        variable_sip_from_uri: 1001%4010.0.1.100
        variable_sip_from_host: 10.0.1.100
        variable_sip_from_user_stripped: 1001
        variable_sip_from_tag: wrgb4s5idf
        variable_sofia_profile_name: default
        variable_sofia_profile_domain_name: 10.0.1.100
        variable_sofia_profile_domain_name: 10.0.1.100
        variable_sip_req_params: user%3Dphone
        variable_sip_req_user: 886
        variable_sip_req_uri: 886%4010.0.1.100
        variable_sip_req_host: 10.0.1.100
        variable_sip_to_params: user%3Dphone
        variable_sip_to_user: 886
        variable_sip_to_uri: 886%4010.0.1.100
        variable_sip_to_host: 10.0.1.100
        variable_sip_contact_params: line%3Dnc7obl5w
        variable_sip_contact_user: 1001
        variable_sip_contact_port: 2048
        variable_sip_contact_uri: 1001%4010.0.1.241:2048
        variable_sip_contact_host: 10.0.1.241
        variable_channel_name: sofia/default/1001%4010.0.1.100
        variable_sip_call_id: 3c2bb21af10b-ogphkonpwqet
        variable_sip_user_agent: snom300/7.1.30
        variable_sip_via_host: 10.0.1.241
        variable_sip_via_port: 2048
        variable_sip_via_rport: 2048
        variable_max_forwards: 70
        variable_presence_id: 1001%4010.0.1.100
        variable_sip_h_P-Key-Flags: keys%3D%223%22
        variable_remote_media_ip: 10.0.1.241
        variable_remote_media_port: 62258
        variable_read_codec: G722
        variable_read_rate: 16000
        variable_write_codec: G722
        variable_write_rate: 16000
        variable_open: true
        variable_socket_host: 127.0.0.1
        variable_local_media_ip: 10.0.1.100
        variable_local_media_port: 62258
        variable_endpoint_disposition: EARLY%20MEDIA
        Content-Type: command/reply
        Socket-Mode: async
        Control: full"""
    )
    return event


@pytest.fixture
def generic() -> str:
    event = dedent(
        """\
        Content-Type: command/reply
        Reply-Text: Reply generic command
        """
    )
    return event


def get_free_tcp_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("", 0))
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return sock.getsockname()[1]


def get_random_password(length: int) -> str:
    options = string.ascii_letters + string.digits + string.punctuation
    result = "".join(choices(options, k=length))
    return result


class ESLMixin(ABC):
    is_running: bool
    commands: Dict[str, str]

    @staticmethod
    async def send(
        writer: StreamWriter, lines: Union[List[str], str]
    ) -> Awaitable[None]:
        if isinstance(lines, str):
            writer.write((lines + "\n").encode("utf-8"))

        else:
            for line in lines:
                writer.write((line + "\n").encode("utf-8"))

        writer.write("\n".encode("utf-8"))
        await writer.drain()

    def oncommand(self, command: str, response: str) -> None:
        self.commands[command] = response

    @abstractmethod
    async def process(self, writer: StreamWriter, request: str) -> Awaitable[None]:
        raise NotImplementedError()

    @staticmethod
    async def handler(
        server_instance: ESLMixin, reader: StreamReader, writer: StreamWriter, dial_param: bool
    ) -> None:
        client_address_info = writer.get_extra_info('peername')
        conftest_logger.debug(f"ESLMIXIN HANDLER [{client_address_info}]: New connection received. dial_param={dial_param}")

        if not dial_param and hasattr(server_instance, 'send') and callable(getattr(server_instance, 'send')):
            conftest_logger.debug(f"ESLMIXIN HANDLER [{client_address_info}]: Sending auth/request.")
            await server_instance.send(writer, ["Content-Type: auth/request"])

        try:
            while server_instance.is_running and not writer.is_closing():
                buffer = ""
                # Inner loop for reading a full request (until \n\n or \r\n\r\n)
                while server_instance.is_running and not writer.is_closing():
                    try:
                        # Add a timeout to reader.read to make it responsive to cancellation
                        char_bytes = await asyncio.wait_for(reader.read(1), timeout=0.1)
                    except AsyncioTimeoutError:
                        # Timeout is okay, just means no data, loop again to check server_instance.is_running
                        if not server_instance.is_running or writer.is_closing():
                            break # Break inner while if server stopped during timeout
                        continue
                    except CancelledError:
                        conftest_logger.debug(f"ESLMIXIN HANDLER [{client_address_info}]: Read cancelled.")
                        raise  # Propagate to outer try-except
                    except ConnectionResetError:
                        conftest_logger.debug(f"ESLMIXIN HANDLER [{client_address_info}]: Connection reset.")
                        return  # Connection is gone, exit handler
                    except Exception as e_read:
                        if server_instance.is_running: # Log only if we expected to be running
                             conftest_logger.error(f"ESLMIXIN HANDLER [{client_address_info}]: Exception during read: {e_read}", exc_info=True)
                        return  # Error, exit handler

                    if not char_bytes:  # EOF
                        conftest_logger.debug(f"ESLMIXIN HANDLER [{client_address_info}]: EOF received.")
                        return  # Connection closed by peer, exit handler
                    
                    try:
                        buffer += char_bytes.decode("utf-8", errors="ignore")
                    except UnicodeDecodeError:
                        conftest_logger.warning("Non-decodable character encountered, skipping.")
                        continue

                    if buffer.endswith("\n\n") or buffer.endswith("\r\n\r\n"):
                        break  # Got a full request
                
                if not server_instance.is_running or writer.is_closing():
                    conftest_logger.debug(f"ESLMIXIN HANDLER [{client_address_info}]: Exiting main read loop. is_running={server_instance.is_running}, writer_closing={writer.is_closing()}")
                    break  # Exit main while loop

                request_data = buffer.strip()
                if not request_data:
                    if reader.at_eof() or writer.is_closing():
                        conftest_logger.debug(f"ESLMIXIN HANDLER [{client_address_info}]: Empty request and EOF/closing. Exiting.")
                        break
                    continue

                conftest_logger.trace(f"ESLMIXIN HANDLER [{client_address_info}]: Processing request: {request_data[:100]}...")
                await server_instance.process(writer, request_data)

        except CancelledError:
            conftest_logger.debug(f"ESLMIXIN HANDLER [{client_address_info}]: Handler task cancelled.")
        except Exception as e_handler:
            if server_instance.is_running:
                conftest_logger.error(f"ESLMIXIN HANDLER [{client_address_info}]: Unhandled exception in handler: {e_handler} (Type: {type(e_handler)})", exc_info=True)
        finally:
            conftest_logger.debug(f"ESLMIXIN HANDLER [{client_address_info}]: Handler finishing. Closing writer.")
            if writer and not writer.is_closing():
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception as e_wc:
                    conftest_logger.warning(f"ESLMIXIN HANDLER [{client_address_info}]: Error during final writer.wait_closed(): {e_wc}")
            conftest_logger.debug(f"ESLMIXIN HANDLER [{client_address_info}]: Handler finished.")


class Freeswitch(ESLMixin):
    def __init__(self, host: str, port: int, password: str) -> None:
        conftest_logger.debug(f"FREESWITCH MOCK [{port}]: __init__ called.")
        self.host = host
        self.port = port
        self.password = password
        self.is_running = False
        self.commands = dict()
        self.events = list()
        self.server: Optional[Server] = None
        self.processor: Optional[Future] = None # This is the serve_forever task
        self.client_handler_tasks: List[asyncio.Task] = [] # To keep track of client handlers

    @property
    def address(self):
        return [self.host, self.port, self.password]

    async def shoot(self, writer: StreamWriter) -> None:
        if self.events:
            for event in self.events:
                await self.send(writer, event.splitlines())

    async def _client_handler_wrapper(self, reader: StreamReader, writer: StreamWriter):
        # Wrapper to manage client handler tasks
        task = asyncio.create_task(ESLMixin.handler(self, reader, writer, False))
        self.client_handler_tasks.append(task)
        try:
            await task
        except CancelledError:
            conftest_logger.debug(f"FREESWITCH MOCK [{self.port}]: Client handler task cancelled.")
        finally:
            if task in self.client_handler_tasks:
                self.client_handler_tasks.remove(task)


    async def start(self) -> Awaitable[None]:
        conftest_logger.trace(f"FREESWITCH MOCK [{self.port}]: start() - ENTER")
        if self.is_running:
            conftest_logger.warning(f"FREESWITCH MOCK [{self.port}]: start() called but server is already running. Skipping.")
            return

        self.is_running = True # Set before starting server to allow handlers to run
        
        conftest_logger.debug(f"FREESWITCH MOCK [{self.port}]: start() - About to call start_server for {self.host}:{self.port}")
        try:
            self.server = await start_server(
                self._client_handler_wrapper, self.host, self.port, family=socket.AF_INET
            )
            conftest_logger.debug(f"FREESWITCH MOCK [{self.port}]: start() - start_server SUCCEEDED. Server: {self.server}")
        except Exception as e_ss:
            conftest_logger.critical(f"FREESWITCH MOCK [{self.port}]: start() - start_server FAILED: {type(e_ss).__name__}: {e_ss}", exc_info=True)
            self.is_running = False 
            raise

        self.processor = ensure_future(self.server.serve_forever())
        conftest_logger.debug(f"FREESWITCH MOCK [{self.port}]: start() - serve_forever task created: {self.processor}")

    async def stop(self) -> Awaitable[None]:
        current_is_running = self.is_running
        self.is_running = False # Signal all handlers to stop first

        if not current_is_running and not self.server and not self.client_handler_tasks:
            conftest_logger.debug(f"FREESWITCH MOCK [{self.port}]: stop() - Already stopped or never fully started, returning.")
            return

        # Cancel and await client handler tasks
        if self.client_handler_tasks:
            conftest_logger.debug(f"FREESWITCH MOCK [{self.port}]: stop() - Cancelling {len(self.client_handler_tasks)} client handler tasks.")
            for task in list(self.client_handler_tasks): # Iterate over a copy
                if not task.done():
                    task.cancel()
            results = await asyncio.gather(*self.client_handler_tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, CancelledError):
                    conftest_logger.debug(f"FREESWITCH MOCK [{self.port}]: Client handler task {i} successfully cancelled.")
                elif isinstance(result, Exception):
                    conftest_logger.error(f"FREESWITCH MOCK [{self.port}]: Client handler task {i} raised an exception: {result}", exc_info=True)
            self.client_handler_tasks.clear()
            conftest_logger.debug(f"FREESWITCH MOCK [{self.port}]: stop() - All client handler tasks processed.")


        # Stop the main server
        if self.server:
            self.server.close()
            try:
                await self.server.wait_closed()
                conftest_logger.debug(f"FREESWITCH MOCK [{self.port}]: stop() - Server.wait_closed() completed.")
            except Exception as e_wc:
                conftest_logger.warning(f"FREESWITCH MOCK [{self.port}]: stop() - Exception during server.wait_closed(): {e_wc}")
            self.server = None

        # Cancel and await the server's serve_forever task (self.processor)
        if self.processor:
            if not self.processor.done():
                self.processor.cancel()
                try:
                    await self.processor
                    conftest_logger.debug(f"FREESWITCH MOCK [{self.port}]: stop() - Awaited self.processor successfully after cancel.")
                except CancelledError:
                    conftest_logger.debug(f"FREESWITCH MOCK [{self.port}]: stop() - self.processor successfully cancelled.")
                except Exception as e_proc:
                    conftest_logger.error(f"FREESWITCH MOCK [{self.port}]: stop() - Exception from self.processor: {e_proc}", exc_info=True)
            else: # If already done, check for exceptions
                try:
                    exc = self.processor.exception()
                    if exc:
                         conftest_logger.warning(f"FREESWITCH MOCK [{self.port}]: stop() - self.processor was already done with exception: {exc}")
                except (CancelledError, asyncio.InvalidStateError):
                    pass # Expected or already handled
            self.processor = None

    async def __aenter__(self) -> Freeswitch:
        await self.start()
        return self

    async def __aexit__(self, *args, **kwargs) -> Awaitable[None]:
        await self.stop()

    async def command(self, writer: StreamWriter, command: str) -> Awaitable[None]:
        await self.send(
            writer, ["Content-Type: command/reply", f"Reply-Text: {command}"]
        )

    async def api(self, writer: StreamWriter, content: str) -> Awaitable[None]:
        length = len(content)
        await self.send(
            writer,
            [
                "Content-Type: api/response",
                f"Content-Length: {length}",
                "",
                *content.strip().splitlines(),
            ],
        )

    async def disconnect(self, writer: StreamWriter) -> Awaitable[None]:
        await self.send(
            writer,
            [
                "Content-Type: text/disconnect-notice",
                "Content-Length: 67",
            ],
        )
        await self.send(
            writer,
            [
                "Disconnected, goodbye.",
                "See you at ClueCon! http://www.cluecon.com/",
            ],
        )
        if not writer.is_closing():
            writer.close()
            try:
                await writer.wait_closed()
            except Exception as e_wdc:
                 conftest_logger.warning(f"FREESWITCH MOCK [{self.port}]: Exception during writer.wait_closed in disconnect: {e_wdc}")


    async def process(self, writer: StreamWriter, request: str) -> Awaitable[None]:
        payload = copy(request)
        client_address_info = writer.get_extra_info('peername', 'Unknown Peer')
        conftest_logger.trace(f"FREESWITCH MOCK [{self.port}] PROCESS from [{client_address_info}]: Received payload: {payload[:100]}...")


        if payload.startswith("auth"):
            received_password = payload.split().pop().strip()

            if self.password == received_password:
                await self.command(writer, "+OK accepted")

            else:
                await self.command(writer, "-ERR invalid")
                await self.disconnect(writer)

        elif payload == "exit":
            await self.command(writer, "+OK bye")
            await self.disconnect(writer)
            # No longer call self.stop() here, let __aexit__ or explicit test cleanup handle it.
            # This prevents issues if 'exit' is received while other clients are connected.

        elif payload == "events plain ALL":
            await self.command(writer, "+OK event listener enabled plain")
            await self.shoot(writer)

        elif payload in self.commands:
            response = self.commands.get(payload)
            if response is None: # Should not happen if key is in self.commands
                await self.command(writer, "-ERR command response not configured")
                return

            if payload.startswith("api"):
                await self.api(writer, response)
            else:
                await self.command(writer, response)

        else:
            if payload.startswith("api"):
                command_part = payload.split(" ", 1)
                actual_command = command_part[1] if len(command_part) > 1 else ""
                await self.command(writer, f"-ERR api {actual_command} command not found")
            else:
                await self.command(writer, f"-ERR {payload.split()[0] if payload else 'empty'} command not found")


@pytest.fixture(scope="session")
def event_loop(request: pytest.FixtureRequest):
    loop = get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def host() -> Callable[[], str]:
    return lambda: "127.0.0.1"


@pytest.fixture(scope="session")
async def port() -> Callable[[], int]:
    return lambda: get_free_tcp_port()


@pytest.fixture(scope="session")
async def password() -> Callable[[], str]:
    return lambda: get_random_password(7)


@pytest.fixture()
async def freeswitch(host, port, password) -> Freeswitch:
    server_instance = Freeswitch(host(), port(), password())
    conftest_logger.debug(f"PYTEST FIXTURE freeswitch - Freeswitch instance created for port {server_instance.port}. About to YIELD.")
    yield server_instance 
    conftest_logger.debug(f"PYTEST FIXTURE freeswitch - Resumed after YIELD for port {server_instance.port}. Ensuring server is stopped.")
    await server_instance.stop() # Ensure server is stopped after test, even if __aexit__ was used.
    conftest_logger.debug(f"PYTEST FIXTURE freeswitch - server_instance.stop() called. EXIT.")


class Dialplan(ESLMixin):
    def __init__(self) -> None:
        self.commands = dict()
        self.is_running = False
        self.worker: Optional[Future] = None # This is the ESLMixin.handler task
        self.reader: Optional[StreamReader] = None
        self.writer: Optional[StreamWriter] = None

    async def process(self, writer: StreamWriter, request: str) -> Awaitable[None]:
        payload = copy(request)
        client_address_info = writer.get_extra_info('peername', 'Unknown Peer')
        conftest_logger.trace(f"DIALPLAN PROCESS from [{client_address_info}]: Received payload: {payload[:100]}...")

        if payload in self.commands:
            response = self.commands.get(payload)
            if response is None: # Should not happen
                 await self.send(writer, ["Content-Type: command/reply", "Reply-Text: -ERR command response not configured"])
                 return
            await self.send(writer, response.splitlines())

        elif payload in dir(self) and callable(getattr(self, payload)):
            method = getattr(self, payload)
            await method()
        else:
            await self.send(writer, ["Content-Type: command/reply", f"Reply-Text: -ERR {payload.split()[0] if payload else 'empty'} command not found in Dialplan"])


    async def start(self, host_val, port_val) -> Awaitable[None]: # Renamed params to avoid conflict
        if self.is_running:
            conftest_logger.debug(f"Dialplan.start(): Already running. Skipping.")
            return

        self.is_running = True # Set before attempting connection
        try:
            conftest_logger.debug(f"Dialplan.start(): Attempting open_connection to {host_val}:{port_val}")
            self.reader, self.writer = await asyncio.wait_for(
                open_connection(host_val, port_val),
                timeout=10.0
            )
            conftest_logger.debug(f"Dialplan.start(): open_connection SUCCEEDED. Reader: {self.reader}, Writer: {self.writer}.")
        except AsyncioTimeoutError:
            conftest_logger.error(f"Dialplan.start(): TIMEOUT during open_connection to {host_val}:{port_val}")
            self.is_running = False
            raise ConnectionRefusedError(f"Dialplan timed out connecting to {host_val}:{port_val}")
        except ConnectionRefusedError as e_cr:
            conftest_logger.error(f"Dialplan.start(): ConnectionRefusedError during open_connection to {host_val}:{port_val}: {e_cr}")
            self.is_running = False
            raise
        except Exception as e_oc:
            conftest_logger.error(f"Dialplan.start(): EXCEPTION during open_connection to {host_val}:{port_val}: {type(e_oc).__name__}: {e_oc}", exc_info=True)
            self.is_running = False
            raise

        handler_coroutine = ESLMixin.handler(self, self.reader, self.writer, True)
        self.worker = ensure_future(handler_coroutine)
        conftest_logger.debug(f"Dialplan.start(): Worker task created: {self.worker}. ")

    async def stop(self) -> Awaitable[None]:
        conftest_logger.debug(f"Dialplan.stop(): ENTER. is_running={self.is_running}")
        current_is_running = self.is_running
        self.is_running = False # Signal handler to stop first

        if not current_is_running and not self.worker :
            conftest_logger.debug(f"Dialplan.stop(): Already stopped or never fully started.")
            return

        if self.worker:
            if not self.worker.done():
                self.worker.cancel()
                try:
                    await self.worker
                    conftest_logger.debug(f"Dialplan.stop(): Awaited self.worker successfully after cancel.")
                except CancelledError:
                    conftest_logger.debug(f"Dialplan.stop(): self.worker successfully cancelled.")
                except Exception as e_worker:
                    conftest_logger.error(f"Dialplan.stop(): Exception from self.worker: {e_worker}", exc_info=True)
            else:
                try:
                    exc = self.worker.exception()
                    if exc:
                         conftest_logger.warning(f"Dialplan.stop(): self.worker was already done with exception: {exc}")
                except (CancelledError, asyncio.InvalidStateError):
                    pass # Expected or already handled
            self.worker = None

        if self.writer:
            if not self.writer.is_closing():
                self.writer.close()
                try:
                    await self.writer.wait_closed()
                except Exception as e_wc:
                    conftest_logger.warning(f"Dialplan.stop(): Exception during self.writer.wait_closed(): {e_wc}")
            self.writer = None
        
        self.reader = None


@pytest.fixture
async def dialplan(connect, generic) -> Dialplan:
    instance = Dialplan()
    instance.oncommand("linger", generic)
    instance.oncommand("connect", connect)
    instance.oncommand("myevents", generic)
    yield instance
    conftest_logger.debug("PYTEST FIXTURE dialplan - Resumed after YIELD. Ensuring dialplan is stopped.")
    await instance.stop()
    conftest_logger.debug("PYTEST FIXTURE dialplan - instance.stop() called. EXIT.")
