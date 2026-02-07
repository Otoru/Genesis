---
title: Observability
weight: 60
---

Genesis ships with **OpenTelemetry** for tracing, logging, and metrics. You get spans for connections and commands, structured logs with trace IDs, health and readiness endpoints, and Prometheus-compatible metrics — with no extra setup when using the CLI.

## Components

{{< cards cols="1" >}}
  {{< card link="tracing/" title="Tracing" icon="map" subtitle="Automatic spans for connections, commands, and events." >}}
  {{< card link="logging/" title="Logging" icon="terminal" subtitle="Structured logs with trace correlation and optional JSON output." >}}
  {{< card link="server/" title="Server" icon="server" subtitle="Health, readiness, and metrics over HTTP." >}}
  {{< card link="metrics/" title="Metrics" icon="chart-bar" subtitle="Counters and histograms for commands, events, channels, and ring groups." >}}
{{< /cards >}}
