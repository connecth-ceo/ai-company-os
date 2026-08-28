from unittest.mock import AsyncMock, patch

from app.agents.contracts import ToolAuthorization
from app.agents.orchestrator import OrchestrationResult
from app.models import ReviewVerdict


def test_public_tool_catalog_is_read_only_and_secret_free(client):
    response = client.get("/api/v1/tool-catalog")

    assert response.status_code == 200
    assert response.json() == [
        {
            "key": "web_search",
            "purpose": "Search public web sources for research evidence.",
            "provider": "openai",
            "risk": "read_only",
            "required_permissions": ["web.search"],
            "side_effects": False,
            "approval_required": False,
        }
    ]


def test_task_run_records_authorization_without_claiming_tool_invocation(client):
    outcome = OrchestrationResult(
        final_report="done",
        research="evidence",
        strategy="plan",
        verdict=ReviewVerdict.PASS,
        feedback="ready",
        rework_count=0,
        tool_authorizations=[
            ToolAuthorization(
                tool_name="web_search",
                agent_key="research",
                risk="read_only",
                required_permissions=("web.search",),
            )
        ],
    )
    with patch("app.services.task_service.orchestrate", new=AsyncMock(return_value=outcome)):
        task = client.post(
            "/api/v1/tasks",
            json={"title": "Tool audit", "request": "Research"},
        ).json()
        response = client.post(f"/api/v1/tasks/{task['id']}/run")

    assert response.status_code == 202
    detail = client.get(f"/api/v1/tasks/{task['id']}").json()
    authorization = detail["runs"][0]["artifacts"]["tool_authorizations"][0]
    assert authorization["tool_name"] == "web_search"
    assert authorization["invocation_observed"] is False

    events = client.get("/api/v1/audit-events").json()
    event = next(item for item in events if item["action"] == "tool.access_authorized")
    assert event["resource_id"] == task["id"]
    assert event["details"]["invocation_observed"] is False
