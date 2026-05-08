"""Tests for the diagnostic panel HTTP API.

Use FastAPI's TestClient (synchronous) against an app constructed with a
fresh runtime / state / context. Audit emit is patched so tests don't write
to the real Redis stream.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from ponder.diagnostics.runtime_factory import build_panel_runtime
from ponder.diagnostics.server import create_app


@pytest.fixture(autouse=True)
def silence_audit():
    with patch("ponder.audit.emitter.emit"), \
         patch("ponder.orchestrator.dispatcher.emit"), \
         patch("ponder.orchestrator.runtime.emit"), \
         patch("ponder.orchestrator.runtime.emit_pipeline_event", return_value="span-x"), \
         patch("ponder.audit.service.list_events", return_value={"events": [], "next_cursor": "0", "has_more": False}), \
         patch("ponder.audit.service.stream_info", return_value={"reachable": False}):
        yield


@pytest.fixture
def client():
    rt, state, context = build_panel_runtime()
    app = create_app(rt, state, context)
    return TestClient(app)


def test_index_serves_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "<html" in resp.text.lower()
    assert "Ponder Diagnostic Panel" in resp.text


def test_snapshot_returns_components_state_context(client):
    resp = client.get("/api/snapshot")
    assert resp.status_code == 200
    data = resp.json()
    assert "components" in data
    assert "state" in data
    assert "context" in data
    component_names = {c["name"] for c in data["components"]}
    assert {"input_bridge", "cogitator", "speaker", "interrupt_handler"} <= component_names


def test_snapshot_components_carry_metadata(client):
    resp = client.get("/api/snapshot")
    components = resp.json()["components"]
    cogitator = next(c for c in components if c["name"] == "cogitator")
    assert cogitator["needs_model"] is True
    assert cogitator["priority"] == 20
    assert cogitator["watches"] == ["component:input_receiver:raw"]


def test_snapshot_context_includes_registered_urns(client):
    resp = client.get("/api/snapshot")
    context = resp.json()["context"]
    assert "context:current_input" in context
    assert "context:active_message" in context
    assert "context:cogitator_state" in context
    assert context["context:cogitator_state"] == "idle"  # default_if_unset baseline


def test_input_endpoint_writes_to_panel_request(client):
    resp = client.post("/api/input", json={"text": "hello world"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["wrote"] == "component:panel:request"

    # Confirm the snapshot reflects it.
    snap = client.get("/api/snapshot").json()
    assert snap["state"]["component:panel:request"] == "hello world"


def test_interrupt_endpoint_writes_to_user_interrupt(client):
    resp = client.post("/api/interrupt", json={"reason": "stop"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["wrote"] == "component:user:interrupt"
    assert body["value"] == "stop"


def test_health_endpoint_reports_specialist_count(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["specialists"] == 4
    assert data["registered_context_urns"] == 4


def test_events_endpoint_returns_pagination_shape(client):
    resp = client.get("/api/events?after=0&limit=50")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"events", "next_cursor", "has_more"}


def test_input_payload_validation(client):
    """Missing 'text' field should produce a 422."""
    resp = client.post("/api/input", json={"wrong_field": "x"})
    assert resp.status_code == 422


# ── SSE endpoints ────────────────────────────────────────────────────────────
#
# Full SSE iteration tests against TestClient hang reliably (the streaming
# response generators are infinite, and synchronous iteration interacts badly
# with anyio's scheduling). We verify route registration + headers via HEAD,
# and rely on the live integration check for end-to-end SSE behavior.


def test_state_stream_route_registered(client):
    """State-stream route exists and is reachable via HEAD."""
    resp = client.head("/api/state/stream")
    # Some FastAPI/Starlette versions return 405 for HEAD on a GET route, others 200.
    # Either way, the route is registered.
    assert resp.status_code in (200, 405)


def test_events_stream_route_registered(client):
    resp = client.head("/api/events/stream")
    assert resp.status_code in (200, 405)


def test_state_stream_route_in_openapi(client):
    """Both SSE endpoints should appear in the OpenAPI schema."""
    schema = client.get("/openapi.json").json()
    assert "/api/state/stream" in schema["paths"]
    assert "/api/events/stream" in schema["paths"]
