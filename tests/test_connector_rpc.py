import pytest
import httpx

from app.connectors.registry import connector_registry
from tests.conftest import SampleAssistedConnector, SampleAutomatedConnector


@pytest.mark.asyncio
async def test_get_connectors_list_empty(async_client: httpx.AsyncClient):
    """GET /api/v1/connectors returns empty list when no connectors are registered."""
    response = await async_client.get("/api/v1/connectors")
    assert response.status_code == 200
    data = response.json()
    assert data == {"connectors": []}


@pytest.mark.asyncio
async def test_get_connectors_and_manifest(async_client: httpx.AsyncClient):
    """Register connector and verify /api/v1/connectors and /manifest endpoints."""
    connector = SampleAutomatedConnector(key="platform_rpc_test")
    connector_registry.register(connector)

    # List connectors
    list_resp = await async_client.get("/api/v1/connectors")
    assert list_resp.status_code == 200
    connectors = list_resp.json()["connectors"]
    assert len(connectors) == 1
    assert connectors[0]["connector_key"] == "platform_rpc_test"

    # Get manifest
    man_resp = await async_client.get("/api/v1/connectors/platform_rpc_test/manifest")
    assert man_resp.status_code == 200
    manifest = man_resp.json()
    assert manifest["connector_key"] == "platform_rpc_test"
    assert "supported_methods" in manifest


@pytest.mark.asyncio
async def test_get_manifest_unknown_connector_returns_404(async_client: httpx.AsyncClient):
    """Manifest query for unknown connector returns 404 and CONNECTOR_NOT_FOUND error code."""
    response = await async_client.get("/api/v1/connectors/non_existent_platform/manifest")
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "CONNECTOR_NOT_FOUND"
    assert data["error"]["retryable"] is False


