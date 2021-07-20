import pytest

from genesis.parser import parse

from environment import EVENTS


def test_parse_heartbeat_event():
    heartbeat = EVENTS["HEARTBEAT"]
    got = parse(heartbeat)

    expected = {
        "Event-Name": "HEARTBEAT",
        "Core-UUID": "cb2d5146-9a99-11e4-9291-092b1a87b375",
        "FreeSWITCH-Hostname": "development",
        "FreeSWITCH-Switchname": "freeswitch",
        "FreeSWITCH-IPv4": "172.16.7.47",
        "FreeSWITCH-IPv6": "::1",
        "Event-Date-Local": "2015-01-19 12:06:19",
        "Event-Date-GMT": "Mon, 19 Jan 2015 15:06:19 GMT",
        "Event-Date-Timestamp": "1421679979428652",
        "Event-Calling-File": "switch_core.c",
        "Event-Calling-Function": "send_heartbeat",
        "Event-Calling-Line-Number": "70",
        "Event-Sequence": "23910",
        "Event-Info": "System Ready",
        "Up-Time": "0 years, 1 day, 16 hours, 53 minutes, 14 seconds, 552 milliseconds, 35 microseconds",
        "FreeSWITCH-Version": "1.5.15b+git~20141226T052811Z~0a66db6f12~64bit",
        "Uptime-msec": "147194552",
        "Session-Count": "0",
        "Max-Sessions": "1000",
        "Session-Per-Sec": "30",
        "Session-Per-Sec-Max": "2",
        "Session-Per-Sec-FiveMin": "0",
        "Session-Since-Startup": "34",
        "Session-Peak-Max": "4",
        "Session-Peak-FiveMin": "0",
        "Idle-CPU": "98.700000",
    }

    assert got == expected, "Event parsing did not happen as expected"


def test_parse_multiline_field_on_event():
    channel_create = EVENTS["CHANNEL_CREATE"]
    result = parse(channel_create)
    got = result["variable_switch_r_sdp"]

    expected = (
        "v=0\n"
        "o=- 3631463817 3631463817 IN IP4 172.16.7.70\n"
        "s=pjmedia\n"
        "b=AS:84\n"
        "t=0 0\n"
        "a=X-nat:0\n"
        "m=audio 4016 RTP/AVP 103 102 104 109 3 0 8 9 101\n"
        "c=IN IP4 172.16.7.70\n"
        "b=AS:64000\n"
        "a=rtpmap:103 speex/16000\n"
        "a=rtpmap:102 speex/8000\n"
        "a=rtpmap:104 speex/32000\n"
        "a=rtpmap:109 iLBC/8000\n"
        "a=fmtp:109 mode=30\n"
        "a=rtpmap:3 GSM/8000\n"
        "a=rtpmap:0 PCMU/8000\n"
        "a=rtpmap:8 PCMA/8000\n"
        "a=rtpmap:9 G722/8000\n"
        "a=rtpmap:101 telephone-event/8000\n"
        "a=fmtp:101 0-15\n"
        "a=rtcp:4017 IN IP4 172.16.7.70"
    )

    assert got == expected, "Parsing a field with many lines was not as it should."


def test_double_field_in_event():
    background_job = EVENTS["BACKGROUND_JOB"]
    got = parse(background_job)
    expected = {
        "Content-Length": ["625", "41"],
        "Content-Type": "text/event-plain",
        "X-Event-Content-Text": "+OK 7f4de4bc-17d7-11dd-b7a0-db4edd065621",
        "Job-UUID": "7f4db78a-17d7-11dd-b7a0-db4edd065621",
        "Job-Command": "originate",
        "Job-Command-Arg": "sofia/default/1005 '&park'",
        "Event-Name": "BACKGROUND_JOB",
        "Core-UUID": "42bdf272-16e6-11dd-b7a0-db4edd065621",
        "FreeSWITCH-Hostname": "ser",
        "FreeSWITCH-IPv4": "192.168.1.104",
        "FreeSWITCH-IPv6": "127.0.0.1",
        "Event-Date-Local": "2008-05-02 07:37:03",
        "Event-Date-GMT": "Thu, 01 May 2008 23:37:03 GMT",
        "Event-Date-timestamp": "1209685023894968",
        "Event-Calling-File": "mod_event_socket.c",
        "Event-Calling-Function": "api_exec",
        "Event-Calling-Line-Number": "609",
    }
    assert got == expected, "Event parsing did not happen as expected"
