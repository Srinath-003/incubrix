import httpx
import pytest

from app.connectors.discourse.connector import DiscourseConnector
from app.connectors.registry import connector_registry
from app.policies.rules import PolicyEngine


@pytest.fixture(autouse=True)
def setup_discourse():
    connector_registry.clear()
    connector_registry.register(DiscourseConnector())
    yield
    connector_registry.clear()


def test_policy_frequency_cap_exceeded():
    """Destination frequency cap flags violations when threshold is reached."""
    rendition = {"title": "Normal Title", "caption": "Normal caption."}
    destination = {
        "platform": "discourse",
        "settings": {"frequency_cap_exceeded": True},
    }

    result = PolicyEngine.evaluate(rendition, destination)
    assert result.ok is False
    assert any("frequency cap exceeded" in v.lower() for v in result.violations)


def test_policy_self_promotion_prohibited():
    """Self-promotion phrases are rejected when prohibit_self_promotion is True."""
    rendition_bad = {
        "title": "Exciting Announcement",
        "caption": "Check out our special discount and buy now for best rates!",
    }
    destination = {
        "platform": "discourse",
        "settings": {"prohibit_self_promotion": True},
    }

    result = PolicyEngine.evaluate(rendition_bad, destination)
    assert result.ok is False
    assert any("self-promotion" in v.lower() for v in result.violations)

    # Clean content passes
    rendition_clean = {
        "title": "Open Source Release",
        "caption": "We have published our new documentation for the library.",
    }
    res_clean = PolicyEngine.evaluate(rendition_clean, destination)
    assert res_clean.ok is True


def test_policy_link_restrictions():
    """Link restrictions reject content containing external links or exceeding max_links."""
    # 1. Prohibit links entirely
    rendition_with_link = {
        "title": "Check this resource",
        "caption": "Read more at https://external-blog.com/post for details.",
    }
    destination_no_links = {
        "platform": "discourse",
        "settings": {"prohibit_links": True},
    }
    res1 = PolicyEngine.evaluate(rendition_with_link, destination_no_links)
    assert res1.ok is False
    assert any("prohibits external urls" in v.lower() for v in res1.violations)

    # 2. Maximum links exceeded
    rendition_multi_links = {
        "title": "Multiple Links",
        "caption": "Visit https://link1.org and https://link2.org and https://link3.org.",
    }
    destination_max_1 = {
        "platform": "discourse",
        "settings": {"max_links": 1},
    }
    res2 = PolicyEngine.evaluate(rendition_multi_links, destination_max_1)
    assert res2.ok is False
    assert any("maximum permitted is 1" in v.lower() for v in res2.violations)


def test_policy_ai_disclosure_requirement():
    """AI-generated content must include an AI disclosure when required by destination."""
    destination_ai_req = {
        "platform": "discourse",
        "settings": {"require_ai_disclosure": True},
    }

    # AI content without disclosure -> fails
    rendition_no_disclosure = {
        "title": "Generated Story",
        "caption": "Once upon a time in a digital kingdom.",
        "extra": {"is_ai_generated": True},
    }
    res1 = PolicyEngine.evaluate(rendition_no_disclosure, destination_ai_req)
    assert res1.ok is False
    assert any("ai disclosure required" in v.lower() for v in res1.violations)

    # AI content with #ai disclosure -> passes
    rendition_with_disclosure = {
        "title": "Generated Story",
        "caption": "Once upon a time in a digital kingdom. #ai",
        "extra": {"is_ai_generated": True},
    }
    res2 = PolicyEngine.evaluate(rendition_with_disclosure, destination_ai_req)
    assert res2.ok is True


@pytest.mark.asyncio
async def test_publish_cannot_bypass_policy_hook(async_client: httpx.AsyncClient):
    """Publish endpoint enforces policy hook, returning 422 POLICY_VIOLATION before platform call."""
    payload = {
        "rendition": {
            "title": "Buy Now Discount",
            "caption": "Limited time offer! Buy now for best deal.",
        },
        "destination": {
            "platform": "discourse",
            "settings": {
                "instance_url": "https://discourse.example.com",
                "category": 1,
                "prohibit_self_promotion": True,
            },
        },
        "connection": {
            "auth_type": "api_key",
            "credentials": {"api_key": "k", "api_username": "u"},
        },
        "idempotency_key": "policy-test-key-001",
    }

    response = await async_client.post("/connector/v1/discourse/publish", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "POLICY_VIOLATION"
    assert "violations" in data["error"]["details"]
    assert any("self-promotion" in v.lower() for v in data["error"]["details"]["violations"])
