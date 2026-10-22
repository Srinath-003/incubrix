import inspect
import pytest
from app.connectors.base import BaseConnector
from app.models.common import Connection, Destination, Rendition
from app.models.connector import (
    AssistPackResponse,
    DeleteResponse,
    MetricsResponse,
    PublishResponse,
    RefreshAuthResponse,
    StatusResponse,
    ValidateResponse,
)
from tests.conftest import SampleAssistedConnector, SampleAutomatedConnector


def test_base_connector_method_signatures_exact():
    """Verify exact method names and argument names match Appendix A authoritative contract."""
    # 1. validate(rendition, destination, connection) -> ValidateResponse
    sig_validate = inspect.signature(BaseConnector.validate)
    params_validate = list(sig_validate.parameters.keys())
    assert params_validate == ["self", "rendition", "destination", "connection"]

    # 2. publish(rendition, destination, connection, idempotency_key) -> PublishResponse
    sig_publish = inspect.signature(BaseConnector.publish)
    params_publish = list(sig_publish.parameters.keys())
    assert params_publish == ["self", "rendition", "destination", "connection", "idempotency_key"]

    # 3. get_status(platform_post_id, connection) -> StatusResponse
    sig_status = inspect.signature(BaseConnector.get_status)
    params_status = list(sig_status.parameters.keys())
    assert params_status == ["self", "platform_post_id", "connection"]

    # 4. delete(platform_post_id, connection) -> DeleteResponse
    sig_delete = inspect.signature(BaseConnector.delete)
    params_delete = list(sig_delete.parameters.keys())
    assert params_delete == ["self", "platform_post_id", "connection"]

    # 5. fetch_metrics(platform_post_id, connection, since) -> MetricsResponse
    sig_metrics = inspect.signature(BaseConnector.fetch_metrics)
    params_metrics = list(sig_metrics.parameters.keys())
    assert params_metrics == ["self", "platform_post_id", "connection", "since"]

    # 6. refresh_auth(connection) -> RefreshAuthResponse
    sig_refresh = inspect.signature(BaseConnector.refresh_auth)
    params_refresh = list(sig_refresh.parameters.keys())
    assert params_refresh == ["self", "connection"]

    # 7. build_assist_pack(rendition, destination) -> AssistPackResponse
    sig_assist = inspect.signature(BaseConnector.build_assist_pack)
    params_assist = list(sig_assist.parameters.keys())
    assert params_assist == ["self", "rendition", "destination"]


@pytest.mark.asyncio
async def test_automated_connector_contract_execution():
    """Execute methods on automated connector and verify return data types."""
    connector = SampleAutomatedConnector(key="test_auto")
    rendition = Rendition(url="https://media.incubrix.com/v1.mp4", media_type="video")
    destination = Destination(platform="sample_platform")
    connection = Connection(auth_type="oauth2", credentials={"token": "abc"})

    # validate
    val_res = await connector.validate(rendition, destination, connection)
    assert isinstance(val_res, ValidateResponse)
    assert val_res.ok is True
    assert isinstance(val_res.violations, list)

    # publish
    pub_res = await connector.publish(rendition, destination, connection, idempotency_key="idem_123")
    assert isinstance(pub_res, PublishResponse)
    assert pub_res.platform_post_id == "sample_idem_123"
    assert pub_res.status == "published"
    assert pub_res.live_url is not None

    # get_status
    stat_res = await connector.get_status("sample_idem_123", connection)
    assert isinstance(stat_res, StatusResponse)
    assert stat_res.status == "published"

    # delete
    del_res = await connector.delete("sample_idem_123", connection)
    assert isinstance(del_res, DeleteResponse)
    assert del_res.deleted is True

    # fetch_metrics
    met_res = await connector.fetch_metrics("sample_idem_123", connection)
    assert isinstance(met_res, MetricsResponse)
    assert "views" in met_res.metrics

    # refresh_auth
    ref_res = await connector.refresh_auth(connection)
    assert isinstance(ref_res, RefreshAuthResponse)
    assert ref_res.refreshed is True


@pytest.mark.asyncio
async def test_assisted_connector_contract_execution():
    """Execute build_assist_pack on assisted connector."""
    connector = SampleAssistedConnector()
    rendition = Rendition(url="https://media.incubrix.com/v2.mp4", media_type="video")
    destination = Destination(platform="sample_assisted")

    pack_res = await connector.build_assist_pack(rendition, destination)
    assert isinstance(pack_res, AssistPackResponse)
    assert pack_res.instructions is not None
    assert len(pack_res.assets) > 0
