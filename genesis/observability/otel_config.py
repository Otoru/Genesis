"""
OpenTelemetry configuration via environment variables.
------------------------------------------------------

Supports the standard OTEL environment variables for configuring
tracing and metrics in Genesis.
"""

import os
from typing import Dict, Optional

from opentelemetry.sdk.resources import Resource


def _parse_boolean(value: str) -> bool:
    """Parse OTEL boolean env: only 'true' (case-insensitive) is True."""
    return value.strip().lower() == "true"


def _parse_resource_attributes(value: str) -> Dict[str, str]:
    """
    Parse OTEL_RESOURCE_ATTRIBUTES string into a dict.

    Format: key1=value1,key2=value2
    Values may contain equals signs; only the first '=' splits key and value.
    """
    attrs: Dict[str, str] = {}
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        idx = item.find("=")
        if idx < 0:
            continue
        key = item[:idx].strip()
        val = item[idx + 1 :].strip()
        if key:
            attrs[key] = val
    return attrs


def is_otel_sdk_disabled() -> bool:
    """
    Return whether the OpenTelemetry SDK is disabled via environment.

    Reads OTEL_SDK_DISABLED. Only the case-insensitive value "true"
    disables the SDK (per OpenTelemetry spec).
    """
    raw = os.getenv("OTEL_SDK_DISABLED", "").strip()
    if not raw:
        return False
    return _parse_boolean(raw)


def get_otel_service_name() -> str:
    """
    Return the service name for the OTEL resource.

    Reads OTEL_SERVICE_NAME. Defaults to "genesis" when unset.
    """
    return os.getenv("OTEL_SERVICE_NAME", "genesis").strip() or "genesis"


def get_otel_resource_attributes() -> Dict[str, str]:
    """
    Return resource attributes from OTEL_RESOURCE_ATTRIBUTES.

    Format: key1=value1,key2=value2. OTEL_SERVICE_NAME is applied
    separately and takes precedence over service.name here.
    """
    raw = os.getenv("OTEL_RESOURCE_ATTRIBUTES", "").strip()
    if not raw:
        return {}
    return _parse_resource_attributes(raw)


def get_otel_exporter_otlp_endpoint() -> Optional[str]:
    """
    Return the OTLP exporter endpoint for HTTP (all signals).

    Reads OTEL_EXPORTER_OTLP_ENDPOINT. When set, metrics (and traces if
    configured) can be sent to this endpoint via OTLP/HTTP.
    Default per spec for HTTP is http://localhost:4318.
    """
    raw = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()
    return raw if raw else None


def get_otel_exporter_otlp_metrics_endpoint() -> Optional[str]:
    """
    Return the OTLP metrics exporter endpoint (overrides OTEL_EXPORTER_OTLP_ENDPOINT for metrics).
    """
    raw = os.getenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", "").strip()
    return raw if raw else get_otel_exporter_otlp_endpoint()


def get_otel_exporter_otlp_traces_endpoint() -> Optional[str]:
    """
    Return the OTLP traces exporter endpoint (overrides OTEL_EXPORTER_OTLP_ENDPOINT for traces).
    """
    raw = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "").strip()
    return raw if raw else get_otel_exporter_otlp_endpoint()


def create_resource() -> Resource:
    """
    Create an OpenTelemetry Resource from OTEL environment variables.

    Uses:
    - OTEL_SERVICE_NAME for service.name (default: "genesis")
    - OTEL_RESOURCE_ATTRIBUTES for additional key=value pairs

    OTEL_SERVICE_NAME takes precedence over service.name in
    OTEL_RESOURCE_ATTRIBUTES (per OpenTelemetry spec).
    """
    attrs: Dict[str, str] = dict(get_otel_resource_attributes())
    attrs["service.name"] = get_otel_service_name()
    return Resource.create(attrs)
