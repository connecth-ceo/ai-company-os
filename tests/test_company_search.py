def seed_company_context(client, *, tenant="owner"):
    headers = {"X-Tenant-ID": tenant}
    memory = client.post(
        "/api/v1/memories",
        json={
            "category": "product",
            "content": "Project Atlas는 중소기업 CEO를 위한 운영 자동화 제품이다.",
        },
        headers=headers,
    )
    decision = client.post(
        "/api/v1/decisions",
        json={
            "subject": "Project Atlas 출시 시장",
            "choice": "한국 시장에서 먼저 출시한다.",
            "rationale": "기존 고객 인터뷰 근거가 가장 충분하다.",
        },
        headers=headers,
    )
    knowledge = client.post(
        "/api/v1/knowledge",
        json={
            "title": "Project Atlas 출시 체크리스트",
            "content": "가격 페이지와 고객 온보딩을 출시 전에 확인한다.",
            "source": "internal-playbook",
        },
        headers=headers,
    )
    assert memory.status_code == 201
    assert decision.status_code == 201
    assert knowledge.status_code == 201
    return memory.json(), decision.json(), knowledge.json()


def test_search_returns_ranked_unified_company_context(client):
    seed_company_context(client)

    response = client.get("/api/v1/context/search", params={"q": "Project Atlas"})

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "Project Atlas"
    assert body["total"] == 3
    assert {item["resource_type"] for item in body["items"]} == {
        "memory",
        "decision",
        "knowledge",
    }
    assert [item["score"] for item in body["items"]] == sorted(
        [item["score"] for item in body["items"]],
        reverse=True,
    )
    assert all(len(item["excerpt"]) <= 322 for item in body["items"])


def test_search_filters_resource_type_and_respects_limit(client):
    _, _, knowledge = seed_company_context(client)

    response = client.get(
        "/api/v1/context/search",
        params=[("q", "출시"), ("type", "knowledge"), ("limit", "1")],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["resource_id"] == knowledge["id"]
    assert body["items"][0]["metadata"]["source"] == "internal-playbook"


def test_search_defaults_to_effective_decisions_only(client):
    proposed = client.post(
        "/api/v1/decisions",
        json={
            "subject": "Project Nova 실험",
            "choice": "부산에서 비공개 파일럿을 진행한다.",
            "rationale": "검토 중인 가설이다.",
            "status": "proposed",
        },
    )
    assert proposed.status_code == 201

    hidden = client.get("/api/v1/context/search", params={"q": "Project Nova"})
    included = client.get(
        "/api/v1/context/search",
        params={"q": "Project Nova", "effective_decisions_only": "false"},
    )

    assert hidden.status_code == 200
    assert hidden.json()["total"] == 0
    assert included.status_code == 200
    assert included.json()["items"][0]["resource_id"] == proposed.json()["id"]
    assert included.json()["items"][0]["metadata"]["status"] == "proposed"


def test_search_is_tenant_isolated(client):
    seed_company_context(client, tenant="owner")

    other = client.get(
        "/api/v1/context/search",
        params={"q": "Project Atlas"},
        headers={"X-Tenant-ID": "other"},
    )

    assert other.status_code == 200
    assert other.json() == {"query": "Project Atlas", "total": 0, "items": []}


def test_search_rejects_invalid_filters_and_short_queries(client):
    short = client.get("/api/v1/context/search", params={"q": "x"})
    invalid_type = client.get(
        "/api/v1/context/search",
        params=[("q", "valid query"), ("type", "secret")],
    )

    assert short.status_code == 422
    assert invalid_type.status_code == 422
