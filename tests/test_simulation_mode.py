from unittest.mock import patch
import httpx
import pytest

from app.config import Settings
from app.connectors.discourse.connector import DiscourseConnector
from app.models.common import Connection, Destination, Rendition
from app.simulation.adapter import SimulationAdapter
from app.simulation.store import simulation_store


@pytest.fixture
def discourse():
    return DiscourseConnector()


def test_simulation_mode_default_enabled():
    """Simulation mode is active by default in Settings for safe local development."""
    settings = Settings()
    assert settings.simulation_mode is True


@pytest.mark.asyncio
async def test_simulation_makes_zero_external_http_requests(discourse: DiscourseConnector):
    """Simulation mode must never make an outbound HTTP request."""
    rendition = Rendition(
        title="Simulated Test Topic",
        caption="Simulated topic body text without credentials.",
    )
    destination = Destination(
        platform="discourse",
        settings={"instance_url": "https://external-discourse.org", "category": 1},
    )
    connection = Connection(
        auth_type="api_key",
        credentials={},  # No credentials required in simulation
    )

    with patch("httpx.AsyncClient.post") as mock_post:
        res = await discourse.publish(
            rendition=rendition,
            destination=destination,
            connection=connection,
            idempotency_key="sim-key-12345",
        )
        # Verify 0 HTTP calls
        mock_post.assert_not_called()

        assert res.platform_post_id.startswith("sim_discourse_")
        assert res.status == "published"
        assert "simulated-discourse-post" in str(res.live_url)


@pytest.mark.asyncio
async def test_simulation_publish_status_and_delete_lifecycle(discourse: DiscourseConnector):
    """Simulated lifecycle: publish records state, get_status retrieves it, delete removes it."""
    rendition = Rendition(title="Demo Topic", caption="Demo body.")
    destination = Destination(
        platform="discourse",
        settings={"instance_url": "https://forum.local", "category": 2},
    )
    connection = Connection(auth_type="api_key", credentials={})

    # 1. Publish
    pub_res = await discourse.publish(rendition, destination, connection, "lifecycle-key")
    post_id = pub_res.platform_post_id

    # 2. Get status
    stat_res = await discourse.get_status(post_id, connection)
    assert stat_res.status == "published"
    assert stat_res.live_url is not None

    # 3. Delete
    del_res = await discourse.delete(post_id, connection)
    assert del_res.deleted is True

    # 4. Check status again -> now deleted
    stat_after = await discourse.get_status(post_id, connection)
    assert stat_after.status == "deleted"
    assert stat_after.live_url is None


@pytest.mark.asyncio
async def test_simulation_store_isolation():
    """Simulation state is isolated between operations and can be cleared cleanly."""
    simulation_store.clear()
    assert len(simulation_store._posts) == 0

    SimulationAdapter.publish(
        rendition={"title": "T"},
        destination={},
        connection={},
        idempotency_key="k1",
        platform="discourse",
    )
    assert len(simulation_store._posts) == 1

    simulation_store.clear()
    assert len(simulation_store._posts) == 0


@pytest.mark.asyncio
async def test_no_silent_fallback_to_simulation():
    """When simulation_mode is False, platform failures never silently fall back to simulation mode."""
    live_settings = Settings(SIMULATION_MODE=False, ALLOW_LOCAL_DESTINATIONS=True)
    connector = DiscourseConnector()

    rendition = Rendition(title="Live Topic Title", caption="Live body content here.")
    destination = Destination(platform="discourse", settings={"instance_url": "https://discourse.example.com", "category": 1})
    connection = Connection(auth_type="api_key", credentials={"api_key": "live_key"})

    # Mock an upstream failure
    with patch("app.connectors.discourse.connector.get_settings", return_value=live_settings):
        with patch("httpx.AsyncClient.post", side_effect=httpx.ConnectError("Network is unreachable")):
            with pytest.raises(Exception) as exc_info:
                await connector.publish(rendition, destination, connection, "k_fail")
            # Must raise PlatformUnavailableError, NOT silently return a simulated post!
            assert "PlatformUnavailableError" in type(exc_info.value).__name__
