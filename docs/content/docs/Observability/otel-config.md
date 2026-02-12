---
title: Configuration
weight: 70
---

Genesis supports configuring OpenTelemetry via standard environment variables. When you run the CLI (`genesis consumer` or `genesis outbound`), these variables control the metrics resource and whether the SDK is enabled.

## Supported variables

- **`OTEL_SDK_DISABLED`**
  - Disables the OpenTelemetry SDK when set to `true` (case-insensitive).
  - When disabled, the CLI does not set a meter provider; metrics are no-ops.
  - Default: not set (SDK enabled).

- **`OTEL_SERVICE_NAME`**
  - Sets the `service.name` resource attribute for metrics (and traces if you configure a tracer provider).
  - Default: `genesis`.

- **`OTEL_RESOURCE_ATTRIBUTES`**
  - Extra resource attributes as comma-separated key-value pairs: `key1=value1,key2=value2`.
  - If `service.name` is present here, it is overridden by `OTEL_SERVICE_NAME` when that variable is set.
  - Example: `deployment.environment=production,service.version=1.0.0`.

- **`OTEL_EXPORTER_OTLP_ENDPOINT`**
  - Base URL for OTLP/HTTP export (traces and metrics). When set, the CLI configures an OTLP HTTP exporter so telemetry is sent to this endpoint (e.g. an OpenTelemetry Collector).
  - Default for HTTP per spec: `http://localhost:4318` (collector OTLP HTTP receiver).

- **`OTEL_EXPORTER_OTLP_METRICS_ENDPOINT`**
  - Overrides the metrics endpoint (if unset, `OTEL_EXPORTER_OTLP_ENDPOINT` is used).

- **`OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`**
  - Overrides the traces endpoint (if unset, `OTEL_EXPORTER_OTLP_ENDPOINT` is used). When set (or when `OTEL_EXPORTER_OTLP_ENDPOINT` is set), the CLI also sets a TracerProvider with OTLP HTTP span exporter.

## Examples

Disable OpenTelemetry (e.g. in tests or when using another instrumentation):

```bash
export OTEL_SDK_DISABLED=true
genesis consumer ...
```

Set a custom service name and environment:

```bash
export OTEL_SERVICE_NAME=my-call-center
export OTEL_RESOURCE_ATTRIBUTES=deployment.environment=production
genesis outbound ...
```

Send metrics and traces to an OTLP collector over HTTP:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
genesis consumer ...
```
