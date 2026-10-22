import inspect
from unittest.mock import AsyncMock, patch
import httpx
import pytest

from app.config import Settings
from app.connectors.discourse.connector import DiscourseConnector
from app.core.errors import (
    AmbiguousTimeoutError,
    AuthenticationError,
    ContentRejectedError,
    ErrorCode,
    IncuBrixError,
    PlatformUnavailableError,
    RateLimitedError,
    SecurityViolationError,
)
from app.models.common import Connection, ConnectorTier, Destination, Rendition


@pytest.fixture
def discourse_connector() -> DiscourseConnector:
    return DiscourseConnector()


@pytest.fixture
def live_settings() -> Settings:
    """Settings with simulation_mode=False for testing real adapter logic."""
    return Settings(
        SIMULATION_MODE=False,
        ALLOW_LOCAL_DESTINATIONS=True,
        DISCOURSE_TEST_URL="http://127.0.0.1:4200",
    )


def test_discourse_manifest(discourse_connector: DiscourseConnector):
    """Discourse manifest declares all capabilities, tier, methods, and parameters accurately."""
    manifest = discourse_connector.manifest
    assert manifest.connector_key == "discourse"
    assert manifest.tier == ConnectorTier.AUTOMATED
    assert manifest.platform == "discourse"
    assert manifest.auth_type == "api_key"
    assert set(manifest.supported_methods) == {"validate", "publish", "get_status", "delete"}
    manifest.validate_tier_requirements()

    # Capabilities and limits
    assert manifest.capabilities.supports_delete is True
    assert manifest.capabilities.custom_limits["min_title_length"] == 5
    assert "post" in manifest.supported_surfaces or "topic" in manifest.supported_surfaces
    assert "api_key" in manifest.auth_requirements
    assert "instance_url" in manifest.instance_parameters
    assert "429" in manifest.error_mapping


@pytest.mark.asyncio
async def test_discourse_validate_success(discourse_connector: DiscourseConnector):
    """Validation succeeds when title, caption, destination URL, category, and api_key are valid."""
    rendition = Rendition(
        title="Valid Discourse Topic Title",
        caption="This is a valid discussion body for Discourse topic creation.",
        tags=["technology", "engineering"],
    )
    destination = Destination(
        platform="discourse",
        settings={"instance_url": "https://forum.example.com", "category": 1},
    )
    connection = Connection(
        auth_type="api_key",
        credentials={"api_key": "mock_api_key_123", "api_username": "moderator"},
    )

    res = await discourse_connector.validate(rendition, destination, connection)
    assert res.ok is True
    assert res.violations == []


@pytest.mark.asyncio
async def test_discourse_validate_rendition_title_and_body(discourse_connector: DiscourseConnector):
    """Validation flags missing or too-short title and caption."""
    # Title too short (< 5 chars), body too short (< 10 chars)
    rendition = Rendition(title="Hi", caption="Short")
    destination = Destination(
        platform="discourse",
        settings={"instance_url": "https://forum.example.com", "category": 1},
    )
    connection = Connection(
        auth_type="api_key",
        credentials={"api_key": "valid_key", "api_username": "user"},
    )

    res = await discourse_connector.validate(rendition, destination, connection)
    assert res.ok is False
    assert any("title is too short" in v.lower() for v in res.violations)
    assert any("body is too short" in v.lower() for v in res.violations)


@pytest.mark.asyncio
async def test_discourse_validate_destination_and_credentials(discourse_connector: DiscourseConnector):
    """Validation flags missing category, instance URL, and API key."""
    rendition = Rendition(
        title="Valid Long Title Here",
        caption="Valid long discussion body for topic.",
    )
    destination = Destination(platform="discourse", settings={})
    connection = Connection(auth_type="api_key", credentials={})

    res = await discourse_connector.validate(rendition, destination, connection)
    assert res.ok is False
    assert any("instance_url" in v for v in res.violations)
    assert any("category" in v for v in res.violations)
    assert any("api_key" in v for v in res.violations)


@pytest.mark.asyncio
async def test_discourse_validate_rejects_ssrf_destination(discourse_connector: DiscourseConnector):
    """Validation rejects internal/private IP destination addresses under default security settings."""
    rendition = Rendition(
        title="Valid Topic Title",
        caption="Valid long discussion body for topic.",
    )
    destination = Destination(
        platform="discourse",
        settings={"instance_url": "http://169.254.169.254/latest", "category": 1},
    )
    connection = Connection(
        auth_type="api_key",
        credentials={"api_key": "key", "api_username": "user"},
    )

    res = await discourse_connector.validate(rendition, destination, connection)
    assert res.ok is False
    assert any("restricted" in v.lower() or "local" in v.lower() for v in res.violations)


