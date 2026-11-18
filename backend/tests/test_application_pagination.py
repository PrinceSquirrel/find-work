import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas import ApplicationPlatformProof, JobMatch, JobPosting
from app.storage import SQLiteStore


@pytest.fixture
def data(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_BUSINESS_ENV_FILE", str(tmp_path / "missing.env"))
    app = create_app(db_path=tmp_path / "pages.sqlite3")
    store = app.state.service.store
    # Synthetic records are inserted atomically; no real browser, model or user database.
    with store._connect() as conn:
        for index in range(137):
            conn.execute("""INSERT INTO jobs (id,company,title,platform,city,salary,description,url,job_type,match_json,created_at)
                VALUES (?,?,'测试岗位','boss',?,'面议','原岗位正文','https://example.com','internship','{}','2026-11-18')""", (index + 1, f"公司{index}", "上海"))
            conn.execute("""INSERT INTO applications (job_id,company,title,platform,applied_at,current_status,progress_stage,latest_note,platform_proof_json,job_city_snapshot,job_description_snapshot,job_snapshot_origin)
                VALUES (?, ?, ?, 'boss', '2026-11-18T00:00:00+00:00', 'applied','已投递', ?, '{}', ?, ?, 'at_application')""",
                (index + 1, f"公司{index}", "Python 实习" if index % 2 else "产品 实习", "100%_匹配" if index == 1 else "备注", "上海浦东张江" if index % 2 else "北京", "SQL 可视化" if index % 3 else "产品需求"))
            conn.execute("INSERT INTO application_events (application_id,status,occurred_at,note) VALUES (?, 'applied','2026-11-18T00:00:00+00:00','测试事件')", (index + 1,))
    return TestClient(app), store


@pytest.mark.parametrize("size", [25, 50, 100])
def test_pages_are_bounded_stable_complete_and_array_endpoint_compatible(data, size):
    client, _ = data
    ids = []
    for page in range(1, (137 + size - 1) // size + 1):
        response = client.get("/api/applications/page", params={"page": page, "page_size": size})
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 137 and len(body["items"]) <= size
        assert body["statistics_scope"] == "all_applications"
        assert all(item["events"] for item in body["items"])
        ids.extend(item["id"] for item in body["items"])
    assert ids == list(range(137, 0, -1))
    assert isinstance(client.get("/api/applications").json(), list)
    assert len(client.get("/api/applications").json()) == 137


def test_filters_apply_before_pagination_and_use_literal_case_insensitive_and(data):
    client, _ = data
    params = {"position": " python ", "keyword": "sql", "location": "张江", "page_size": 25}
    body = client.get("/api/applications/page", params=params).json()
    assert body["total"] == len([i for i in range(137) if i % 2 and i % 3])
    assert body["total"] > 25
    assert all(item["title"] == "Python 实习" and "张江" in item["location"] for item in body["items"])
    assert client.get("/api/applications/page", params={"keyword": "100%_匹配"}).json()["total"] == 1
    assert client.get("/api/applications/page", params={"keyword": "' OR 1=1 --"}).json()["total"] == 0
    assert client.get("/api/applications/page", params={"keyword": "公司136"}).json()["total"] == 1


def test_empty_results_and_out_of_range_pages_are_explicit(data):
    client, _ = data
    empty = client.get("/api/applications/page", params={"position": "不存在", "page": 40}).json()
    assert empty["items"] == [] and empty["pages"] == 0 and empty["total"] == 0
    last = client.get("/api/applications/page", params={"page": 999}).json()
    assert last["page"] == 6 and len(last["items"]) == 12
    assert client.get("/api/applications/page", params={"position": "  "}).json()["total"] == 137


@pytest.mark.parametrize("params", [{"page": 0}, {"page": -1}, {"page_size": 30}, {"page_size": "bad"}, {"page": 1000001}, {"keyword": "a" * 201}])
def test_query_validation(data, params):
    assert data[0].get("/api/applications/page", params=params).status_code == 422


def test_deletion_on_last_page_preserves_unselected_records_and_count(data):
    client, _ = data
    last = client.get("/api/applications/page", params={"page": 6}).json()
    ids = [item["id"] for item in last["items"]]
    assert client.post("/api/applications/bulk-delete", json={"ids": ids, "confirmed": True}).json()["deleted_ids"] == sorted(ids)
    body = client.get("/api/applications/page", params={"page": 6}).json()
    assert body["total"] == 125 and body["page"] == 5
    assert {item["id"] for item in body["items"]}.isdisjoint(ids)


def test_new_snapshot_survives_job_changes_and_does_not_weaken_proof(data):
    client, store = data
    job = store.save_job(JobPosting(platform="boss", company="真实来源公司", title="岗位", city="苏州", salary="面议", description="原始JD", url="https://example.com/job"), 1, JobMatch(score=70, recommendation="review"))
    with pytest.raises(ValueError):
        store.create_application(job)
    proof = ApplicationPlatformProof(platform="boss", source_url=job.url, action="clicked_apply", status="applied", evidence="合成发送证明", confirmed_at=datetime.now(UTC))
    record = store.create_application(job, platform_proof=proof)
    with store._connect() as conn:
        conn.execute("UPDATE jobs SET city='广州', description='改动JD' WHERE id=?", (job.id,))
    SQLiteStore(store.db_path)
    result = client.get("/api/applications/page", params={"location": "苏州", "keyword": "原始JD"}).json()["items"][0]
    assert result["id"] == record.id and result["location_source"] == "投递时岗位快照"
    assert result["platform_proof"] == json.loads(proof.model_dump_json())


def test_legacy_migration_is_idempotent_and_missing_location_is_not_guessed(data):
    client, store = data
    with store._connect() as conn:
        for column in ("job_city_snapshot", "job_description_snapshot", "job_snapshot_origin"):
            conn.execute(f"ALTER TABLE applications DROP COLUMN {column}")
        conn.execute("UPDATE jobs SET city='杭州', description='迁移正文' WHERE id=1")
        conn.execute("DELETE FROM jobs WHERE id=137")
    SQLiteStore(store.db_path)
    with store._connect() as conn:
        conn.execute("UPDATE jobs SET city='广州' WHERE id=1")
    SQLiteStore(store.db_path)
    result = client.get("/api/applications/page", params={"location": "杭州"}).json()
    assert result["total"] == 1
    assert result["items"][0]["location_source"] == "历史关联岗位（迁移时）"
    assert client.get("/api/applications/page", params={"location": "广州"}).json()["total"] == 0
    unknown = client.get("/api/applications/page", params={"keyword": "公司136"}).json()["items"][0]
    assert unknown["location"] == "" and unknown["location_source"] == "未提供"
