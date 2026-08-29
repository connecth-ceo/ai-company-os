from app.services.provenance import extract_source_uris


def create_and_run_task(client, request: str) -> dict:
    created = client.post(
        "/api/v1/tasks",
        json={"title": "Provenance test", "request": request},
    )
    assert created.status_code == 201
    task_id = created.json()["id"]
    dispatched = client.post(f"/api/v1/tasks/{task_id}/run")
    assert dispatched.status_code == 202
    detail = client.get(f"/api/v1/tasks/{task_id}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "completed"
    return detail.json()


def test_extract_source_uris_is_bounded_normalized_and_deduplicated():
    content = (
        "See HTTPS://Example.COM/report?q=1#section and "
        "https://example.com/report?q=1. Invalid ftp://example.com/file."
    )

    assert extract_source_uris(content) == ["https://example.com/report?q=1"]


def test_research_provenance_is_captured_and_tenant_safe(client):
    task = create_and_run_task(
        client,
        "근거 https://Example.com/report#summary 를 포함해 검토해줘.",
    )

    response = client.get(f"/api/v1/provenance?task_id={task['id']}")
    assert response.status_code == 200
    records = response.json()
    assert len(records) == 1
    record = records[0]
    assert record["subject_type"] == "knowledge"
    assert record["source_type"] == "url"
    assert record["source_uri"] == "https://example.com/report"
    assert record["claim_reference"] == "research_brief"
    assert record["verification_status"] == "observed"
    assert record["task_run_id"] == task["runs"][0]["id"]
    assert len(record["content_hash"]) == 64
    assert record["record_metadata"]["citation_count"] == 1

    hidden_list = client.get(
        "/api/v1/provenance",
        headers={"X-Tenant-ID": "other"},
    )
    hidden_detail = client.get(
        f"/api/v1/provenance/{record['id']}",
        headers={"X-Tenant-ID": "other"},
    )
    assert hidden_list.json() == []
    assert hidden_detail.status_code == 404


def test_decision_inherits_task_research_provenance(client):
    task = create_and_run_task(
        client,
        "https://example.com/source 를 근거로 선택지를 검토해줘.",
    )
    knowledge_record = client.get(
        f"/api/v1/provenance?task_id={task['id']}&subject_type=knowledge"
    ).json()[0]

    created = client.post(
        "/api/v1/decisions",
        json={
            "subject": "출시 방식",
            "choice": "단계적 출시",
            "rationale": "연구 결과에 따라 위험을 줄이는 방식을 선택한다.",
            "task_id": task["id"],
        },
    )
    assert created.status_code == 201

    records = client.get(f"/api/v1/provenance?decision_id={created.json()['id']}").json()
    assert len(records) == 1
    record = records[0]
    assert record["subject_type"] == "decision"
    assert record["source_type"] == "inherited"
    assert record["source_record_id"] == knowledge_record["id"]
    assert record["source_uri"] == "https://example.com/source"
    assert record["claim_reference"] == "decision_rationale"


def test_manual_decision_records_unverified_rationale(client):
    created = client.post(
        "/api/v1/decisions",
        json={
            "subject": "내부 운영 방식",
            "choice": "주간 검토",
            "rationale": "대표의 운영 판단",
        },
    )

    records = client.get(f"/api/v1/provenance?decision_id={created.json()['id']}").json()
    assert len(records) == 1
    assert records[0]["source_type"] == "manual"
    assert records[0]["verification_status"] == "unverified"