@pytest.mark.asyncio
async def test_discourse_publish_mapped_request(discourse_connector: DiscourseConnector, live_settings: Settings):
    """Verify HTTP request mapping (headers, title, raw, category, tags) on real publish call."""
    rendition = Rendition(
        title="Scaling Microservices",
        caption="Here is an in-depth guide to scaling backend microservices safely.",
        tags=["devops", "cloud"],
    )
    destination = Destination(
        platform="discourse",
        settings={"instance_url": "https://discourse.example.com", "category": 7},
    )
    connection = Connection(
        auth_type="api_key",
        credentials={"api_key": "secret_key_abc", "api_username": "author_bob"},
    )

    mock_resp = httpx.Response(
        status_code=200,
        json={"id": 8812, "topic_id": 4321, "topic_slug": "scaling-microservices"},
        request=httpx.Request("POST", "https://discourse.example.com/posts.json"),
    )

    with patch("app.connectors.discourse.connector.get_settings", return_value=live_settings):
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_resp

            pub_res = await discourse_connector.publish(
                rendition, destination, connection, idempotency_key="key-001"
            )

            assert pub_res.platform_post_id == "8812"
            assert pub_res.status == "published"
            assert pub_res.live_url == "https://discourse.example.com/t/scaling-microservices/4321"

            # Check outbound request payload and headers
            mock_post.assert_called_once()
            _, kwargs = mock_post.call_args
            assert kwargs["json"]["title"] == "Scaling Microservices"
            assert kwargs["json"]["raw"] == "Here is an in-depth guide to scaling backend microservices safely."
            assert kwargs["json"]["category"] == 7
            assert kwargs["json"]["tags"] == ["devops", "cloud"]
            assert kwargs["headers"]["Api-Key"] == "secret_key_abc"
            assert kwargs["headers"]["Api-Username"] == "author_bob"


@pytest.mark.asyncio
async def test_discourse_publish_authentication_failure(discourse_connector: DiscourseConnector, live_settings: Settings):
    """HTTP 401/403 maps to AuthenticationError."""
    rendition = Rendition(title="Valid Title", caption="Valid body for discussion topic.")
    destination = Destination(platform="discourse", settings={"instance_url": "https://discourse.example.com", "category": 1})
    connection = Connection(auth_type="api_key", credentials={"api_key": "bad_key"})

    mock_resp = httpx.Response(
        status_code=403,
        json={"error_type": "invalid_access"},
        request=httpx.Request("POST", "https://discourse.example.com/posts.json"),
    )

    with patch("app.connectors.discourse.connector.get_settings", return_value=live_settings):
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            with pytest.raises(AuthenticationError) as exc_info:
                await discourse_connector.publish(rendition, destination, connection, "k1")
            assert exc_info.value.code == ErrorCode.AUTHENTICATION_ERROR


@pytest.mark.asyncio
async def test_discourse_publish_rate_limited(discourse_connector: DiscourseConnector, live_settings: Settings):
    """HTTP 429 maps to RateLimitedError with retryable=True."""
    rendition = Rendition(title="Valid Title", caption="Valid body for discussion topic.")
    destination = Destination(platform="discourse", settings={"instance_url": "https://discourse.example.com", "category": 1})
    connection = Connection(auth_type="api_key", credentials={"api_key": "key"})

    mock_resp = httpx.Response(
        status_code=429,
        json={"errors": ["You've performed this action too many times."]},
        request=httpx.Request("POST", "https://discourse.example.com/posts.json"),
    )

    with patch("app.connectors.discourse.connector.get_settings", return_value=live_settings):
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            with pytest.raises(RateLimitedError) as exc_info:
                await discourse_connector.publish(rendition, destination, connection, "k2")
            assert exc_info.value.code == ErrorCode.RATE_LIMITED
            assert exc_info.value.retryable is True


@pytest.mark.asyncio
async def test_discourse_publish_content_rejected(discourse_connector: DiscourseConnector, live_settings: Settings):
    """HTTP 422 maps to ContentRejectedError with details."""
    rendition = Rendition(title="Valid Title", caption="Valid body for discussion topic.")
    destination = Destination(platform="discourse", settings={"instance_url": "https://discourse.example.com", "category": 1})
    connection = Connection(auth_type="api_key", credentials={"api_key": "key"})

    mock_resp = httpx.Response(
        status_code=422,
        json={"errors": ["Body seems unclear, is it a complete sentence?"]},
        request=httpx.Request("POST", "https://discourse.example.com/posts.json"),
    )

    with patch("app.connectors.discourse.connector.get_settings", return_value=live_settings):
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            with pytest.raises(ContentRejectedError) as exc_info:
                await discourse_connector.publish(rendition, destination, connection, "k3")
            assert exc_info.value.code == ErrorCode.CONTENT_REJECTED


