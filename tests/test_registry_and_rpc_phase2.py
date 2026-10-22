import logging
import httpx
import pytest

from app.connectors.base import BaseConnector
from app.connectors.discourse.connector import DiscourseConnector
from app.connectors.registry import connector_registry
from app.core.errors import ConnectorDisabledError, ConnectorNotFoundError, DuplicateConnectorError, ErrorCode, SecurityViolationError
from app.core.security import RedactingFilter, redact_sensitive_data, validate_destination_url
from app.models.common import Connection, Destination, Rendition
from app.models.manifest import ConnectorManifest
from tests.conftest import SampleAutomatedConnector


@pytest.fixture(autouse=True)
def clean():
    connector_registry.clear()
    yield
    connector_registry.clear()


def test_registry_handles_disabled_connectors():
    """Disabled connectors are tracked and raise ConnectorDisabledError upon retrieval."""
    connector = SampleAutomatedConnector(key="platform_to_disable")
    connector_registry.register(connector)

    assert connector_registry.is_disabled("platform_to_disable") is False

    # Disable connector
    connector_registry.disable("platform_to_disable")
    assert connector_registry.is_disabled("platform_to_disable") is True

    # Retrieval raises ConnectorDisabledError
    with pytest.raises(ConnectorDisabledError) as exc_info:
        connector_registry.get("platform_to_disable")
    assert exc_info.value.code == ErrorCode.CONNECTOR_DISABLED

    # Re-enable
    connector_registry.enable("platform_to_disable")
    assert connector_registry.is_disabled("platform_to_disable") is False
    assert connector_registry.get("platform_to_disable") is connector


@pytest.mark.asyncio
async def test_rpc_disabled_connector_returns_403(async_client: httpx.AsyncClient):
    """Calling an RPC method on a disabled connector returns HTTP 403 CONNECTOR_DISABLED."""
    connector = SampleAutomatedConnector(key="auto_disabled")
    connector_registry.register(connector)
    connector_registry.disable("auto_disabled")

    response = await async_client.post(
        "/connector/v1/auto_disabled/validate",
        json={"rendition": {}, "destination": {}, "connection": {}},
    )
    assert response.status_code == 403
    data = response.json()
    assert data["error"]["code"] == "CONNECTOR_DISABLED"
    assert "disabled" in data["error"]["message"].lower()


@pytest.mark.asyncio
async def test_rpc_unknown_connector_returns_404(async_client: httpx.AsyncClient):
    """Calling an RPC method on an unregistered connector returns HTTP 404 CONNECTOR_NOT_FOUND."""
    response = await async_client.post(
        "/connector/v1/unregistered_service_xyz/get_status",
        json={"platform_post_id": "123", "connection": {}},
    )
    assert response.status_code == 404
    data = response.json()
    assert data["error"]["code"] == "CONNECTOR_NOT_FOUND"


def test_ssrf_validation_blocks_private_and_metadata_addresses():
    """validate_destination_url rejects loopback, private ranges, and cloud metadata IPs."""
    unsafe_urls = [
        "http://localhost:8080/api",
        "http://127.0.0.1:27017",
        "http://169.254.169.254/computeMetadata/v1",
        "http://10.0.0.5/admin",
        "http://192.168.1.100:8000",
        "http://[::1]:8000",
    ]

    for url in unsafe_urls:
        with pytest.raises(SecurityViolationError):
            validate_destination_url(url, allow_local=False)

    # Safe public URL passes
    assert validate_destination_url("https://discourse.example.com") == "https://discourse.example.com"

    # Local testing allowed when allow_local=True
    assert validate_destination_url("http://localhost:8000", allow_local=True) == "http://localhost:8000"


def test_sensitive_credential_redaction():
    """redact_sensitive_data recursively scrubs api keys, tokens, and passwords."""
    data = {
        "title": "Public Title",
        "connection": {
            "auth_type": "api_key",
            "credentials": {
                "api_key": "top_secret_key_12345",
                "api_username": "admin",
                "secret_token": "my_jwt_token_xyz",
            },
        },
        "items": [
            {"name": "test", "password": "super_secret_pw"},
        ],
    }

    sanitized = redact_sensitive_data(data)
    assert sanitized["title"] == "Public Title"
    assert sanitized["connection"]["credentials"]["api_key"] == "***REDACTED***"
    assert sanitized["connection"]["credentials"]["secret_token"] == "***REDACTED***"
    assert sanitized["items"][0]["password"] == "***REDACTED***"
    assert sanitized["connection"]["credentials"]["api_username"] == "admin"


def test_redacting_logger_filter():
    """RedactingFilter masks API keys and tokens in log messages."""
    filter_obj = RedactingFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="Sent request with Api-Key: super_secret_discourse_key and Bearer token12345",
        args=(),
        exc_info=None,
    )

    filter_obj.filter(record)
    assert "super_secret_discourse_key" not in record.msg
    assert "token12345" not in record.msg
    assert "***REDACTED***" in record.msg
