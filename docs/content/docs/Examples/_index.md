---
title: Examples
weight: 70
---

> [!IMPORTANT]
> These examples are for demonstration purposes only and are not production-ready.

Practical examples demonstrating how to use Genesis in real-world scenarios.

## Examples environment

This project includes a ready-to-use FreeSWITCH Docker environment for testing and development. If you want to test the examples or develop your own applications, you can start the FreeSWITCH container with the following steps:

### Starting FreeSWITCH with Docker

1. Clone the repository:
```bash
git clone https://github.com/Otoru/Genesis.git
cd Genesis
```

2. Navigate to the Docker directory:
```bash
cd docker/freeswitch
```

3. Start the FreeSWITCH container:
```bash
docker-compose up -d
```

4. Verify it's running:
```bash
docker ps | grep genesis-freeswitch
```

The FreeSWITCH instance will be available at:
- **ESL Host:** `127.0.0.1`
- **ESL Port:** `8021`
- **ESL Password:** `ClueCon`
- **Outbound Socket Port:** `9696`

To stop the FreeSWITCH container:
```bash
docker-compose down
```

For more details about the Docker setup, see the [docker/freeswitch/README.md](https://github.com/Otoru/Genesis/blob/main/docker/freeswitch/README.md) file.

## Testing with a SIP Client

You can test the examples using a SIP client (e.g. Linphone, Zoiper, or X-Lite):

1. Configure your SIP client to connect to FreeSWITCH:
   - **Server:** `127.0.0.1:5060`
   - **Username:** `1000` or `1001`
   - **Password:** `1000` or `1001` (same as username)
   - **Domain:** `127.0.0.1`

2. Register the SIP client.

## Dialplan Configuration

The Docker environment includes a dialplan entry that routes calls to `9999` to the outbound socket:

```xml
<extension name="outbound_socket_test">
  <condition field="destination_number" expression="^(9999)$">
    <action application="socket" data="127.0.0.1:9696 async full"/>
  </condition>
</extension>
```

Calls to `9999` trigger FreeSWITCH to connect to your application at `127.0.0.1:9696`.

## Available Examples

{{< cards cols="1" >}}
  {{< card link="fastapi-click2call/" title="Click2Call API" icon="code" subtitle="REST API endpoint for click2call functionality using FastAPI." >}}
  {{< card link="ivr/" title="IVR" icon="phone" subtitle="Simple IVR system using Outbound mode with DTMF interaction." >}}
  {{< card link="group-call/" title="Group Call" icon="users" subtitle="Simultaneous originate that calls multiple destinations and bridges with the first to answer." >}}
  {{< card link="queue/" title="Queue" icon="view-list" subtitle="Outbound with a queue: one call at a time; others wait in line (FIFO)." >}}
{{< /cards >}}