@pytest.mark.asyncio
async def test_discourse_publish_platform_unavailable(discourse_connector: DiscourseConnector, live_settings: Settings):
    """HTTP 502/503 maps to PlatformUnavailableError with retryable=True."""
    rendition = Rendition(title="Valid Title", caption="Valid body for discussion topic.")
    destination = Destination(platform="discourse", settings={"instance_url": "https://discourse.example.com", "category": 1})
    connection = Connection(auth_type="api_key", credentials={"api_key": "key"})

    mock_resp = httpx.Response(
        status_code=503,
        request=httpx.Request("POST", "https://discourse.example.com/posts.json"),
    )

    with patch("app.connectors.discourse.connector.get_settings", return_value=live_settings):
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            with pytest.raises(PlatformUnavailableError) as exc_info:
                await discourse_connector.publish(rendition, destination, connection, "k4")
            assert exc_info.value.code == ErrorCode.PLATFORM_UNAVAILABLE
            assert exc_info.value.retryable is True


@pytest.mark.asyncio
async def test_discourse_publish_ambiguous_timeout(discourse_connector: DiscourseConnector, live_settings: Settings):
    """Client timeout maps to AmbiguousTimeoutError (retryable=False)."""
    rendition = Rendition(title="Valid Title", caption="Valid body for discussion topic.")
    destination = Destination(platform="discourse", settings={"instance_url": "https://discourse.example.com", "category": 1})
    connection = Connection(auth_type="api_key", credentials={"api_key": "key"})

    with patch("app.connectors.discourse.connector.get_settings", return_value=live_settings):
        with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Read timed out")):
            with pytest.raises(AmbiguousTimeoutError) as exc_info:
                await discourse_connector.publish(rendition, destination, connection, "k5")
            assert exc_info.value.code == ErrorCode.AMBIGUOUS_TIMEOUT
            assert exc_info.value.retryable is False


@pytest.mark.asyncio
async def test_discourse_get_status(discourse_connector: DiscourseConnector, live_settings: Settings):
    """get_status queries post endpoint and handles deleted posts."""
    connection = Connection(auth_type="api_key", credentials={"api_key": "k"})

    # 1. Published post
    mock_active = httpx.Response(
        status_code=200,
        json={"id": 100, "topic_id": 50, "topic_slug": "my-topic", "deleted_at": None},
        request=httpx.Request("GET", "http://test/posts/100.json"),
    )
    with patch("app.connectors.discourse.connector.get_settings", return_value=live_settings):
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_active):
            res = await discourse_connector.get_status("100", connection)
            assert res.status == "published"
            assert "my-topic/50" in str(res.live_url)

    # 2. Deleted post
    mock_deleted = httpx.Response(
        status_code=200,
        json={"id": 100, "topic_id": 50, "topic_slug": "my-topic", "deleted_at": "2026-10-22T00:00:00Z"},
        request=httpx.Request("GET", "http://test/posts/100.json"),
    )
    with patch("app.connectors.discourse.connector.get_settings", return_value=live_settings):
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_deleted):
            res_del = await discourse_connector.get_status("100", connection)
            assert res_del.status == "deleted"
            assert res_del.live_url is None


@pytest.mark.asyncio
async def test_discourse_delete(discourse_connector: DiscourseConnector, live_settings: Settings):
    """delete issues DELETE request against post and returns DeleteResponse."""
    connection = Connection(auth_type="api_key", credentials={"api_key": "k"})
    mock_del = httpx.Response(
        status_code=200,
        request=httpx.Request("DELETE", "http://test/posts/100.json"),
    )
    with patch("app.connectors.discourse.connector.get_settings", return_value=live_settings):
        with patch("httpx.AsyncClient.delete", new_callable=AsyncMock, return_value=mock_del):
            res = await discourse_connector.delete("100", connection)
            assert res.deleted is True


def test_no_disabled_tls_verification():
    """Verify production code never sets verify=False on HTTP client."""
    from app.connectors.discourse import connector
    source = inspect.getsource(connector)
    assert "verify=False" not in source
    assert "verify = False" not in source
