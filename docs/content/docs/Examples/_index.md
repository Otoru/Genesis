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

## Available Examples

{{< cards cols="1" >}}
  {{< card link="fastapi-click2call/" title="Click2Call API" icon="code" subtitle="REST API endpoint for click2call functionality using FastAPI." >}}
  {{< card link="ivr/" title="IVR" icon="phone" subtitle="Simple IVR system using Outbound mode with DTMF interaction." >}}
{{< /cards >}}
