import pytest
from time import sleep
from fastapi.testclient import TestClient
from genesis.observability import Observability, AppType


@pytest.fixture
def observability():
    return Observability()


@pytest.fixture
def client(observability):
    return TestClient(observability.app)


def test_health_endpoint_outbound(observability, client):
    observability.set_app_type(AppType.OUTBOUND)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_endpoint_consumer_without_heartbeat(observability, client):
    observability.set_app_type(AppType.CONSUMER)
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json() == {"status": "unhealthy"}


def test_health_endpoint_consumer_after_heartbeat(observability, client):
    observability.set_app_type(AppType.CONSUMER)
    observability.record_heartbeat()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_metrics_endpoint(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    # Prometheus metrics usually contain some comments or data
    assert response.text


def test_consumer_readiness_initial(observability, client):
    observability.set_app_type(AppType.CONSUMER)
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not ready"}


def test_consumer_readiness_after_heartbeat(observability, client):
    observability.set_app_type(AppType.CONSUMER)
    observability.record_heartbeat()
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_outbound_readiness_initial(observability, client):
    observability.set_app_type(AppType.OUTBOUND)
    # Default is not ready
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not ready"}


def test_outbound_readiness_set_true(observability, client):
    observability.set_app_type(AppType.OUTBOUND)
    observability.set_outbound_ready(True)
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_outbound_readiness_set_false(observability, client):
    observability.set_app_type(AppType.OUTBOUND)
    observability.set_outbound_ready(True)
    observability.set_outbound_ready(False)
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not ready"}