@pytest.mark.asyncio
async def test_rpc_validate(async_client: httpx.AsyncClient):
    """POST /connector/v1/{key}/validate invokes connector validate method."""
    connector = SampleAutomatedConnector(key="rpc_auto")
    connector_registry.register(connector)

    payload = {
        "rendition": {"url": "https://media.incubrix.com/test.mp4", "media_type": "video"},
        "destination": {"platform": "rpc_auto"},
        "connection": {"auth_type": "oauth2", "credentials": {"token": "xyz"}},
    }
    resp = await async_client.post("/connector/v1/rpc_auto/validate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["violations"] == []


@pytest.mark.asyncio
async def test_rpc_publish(async_client: httpx.AsyncClient):
    """POST /connector/v1/{key}/publish invokes connector publish method."""
    connector = SampleAutomatedConnector(key="rpc_auto")
    connector_registry.register(connector)

    payload = {
        "rendition": {"url": "https://media.incubrix.com/test.mp4", "media_type": "video"},
        "destination": {"platform": "rpc_auto"},
        "connection": {"auth_type": "oauth2", "credentials": {"token": "xyz"}},
        "idempotency_key": "unique-idempotency-key-001",
    }
    resp = await async_client.post("/connector/v1/rpc_auto/publish", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["platform_post_id"] == "sample_unique-i"
    assert data["status"] == "published"
    assert "https://sample.platform/post/" in data["live_url"]


@pytest.mark.asyncio
async def test_rpc_get_status(async_client: httpx.AsyncClient):
    """POST /connector/v1/{key}/get_status invokes connector get_status method."""
    connector = SampleAutomatedConnector(key="rpc_auto")
    connector_registry.register(connector)

    payload = {
        "platform_post_id": "post_789",
        "connection": {"auth_type": "oauth2", "credentials": {"token": "xyz"}},
    }
    resp = await async_client.post("/connector/v1/rpc_auto/get_status", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "published"
    assert data["live_url"] == "https://sample.platform/post/post_789"


@pytest.mark.asyncio
async def test_rpc_delete(async_client: httpx.AsyncClient):
    """POST /connector/v1/{key}/delete invokes connector delete method."""
    connector = SampleAutomatedConnector(key="rpc_auto")
    connector_registry.register(connector)

    payload = {
        "platform_post_id": "post_789",
        "connection": {"auth_type": "oauth2", "credentials": {"token": "xyz"}},
    }
    resp = await async_client.post("/connector/v1/rpc_auto/delete", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["deleted"] is True


@pytest.mark.asyncio
async def test_rpc_fetch_metrics(async_client: httpx.AsyncClient):
    """POST /connector/v1/{key}/fetch_metrics invokes connector fetch_metrics method."""
    connector = SampleAutomatedConnector(key="rpc_auto")
    connector_registry.register(connector)

    payload = {
        "platform_post_id": "post_789",
        "connection": {"auth_type": "oauth2", "credentials": {"token": "xyz"}},
        "since": "2026-10-01T00:00:00Z",
    }
    resp = await async_client.post("/connector/v1/rpc_auto/fetch_metrics", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "metrics" in data
    assert data["metrics"]["views"] == 42
    assert "fetched_at" in data


@pytest.mark.asyncio
async def test_rpc_refresh_auth(async_client: httpx.AsyncClient):
    """POST /connector/v1/{key}/refresh_auth invokes connector refresh_auth method."""
    connector = SampleAutomatedConnector(key="rpc_auto")
    connector_registry.register(connector)

    payload = {
        "connection": {"auth_type": "oauth2", "credentials": {"token": "expired_token"}},
    }
    resp = await async_client.post("/connector/v1/rpc_auto/refresh_auth", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["refreshed"] is True
    assert data["credentials"]["access_token"] == "new_mock_token"


@pytest.mark.asyncio
async def test_rpc_build_assist_pack(async_client: httpx.AsyncClient):
    """POST /connector/v1/{key}/build_assist_pack invokes assisted connector method."""
    connector = SampleAssistedConnector()
    connector_registry.register(connector)

    payload = {
        "rendition": {"url": "https://media.incubrix.com/test.mp4", "media_type": "video"},
        "destination": {"platform": "sample_assisted"},
    }
    resp = await async_client.post("/connector/v1/sample_assisted/build_assist_pack", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "instructions" in data
    assert len(data["assets"]) > 0


@pytest.mark.asyncio
async def test_rpc_unknown_connector_returns_404(async_client: httpx.AsyncClient):
    """Invoking a method on an unregistered connector returns 404 with standard envelope."""
    resp = await async_client.post(
        "/connector/v1/ghost_connector/publish",
        json={"idempotency_key": "123"},
    )
    assert resp.status_code == 404
    data = resp.json()
    assert data["error"]["code"] == "CONNECTOR_NOT_FOUND"


@pytest.mark.asyncio
async def test_rpc_unsupported_method_returns_405(async_client: httpx.AsyncClient):
    """Invoking a method not supported by the connector returns 405 METHOD_NOT_SUPPORTED."""
    connector = SampleAssistedConnector()
    connector_registry.register(connector)

    resp = await async_client.post(
        "/connector/v1/sample_assisted/publish",
        json={
            "rendition": {},
            "destination": {},
            "connection": {},
            "idempotency_key": "test",
        },
    )
    assert resp.status_code == 405
    data = resp.json()
    assert data["error"]["code"] == "METHOD_NOT_SUPPORTED"


@pytest.mark.asyncio
async def test_rpc_invalid_payload_returns_422(async_client: httpx.AsyncClient):
    """Omitting required payload fields returns 422 with standard VALIDATION_ERROR envelope."""
    connector = SampleAutomatedConnector(key="rpc_auto")
    connector_registry.register(connector)

    # Missing idempotency_key
    payload = {
        "rendition": {},
        "destination": {},
        "connection": {},
    }
    resp = await async_client.post("/connector/v1/rpc_auto/publish", json=payload)
    assert resp.status_code == 422
    data = resp.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert "details" in data["error"]
