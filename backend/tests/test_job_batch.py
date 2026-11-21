from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas import JobMatch, JobPosting
from app.services import job_batch_service
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


def test_reviewed_send_keeps_exact_text_and_only_persists_proven_results(tmp_path, monkeypatch):
    db_path = tmp_path / "send.db"
    app = create_app(db_path)
    store = app.state.service.store
    jobs = [store.save_job(job(i, f"合成岗位 {i}", "岗位需求"), 1, JobMatch(score=80, recommendation="review")) for i in range(1, 4)]
    payload = {"items": [{"job_id": item.id, "text": f"已审核 {i}\n面向这份 JD。"} for i, item in enumerate(jobs)], "confirmed": True}
    calls = []

    def send(job, text):
        calls.append((job.id, text))
        if job.id == jobs[0].id:
            return {"status": "confirmed", "message": "出站原文获平台确认。", "verified_company": "详情页公司", "verified_city": "苏州"}
        return {"status": "unknown", "message": "未收到回执。"}

    monkeypatch.setattr(job_batch_service, "BossGreetingService", lambda: SimpleNamespace(send=send))
    client = TestClient(app)
    path = "/api/job-batches/send-greetings"
    for invalid in [{**payload, "confirmed": False}, {**payload, "confirmed": 1},
                    {**payload, "items": payload["items"][:1] * 2}, {**payload, "items": [{"job_id": 1, "text": " "}]}]:
        assert client.post(path, json=invalid).status_code == 422
    assert not calls
    result = client.post(path, json=payload).json()["items"]
    assert [item["status"] for item in result] == ["confirmed", "unknown", "not_attempted"]
    assert calls == [(item["job_id"], item["text"]) for item in payload["items"][:2]]
    records = store.list_applications()
    assert len(records) == 1 and records[0].platform_proof.action == "sent_custom_greeting"
    assert records[0].platform_proof.source_url == jobs[0].url
    assert records[0].company == "详情页公司"
    assert client.get("/api/applications/page", params={"location": "苏州"}).json()["total"] == 1
    assert store.get_job(jobs[0].id).company == "合成公司"
    assert payload["items"][0]["text"] not in records[0].latest_note
    recreated = TestClient(create_app(db_path))
    assert [row["status"] for row in recreated.post(path, json=payload).json()["items"]] == ["skipped", "unknown", "not_attempted"]
    assert len(calls) == 2


def test_proven_no_action_can_retry_after_login_and_other_platform_does_not_send(tmp_path, monkeypatch):
    app = create_app(tmp_path / "blocked.db")
    store = app.state.service.store
    boss = store.save_job(job(1, "合成岗位", "岗位需求"), 1, JobMatch(score=80, recommendation="review"))
    other = store.save_job(job(2, "另一个岗位", "岗位需求").model_copy(update={"platform": "shixiseng"}), 1,
                           JobMatch(score=80, recommendation="review"))
    calls = []
    def send(job, text):
        calls.append(job.id)
        return {"status": "blocked", "message": "还未登录。"} if len(calls) == 1 else {"status": "already_confirmed", "message": "原文已有回执。"}
    monkeypatch.setattr(job_batch_service, "BossGreetingService", lambda: SimpleNamespace(send=send))
    client = TestClient(app)
    request = {"items": [{"job_id": item.id, "text": "我审核的招呼"} for item in (other, boss)], "confirmed": True}
    assert [x["status"] for x in client.post("/api/job-batches/send-greetings", json=request).json()["items"]] == ["skipped", "blocked"]
    assert not store.list_applications()
    assert [x["status"] for x in client.post("/api/job-batches/send-greetings", json=request).json()["items"]] == ["skipped", "confirmed"]
    assert calls == [boss.id, boss.id]


def test_greeting_joins_user_confirmed_profile_without_sending_it_to_model(tmp_path, monkeypatch):
    client, service = setup_batch(tmp_path, monkeypatch)
    path = "/api/job-batches/greetings"
    introduction = "我是2028届示例大学管理科学与工程专业硕士研究生"
    availability = "每周可到岗4天"
    profile = {"introduction": introduction, "availability": availability, "confirmed": True}
    assert client.post(path, json={"job_ids": [1], "profile": {**profile, "confirmed": False}}).status_code == 422
    default = client.post(path, json={"job_ids": [1]}).json()["items"][0]
    assert introduction not in default["text"] and availability not in default["text"]
    local = client.post(path, json={"job_ids": [1], "profile": profile}).json()["items"][0]
    assert local["text"].startswith(f"您好，{introduction}。")
    assert availability + "。方便" in local["text"] and "用户访谈" in local["text"]
    calls = []
    def draft(_config, selected_job, cards):
        calls.append((selected_job.id, cards))
        return SimpleNamespace(content='{"greeting_message":"您好！关注贵司产品实习中的用户访谈。方便交流吗？"}')
    monkeypatch.setattr(service.model_router, "route_for_agent", lambda *_: SimpleNamespace(mode="external"))
    monkeypatch.setattr(service.llm_client, "generate_job_greeting", draft)
    monkeypatch.setattr(client.app.state.evidence_service, "_record_llm_usage", lambda *_: None)
    model = client.post(path, json={"job_ids": [1], "profile": profile}).json()["items"][0]
    assert model["text"] == f"您好，{introduction}。关注贵司产品实习中的用户访谈。{availability}。方便交流吗？"
    assert calls == [(1, [])]


def test_send_skill_only_runs_through_reviewed_queue(tmp_path, monkeypatch):
    client, _ = setup_batch(tmp_path, monkeypatch)
    skills = {row["id"]: row for row in client.get("/api/skills").json()}
    sending = skills["application.greeting.send"]
    assert sending["executor"] == "local" and sending["risk_level"] == "high" and sending["requires_confirmation"]
    assert skills["job.preference"]["executor"] == "local"
    assert client.post("/api/skills/application.greeting.send/run").json()["status"] == "requires_confirmation"
    assert client.post("/api/skills/application.greeting.send/run", json={"confirmed": True}).status_code == 409
