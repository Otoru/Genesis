---
title: HTTP Server
weight: 30
---

A built-in HTTP server exposes health, readiness, and metrics. Port **8000** by default; set `GENESIS_OBSERVABILITY_PORT` to change it. With the CLI, the server starts automatically; with the library, you start it yourself (see below).

## Endpoints

{{% details title="GET /health" closed="true" %}}
**Purpose**
<br />Check that the application is healthy. Use this when you need a signal that the process is up and (for Consumer) still connected to FreeSWITCH.

**Behavior:**
- **Consumer:** Returns healthy only if a `HEARTBEAT` from FreeSWITCH was received in the last 30 seconds. If the connection is lost or no heartbeat arrived recently, the endpoint responds with `503` so the app can be restarted or removed from rotation.
- **Outbound:** Returns healthy as long as the HTTP server is responding (no external dependency).

**Response:**
- **Healthy:** Status `200 OK`, body `{"status": "ok"}`.
- **Unhealthy:** Status `503 Service Unavailable`, body `{"status": "unhealthy"}`.
{{% /details %}}

{{% details title="GET /ready" closed="true" %}}
**Purpose**<br />Check whether the application is in a state where it can accept work. Use this to avoid sending traffic (e.g. from a load balancer) before the app is actually ready.

**When the app is considered ready:**
- **Consumer:** After the first `HEARTBEAT` event is received from FreeSWITCH. Until then, the ESL connection may not be established and the app is not really consuming events.
- **Outbound:** As soon as the TCP server is listening and accepting connections. There is no external dependency to wait for.

**Response:**
- **Ready:** Status `200 OK`, body `{"status": "ready"}`.
- **Not ready:** Status `503 Service Unavailable`, body `{"status": "not ready"}`.
{{% /details %}}

{{% details title="GET /metrics" closed="true" %}}
**Purpose**<br />Expose all Genesis metrics (and any other OpenTelemetry metrics from your app). The same metrics described in [Metrics]({{< relref "metrics.md" >}}) — commands, events, connections, channel operations, ring groups, etc. — are available here.

**Response:** `200 OK` with body following the Prometheus exposition format.
{{% /details %}}

## CLI

Server starts with `genesis consumer` or `genesis outbound`. Optional port:

```bash
export GENESIS_OBSERVABILITY_PORT=9090
genesis consumer ./app.py
```

## Library

Start the HTTP server and set the OpenTelemetry meter provider with a Prometheus reader:

```python
import asyncio
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from prometheus_client import start_http_server
from genesis import Inbound

start_http_server(8000)

metric_reader = PrometheusMetricReader()
provider = MeterProvider(
    resource=Resource.create({"service.name": "genesis-app"}),
    metric_readers=[metric_reader],
)
metrics.set_meter_provider(provider)

async def main():
    async with Inbound("127.0.0.1", 8021, "ClueCon") as client:
        await client.send("uptime")
        await asyncio.sleep(60)

asyncio.run(main())
```

See [Logging]({{< relref "logging.md" >}}) for structured logging and trace correlation.
