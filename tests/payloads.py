from textwrap import dedent


mod_audio_stream_play = dedent(
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


heartbeat = dedent(
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


channel_create = dedent(
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


background_job = dedent(
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


custom = dedent(
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


register = dedent(
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


connect = dedent(
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


generic = dedent(
    """\
    Content-Type: command/reply
    Reply-Text: Reply generic command
    """
)


channel_state = dedent(
    """\
    Event-Name: CHANNEL_STATE
    Unique-ID: {unique_id}
    Channel-State: {state}
    variable_test_key: {variable_test_key}
    Content-Type: text/event-plain
    Content-Length: 0
    """
)


dtmf = dedent(
    """\
    Event-Name: DTMF
    DTMF-Digit: {digit}
    Unique-ID: {unique_id}
    """
)


channel_answer = dedent(
    """\
    Event-Name: CHANNEL_ANSWER
    Unique-ID: {unique_id}
    """
)
