from genesis.parser import parse_headers
from textwrap import dedent


def test_parse_heartbeat_event(heartbeat):
    got = parse_headers(heartbeat)
    expected = {
        "Core-UUID": "cb2d5146-9a99-11e4-9291-092b1a87b375",
        "Event-Calling-File": "switch_core.c",
        "Event-Calling-Function": "send_heartbeat",
        "Event-Calling-Line-Number": "70",
        "Event-Date-GMT": "Mon, 19 Jan 2015 15:06:19 GMT",
        "Event-Date-Local": "2015-01-19 12:06:19",
        "Event-Date-Timestamp": "1421679979428652",
        "Event-Info": "System Ready",
        "Event-Name": "HEARTBEAT",
        "Event-Sequence": "23910",
        "FreeSWITCH-Hostname": "evoluxdev",
        "FreeSWITCH-IPv4": "172.16.7.47",
        "FreeSWITCH-IPv6": "::1",
        "FreeSWITCH-Switchname": "freeswitch",
        "FreeSWITCH-Version": "1.5.15b+git~20141226T052811Z~0a66db6f12~64bit",
        "Idle-CPU": "98.700000",
        "Max-Sessions": "1000",
        "Session-Count": "0",
        "Session-Peak-FiveMin": "0",
        "Session-Peak-Max": "4",
        "Session-Per-Sec": "30",
        "Session-Per-Sec-FiveMin": "0",
        "Session-Per-Sec-Max": "2",
        "Session-Since-Startup": "34",
        "Up-Time": "0 years, 1 day, 16 hours, 53 minutes, 14 seconds, 552 milliseconds, 35 microseconds",
        "Uptime-msec": "147194552",
    }
    assert got == expected, "Event parsing did not happen as expected"


def test_parse_channel_create_event_with_multiline_field(channel):
    headers = parse_headers(channel["create"])
    got = headers["variable_switch_r_sdp"]
    expected = dedent(
        """\
            v=0
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
            a=rtcp:4017 IN IP4 172.16.7.70"""
    )

    assert got == expected, "Event parsing did not happen as expected"


def test_parse_background_job(background_job):
    got = parse_headers(background_job.split("\n\n").pop(1))
    expected = {
        "Content-Length": "40",
        "Core-UUID": "42bdf272-16e6-11dd-b7a0-db4edd065621",
        "Event-Calling-File": "mod_event_socket.c",
        "Event-Calling-Function": "api_exec",
        "Event-Calling-Line-Number": "609",
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
    }

    assert got == expected, "Event parsing did not happen as expected"


def test_parse_event_with_3_repeated_headers(custom):
    got = parse_headers(custom)
    expected = {
        "Content-Length": ["41", "42", "43"],
        "Core-UUID": "6c6def18-9562-de11-a8e0-001fc6ab49e2",
        "Event-Calling-File": "switch_xml.c",
        "Event-Calling-Function": "switch_xml_open_root",
        "Event-Calling-Line-Number": "1917",
        "Event-Date-GMT": "Fri, 26 Jun 2009 21:06:33 GMT",
        "Event-Date-Local": "2009-06-26 17:06:33",
        "Event-Date-Timestamp": "1246050393884782",
        "Event-Name": "RELOADXML",
        "FreeSWITCH-Hostname": "localhost.localdomain",
        "FreeSWITCH-IPv4": "10.0.1.250",
        "FreeSWITCH-IPv6": "::1",
    }

    assert got == expected, "Event parsing did not happen as expected"
