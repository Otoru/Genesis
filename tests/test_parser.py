import pytest

from genesis.parser import parse

from environment import EVENTS


def test_parse_log_event():
    log = EVENTS["LOG"]
    got = parse(log)

    expected = {
        "Content-Type": "log/data",
        "Content-Length": "126",
        "Log-Level": "7",
        "Text-Channel": "3",
        "Log-File": "switch_core_state_machine.c",
        "Log-Func": "switch_core_session_destroy_state",
        "Log-Line": "710",
        "User-Data": "4c882cc4-cd02-11e6-8b82-395b501876f9",
        "X-Event-Content": "2016-12-28 10:34:08.398763 [DEBUG] switch_core_state_machine.c:710 (sofia/internal/7071@devitor) State DESTROY going to sleep",
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
        "X-Event-Content": "+OK 7f4de4bc-17d7-11dd-b7a0-db4edd065621",
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


def test_parse_triple_field_in_event():
    reloadxml_with_3_headers = EVENTS["RELOADXML_WITH_3_HEADERS"]
    got = parse(reloadxml_with_3_headers)
    expected = {
        "Event-Name": "RELOADXML",
        "Core-UUID": "6c6def18-9562-de11-a8e0-001fc6ab49e2",
        "FreeSWITCH-Hostname": "localhost.localdomain",
        "FreeSWITCH-IPv4": "10.0.1.250",
        "FreeSWITCH-IPv6": "::1",
        "Event-Date-Local": "2009-06-26 17:06:33",
        "Event-Date-GMT": "Fri, 26 Jun 2009 21:06:33 GMT",
        "Event-Date-Timestamp": "1246050393884782",
        "Event-Calling-File": "switch_xml.c",
        "Event-Calling-Function": "switch_xml_open_root",
        "Event-Calling-Line-Number": "1917",
        "Content-Length": ["41", "42", "43"],
    }
    assert got == expected, "Event parsing did not happen as expected"
