import pytest

from genesis.observability.otel_config import (
    create_resource,
    get_otel_exporter_otlp_endpoint,
    get_otel_exporter_otlp_metrics_endpoint,
    get_otel_exporter_otlp_traces_endpoint,
    get_otel_resource_attributes,
    get_otel_service_name,
    is_otel_sdk_disabled,
)


def test_is_otel_sdk_disabled_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTEL_SDK_DISABLED", raising=False)
    assert is_otel_sdk_disabled() is False


def test_is_otel_sdk_disabled_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    assert is_otel_sdk_disabled() is True


def test_is_otel_sdk_disabled_true_case_insensitive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OTEL_SDK_DISABLED", "TRUE")
    assert is_otel_sdk_disabled() is True


def test_is_otel_sdk_disabled_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_SDK_DISABLED", "false")
    assert is_otel_sdk_disabled() is False


def test_get_otel_service_name_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)
    assert get_otel_service_name() == "genesis"


def test_get_otel_service_name_custom(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_SERVICE_NAME", "my-service")
    assert get_otel_service_name() == "my-service"


def test_get_otel_resource_attributes_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTEL_RESOURCE_ATTRIBUTES", raising=False)
    assert get_otel_resource_attributes() == {}


def test_get_otel_resource_attributes_single(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "deployment.environment=prod")
    assert get_otel_resource_attributes() == {"deployment.environment": "prod"}


def test_get_otel_resource_attributes_multiple(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "OTEL_RESOURCE_ATTRIBUTES",
        "deployment.environment=prod,service.version=1.0.0",
    )
    assert get_otel_resource_attributes() == {
        "deployment.environment": "prod",
        "service.version": "1.0.0",
    }


def test_get_otel_resource_attributes_value_with_equals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "key=value=with=equals")
    assert get_otel_resource_attributes() == {"key": "value=with=equals"}


def test_create_resource_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)
    monkeypatch.delenv("OTEL_RESOURCE_ATTRIBUTES", raising=False)
    resource = create_resource()
    assert resource.attributes["service.name"] == "genesis"


def test_create_resource_custom_service_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_SERVICE_NAME", "custom-app")
    monkeypatch.delenv("OTEL_RESOURCE_ATTRIBUTES", raising=False)
    resource = create_resource()
    assert resource.attributes["service.name"] == "custom-app"


def test_create_resource_service_name_overrides_attributes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OTEL_SERVICE_NAME", "from-env")
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "service.name=from-attributes")
    resource = create_resource()
    assert resource.attributes["service.name"] == "from-env"


def test_create_resource_with_attributes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTEL_SERVICE_NAME", raising=False)
    monkeypatch.setenv(
        "OTEL_RESOURCE_ATTRIBUTES",
        "deployment.environment=staging,service.version=2.0",
    )
    resource = create_resource()
    assert resource.attributes["service.name"] == "genesis"
    assert resource.attributes["deployment.environment"] == "staging"
    assert resource.attributes["service.version"] == "2.0"


def test_get_otel_exporter_otlp_endpoint_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
    assert get_otel_exporter_otlp_endpoint() is None


def test_get_otel_exporter_otlp_endpoint_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318")
    assert get_otel_exporter_otlp_endpoint() == "http://localhost:4318"


def test_get_otel_exporter_otlp_metrics_endpoint_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4318")
    assert get_otel_exporter_otlp_metrics_endpoint() == "http://collector:4318"


def test_get_otel_exporter_otlp_metrics_endpoint_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://default:4318")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT", "http://metrics:4318")
    assert get_otel_exporter_otlp_metrics_endpoint() == "http://metrics:4318"


def test_get_otel_exporter_otlp_traces_endpoint_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", raising=False)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4318")
    assert get_otel_exporter_otlp_traces_endpoint() == "http://collector:4318"


def test_get_otel_exporter_otlp_traces_endpoint_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://default:4318")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://traces:4318")
    assert get_otel_exporter_otlp_traces_endpoint() == "http://traces:4318"
