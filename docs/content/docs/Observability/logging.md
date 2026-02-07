---
title: Logging
weight: 20
---

Genesis provides structured logging with automatic trace correlation via `genesis.observability.logger`.

## Log Correlation

When logs are generated within an active trace span, Genesis automatically injects `trace_id` and `span_id` into log records.

**Default Output:**
```text
[10:34:43] INFO     This is a log message (trace_id=... span_id=...)
```

## JSON Logging

Enable JSON logging for production environments using the `--json` flag:

```bash
genesis --json consumer ./app.py
```

**JSON Output:**
```json
{
  "timestamp": "2026-01-16T13:35:11.813625+00:00",
  "level": "INFO",
  "message": "This is a log message",
  "logger": "genesis.observability.logger",
  "trace_id": "eee4dfc73530a13a846ec8f1e61561f4",
  "span_id": "639ec6ffc3f956f2"
}
```
