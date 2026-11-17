import sqlite3
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas import ApplicationPlatformProof, GreetingMessage, JobMatch, JobPosting, TailoredClaim, TailoredResume


@pytest.fixture
def context(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_BUSINESS_ENV_FILE", str(tmp_path / "missing.env"))
    app = create_app(db_path=tmp_path / "bulk.sqlite3")
    store = app.state.service.store
    jobs = [store.save_job(JobPosting(platform="boss", company=f"公司{i}", title=f"岗位{i}", city="上海", salary="面议", description="Python 开发", url=f"https://example.com/{i}"), 1, JobMatch(score=80, recommendation="review")) for i in range(3)]
    proof = ApplicationPlatformProof(platform="boss", source_url=jobs[1].url, status="applied", action="clicked_apply", evidence="已发送招呼", confirmed_at=datetime.now(UTC))
    record = store.create_application(jobs[1], platform_proof=proof)
    material = store.save_tailor_bundle(TailoredResume(job_id=jobs[0].id, resume_id=1, resume_text="真实经历", truth_check_passed=True), GreetingMessage(job_id=jobs[0].id, message="您好"), {})
    store.create_tailored_claim(TailoredClaim(tailored_resume_id=material["id"], text="真实经历", evidence_card_ids=[]))
    store.reindex_knowledge()
    return TestClient(app), store, jobs, record, material


def test_delete_jobs_is_explicit_preserves_applications_and_cleans_materials(context):
    client, store, jobs, record, material = context
    result = client.post("/api/jobs/bulk-delete", json={"ids": [jobs[0].id, jobs[0].id, jobs[1].id, 99999], "confirmed": True})
    assert result.status_code == 200
    assert result.json() == {"deleted_ids": [jobs[0].id], "protected_ids": [jobs[1].id], "missing_ids": [99999]}
    assert store.get_application(record.id).job_id == jobs[1].id
    assert store.get_job(jobs[2].id)
    with pytest.raises(KeyError):
        store.get_tailor_bundle(material["id"])
    assert all(doc.source_id != jobs[0].id or doc.source_type != "job" for doc in store.list_knowledge_documents())
    with store._connect() as conn:
        assert conn.execute("SELECT count(*) FROM tailored_claims WHERE tailored_resume_id=?", (material["id"],)).fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM knowledge_chunks_fts WHERE source_type='job' AND source_id=?", (str(jobs[0].id),)).fetchone()[0] == 0


def test_delete_applications_removes_events_statistics_and_index_not_job(context):
    client, store, jobs, record, _ = context
    response = client.post("/api/applications/bulk-delete", json={"ids": [record.id], "confirmed": True})
    assert response.json()["deleted_ids"] == [record.id]
    assert client.get("/api/applications").json() == []
    assert store.get_job(jobs[1].id)
    with store._connect() as conn:
        assert conn.execute("SELECT count(*) FROM application_events WHERE application_id=?", (record.id,)).fetchone()[0] == 0
        for table in ("knowledge_documents", "knowledge_chunks", "knowledge_chunks_fts"):
            assert conn.execute(f"SELECT count(*) FROM {table} WHERE source_type='application'").fetchone()[0] == 0
    repeated = client.post("/api/applications/bulk-delete", json={"ids": [record.id], "confirmed": True}).json()
    assert repeated["deleted_ids"] == [] and repeated["missing_ids"] == [record.id]
    assert client.get("/api/analytics/applications").status_code == 200


@pytest.mark.parametrize("payload", [{}, {"ids": [], "confirmed": True}, {"ids": [1]}, {"ids": [1], "confirmed": False}, {"ids": [0], "confirmed": True}, {"ids": [True], "confirmed": True}, {"ids": ["1 OR 1=1"], "confirmed": True}, {"ids": list(range(1, 1002)), "confirmed": True}])
def test_delete_requires_bounded_positive_ids_and_confirmation(context, payload):
    client, store, jobs, _, _ = context
    for path in ("jobs", "applications"):
        assert client.post(f"/api/{path}/bulk-delete", json=payload).status_code == 422
    assert len(store.list_jobs()) == len(jobs)


def test_delete_rolls_back_dependencies_on_database_failure(context):
    client, store, jobs, _, material = context
    with store._connect() as conn:
        conn.execute("CREATE TRIGGER refuse_delete BEFORE DELETE ON jobs BEGIN SELECT RAISE(ABORT, 'test rollback'); END")
    with pytest.raises(sqlite3.IntegrityError):
        client.post("/api/jobs/bulk-delete", json={"ids": [jobs[0].id], "confirmed": True})
    assert store.get_job(jobs[0].id)
    assert store.get_tailor_bundle(material["id"])
    assert len(store.list_tailored_claims(material["id"])) == 1
