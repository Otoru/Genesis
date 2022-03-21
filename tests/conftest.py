from __future__ import annotations

from asyncio import (
    open_connection,
    ensure_future,
    StreamReader,
    StreamWriter,
    start_server,
    Future,
    sleep,
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

import pytest


@pytest.fixture
def heartbeat() -> str:
    event = dedent(
        """\
            Event-Name: HEARTBEAT
            Core-UUID: cb2d5146-9a99-11e4-9291-092b1a87b375
            FreeSWITCH-Hostname: evoluxdev
            FreeSWITCH-Switchname: freeswitch
            FreeSWITCH-IPv4: 172.16.7.47
            FreeSWITCH-IPv6: %3A%3A1
            Event-Date-Local: 2015-01-19%2012%3A06%3A19
            Event-Date-GMT: Mon,%2019%20Jan%202015%2015%3A06%3A19%20GMT
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
        Content-Length: 625
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
        Content-Length: 41

        +OK 7f4de4bc-17d7-11dd-b7a0-db4edd065621
        """
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
        FreeSWITCH-IPv6: %3A%3A1
        Event-Date-Local: 2009-06-26%2017%3A06%3A33
        Event-Date-GMT: Fri,%2026%20Jun%202009%2021%3A06%3A33%20GMT
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
        Event-Subclass: sofia%3A%3Aregister
        Event-Name: CUSTOM
        Core-UUID: 662db344-5ecc-4eaa-9002-9992b7ab7c4d
        FreeSWITCH-Hostname: DEV-CS2
        FreeSWITCH-IPv4: 192.168.1.15
        FreeSWITCH-IPv6: %3A%3A1
        Event-Date-Local: 2009-06-16%2018%3A15%3A46
        Event-Date-GMT: Tue,%2016%20Jun%202009%2022%3A15%3A46%20GMT
        Event-Date-Timestamp: 1245190546126571
        Event-Calling-File: sofia_reg.c
        Event-Calling-Function: sofia_reg_handle_register
        Event-Calling-Line-Number: 1113
        profile-name: internal
        from-user: 1000
        from-host: 192.168.1.15
        presence-hosts: 192.168.1.15
        contact: %221000%22%20%3Csip%3A1000%40192.168.1.23%3A5060%3Bfs_nat%3Dyes%3Bfs_path%3Dsip%253A1000%2540192.168.1.23%253A5060%3E
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
        variable_sip_contact_uri: 1001%4010.0.1.241%3A2048
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
        server: ESLMixin, reader: StreamReader, writer: StreamWriter, dial: bool
    ) -> Awaitable[None]:

        if not dial:
            await server.send(writer, ["Content-Type: auth/request"])

        while server.is_running:
            request = None
            buffer = ""

            while server.is_running and not writer.is_closing():
                try:
                    content = await reader.read(1)

                except:
                    server.is_running = False
                    await server.stop()
                    break

                buffer += content.decode("utf-8")

                if buffer[-2:] == "\n\n" or buffer[-4:] == "\r\n\r\n":
                    request = buffer
                    break

            request = buffer.strip()

            if not request or not server.is_running:
                break

            else:
                await server.process(writer, request)


class Freeswitch(ESLMixin):
    def __init__(self, host: str, port: int, password: str) -> None:
        self.host = host
        self.port = port
        self.password = password
        self.is_running = False
        self.commands = dict()
        self.events = list()
        self.server: Optional[Server] = None
        self.processor: Optional[Awaitable] = None

    @property
    def address(self):
        return [self.host, self.port, self.password]

    async def shoot(self, writer: StreamWriter) -> None:
        if self.events:
            for event in self.events:
                await self.send(writer, event.splitlines())

    async def start(self) -> Awaitable[None]:
        handler = partial(self.handler, self, dial=False)
        self.server = await start_server(
            handler, self.host, self.port, family=socket.AF_INET
        )
        self.processor = ensure_future(self.server.serve_forever())
        self.is_running = True

    async def stop(self) -> Awaitable[None]:
        if self.server:
            self.is_running = False
            self.server.close()

            if self.processor:
                self.processor.cancel()

        await sleep(0.00001)

    async def __aenter__(self) -> Awaitable[Server]:
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
            await writer.wait_closed()

    async def process(self, writer: StreamWriter, request: str) -> Awaitable[None]:
        payload = copy(request)

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
            await self.stop()

        elif payload == "events plain ALL":
            await self.command(writer, "+OK event listener enabled plain")
            await self.shoot(writer)

        elif payload in self.commands:
            response = self.commands.get(payload)

            if payload.startswith("api"):
                await self.api(writer, response)

            else:
                await self.command(writer, response)

        else:
            if payload.startswith("api"):
                command = payload.replace("api", "").split().pop().strip()
                await self.command(writer, f"-ERR {command} command not found")

            else:
                await self.command(writer, "-ERR command not found")


@pytest.fixture
async def host() -> Callable[[], str]:
    return lambda: socket.gethostbyname(socket.gethostname())


@pytest.fixture
async def port() -> Callable[[], int]:
    return lambda: get_free_tcp_port()


@pytest.fixture
async def password() -> Callable[[], str]:
    return lambda: get_random_password(7)


@pytest.fixture
async def freeswitch(host, port, password) -> Freeswitch:
    server = Freeswitch(host(), port(), password())
    return server


class Dialplan(ESLMixin):
    def __init__(self) -> None:
        self.commands = dict()
        self.is_running = False
        self.worker: Optional[Future] = None
        self.reader: Optional[StreamReader] = None
        self.writer: Optional[StreamWriter] = None

    async def process(self, writer: StreamWriter, request: str) -> Awaitable[None]:
        payload = copy(request)

        if payload in self.commands:
            response = self.commands.get(payload)
            await self.send(writer, response.splitlines())

        elif payload in dir(self):
            method = getattr(self, payload)
            return await method()

    async def start(self, host, port) -> Awaitable[None]:
        self.is_running = True
        handler = partial(self.handler, self, dial=True)
        self.reader, self.writer = await open_connection(host, port)
        self.worker = ensure_future(handler(self.reader, self.writer))

    async def stop(self) -> Awaitable[None]:
        self.is_running = False

        if self.worker:
            self.worker.cancel()

        if not self.writer.is_closing():
            self.writer.close()
            await self.writer.wait_closed()

        await sleep(0.00001)


@pytest.fixture
async def dialplan(connect, generic) -> Dialplan:
    instance = Dialplan()
    instance.oncommand("linger", generic)
    instance.oncommand("connect", connect)
    instance.oncommand("myevents", generic)

    return instance
