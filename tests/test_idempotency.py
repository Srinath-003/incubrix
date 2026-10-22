import asyncio
from unittest.mock import AsyncMock, patch
import httpx
import pytest

from app.connectors.discourse.connector import DiscourseConnector
from app.connectors.registry import connector_registry
from app.core.errors import AmbiguousTimeoutError, IdempotencyConflictError
from app.idempotency.repository import compute_request_hash, idempotency_repository


@pytest.fixture(autouse=True)
def setup_discourse():
    connector_registry.clear()
    idempotency_repository.clear()
    connector_registry.register(DiscourseConnector())
    yield
    connector_registry.clear()
    idempotency_repository.clear()


@pytest.mark.asyncio
async def test_idempotent_repeated_publish_requests(async_client: httpx.AsyncClient):
    """Repeating a request with the same idempotency key and payload returns the cached result."""
    payload = {
        "rendition": {
            "title": "Idempotent Publishing Guide",
            "caption": "Exploring robust idempotency patterns in distributed systems.",
            "media_type": "text",
        },
        "destination": {
            "platform": "discourse",
            "settings": {"instance_url": "https://discourse.example.com", "category": 1},
        },
        "connection": {
            "auth_type": "api_key",
            "credentials": {"api_key": "secret", "api_username": "moderator"},
        },
        "idempotency_key": "idem-key-stable-001",
    }

    # First request
    resp1 = await async_client.post("/connector/v1/discourse/publish", json=payload)
    assert resp1.status_code == 200
    data1 = resp1.json()
    post_id_1 = data1["platform_post_id"]

    # Second identical request with same idempotency key
    resp2 = await async_client.post("/connector/v1/discourse/publish", json=payload)
    assert resp2.status_code == 200
    data2 = resp2.json()
    post_id_2 = data2["platform_post_id"]

    # Identical post ID returned (reused result)
    assert post_id_1 == post_id_2
    assert data1 == data2


@pytest.mark.asyncio
async def test_conflicting_idempotency_key_with_different_payload(async_client: httpx.AsyncClient):
    """Reusing the same key with a different payload produces HTTP 409 IDEMPOTENCY_CONFLICT."""
    base_destination = {
        "platform": "discourse",
        "settings": {"instance_url": "https://discourse.example.com", "category": 1},
    }
    connection = {"auth_type": "api_key", "credentials": {"api_key": "k"}}

    payload_a = {
        "rendition": {"title": "First Version of Post", "caption": "First body content."},
        "destination": base_destination,
        "connection": connection,
        "idempotency_key": "shared-conflict-key",
    }
    payload_b = {
        "rendition": {"title": "Different Second Version", "caption": "Completely altered body content."},
        "destination": base_destination,
        "connection": connection,
        "idempotency_key": "shared-conflict-key",  # Same key, different body
    }

    # First call succeeds
    resp1 = await async_client.post("/connector/v1/discourse/publish", json=payload_a)
    assert resp1.status_code == 200

    # Second call with conflicting payload must fail with 409 IDEMPOTENCY_CONFLICT
    resp2 = await async_client.post("/connector/v1/discourse/publish", json=payload_b)
    assert resp2.status_code == 409
    data2 = resp2.json()
    assert data2["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert "different request payload" in data2["error"]["message"]


@pytest.mark.asyncio
async def test_header_and_body_idempotency_key_reconciliation(async_client: httpx.AsyncClient):
    """Reconciliation of Idempotency-Key header with request body."""
    payload = {
        "rendition": {"title": "Header Reconciliation", "caption": "Testing header reconciliation."},
        "destination": {"platform": "discourse", "settings": {"instance_url": "https://forum.local", "category": 1}},
        "connection": {"auth_type": "api_key", "credentials": {}},
    }

    # 1. Header only -> succeeds, injected into request
    headers_1 = {"Idempotency-Key": "header-only-key-999"}
    resp1 = await async_client.post("/connector/v1/discourse/publish", json=payload, headers=headers_1)
    assert resp1.status_code == 200

    # 2. Matching header and body -> succeeds
    payload_matching = dict(payload)
    payload_matching["idempotency_key"] = "matching-key-888"
    headers_2 = {"Idempotency-Key": "matching-key-888"}
    resp2 = await async_client.post("/connector/v1/discourse/publish", json=payload_matching, headers=headers_2)
    assert resp2.status_code == 200

    # 3. Conflicting header and body -> 409 IDEMPOTENCY_CONFLICT
    headers_conflict = {"Idempotency-Key": "conflicting-header-key"}
    resp3 = await async_client.post("/connector/v1/discourse/publish", json=payload_matching, headers=headers_conflict)
    assert resp3.status_code == 409
    data3 = resp3.json()
    assert data3["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert "conflicting" in data3["error"]["message"].lower()


@pytest.mark.asyncio
async def test_concurrent_duplicate_publishing_requests():
    """Simultaneous concurrent requests with identical key reject racing execution with conflict."""
    rendition = {"title": "Concurrent Post", "caption": "Testing concurrent safety."}
    destination = {"platform": "discourse", "settings": {}}

    hash_val = compute_request_hash(rendition, destination)

    # First acquires
    status1, _ = await idempotency_repository.acquire_or_get("discourse", "concurrent-key", hash_val)
    assert status1 == "acquired"

    # Second concurrent call while first is in_progress must raise IdempotencyConflictError
    with pytest.raises(IdempotencyConflictError) as exc_info:
        await idempotency_repository.acquire_or_get("discourse", "concurrent-key", hash_val)
    assert "currently in progress" in exc_info.value.message


@pytest.mark.asyncio
async def test_ambiguous_timeout_marks_uncertain_and_prevents_blind_retry():
    """Ambiguous timeout marks idempotency record as uncertain, preventing duplicate publishes."""
    rendition = {"title": "Timeout Test", "caption": "Testing timeout handling."}
    destination = {"platform": "discourse", "settings": {}}
    hash_val = compute_request_hash(rendition, destination)

    await idempotency_repository.acquire_or_get("discourse", "timeout-key", hash_val)
    await idempotency_repository.mark_uncertain(
        "discourse",
        "timeout-key",
        {"code": "AMBIGUOUS_TIMEOUT", "message": "Timed out waiting for Discourse"},
    )

    # Subsequent attempt must raise AmbiguousTimeoutError requiring reconciliation
    with pytest.raises(AmbiguousTimeoutError) as exc_info:
        await idempotency_repository.acquire_or_get("discourse", "timeout-key", hash_val)
    assert "reconciliation required" in exc_info.value.message.lower()


def test_no_credentials_stored_in_idempotency_hash():
    """Verify compute_request_hash strictly excludes secrets, credentials, and tokens."""
    rendition = {
        "title": "Title",
        "caption": "Body",
        "secret": "leaked_secret_in_rendition",
    }
    destination = {
        "platform": "discourse",
        "settings": {"instance_url": "https://test.com"},
        "credentials": {"api_key": "top_secret_key"},
    }

    hash1 = compute_request_hash(rendition, destination)

    # Changing credentials must NOT change the request hash (credentials are ignored)
    destination_with_different_creds = {
        "platform": "discourse",
        "settings": {"instance_url": "https://test.com"},
        "credentials": {"api_key": "completely_different_key"},
    }
    hash2 = compute_request_hash(rendition, destination_with_different_creds)

    assert hash1 == hash2
