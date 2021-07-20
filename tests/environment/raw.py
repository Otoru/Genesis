STATUS = """UP 0 years, 80 days, 8 hours, 25 minutes, 5 seconds, 869 milliseconds, 87 microseconds
FreeSWITCH (Version 1.10.3-release git e52b1a8 2020-09-09 12:16:24Z 64bit) is ready
7653 session(s) since startup
0 session(s) - peak 2, last 5min 0
0 session(s) per Sec out of max 30, peak 14, last 5min 0
1000 session(s) max
min idle cpu 0.00/99.00
Current Stack Size/Max 240K/8192K"""

CONSOSE = "+OK console log level set to DEBUG"

COLORIZE = "+OK console color enabled"

VERSION = "FreeSWITCH Version 1.10.3-release+git~20200909T121624Z~e52b1a859b~64bit (git e52b1a8 2020-09-09 12:16:24Z 64bit)"

UPTIME = "6943047"

HEARTBEAT = """Event-Name: HEARTBEAT
Core-UUID: cb2d5146-9a99-11e4-9291-092b1a87b375
FreeSWITCH-Hostname: development
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

SHUTDOWN = """Event-Info: System Shutting Down
Event-Name: SHUTDOWN
Core-UUID: 596ab2fd-14c5-44b5-a02b-93ffb7cd5dd6
FreeSWITCH-Hostname: ********
FreeSWITCH-IPv4: ********
FreeSWITCH-IPv6: 127.0.0.1
Event-Date-Local: 2008-01-23%2013%3A48%3A13
Event-Date-GMT: Wed,%2023%20Jan%202008%2018%3A48%3A13%20GMT
Event-Date-timestamp: 1201114093012795
Event-Calling-File: switch_core.c
Event-Calling-Function: switch_core_destroy
Event-Calling-Line-Number: 1046"""

MODULE_LOAD = """type: codec
name: LPC-10%202.4kbps
Event-Name: MODULE_LOAD
Core-UUID: 2130a7d1-c1f7-44cd-8fae-8ed5946f3cec
FreeSWITCH-Hostname: localhost.localdomain
FreeSWITCH-IPv4: 10.0.1.250
FreeSWITCH-IPv6: 127.0.0.1
Event-Date-Local: 2007-12-16%2022%3A24%3A56
Event-Date-GMT: Mon,%2017%20Dec%202007%2004%3A24%3A56%20GMT
Event-Date-timestamp: 1197865496783828
Event-Calling-File: switch_loadable_module.c
Event-Calling-Function: switch_loadable_module_process
Event-Calling-Line-Number: 174"""

MODULE_UNLOAD = """
type: application
name: lua
description: Launch%20LUA%20ivr
syntax: %3Cscript%3E
Event-Name: MODULE_UNLOAD
Core-UUID: ab0feafa-a9b0-4d77-b0a8-341d6b100b4f
FreeSWITCH-Hostname: vertux
FreeSWITCH-IPv4: 192.168.77.248
FreeSWITCH-IPv6: %3A%3A1
Event-Date-Local: 2008-12-11%2013%3A14%3A23
Event-Date-GMT: Thu,%2011%20Dec%202008%2012%3A14%3A23%20GMT
Event-Date-timestamp: 1228997663531389
Event-Calling-File: switch_loadable_module.c
Event-Calling-Function: switch_loadable_module_unprocess
Event-Calling-Line-Number: 524"""

RELOADXML = """Event-Name: RELOADXML
Core-UUID: 6c6def18-9562-de11-a8e0-001fc6ab49e2
FreeSWITCH-Hostname: localhost.localdomain
FreeSWITCH-IPv4: 10.0.1.250
FreeSWITCH-IPv6: %3A%3A1
Event-Date-Local: 2009-06-26%2017%3A06%3A33
Event-Date-GMT: Fri,%2026%20Jun%202009%2021%3A06%3A33%20GMT
Event-Date-Timestamp: 1246050393884782
Event-Calling-File: switch_xml.c
Event-Calling-Function: switch_xml_open_root
Event-Calling-Line-Number: 1917"""

MESSAGE = """sip_mailbox: 1006
sip_auth_username: 1006
sip_auth_realm: 10.0.1.250
mailbox: 1006
user_name: 1006
domain_name: 10.0.1.250
accountcode: 1006
presence_id: 1006%4010.0.1.250
user_context: default
effective_caller_id_name: Extension%201006
effective_caller_id_number: 1006
Event-Name: MESSAGE
Core-UUID: 2130a7d1-c1f7-44cd-8fae-8ed5946f3cec
FreeSWITCH-Hostname: localhost.localdomain
FreeSWITCH-IPv4: 10.0.1.250
FreeSWITCH-IPv6: 127.0.0.1
Event-Date-Local: 2007-12-16%2022%3A28%3A29
Event-Date-GMT: Mon,%2017%20Dec%202007%2004%3A28%3A29%20GMT
Event-Date-timestamp: 1197865709262950
Event-Calling-File: sofia_reg.c
Event-Calling-Function: sofia_reg_handle_sip_i_register
Event-Calling-Line-Number: 636"""


CHANNEL_CREATE = """Event-Name: CHANNEL_CREATE
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

BACKGROUND_JOB = """Content-Length: 625
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

+OK 7f4de4bc-17d7-11dd-b7a0-db4edd065621"""

COMMANDS = {
    "uptime": UPTIME,
    "version": VERSION,
    "api status": STATUS,
    "api console loglevel": CONSOSE,
    "api console colorize": COLORIZE,
}

EVENTS = {
    "MESSAGE": MESSAGE,
    "SHUTDOWN": SHUTDOWN,
    "HEARTBEAT": HEARTBEAT,
    "RELOADXML": RELOADXML,
    "MODULE_LOAD": MODULE_LOAD,
    "MODULE_UNLOAD": MODULE_UNLOAD,
    "CHANNEL_CREATE": CHANNEL_CREATE,
    "BACKGROUND_JOB": BACKGROUND_JOB,
}
