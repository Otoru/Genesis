from genesis.parser import parse_headers
from textwrap import dedent

# Sample large payload to simulate real workload
LARGE_PAYLOAD = dedent(
    """\
    Event-Name: CUSTOM
    Core-UUID: 6c6def18-9562-de11-a8e0-001fc6ab49e2
    FreeSWITCH-Hostname: localhost.localdomain
    FreeSWITCH-Switchname: freeswitch
    FreeSWITCH-IPv4: 10.0.1.250
    FreeSWITCH-IPv6: ::1
    Event-Date-Local: 2009-06-26 17:06:33
    Event-Date-GMT: Fri, 26 Jun 2009 21:06:33 GMT
    Event-Date-Timestamp: 1246050393884782
    Event-Calling-File: switch_xml.c
    Event-Calling-Function: switch_xml_open_root
    Event-Calling-Line-Number: 1917
    Content-Length: 41
    variable_switch_r_sdp: v=0%0D%0Ao=- 3631463817 3631463817 IN IP4 172.16.7.70%0D%0As=pjmedia%0D%0Ab=AS:84%0D%0At=0 0%0D%0Aa=X-nat:0%0D%0Am=audio 4016 RTP/AVP 103 102 104 109 3 0 8 9 101%0D%0Ac=IN IP4 172.16.7.70%0D%0Ab=AS:64000%0D%0Aa=rtpmap:103 speex/16000%0D%0Aa=rtpmap:102 speex/8000%0D%0Aa=rtpmap:104 speex/32000%0D%0Aa=rtpmap:109 iLBC/8000%0D%0Aa=fmtp:109 mode=30%0D%0Aa=rtpmap:3 GSM/8000%0D%0Aa=rtpmap:0 PCMU/8000%0D%0Aa=rtpmap:8 PCMA/8000%0D%0Aa=rtpmap:9 G722/8000%0D%0Aa=rtpmap:101 telephone-event/8000%0D%0Aa=fmtp:101 0-15%0D%0Aa=rtcp:4017 IN IP4 172.16.7.70
    some_url_encoded_field: http%3A%2F%2Fexample.com%2Fpath%3Fquery%3Dvalue
    complex_nested_field: key%3Dvalue%26other%3Dsomething%2520else
    """
)


def test_parse_headers_performance(benchmark):
    benchmark(parse_headers, LARGE_PAYLOAD)
