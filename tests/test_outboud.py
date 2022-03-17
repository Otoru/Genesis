from asyncio import ensure_future, sleep, Queue
from typing import Awaitable

from genesis import Outbound, Session


async def test_outbound_session_has_context(host, port, dialplan):
    buffer = Queue(maxsize=1)

    async def handler(session: Session) -> Awaitable[None]:
        print(session.context)
        await buffer.put(session.context)

    address = (host(), port())
    application = Outbound(*address, handler)
    future = ensure_future(application.start())

    while not application.server or not application.server.is_serving:
        await sleep(0.0001)

    await dialplan.start(*address)

    got = await buffer.get()
    expected = {
        "Answer-State": "early",
        "Call-Direction": "inbound",
        "Caller-Caller-ID-Name": "1001",
        "Caller-Caller-ID-Number": "1001",
        "Caller-Channel-Answered-Time": "0",
        "Caller-Channel-Created-Time": "1209749769132614",
        "Caller-Channel-Hangup-Time": "0",
        "Caller-Channel-Name": "sofia/default/1001@10.0.1.100",
        "Caller-Channel-Transfer-Time": "0",
        "Caller-Context": "default",
        "Caller-Destination-Number": "886",
        "Caller-Dialplan": "XML",
        "Caller-Network-Addr": "10.0.1.241",
        "Caller-Privacy-Hide-Name": "no",
        "Caller-Privacy-Hide-Number": "no",
        "Caller-Profile-Index": "1",
        "Caller-Screen-Bit": "yes",
        "Caller-Source": "mod_sofia",
        "Caller-Unique-ID": "40117b0a-186e-11dd-bbcd-7b74b6b4d31e",
        "Caller-Username": "1001",
        "Channel-Caller-ID-Name": "1001",
        "Channel-Caller-ID-Number": "1001",
        "Channel-Channel-Answered-Time": "0",
        "Channel-Channel-Created-Time": "1209749769132614",
        "Channel-Channel-Hangup-Time": "0",
        "Channel-Channel-Name": "sofia/default/1001@10.0.1.100",
        "Channel-Channel-Transfer-Time": "0",
        "Channel-Context": "default",
        "Channel-Destination-Number": "886",
        "Channel-Dialplan": "XML",
        "Channel-Name": "sofia/default/1001@10.0.1.100",
        "Channel-Network-Addr": "10.0.1.241",
        "Channel-Privacy-Hide-Name": "no",
        "Channel-Privacy-Hide-Number": "no",
        "Channel-Profile-Index": "1",
        "Channel-Read-Codec-Name": "G722",
        "Channel-Read-Codec-Rate": "16000",
        "Channel-Screen-Bit": "yes",
        "Channel-Source": "mod_sofia",
        "Channel-State": "CS_EXECUTE",
        "Channel-State-Number": "4",
        "Channel-Unique-ID": "40117b0a-186e-11dd-bbcd-7b74b6b4d31e",
        "Channel-Username": "1001",
        "Channel-Write-Codec-Name": "G722",
        "Channel-Write-Codec-Rate": "16000",
        "Content-Type": "command/reply",
        "Control": "full",
        "Socket-Mode": "async",
        "Unique-ID": "40117b0a-186e-11dd-bbcd-7b74b6b4d31e",
        "variable_accountcode": "1001",
        "variable_channel_name": "sofia/default/1001@10.0.1.100",
        "variable_domain_name": "10.0.1.100",
        "variable_effective_caller_id_name": "Extension 1001",
        "variable_effective_caller_id_number": "1001",
        "variable_endpoint_disposition": "EARLY MEDIA",
        "variable_local_media_ip": "10.0.1.100",
        "variable_local_media_port": "62258",
        "variable_mailbox": "1001",
        "variable_max_forwards": "70",
        "variable_open": "true",
        "variable_presence_id": "1001@10.0.1.100",
        "variable_read_codec": "G722",
        "variable_read_rate": "16000",
        "variable_remote_media_ip": "10.0.1.241",
        "variable_remote_media_port": "62258",
        "variable_sip_auth_realm": "10.0.1.100",
        "variable_sip_auth_username": "1001",
        "variable_sip_authorized": "true",
        "variable_sip_call_id": "3c2bb21af10b-ogphkonpwqet",
        "variable_sip_contact_host": "10.0.1.241",
        "variable_sip_contact_params": "line=nc7obl5w",
        "variable_sip_contact_port": "2048",
        "variable_sip_contact_uri": "1001@10.0.1.241:2048",
        "variable_sip_contact_user": "1001",
        "variable_sip_from_host": "10.0.1.100",
        "variable_sip_from_tag": "wrgb4s5idf",
        "variable_sip_from_uri": "1001@10.0.1.100",
        "variable_sip_from_user": "1001",
        "variable_sip_from_user_stripped": "1001",
        "variable_sip_h_P-Key-Flags": 'keys="3"',
        "variable_sip_mailbox": "1001",
        "variable_sip_req_host": "10.0.1.100",
        "variable_sip_req_params": "user=phone",
        "variable_sip_req_uri": "886@10.0.1.100",
        "variable_sip_req_user": "886",
        "variable_sip_to_host": "10.0.1.100",
        "variable_sip_to_params": "user=phone",
        "variable_sip_to_uri": "886@10.0.1.100",
        "variable_sip_to_user": "886",
        "variable_sip_user_agent": "snom300/7.1.30",
        "variable_sip_via_host": "10.0.1.241",
        "variable_sip_via_port": "2048",
        "variable_sip_via_rport": "2048",
        "variable_socket_host": "127.0.0.1",
        "variable_sofia_profile_domain_name": ["10.0.1.100", "10.0.1.100"],
        "variable_sofia_profile_name": "default",
        "variable_user_context": "default",
        "variable_user_name": "1001",
        "variable_write_codec": "G722",
        "variable_write_rate": "16000",
    }

    assert got == expected, "The call context is incorrect"

    await dialplan.stop()

    await application.stop()
    future.cancel()
