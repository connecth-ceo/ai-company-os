from app.agents.operational_registry import LEGAL_REVIEW_AGENT_KEY, MARKETING_AGENT_KEY
from app.agents.v04_registry import (
    CHIEF_AGENT_KEY,
    RESEARCH_AGENT_KEY,
    REVIEWER_AGENT_KEY,
    STRATEGY_AGENT_KEY,
)

EXPECTED_AGENT_KEYS = {
    CHIEF_AGENT_KEY,
    RESEARCH_AGENT_KEY,
    STRATEGY_AGENT_KEY,
    REVIEWER_AGENT_KEY,
    MARKETING_AGENT_KEY,
    LEGAL_REVIEW_AGENT_KEY,
}


def test_agent_directory_lists_operational_registry_without_prompts(client):
    response = client.get("/api/v1/agents")

    assert response.status_code == 200
    agents = response.json()
    assert [agent["key"] for agent in agents] == sorted(EXPECTED_AGENT_KEYS)
    assert len(agents) == 6
    for agent in agents:
        assert "system_prompt" not in agent
        assert "output_schema" not in agent
        assert "api_key" not in agent
        assert "secret" not in agent


def test_agent_directory_exposes_declarative_policy_not_runtime_objects(client):
    research = client.get(f"/api/v1/agents/{RESEARCH_AGENT_KEY}")

    assert research.status_code == 200
    profile = research.json()
    assert profile["role"] == "Research Agent"
    assert profile["allowed_tools"] == ["web_search"]
    assert "web.search" in profile["permissions"]
    assert profile["evaluation_status"] == "baseline"
    assert profile["provider"] == "openai"
    assert isinstance(profile["structured_output"], bool)


def test_agent_directory_specialist_safety_policies_are_visible(client):
    marketing = client.get(f"/api/v1/agents/{MARKETING_AGENT_KEY}").json()
    legal = client.get(f"/api/v1/agents/{LEGAL_REVIEW_AGENT_KEY}").json()

    assert marketing["approval_policy"] == "draft_only_external_publish_requires_ceo"
    assert legal["approval_policy"] == "advisory_only_no_legal_action"
    assert marketing["allowed_tools"] == []
    assert legal["allowed_tools"] == []


def test_unknown_agent_is_404_and_directory_is_read_only(client):
    before = client.get("/api/v1/audit-events").json()

    missing = client.get("/api/v1/agents/missing_agent")
    unsupported_write = client.post("/api/v1/agents", json={"role": "Shadow Agent"})

    assert missing.status_code == 404
    assert unsupported_write.status_code in {404, 405}
    assert client.get("/api/v1/audit-events").json() == before
