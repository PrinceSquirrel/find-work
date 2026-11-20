from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas import JobPosting
from app.services.llm_client_service import LLMClientUnavailable


def setup_batch(tmp_path, monkeypatch):
    app = create_app(tmp_path / "batch.db")
    service = app.state.service
    jobs = {
        1: job(1, "产品经理", "负责用户访谈和需求梳理。"),
        2: job(2, "分析师", "负责零售交易数据分析。"),
        3: job(3, "摘要岗位", "列表摘要", "card_only"),
    }
    monkeypatch.setattr(service.store, "get_job", lambda job_id: jobs[job_id])
    monkeypatch.setattr(service.store, "get_agent_model_route", lambda agent: SimpleNamespace(model="mock-model"))
    monkeypatch.setattr(service.model_router, "route_for_agent", lambda *_: SimpleNamespace(mode="local_estimate"))
    monkeypatch.setattr(app.state.evidence_service, "recommend_cards", lambda *_: [])
    monkeypatch.setattr(service, "refresh_job_detail", lambda _: None)
    return TestClient(app), service


def job(id, title, jd, status="detail_fetched"):
    return JobPosting(id=id, platform="boss", title=title, company="合成公司", city="上海", salary="未知",
                      description=jd, url=f"https://www.zhipin.com/job_detail/fake-{id}.html", detail_status=status)


def test_prepares_distinct_greetings_only_for_full_jds(tmp_path, monkeypatch):
    client, service = setup_batch(tmp_path, monkeypatch)
    monkeypatch.setattr(service, "apply_to_platform", lambda *_: (_ for _ in ()).throw(AssertionError("prepare sent")))
    rows = client.post("/api/job-batches/greetings", json={"job_ids": [1, 1, 2, 3]}).json()["items"]
    assert [row["status"] for row in rows] == ["ready", "ready", "needs_jd"]
    assert "用户访谈" in rows[0]["text"] and "用户访谈" not in rows[1]["text"]
    assert "零售交易" in rows[1]["text"] and rows[1]["mode"] == "local"
    assert client.post("/api/job-batches/greetings", json={"job_ids": list(range(1, 10))}).status_code == 422


def test_uses_configured_model_and_reports_provider_error_without_silent_fallback(tmp_path, monkeypatch):
    client, service = setup_batch(tmp_path, monkeypatch)
    monkeypatch.setattr(service.model_router, "route_for_agent", lambda *_: SimpleNamespace(mode="external"))
    calls = []
    def draft(config, job, cards):
        calls.append(job.id)
        if job.id == 2:
            raise LLMClientUnavailable("模型认证失败（HTTP 401）")
        return SimpleNamespace(content='{"greeting_message":"您好，想交流用户访谈相关工作。"}')
    monkeypatch.setattr(service.llm_client, "generate_job_greeting", draft)
    monkeypatch.setattr(client.app.state.evidence_service, "_record_llm_usage", lambda *_: None)
    rows = client.post("/api/job-batches/greetings", json={"job_ids": [1, 2]}).json()["items"]
    assert calls == [1, 2]
    assert rows[0]["mode"] == "model" and rows[0]["skill_id"] == "application.greeting"
    assert rows[1]["status"] == "failed" and "401" in rows[1]["message"] and "text" not in rows[1]
    skills = {skill["id"]: skill for skill in client.get("/api/skills").json()}
    assert skills["application.greeting"]["executor"] == "ApplicationWriterAgent"
    assert skills["application.apply.platform"]["requires_confirmation"]


def test_native_batch_explicit_approval_existing_records_and_pause(tmp_path, monkeypatch):
    client, service = setup_batch(tmp_path, monkeypatch)
    path = "/api/job-batches/platform-apply"
    visited = []
    sent = []
    monkeypatch.setattr(service.store, "list_applications", lambda: [SimpleNamespace(job_id=4)])
    def preview(job_id):
        visited.append(job_id)
        return {"ready": True, "status": "ready", "button_text": "立即沟通"}
    def apply(job_id, *, note, expected_button):
        assert expected_button == "立即沟通" and "不包含自定义招呼语" in note
        sent.append(job_id)
        if job_id == 2:
            raise RuntimeError("no proof")
    monkeypatch.setattr(service, "preview_platform_application", preview)
    monkeypatch.setattr(service, "apply_to_platform", apply)
    assert client.post(path, json={"job_ids": [1]}).status_code == 422
    assert client.post(path, json={"job_ids": [1], "confirmed": False}).status_code == 422
    assert not visited and not sent
    items = client.post(path, json={"job_ids": [4, 1, 1, 2, 3], "confirmed": True}).json()["items"]
    assert [row["status"] for row in items] == ["skipped", "confirmed", "unknown", "not_attempted"]
    assert visited == sent == [1, 2]


def test_invalid_platform_url_never_reaches_browser(tmp_path, monkeypatch):
    client, service = setup_batch(tmp_path, monkeypatch)
    monkeypatch.setattr(service.store, "get_job", lambda _: job(1, "合成", "完整 JD").model_copy(update={"url": "https://zhipin.com.example.invalid/job_detail/wrong"}))
    monkeypatch.setattr(service, "preview_platform_application", lambda _: (_ for _ in ()).throw(AssertionError("invalid URL reached browser")))
    response = client.post("/api/job-batches/platform-apply", json={"job_ids": [1], "confirmed": True})
    assert response.json()["items"][0]["status"] == "skipped"
