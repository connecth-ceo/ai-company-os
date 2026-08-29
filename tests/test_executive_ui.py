def test_ceo_desk_exposes_project_and_ai_team_panels(client):
    response = client.get("/")

    assert response.status_code == 200
    html = response.text
    assert 'id="task-project"' in html
    assert 'id="goal-list"' in html
    assert 'id="goal-form"' in html
    assert 'id="project-list"' in html
    assert 'id="project-form"' in html
    assert 'id="project-goal-id"' in html
    assert 'id="portfolio-health"' in html
    assert 'id="agent-list"' in html
    assert 'id="context-search-form"' in html
    assert 'id="context-search-results"' in html
    assert 'id="provenance-list"' in html
    assert "프롬프트와 비밀값은 노출하지 않습니다." in html


def test_ceo_desk_assets_wire_existing_safe_apis(client):
    script = client.get("/static/app.js")
    stylesheet = client.get("/static/app.css")

    assert script.status_code == 200
    assert stylesheet.status_code == 200
    assert 'api("/api/v1/goals")' in script.text
    assert 'api("/api/v1/projects")' in script.text
    assert 'api("/api/v1/portfolio/health")' in script.text
    assert 'api("/api/v1/agents")' in script.text
    assert 'api("/api/v1/provenance?limit=20")' in script.text
    assert "/api/v1/context/search?q=" in script.text
    assert 'project_id: $("#task-project").value || null' in script.text
    assert 'goal_id: $("#project-goal-id").value || null' in script.text
    assert "renderGoals()" in script.text
    assert "renderProjects()" in script.text
    assert "renderPortfolioHealth()" in script.text
    assert "renderAgents()" in script.text
    assert "renderProvenance()" in script.text
    assert "/transition`" in script.text
    assert "data-goal-id" in script.text
    assert "data-project-id" in script.text
    assert ".executive-grid" in stylesheet.text
    assert ".goal-card" in stylesheet.text
    assert ".agent-card" in stylesheet.text
    assert ".context-search-form" in stylesheet.text
    assert ".portfolio-actions" in stylesheet.text
    assert ".portfolio-health" in stylesheet.text
    assert ".portfolio-progress" in stylesheet.text
    assert ".provenance-list" in stylesheet.text
