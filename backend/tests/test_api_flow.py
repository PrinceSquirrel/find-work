import json
import sqlite3
from io import BytesIO

from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas import ExtractedJobCandidate, PlatformJobExtraction, PlatformSession, PlatformSessionsResponse
from app.services import browser_job_extractor_service
from app.services import job_application_service
from app.services import platform_session_service


def _one_page_pdf() -> bytes:
    from reportlab.pdfgen import canvas

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(72, 720, "template pdf")
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def _create_demo_application(client: TestClient) -> int:
    resume_text = (
        "赵六\n"
        "技能: Python, FastAPI, React, SQL, 数据分析\n"
        "项目: 求职 Agent 工作台，负责后端 API 和前端看板。"
    )
    upload_response = client.post(
        "/api/resumes",
        files={"file": ("resume.txt", resume_text.encode("utf-8"), "text/plain")},
    )
    resume_id = upload_response.json()["id"]

    search_response = client.post(
        "/api/search-runs",
        json={
            "resume_id": resume_id,
            "keywords": ["Python 实习"],
            "city": "上海",
            "platforms": ["boss"],
        },
    )
    assert search_response.status_code == 201

    jobs_response = client.get("/api/jobs")
    job_id = jobs_response.json()[0]["id"]
    apply_response = client.post(
        f"/api/jobs/{job_id}/apply-record",
        json={"note": "用户确认后投递"},
    )
    assert apply_response.status_code == 201
    return apply_response.json()["id"]


def test_full_resume_to_application_flow(tmp_path):
    app = create_app(db_path=tmp_path / "agent-business.sqlite3")
    client = TestClient(app)

    resume_text = (
        "李四\n"
        "教育经历: 浙江大学 计算机科学\n"
        "技能: Python, FastAPI, React, SQL, 数据分析\n"
        "项目: 多 Agent 求职助手，负责后端 API、前端看板和模型调用统计。"
    )

    upload_response = client.post(
        "/api/resumes",
        files={"file": ("resume.txt", resume_text.encode("utf-8"), "text/plain")},
    )
    assert upload_response.status_code == 201
    resume_id = upload_response.json()["id"]

    search_response = client.post(
        "/api/search-runs",
        json={
            "resume_id": resume_id,
            "keywords": ["Python 实习", "Agent 实习"],
            "city": "上海",
            "platforms": ["boss", "shixiseng"],
        },
    )
    assert search_response.status_code == 201
    assert search_response.json()["status"] == "completed"

    jobs_response = client.get("/api/jobs")
    assert jobs_response.status_code == 200
    jobs = jobs_response.json()
    assert len(jobs) >= 2
    assert {job["platform"] for job in jobs} == {"boss", "shixiseng"}
    assert all("match" in job for job in jobs)

    target_job_id = jobs[0]["id"]
    tailor_response = client.post(f"/api/jobs/{target_job_id}/tailor", json={"resume_id": resume_id})
    assert tailor_response.status_code == 201
    tailored = tailor_response.json()
    assert tailored["truth_check_passed"] is True
    assert tailored["greeting"]["message"]

    apply_response = client.post(
        f"/api/jobs/{target_job_id}/apply-record",
        json={"note": "用户确认后投递"},
    )
    assert apply_response.status_code == 201
    application_id = apply_response.json()["id"]

    status_response = client.patch(
        f"/api/applications/{application_id}/status",
        json={"status": "read", "note": "半自动同步：招聘方已读"},
    )
    assert status_response.status_code == 200
    assert status_response.json()["current_status"] == "read"

    analytics_response = client.get("/api/analytics/applications")
    assert analytics_response.status_code == 200
    analytics = analytics_response.json()
    assert analytics["totals"]["applications"] == 1
    assert analytics["totals"]["read_rate"] == 1.0
    assert "hourly" in analytics

    metrics_response = client.get("/api/metrics/llm-usage")
    assert metrics_response.status_code == 200
    assert metrics_response.json()["total_tokens"] > 0


def test_docx_resume_upload_preserves_original_template_bytes(tmp_path):
    from docx import Document

    document = Document()
    document.add_paragraph("张三")
    document.add_paragraph("项目经历")
    document.add_paragraph("求职 Agent 工作台，负责 Python 和 React。")
    buffer = BytesIO()
    document.save(buffer)
    content = buffer.getvalue()
    db_path = tmp_path / "agent-business.sqlite3"
    app = create_app(db_path=db_path)
    client = TestClient(app)

    response = client.post(
        "/api/resumes",
        files={"file": ("resume.docx", content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["file_type"] == "docx"
    assert payload["template_available"] is True
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT file_type, template_available, original_file_bytes FROM resumes WHERE id = ?",
            (payload["id"],),
        ).fetchone()
    assert row[0] == "docx"
    assert row[1] == 1
    assert row[2] == content


def test_status_endpoint_rejects_illegal_application_transition(tmp_path):
    app = create_app(db_path=tmp_path / "agent-business.sqlite3")
    client = TestClient(app)
    application_id = _create_demo_application(client)

    status_response = client.patch(
        f"/api/applications/{application_id}/status",
        json={"status": "replied", "note": "不能跳过已读直接回复"},
    )

    assert status_response.status_code == 409
    assert "Cannot transition application" in status_response.json()["detail"]

    applications_response = client.get("/api/applications")
    assert applications_response.status_code == 200
    assert applications_response.json()[0]["current_status"] == "applied"


def test_application_sync_returns_read_only_proposals_without_overwriting_status(tmp_path, monkeypatch):
    class FakeCdpResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return json.dumps(
                [
                    {
                        "type": "page",
                        "url": "https://www.zhipin.com/web/geek/chat?securityId=hidden",
                        "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/1",
                    }
                ]
            ).encode("utf-8")

    def fake_evaluate(self, websocket_url, expression):
        assert websocket_url == "ws://127.0.0.1:9222/devtools/page/1"
        assert "application-sync-readonly" in expression
        return {
            "items": [
                {
                    "text": "星河智能科技 Python 实习 招聘方已回复：方便约聊吗",
                    "url": "https://www.zhipin.com/web/geek/chat?securityId=hidden",
                }
            ],
            "diagnostics": {
                "candidate_item_count": 1,
                "matched_status_keywords": {"已回复": 1},
            },
        }

    monkeypatch.setenv("BROWSER_CDP_URL", "127.0.0.1:9222")
    monkeypatch.setattr(browser_job_extractor_service, "urlopen", lambda url, timeout: FakeCdpResponse())
    monkeypatch.setattr(browser_job_extractor_service.CdpRuntimeClient, "evaluate", fake_evaluate)
    app = create_app(db_path=tmp_path / "agent-business.sqlite3")
    client = TestClient(app)
    application_id = _create_demo_application(client)

    response = client.post("/api/applications/sync", json={"platforms": ["boss"], "limit": 20})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["mode"] == "browser_cdp_readonly"
    assert payload["updated"] == 0
    assert payload["proposals"][0]["application_id"] == application_id
    assert payload["proposals"][0]["detected_status"] == "replied"
    assert payload["proposals"][0]["suggested_status"] == "read"
    assert payload["proposals"][0]["requires_manual_confirmation"] is True
    assert "hidden" not in str(payload)

    applications_response = client.get("/api/applications")
    assert applications_response.json()[0]["current_status"] == "applied"


def test_application_sync_reports_missing_cdp_without_updating_status(tmp_path, monkeypatch):
    monkeypatch.delenv("BROWSER_CDP_URL", raising=False)
    app = create_app(db_path=tmp_path / "agent-business.sqlite3")
    client = TestClient(app)
    application_id = _create_demo_application(client)

    response = client.post("/api/applications/sync", json={"platforms": ["boss"]})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "not_configured"
    assert payload["updated"] == 0
    assert payload["proposals"] == []
    assert payload["diagnostics"][0]["failure_reason"] == "未配置 BROWSER_CDP_URL"
    assert client.get("/api/applications").json()[0]["id"] == application_id
    assert client.get("/api/applications").json()[0]["current_status"] == "applied"


def test_search_run_rejects_unknown_platforms(tmp_path):
    app = create_app(db_path=tmp_path / "agent-business.sqlite3")
    client = TestClient(app)

    upload_response = client.post(
        "/api/resumes",
        files={"file": ("resume.txt", "技能: Python, FastAPI".encode("utf-8"), "text/plain")},
    )
    resume_id = upload_response.json()["id"]

    response = client.post(
        "/api/search-runs",
        json={
            "resume_id": resume_id,
            "keywords": ["Python 实习"],
            "city": "上海",
            "platforms": ["boss", "unknown-platform"],
        },
    )

    assert response.status_code == 400
    assert "Unsupported platforms" in response.json()["detail"]


def test_browser_cdp_search_mode_requires_detected_platform_tab(tmp_path, monkeypatch):
    monkeypatch.delenv("BROWSER_CDP_URL", raising=False)
    app = create_app(db_path=tmp_path / "agent-business.sqlite3")
    client = TestClient(app)

    upload_response = client.post(
        "/api/resumes",
        files={"file": ("resume.txt", "技能: Python, FastAPI".encode("utf-8"), "text/plain")},
    )
    resume_id = upload_response.json()["id"]

    response = client.post(
        "/api/search-runs",
        json={
            "resume_id": resume_id,
            "keywords": ["Python 实习"],
            "city": "上海",
            "platforms": ["boss"],
            "search_mode": "browser_cdp",
        },
    )

    assert response.status_code == 400
    assert "browser_cdp search requires detected platform tabs" in response.json()["detail"]
    assert client.get("/api/jobs").json() == []
    agent_events = client.get("/api/agent-events").json()
    agents = {agent["agent_name"]: agent for agent in agent_events["agents"]}
    assert agents["JobSearchAgent"]["status"] == "failed"
    assert "browser_cdp search requires detected platform tabs" in agents["JobSearchAgent"]["error"]


def test_failed_orchestrator_task_detail_includes_manual_retry_boundary(tmp_path, monkeypatch):
    monkeypatch.delenv("BROWSER_CDP_URL", raising=False)
    app = create_app(db_path=tmp_path / "agent-business.sqlite3")
    client = TestClient(app)

    upload_response = client.post(
        "/api/resumes",
        files={"file": ("resume.txt", "技能: Python, FastAPI".encode("utf-8"), "text/plain")},
    )
    resume_id = upload_response.json()["id"]
    client.post(
        "/api/search-runs",
        json={
            "resume_id": resume_id,
            "keywords": ["Python 实习"],
            "city": "上海",
            "platforms": ["boss"],
            "search_mode": "browser_cdp",
        },
    )
    task_id = client.get("/api/agent-events").json()["orchestrator"]["last_task"]["id"]

    response = client.get(f"/api/orchestrator/tasks/{task_id}")

    assert response.status_code == 200
    retry_suggestion = response.json()["retry_suggestion"]
    assert retry_suggestion["mode"] == "manual_only"
    assert retry_suggestion["retryable"] is True
    assert "CDP" in retry_suggestion["next_action"]
    assert "不会自动投递" in retry_suggestion["safety_boundary"]


def test_browser_cdp_search_mode_saves_extracted_jobs_without_demo_fallback(tmp_path, monkeypatch):
    class FakePlatformSessionService:
        def inspect(self):
            return PlatformSessionsResponse(
                cdp_url="http://127.0.0.1:9222",
                browser_connected=True,
                sessions=[
                    PlatformSession(
                        platform="boss",
                        expected_hosts=["zhipin.com"],
                        state="tab_detected",
                        detected_url="https://www.zhipin.com/web/geek/job",
                        message="已检测到平台标签页",
                    )
                ],
            )

    class FakeBrowserJobExtractorService:
        def extract(self, platforms, limit):
            assert platforms == ["boss"]
            assert limit == 20
            return type(
                "ExtractionResponse",
                (),
                {
                    "extractions": [
                        PlatformJobExtraction(
                            platform="boss",
                            status="success",
                            source_url="https://www.zhipin.com/web/geek/job",
                            jobs=[
                                ExtractedJobCandidate(
                                    platform="boss",
                                    company="真实公司",
                                    title="Python 后端实习生",
                                    city="上海",
                                    salary="200-300/天",
                                    description="真实页面可见岗位内容，需要 Python、FastAPI、SQL。",
                                    url="https://www.zhipin.com/job_detail/abc.html",
                                    job_type="boss_browser",
                                    detail_status="detail_fetched",
                                    detail_reason="详情页已补全岗位要求。",
                                )
                            ],
                        )
                    ]
                },
            )()

    monkeypatch.setattr(job_application_service, "PlatformSessionService", FakePlatformSessionService)
    monkeypatch.setattr(job_application_service, "BrowserJobExtractorService", FakeBrowserJobExtractorService)
    app = create_app(db_path=tmp_path / "agent-business.sqlite3")
    client = TestClient(app)

    upload_response = client.post(
        "/api/resumes",
        files={"file": ("resume.txt", "技能: Python, FastAPI".encode("utf-8"), "text/plain")},
    )
    resume_id = upload_response.json()["id"]

    response = client.post(
        "/api/search-runs",
        json={
            "resume_id": resume_id,
            "keywords": ["Python 实习"],
            "city": "上海",
            "platforms": ["boss"],
            "search_mode": "browser_cdp",
        },
    )

    assert response.status_code == 201
    assert response.json()["status"] == "completed"
    jobs = client.get("/api/jobs").json()
    assert len(jobs) == 1
    assert jobs[0]["platform"] == "boss"
    assert jobs[0]["company"] == "真实公司"
    assert jobs[0]["url"] == "https://www.zhipin.com/job_detail/abc.html"
    assert jobs[0]["detail_status"] == "detail_fetched"
    assert jobs[0]["detail_reason"] == "详情页已补全岗位要求。"
    assert "match" in jobs[0]
    assert "example.test" not in str(jobs)


def test_browser_cdp_search_mode_controls_page_with_keywords_before_extracting(tmp_path, monkeypatch):
    class FakePlatformSessionService:
        def inspect(self):
            return PlatformSessionsResponse(
                cdp_url="http://127.0.0.1:9222",
                browser_connected=True,
                sessions=[
                    PlatformSession(
                        platform="boss",
                        expected_hosts=["zhipin.com"],
                        state="tab_detected",
                        detected_url="https://www.zhipin.com/web/geek/job",
                        message="已检测到平台标签页",
                    )
                ],
            )

    class FakeBrowserJobExtractorService:
        calls = []

        def search_and_extract(self, platforms, keywords, city, limit):
            self.__class__.calls.append(
                {
                    "platforms": platforms,
                    "keywords": keywords,
                    "city": city,
                    "limit": limit,
                }
            )
            return type(
                "ExtractionResponse",
                (),
                {
                    "extractions": [
                        PlatformJobExtraction(
                            platform="boss",
                            status="success",
                            source_url="https://www.zhipin.com/web/geek/job?query=Python",
                            jobs=[
                                ExtractedJobCandidate(
                                    platform="boss",
                                    company="搜索后公司",
                                    title="搜索后 Python 岗位",
                                    city="上海",
                                    salary="18-25K",
                                    description="搜索后真实岗位，需要 Python 和数据分析。",
                                    url="https://www.zhipin.com/job_detail/search.html",
                                    job_type="boss_browser",
                                )
                            ],
                        )
                    ]
                },
            )()

    monkeypatch.setattr(job_application_service, "PlatformSessionService", FakePlatformSessionService)
    monkeypatch.setattr(job_application_service, "BrowserJobExtractorService", FakeBrowserJobExtractorService)
    app = create_app(db_path=tmp_path / "agent-business.sqlite3")
    client = TestClient(app)
    upload_response = client.post(
        "/api/resumes",
        files={"file": ("resume.txt", "技能: Python, 数据分析".encode("utf-8"), "text/plain")},
    )
    resume_id = upload_response.json()["id"]

    response = client.post(
        "/api/search-runs",
        json={
            "resume_id": resume_id,
            "keywords": ["Python 实习", "数据分析"],
            "city": "上海",
            "platforms": ["boss"],
            "search_mode": "browser_cdp",
        },
    )

    assert response.status_code == 201
    assert FakeBrowserJobExtractorService.calls == [
        {
            "platforms": ["boss"],
            "keywords": ["Python 实习", "数据分析"],
            "city": "上海",
            "limit": 20,
        }
    ]
    jobs = client.get(f"/api/jobs?search_run_id={response.json()['id']}").json()
    assert jobs[0]["company"] == "搜索后公司"
    assert jobs[0]["salary"] == "18-25K"


def test_single_job_detail_can_be_refreshed_from_browser_cdp(tmp_path, monkeypatch):
    class FakePlatformSessionService:
        def inspect(self):
            return PlatformSessionsResponse(
                cdp_url="http://127.0.0.1:9222",
                browser_connected=True,
                sessions=[
                    PlatformSession(
                        platform="boss",
                        expected_hosts=["zhipin.com"],
                        state="tab_detected",
                        detected_url="https://www.zhipin.com/web/geek/jobs",
                        message="tab detected",
                    )
                ],
            )

    class FakeBrowserJobExtractorService:
        refreshed = []

        def search_and_extract(self, platforms, keywords, city, limit):
            return type(
                "ExtractionResponse",
                (),
                {
                    "extractions": [
                        PlatformJobExtraction(
                            platform="boss",
                            status="success",
                            source_url="https://www.zhipin.com/web/geek/jobs",
                            jobs=[
                                ExtractedJobCandidate(
                                    platform="boss",
                                    company="Real Company",
                                    title="AI Agent Intern",
                                    city="Shanghai",
                                    salary="薪资读取失败",
                                    description="card only",
                                    url="https://www.zhipin.com/job_detail/refresh.html",
                                    job_type="boss_browser",
                                    detail_status="card_only",
                                    detail_reason="Only card text was available.",
                                )
                            ],
                        )
                    ]
                },
            )()

        def refresh_job_detail(self, platform, url):
            self.__class__.refreshed.append({"platform": platform, "url": url})
            return ExtractedJobCandidate(
                platform=platform,
                company="Real Company",
                title="AI Agent Intern",
                city="Shanghai",
                salary="260-350/天",
                description="完整岗位要求：负责 Agent 工作台、FastAPI、React 和数据分析。",
                url=url,
                job_type="boss_browser",
                detail_status="detail_fetched",
                detail_reason="Detail page refreshed for this job.",
            )

    monkeypatch.setattr(job_application_service, "PlatformSessionService", FakePlatformSessionService)
    monkeypatch.setattr(job_application_service, "BrowserJobExtractorService", FakeBrowserJobExtractorService)
    app = create_app(db_path=tmp_path / "agent-business.sqlite3")
    client = TestClient(app)

    upload_response = client.post(
        "/api/resumes",
        files={"file": ("resume.txt", "Skills: Python, FastAPI, React".encode("utf-8"), "text/plain")},
    )
    resume_id = upload_response.json()["id"]
    run_response = client.post(
        "/api/search-runs",
        json={
            "resume_id": resume_id,
            "keywords": ["Agent Intern"],
            "city": "Shanghai",
            "platforms": ["boss"],
            "search_mode": "browser_cdp",
        },
    )
    job_id = client.get(f"/api/jobs?search_run_id={run_response.json()['id']}").json()[0]["id"]

    response = client.post(f"/api/jobs/{job_id}/refresh-detail")

    assert response.status_code == 200
    refreshed = response.json()
    assert refreshed["id"] == job_id
    assert refreshed["salary"] == "260-350/天"
    assert "完整岗位要求" in refreshed["description"]
    assert refreshed["detail_status"] == "detail_fetched"
    assert refreshed["detail_reason"] == "Detail page refreshed for this job."
    assert FakeBrowserJobExtractorService.refreshed == [
        {"platform": "boss", "url": "https://www.zhipin.com/job_detail/refresh.html"}
    ]
    persisted = client.get(f"/api/jobs?search_run_id={run_response.json()['id']}").json()[0]
    assert persisted["salary"] == "260-350/天"
    assert persisted["detail_status"] == "detail_fetched"


def test_jobs_can_be_filtered_to_the_current_search_run(tmp_path, monkeypatch):
    class FakePlatformSessionService:
        def inspect(self):
            return PlatformSessionsResponse(
                cdp_url="http://127.0.0.1:9222",
                browser_connected=True,
                sessions=[
                    PlatformSession(
                        platform="boss",
                        expected_hosts=["zhipin.com"],
                        state="tab_detected",
                        detected_url="https://www.zhipin.com/web/geek/job",
                        message="已检测到平台标签页",
                    )
                ],
            )

    class FakeBrowserJobExtractorService:
        def extract(self, platforms, limit):
            return type(
                "ExtractionResponse",
                (),
                {
                    "extractions": [
                        PlatformJobExtraction(
                            platform="boss",
                            status="success",
                            source_url="https://www.zhipin.com/web/geek/job",
                            jobs=[
                                ExtractedJobCandidate(
                                    platform="boss",
                                    company="真实公司",
                                    title="真实 Python 岗位",
                                    city="上海",
                                    salary="200-300/天",
                                    description="真实页面岗位，需要 Python。",
                                    url="https://www.zhipin.com/job_detail/real.html",
                                    job_type="boss_browser",
                                )
                            ],
                        )
                    ]
                },
            )()

    monkeypatch.setattr(job_application_service, "PlatformSessionService", FakePlatformSessionService)
    monkeypatch.setattr(job_application_service, "BrowserJobExtractorService", FakeBrowserJobExtractorService)
    app = create_app(db_path=tmp_path / "agent-business.sqlite3")
    client = TestClient(app)

    upload_response = client.post(
        "/api/resumes",
        files={"file": ("resume.txt", "技能: Python, FastAPI".encode("utf-8"), "text/plain")},
    )
    resume_id = upload_response.json()["id"]
    demo_run = client.post(
        "/api/search-runs",
        json={
            "resume_id": resume_id,
            "keywords": ["Demo 实习"],
            "city": "上海",
            "platforms": ["boss"],
            "search_mode": "demo",
        },
    ).json()
    browser_run = client.post(
        "/api/search-runs",
        json={
            "resume_id": resume_id,
            "keywords": ["Python 实习"],
            "city": "上海",
            "platforms": ["boss"],
            "search_mode": "browser_cdp",
        },
    ).json()

    all_jobs = client.get("/api/jobs").json()
    filtered_jobs = client.get(f"/api/jobs?search_run_id={browser_run['id']}").json()

    assert {job["search_run_id"] for job in all_jobs} == {demo_run["id"], browser_run["id"]}
    assert len(filtered_jobs) == 1
    assert filtered_jobs[0]["search_run_id"] == browser_run["id"]
    assert filtered_jobs[0]["company"] == "真实公司"


def test_browser_cdp_search_mode_reports_extraction_failure_without_demo_jobs(tmp_path, monkeypatch):
    class FakePlatformSessionService:
        def inspect(self):
            return PlatformSessionsResponse(
                cdp_url="http://127.0.0.1:9222",
                browser_connected=True,
                sessions=[
                    PlatformSession(
                        platform="boss",
                        expected_hosts=["zhipin.com"],
                        state="tab_detected",
                        detected_url="https://www.zhipin.com/web/geek/job",
                        message="已检测到平台标签页",
                    )
                ],
            )

    class FakeBrowserJobExtractorService:
        def extract(self, platforms, limit):
            return type(
                "ExtractionResponse",
                (),
                {
                    "extractions": [
                        PlatformJobExtraction(
                            platform="boss",
                            status="extract_failed",
                            source_url="https://www.zhipin.com/web/geek/job",
                            error="页面结构变化，未能提取岗位",
                        )
                    ]
                },
            )()

    monkeypatch.setattr(job_application_service, "PlatformSessionService", FakePlatformSessionService)
    monkeypatch.setattr(job_application_service, "BrowserJobExtractorService", FakeBrowserJobExtractorService)
    app = create_app(db_path=tmp_path / "agent-business.sqlite3")
    client = TestClient(app)

    upload_response = client.post(
        "/api/resumes",
        files={"file": ("resume.txt", "技能: Python, FastAPI".encode("utf-8"), "text/plain")},
    )
    resume_id = upload_response.json()["id"]

    response = client.post(
        "/api/search-runs",
        json={
            "resume_id": resume_id,
            "keywords": ["Python 实习"],
            "city": "上海",
            "platforms": ["boss"],
            "search_mode": "browser_cdp",
        },
    )

    assert response.status_code == 400
    assert "browser_cdp extraction failed" in response.json()["detail"]
    assert "页面结构变化" in response.json()["detail"]
    assert client.get("/api/jobs").json() == []
    agent_events = client.get("/api/agent-events").json()
    agents = {agent["agent_name"]: agent for agent in agent_events["agents"]}
    assert agents["JobSearchAgent"]["status"] == "failed"
    assert "browser_cdp extraction failed" in agents["JobSearchAgent"]["error"]


def test_model_config_can_be_saved_without_exposing_api_key(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_BUSINESS_TEST_API_KEY", "secret-value-that-must-not-leak")
    app = create_app(db_path=tmp_path / "agent-business.sqlite3")
    client = TestClient(app)

    update_response = client.put(
        "/api/model-config",
        json={
            "provider": "openai-compatible",
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com/v1",
            "api_key_env_var": "AGENT_BUSINESS_TEST_API_KEY",
            "enabled": True,
            "estimation_only": False,
            "timeout_ms": 45000,
            "input_price_per_million": 1.0,
            "output_price_per_million": 2.0,
        },
    )

    assert update_response.status_code == 200
    saved = update_response.json()
    assert saved["provider"] == "openai-compatible"
    assert saved["model"] == "deepseek-chat"
    assert saved["api_key_env_var"] == "AGENT_BUSINESS_TEST_API_KEY"
    assert saved["api_key_configured"] is True
    assert "secret-value-that-must-not-leak" not in str(saved)

    get_response = client.get("/api/model-config")

    assert get_response.status_code == 200
    persisted = get_response.json()
    assert persisted["model"] == "deepseek-chat"
    assert persisted["api_key_configured"] is True
    assert "secret-value-that-must-not-leak" not in str(persisted)


def test_tailor_uses_enabled_openai_compatible_model_and_records_usage(tmp_path, monkeypatch):
    class FakeLlmResult:
        content = json.dumps(
            {
                "resume_text": "LLM 定制简历：保留 Python、FastAPI、React 项目经历。",
                "greeting_message": "LLM 招呼语：您好，我想投递这个后端实习岗位。",
                "diff_summary": ["突出 FastAPI 项目"],
                "resume_risk_flags": [],
                "greeting_risk_flags": [],
                "tone": "professional",
            },
            ensure_ascii=False,
        )
        provider = "openai-compatible"
        model = "deepseek-chat"
        prompt_tokens = 120
        completion_tokens = 60
        duration_ms = 88
        estimated = False

    class FakeOpenAICompatibleClient:
        def generate_application_materials(self, config, resume, job):
            assert config.enabled is True
            assert config.estimation_only is False
            assert config.model == "deepseek-chat"
            return FakeLlmResult()

    monkeypatch.setenv("AGENT_BUSINESS_TEST_API_KEY", "secret-value-that-must-not-leak")
    monkeypatch.setattr(job_application_service, "OpenAICompatibleClient", FakeOpenAICompatibleClient, raising=False)
    db_path = tmp_path / "agent-business.sqlite3"
    app = create_app(db_path=db_path)
    client = TestClient(app)
    client.put(
        "/api/model-config",
        json={
            "provider": "openai-compatible",
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com/v1",
            "api_key_env_var": "AGENT_BUSINESS_TEST_API_KEY",
            "enabled": True,
            "estimation_only": False,
            "timeout_ms": 45000,
            "input_price_per_million": 1.0,
            "output_price_per_million": 2.0,
        },
    )

    upload_response = client.post(
        "/api/resumes",
        files={"file": ("resume.txt", "技能: Python, FastAPI, React".encode("utf-8"), "text/plain")},
    )
    resume_id = upload_response.json()["id"]
    client.post(
        "/api/search-runs",
        json={
            "resume_id": resume_id,
            "keywords": ["Python 实习"],
            "city": "上海",
            "platforms": ["boss"],
        },
    )
    job_id = client.get("/api/jobs").json()[0]["id"]

    tailor_response = client.post(f"/api/jobs/{job_id}/tailor", json={"resume_id": resume_id})

    assert tailor_response.status_code == 201
    payload = tailor_response.json()
    assert "LLM 定制简历" in payload["resume_text"]
    assert "LLM 招呼语" in payload["greeting"]["message"]
    assert payload["review"]["llm"]["status"] == "success"
    assert "secret-value-that-must-not-leak" not in str(payload)
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT provider, model, prompt_tokens, completion_tokens, estimated, cost_usd "
            "FROM llm_usage WHERE agent_name = 'ApplicationWriterAgent' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row == ("openai-compatible", "deepseek-chat", 120, 60, 0, 0.00024)


def test_tailored_resume_pdf_can_be_downloaded_after_material_generation(tmp_path, monkeypatch):
    class FakeTailoredResumePdfService:
        def render(self, tailored_bundle, template_bytes):
            assert template_bytes.startswith(b"PK")
            assert tailored_bundle["project_rewrite"]
            return _one_page_pdf()

    import app.main as main_module

    monkeypatch.setattr(main_module, "TailoredResumePdfService", FakeTailoredResumePdfService)
    from docx import Document

    document = Document()
    document.add_paragraph("胡俊")
    document.add_paragraph("项目经历")
    document.add_paragraph("旧项目描述")
    buffer = BytesIO()
    document.save(buffer)
    app = create_app(db_path=tmp_path / "agent-business.sqlite3")
    client = TestClient(app)
    upload_response = client.post(
        "/api/resumes",
        files={
            "file": (
                "resume.docx",
                buffer.getvalue(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    resume_id = upload_response.json()["id"]
    client.post(
        "/api/search-runs",
        json={
            "resume_id": resume_id,
            "keywords": ["Python 实习"],
            "city": "上海",
            "platforms": ["boss"],
        },
    )
    job_id = client.get("/api/jobs").json()[0]["id"]
    tailor_response = client.post(f"/api/jobs/{job_id}/tailor", json={"resume_id": resume_id})
    tailored_id = tailor_response.json()["id"]

    pdf_response = client.get(f"/api/tailored-resumes/{tailored_id}/pdf")

    assert pdf_response.status_code == 200
    assert pdf_response.headers["content-type"] == "application/pdf"
    assert pdf_response.content.startswith(b"%PDF")
    assert str(tailored_id) in pdf_response.headers["content-disposition"]
    assert client.get("/api/tailored-resumes/999999/pdf").status_code == 404


def test_tailored_resume_pdf_requires_docx_template(tmp_path):
    app = create_app(db_path=tmp_path / "agent-business.sqlite3")
    client = TestClient(app)
    upload_response = client.post(
        "/api/resumes",
        files={"file": ("resume.txt", "技能: Python, FastAPI, React".encode("utf-8"), "text/plain")},
    )
    resume_id = upload_response.json()["id"]
    client.post(
        "/api/search-runs",
        json={
            "resume_id": resume_id,
            "keywords": ["Python 实习"],
            "city": "上海",
            "platforms": ["boss"],
        },
    )
    job_id = client.get("/api/jobs").json()[0]["id"]
    tailor_response = client.post(f"/api/jobs/{job_id}/tailor", json={"resume_id": resume_id})
    tailored_id = tailor_response.json()["id"]

    pdf_response = client.get(f"/api/tailored-resumes/{tailored_id}/pdf")

    assert pdf_response.status_code == 409
    assert "重新上传 DOCX" in pdf_response.json()["detail"]


def test_tailor_routes_application_writer_through_model_router(tmp_path, monkeypatch):
    from app.services.model_router_service import ModelRoute

    class FakeLlmResult:
        content = json.dumps(
            {
                "resume_text": "Router LLM resume keeps Python and FastAPI.",
                "greeting_message": "Router LLM greeting.",
                "diff_summary": [],
                "resume_risk_flags": [],
                "greeting_risk_flags": [],
                "tone": "professional",
            },
        )
        provider = "openai-compatible"
        model = "deepseek-chat"
        prompt_tokens = 30
        completion_tokens = 12
        duration_ms = 40
        estimated = False

    class FakeModelRouterService:
        requested_agents = []

        def route_for_agent(self, agent_name, config):
            self.requested_agents.append(agent_name)
            if agent_name == "ApplicationWriterAgent":
                return ModelRoute(
                    agent_name=agent_name,
                    mode="external",
                    provider=config.provider,
                    model=config.model,
                    reason="application writing uses configured external model",
                )
            return ModelRoute(
                agent_name=agent_name,
                mode="local_rule",
                provider="local",
                model="local-rule",
                reason="review stays local in 4C",
            )

    class FakeOpenAICompatibleClient:
        def generate_application_materials(self, config, resume, job):
            return FakeLlmResult()

    monkeypatch.setenv("AGENT_BUSINESS_TEST_API_KEY", "secret-value-that-must-not-leak")
    monkeypatch.setattr(job_application_service, "ModelRouterService", FakeModelRouterService, raising=False)
    monkeypatch.setattr(job_application_service, "OpenAICompatibleClient", FakeOpenAICompatibleClient, raising=False)
    app = create_app(db_path=tmp_path / "agent-business.sqlite3")
    client = TestClient(app)
    client.put(
        "/api/model-config",
        json={
            "provider": "openai-compatible",
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com/v1",
            "api_key_env_var": "AGENT_BUSINESS_TEST_API_KEY",
            "enabled": True,
            "estimation_only": False,
            "timeout_ms": 45000,
            "input_price_per_million": 1.0,
            "output_price_per_million": 2.0,
        },
    )
    upload_response = client.post(
        "/api/resumes",
        files={"file": ("resume.txt", "Skills: Python, FastAPI, React".encode("utf-8"), "text/plain")},
    )
    resume_id = upload_response.json()["id"]
    client.post(
        "/api/search-runs",
        json={
            "resume_id": resume_id,
            "keywords": ["Python intern"],
            "city": "Shanghai",
            "platforms": ["boss"],
        },
    )
    job_id = client.get("/api/jobs").json()[0]["id"]

    response = client.post(f"/api/jobs/{job_id}/tailor", json={"resume_id": resume_id})

    assert response.status_code == 201
    payload = response.json()
    assert payload["review"]["llm"]["route"]["mode"] == "external"
    assert payload["review"]["llm"]["review_route"]["mode"] == "local_rule"
    assert FakeModelRouterService.requested_agents == ["ApplicationWriterAgent", "ReviewAgent"]


def test_agent_events_endpoint_reports_real_backend_steps(tmp_path):
    app = create_app(db_path=tmp_path / "agent-business.sqlite3")
    client = TestClient(app)

    upload_response = client.post(
        "/api/resumes",
        files={"file": ("resume.txt", "Skills: Python, FastAPI, React".encode("utf-8"), "text/plain")},
    )
    resume_id = upload_response.json()["id"]
    client.post(
        "/api/search-runs",
        json={
            "resume_id": resume_id,
            "keywords": ["Python intern"],
            "city": "Shanghai",
            "platforms": ["boss"],
        },
    )
    job_id = client.get("/api/jobs").json()[0]["id"]
    client.post(f"/api/jobs/{job_id}/tailor", json={"resume_id": resume_id})

    response = client.get("/api/agent-events")

    assert response.status_code == 200
    payload = response.json()
    agents = {agent["agent_name"]: agent for agent in payload["agents"]}
    assert payload["current_running_agent"] is None
    assert agents["ResumeParserAgent"]["status"] == "success"
    assert agents["JobSearchAgent"]["status"] == "success"
    assert agents["JobMatchAgent"]["status"] == "success"
    assert agents["ApplicationWriterAgent"]["status"] == "success"
    assert agents["ReviewAgent"]["status"] == "success"
    assert agents["ApplicationWriterAgent"]["input_summary"]
    assert agents["ReviewAgent"]["output_summary"]
    assert payload["total_cost_usd"] >= 0
    orchestrator = payload["orchestrator"]
    assert orchestrator["current_task_id"] is None
    assert orchestrator["last_task"]["task_name"] == "application.materials"
    assert orchestrator["last_task"]["status"] == "success"
    assert [
        f"{step['agent_name']}:{step['status']}"
        for step in orchestrator["last_task"]["steps"]
    ] == [
        "ApplicationWriterAgent:running",
        "ApplicationWriterAgent:success",
        "ReviewAgent:running",
        "ReviewAgent:success",
    ]


def test_orchestrator_task_summary_survives_service_restart(tmp_path):
    db_path = tmp_path / "agent-business.sqlite3"
    app = create_app(db_path=db_path)
    client = TestClient(app)

    upload_response = client.post(
        "/api/resumes",
        files={"file": ("resume.txt", "Skills: Python, FastAPI, React".encode("utf-8"), "text/plain")},
    )
    resume_id = upload_response.json()["id"]
    client.post(
        "/api/search-runs",
        json={
            "resume_id": resume_id,
            "keywords": ["Python intern"],
            "city": "Shanghai",
            "platforms": ["boss"],
        },
    )
    job_id = client.get("/api/jobs").json()[0]["id"]
    client.post(f"/api/jobs/{job_id}/tailor", json={"resume_id": resume_id})

    restarted_app = create_app(db_path=db_path)
    restarted_client = TestClient(restarted_app)
    response = restarted_client.get("/api/agent-events")

    assert response.status_code == 200
    orchestrator = response.json()["orchestrator"]
    assert orchestrator["current_task_id"] is None
    assert orchestrator["last_task"]["task_name"] == "application.materials"
    assert orchestrator["last_task"]["status"] == "success"
    assert [step["agent_name"] for step in orchestrator["last_task"]["steps"]] == [
        "ApplicationWriterAgent",
        "ApplicationWriterAgent",
        "ReviewAgent",
        "ReviewAgent",
    ]


def test_orchestrator_task_detail_endpoint_returns_steps(tmp_path):
    db_path = tmp_path / "agent-business.sqlite3"
    app = create_app(db_path=db_path)
    client = TestClient(app)

    upload_response = client.post(
        "/api/resumes",
        files={"file": ("resume.txt", "Skills: Python, FastAPI, React".encode("utf-8"), "text/plain")},
    )
    resume_id = upload_response.json()["id"]
    client.post(
        "/api/search-runs",
        json={
            "resume_id": resume_id,
            "keywords": ["Python intern"],
            "city": "Shanghai",
            "platforms": ["boss"],
        },
    )
    job_id = client.get("/api/jobs").json()[0]["id"]
    client.post(f"/api/jobs/{job_id}/tailor", json={"resume_id": resume_id})
    task_id = client.get("/api/agent-events").json()["orchestrator"]["last_task"]["id"]

    response = client.get(f"/api/orchestrator/tasks/{task_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == task_id
    assert payload["task_name"] == "application.materials"
    assert payload["status"] == "success"
    assert [step["agent_name"] for step in payload["steps"]] == [
        "ApplicationWriterAgent",
        "ApplicationWriterAgent",
        "ReviewAgent",
        "ReviewAgent",
    ]

    missing_response = client.get("/api/orchestrator/tasks/999999")
    assert missing_response.status_code == 404


def test_tailor_falls_back_locally_when_openai_compatible_model_fails(tmp_path, monkeypatch):
    class FakeOpenAICompatibleClient:
        def generate_application_materials(self, config, resume, job):
            raise RuntimeError("upstream timeout")

    monkeypatch.setenv("AGENT_BUSINESS_TEST_API_KEY", "secret-value-that-must-not-leak")
    monkeypatch.setattr(job_application_service, "OpenAICompatibleClient", FakeOpenAICompatibleClient, raising=False)
    db_path = tmp_path / "agent-business.sqlite3"
    app = create_app(db_path=db_path)
    client = TestClient(app)
    client.put(
        "/api/model-config",
        json={
            "provider": "openai-compatible",
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com/v1",
            "api_key_env_var": "AGENT_BUSINESS_TEST_API_KEY",
            "enabled": True,
            "estimation_only": False,
            "timeout_ms": 45000,
            "input_price_per_million": 1.0,
            "output_price_per_million": 2.0,
        },
    )

    upload_response = client.post(
        "/api/resumes",
        files={"file": ("resume.txt", "技能: Python, FastAPI, React".encode("utf-8"), "text/plain")},
    )
    resume_id = upload_response.json()["id"]
    client.post(
        "/api/search-runs",
        json={
            "resume_id": resume_id,
            "keywords": ["Python 实习"],
            "city": "上海",
            "platforms": ["boss"],
        },
    )
    job_id = client.get("/api/jobs").json()[0]["id"]

    tailor_response = client.post(f"/api/jobs/{job_id}/tailor", json={"resume_id": resume_id})

    assert tailor_response.status_code == 201
    payload = tailor_response.json()
    assert payload["greeting"]["message"]
    assert payload["review"]["llm"]["status"] == "fallback"
    assert "upstream timeout" in payload["review"]["llm"]["error"]
    assert "secret-value-that-must-not-leak" not in str(payload)
    agent_events = client.get("/api/agent-events").json()
    agents = {agent["agent_name"]: agent for agent in agent_events["agents"]}
    assert agents["ApplicationWriterAgent"]["status"] == "failed"
    assert "upstream timeout" in agents["ApplicationWriterAgent"]["error"]
    usage = client.get("/api/metrics/llm-usage").json()
    writer_bucket = usage["by_agent"]["ApplicationWriterAgent"]
    assert writer_bucket["failed_calls"] == 1
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT status, error, total_tokens FROM llm_usage "
            "WHERE agent_name = 'ApplicationWriterAgent' AND status = 'failed' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
    assert row[0] == "failed"
    assert "upstream timeout" in row[1]
    assert row[2] == 0


def test_llm_usage_summary_exposes_status_buckets_for_estimated_and_success_calls(tmp_path, monkeypatch):
    class FakeLlmResult:
        content = json.dumps(
            {
                "resume_text": "LLM 定制简历：保留 Python、FastAPI 项目。",
                "greeting_message": "LLM 招呼语：您好。",
                "diff_summary": [],
                "resume_risk_flags": [],
                "greeting_risk_flags": [],
                "tone": "professional",
            },
            ensure_ascii=False,
        )
        provider = "openai-compatible"
        model = "deepseek-chat"
        prompt_tokens = 10
        completion_tokens = 5
        duration_ms = 25
        estimated = False

    class FakeOpenAICompatibleClient:
        def generate_application_materials(self, config, resume, job):
            return FakeLlmResult()

    monkeypatch.setenv("AGENT_BUSINESS_TEST_API_KEY", "secret-value-that-must-not-leak")
    monkeypatch.setattr(job_application_service, "OpenAICompatibleClient", FakeOpenAICompatibleClient, raising=False)
    app = create_app(db_path=tmp_path / "agent-business.sqlite3")
    client = TestClient(app)
    client.put(
        "/api/model-config",
        json={
            "provider": "openai-compatible",
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com/v1",
            "api_key_env_var": "AGENT_BUSINESS_TEST_API_KEY",
            "enabled": True,
            "estimation_only": False,
            "timeout_ms": 45000,
            "input_price_per_million": 1.0,
            "output_price_per_million": 2.0,
        },
    )
    upload_response = client.post(
        "/api/resumes",
        files={"file": ("resume.txt", "技能: Python, FastAPI, React".encode("utf-8"), "text/plain")},
    )
    resume_id = upload_response.json()["id"]
    client.post(
        "/api/search-runs",
        json={
            "resume_id": resume_id,
            "keywords": ["Python 实习"],
            "city": "上海",
            "platforms": ["boss"],
        },
    )
    job_id = client.get("/api/jobs").json()[0]["id"]
    client.post(f"/api/jobs/{job_id}/tailor", json={"resume_id": resume_id})

    usage = client.get("/api/metrics/llm-usage").json()

    assert usage["by_agent"]["ApplicationWriterAgent"]["success_calls"] == 1
    assert usage["by_agent"]["ResumeParserAgent"]["estimated_calls"] == 1


def test_platform_sessions_report_missing_cdp_configuration(tmp_path, monkeypatch):
    monkeypatch.delenv("BROWSER_CDP_URL", raising=False)
    app = create_app(db_path=tmp_path / "agent-business.sqlite3")
    client = TestClient(app)

    response = client.get("/api/platform-sessions")

    assert response.status_code == 200
    payload = response.json()
    assert payload["browser_connected"] is False
    assert payload["cdp_url"] is None
    assert {session["state"] for session in payload["sessions"]} == {"not_configured"}


def test_platform_sessions_detect_open_recruitment_tabs(tmp_path, monkeypatch):
    class FakeCdpResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return json.dumps(
                [
                    {
                        "type": "page",
                        "url": "https://www.zhipin.com/web/geek/job?query=Python&token=hidden",
                    },
                    {
                        "type": "page",
                        "url": "https://example.com/",
                    },
                ]
            ).encode("utf-8")

    def fake_urlopen(url, timeout):
        assert url == "http://127.0.0.1:9222/json"
        assert timeout == 2
        return FakeCdpResponse()

    monkeypatch.setenv("BROWSER_CDP_URL", "127.0.0.1:9222")
    monkeypatch.setattr(platform_session_service, "urlopen", fake_urlopen)
    app = create_app(db_path=tmp_path / "agent-business.sqlite3")
    client = TestClient(app)

    response = client.get("/api/platform-sessions")

    assert response.status_code == 200
    payload = response.json()
    sessions = {session["platform"]: session for session in payload["sessions"]}
    assert payload["browser_connected"] is True
    assert sessions["boss"]["state"] == "tab_detected"
    assert sessions["boss"]["detected_url"] == "https://www.zhipin.com/web/geek/job"
    assert sessions["boss"]["authenticated"] is None
    assert sessions["shixiseng"]["state"] == "tab_not_found"
    assert "token=hidden" not in str(payload)


def test_platform_job_extraction_reads_visible_jobs_from_detected_browser_tab(tmp_path, monkeypatch):
    class FakeCdpResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return json.dumps(
                [
                    {
                        "type": "page",
                        "url": "https://www.zhipin.com/web/geek/job?query=Python&token=hidden",
                        "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/1",
                    }
                ]
            ).encode("utf-8")

    def fake_urlopen(url, timeout):
        assert url == "http://127.0.0.1:9222/json"
        assert timeout == 2
        return FakeCdpResponse()

    def fake_evaluate(self, websocket_url, expression):
        assert websocket_url == "ws://127.0.0.1:9222/devtools/page/1"
        assert "document.querySelectorAll" in expression
        return {
            "jobs": [
                {
                    "title": "Python 后端实习生",
                    "company": "真实公司",
                    "city": "上海",
                    "salary": "200-300/天",
                    "description": "真实页面可见岗位内容",
                    "url": "https://www.zhipin.com/job_detail/abc.html?securityId=hidden",
                    "job_type": "backend",
                }
            ],
            "diagnostics": {
                "matched_selector_counts": {".job-card-wrapper": 1},
                "candidate_card_count": 1,
            },
        }

    monkeypatch.setenv("BROWSER_CDP_URL", "127.0.0.1:9222")
    monkeypatch.setattr(browser_job_extractor_service, "urlopen", fake_urlopen)
    monkeypatch.setattr(browser_job_extractor_service.CdpRuntimeClient, "evaluate", fake_evaluate)
    app = create_app(db_path=tmp_path / "agent-business.sqlite3")
    client = TestClient(app)

    response = client.post("/api/platform-jobs/extract", json={"platforms": ["boss"], "limit": 5})

    assert response.status_code == 200
    payload = response.json()
    extraction = payload["extractions"][0]
    assert extraction["platform"] == "boss"
    assert extraction["status"] == "success"
    assert extraction["source_url"] == "https://www.zhipin.com/web/geek/job"
    assert extraction["jobs"][0]["company"] == "真实公司"
    assert extraction["jobs"][0]["url"] == "https://www.zhipin.com/job_detail/abc.html"
    assert extraction["diagnostics"]["tab_detected"] is True
    assert extraction["diagnostics"]["websocket_detected"] is True
    assert extraction["diagnostics"]["candidate_card_count"] == 1
    assert extraction["diagnostics"]["extracted_job_count"] == 1
    assert extraction["diagnostics"]["matched_selector_counts"][".job-card-wrapper"] == 1
    assert "hidden" not in str(payload)


def test_platform_job_search_controls_page_before_extracting(tmp_path, monkeypatch):
    class FakeCdpResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return json.dumps(
                [
                    {
                        "type": "page",
                        "url": "https://www.zhipin.com/web/geek/job",
                        "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/1",
                    }
                ]
            ).encode("utf-8")

    expressions = []

    def fake_urlopen(url, timeout=2):
        return FakeCdpResponse()

    def fake_evaluate(self, websocket_url, expression):
        expressions.append(expression)
        if "searchUrl" in expression:
            return {"clicked": True, "keyword": "Python 实习", "city": "上海"}
        return {
            "jobs": [
                {
                    "title": "杭州 Python 岗位",
                    "company": "错误城市公司",
                    "city": "杭州",
                    "salary": "18-25K",
                    "description": "错误城市岗位，不应进入上海搜索结果。",
                    "url": "https://www.zhipin.com/job_detail/hangzhou.html",
                    "job_type": "boss_browser",
                },
                {
                    "title": "Python 搜索岗位",
                    "company": "搜索公司",
                    "city": "上海",
                    "salary": "18-25K",
                    "description": "搜索后的真实岗位，需要 Python。",
                    "url": "https://www.zhipin.com/job_detail/search.html",
                    "job_type": "boss_browser",
                }
            ],
            "diagnostics": {"candidate_card_count": 1},
        }

    monkeypatch.setenv("BROWSER_CDP_URL", "127.0.0.1:9222")
    monkeypatch.setattr(browser_job_extractor_service, "urlopen", fake_urlopen)
    monkeypatch.setattr(browser_job_extractor_service, "sleep", lambda seconds: None)
    monkeypatch.setattr(browser_job_extractor_service.CdpRuntimeClient, "evaluate", fake_evaluate)
    app = create_app(db_path=tmp_path / "agent-business.sqlite3")
    client = TestClient(app)

    response = client.post(
        "/api/platform-jobs/search",
        json={"platforms": ["boss"], "keywords": ["Python 实习"], "city": "上海", "limit": 5},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(expressions) == 2
    assert "Python 实习" in expressions[0]
    assert "上海" in expressions[0]
    assert "101020100" in expressions[0]
    assert "document.querySelectorAll" in expressions[1]
    assert len(payload["extractions"][0]["jobs"]) == 1
    assert payload["extractions"][0]["jobs"][0]["title"] == "Python 搜索岗位"
    assert payload["extractions"][0]["jobs"][0]["salary"] == "18-25K"


def test_platform_job_extraction_flags_polluted_text_and_hides_untrusted_fields(tmp_path, monkeypatch):
    class FakeCdpResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return json.dumps(
                [
                    {
                        "type": "page",
                        "url": "https://www.zhipin.com/web/geek/job?query=Python",
                        "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/1",
                    }
                ]
            ).encode("utf-8")

    def fake_evaluate(self, websocket_url, expression):
        return {
            "jobs": [
                {
                    "title": "Python 后端实习生",
                    "company": "真实公司",
                    "city": "上海",
                    "salary": "□□K·□□薪",
                    "description": "真实页面可见岗位内容，需要 Python。",
                    "url": "https://www.zhipin.com/job_detail/abc.html",
                    "job_type": "boss_browser",
                },
                {
                    "title": "□□□",
                    "company": "□□",
                    "city": "□□",
                    "salary": "□□",
                    "description": "□□□",
                    "url": "https://www.zhipin.com/job_detail/bad.html",
                    "job_type": "boss_browser",
                },
                {
                    "title": "□□□□开发□□",
                    "company": "可读公司",
                    "city": "上海",
                    "salary": "薪资面议",
                    "description": "描述可读但标题污染，不应进入岗位池。",
                    "url": "https://www.zhipin.com/job_detail/partial-bad.html",
                    "job_type": "boss_browser",
                },
            ],
            "diagnostics": {
                "matched_selector_counts": {".job-card-wrapper": 2},
                "candidate_card_count": 2,
            },
        }

    monkeypatch.setenv("BROWSER_CDP_URL", "127.0.0.1:9222")
    monkeypatch.setattr(browser_job_extractor_service, "urlopen", lambda url, timeout: FakeCdpResponse())
    monkeypatch.setattr(browser_job_extractor_service.CdpRuntimeClient, "evaluate", fake_evaluate)
    app = create_app(db_path=tmp_path / "agent-business.sqlite3")
    client = TestClient(app)

    response = client.post("/api/platform-jobs/extract", json={"platforms": ["boss"], "limit": 5})

    assert response.status_code == 200
    extraction = response.json()["extractions"][0]
    assert extraction["status"] == "success"
    assert len(extraction["jobs"]) == 1
    assert extraction["jobs"][0]["title"] == "Python 后端实习生"
    assert extraction["jobs"][0]["salary"] == "薪资读取失败"
    assert extraction["diagnostics"]["extracted_job_count"] == 1
    assert extraction["diagnostics"]["text_quality_warnings"]
    assert "dropped polluted job" in " ".join(extraction["diagnostics"]["text_quality_warnings"])


def test_platform_job_extraction_prefers_valid_salary_candidates_over_polluted_salary(tmp_path, monkeypatch):
    class FakeCdpResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return json.dumps(
                [
                    {
                        "type": "page",
                        "url": "https://www.zhipin.com/web/geek/job?query=Python",
                        "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/1",
                    }
                ]
            ).encode("utf-8")

    def fake_evaluate(self, websocket_url, expression):
        assert "salary_candidates" in expression
        return {
            "jobs": [
                {
                    "title": "算法工程师",
                    "company": "真实公司",
                    "city": "杭州",
                    "salary": "□□K·□□薪",
                    "salary_candidates": ["□□K·□□薪", "算法工程师 杭州 15-25K·14薪 经验不限"],
                    "description": "岗位卡片可见内容，需要 Python。",
                    "url": "https://www.zhipin.com/job_detail/real.html",
                    "job_type": "boss_browser",
                },
                {
                    "title": "数据分析实习生",
                    "company": "另一家公司",
                    "city": "上海",
                    "salary": "",
                    "salary_candidates": ["数据分析实习生 上海 经验不限"],
                    "description": "岗位卡片没有展示薪资。",
                    "url": "https://www.zhipin.com/job_detail/no-salary.html",
                    "job_type": "boss_browser",
                },
            ],
            "diagnostics": {
                "matched_selector_counts": {".job-card-wrapper": 2},
                "candidate_card_count": 2,
            },
        }

    monkeypatch.setenv("BROWSER_CDP_URL", "127.0.0.1:9222")
    monkeypatch.setattr(browser_job_extractor_service, "urlopen", lambda url, timeout: FakeCdpResponse())
    monkeypatch.setattr(browser_job_extractor_service.CdpRuntimeClient, "evaluate", fake_evaluate)
    app = create_app(db_path=tmp_path / "agent-business.sqlite3")
    client = TestClient(app)

    response = client.post("/api/platform-jobs/extract", json={"platforms": ["boss"], "limit": 5})

    assert response.status_code == 200
    jobs = response.json()["extractions"][0]["jobs"]
    assert jobs[0]["salary"] == "15-25K·14薪"
    assert jobs[1]["salary"] == "薪资读取失败"
    warnings = response.json()["extractions"][0]["diagnostics"]["text_quality_warnings"]
    assert not any("hid polluted salary" in warning for warning in warnings)


def test_platform_job_extraction_prefers_detail_page_requirements_and_salary(tmp_path, monkeypatch):
    class FakeCdpResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return json.dumps(
                [
                    {
                        "type": "page",
                        "url": "https://www.zhipin.com/web/geek/job?query=Agent",
                        "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/1",
                    }
                ]
            ).encode("utf-8")

    def fake_evaluate(self, websocket_url, expression):
        assert "detail_salary_candidates" in expression
        return {
            "jobs": [
                {
                    "title": "AI Agent优化工程师实习",
                    "company": "真实公司",
                    "city": "上海",
                    "salary": "薪资读取失败",
                    "description": "AI Agent优化工程师实习 - 元/天 4天/周 硕士 上海",
                    "detail_description": (
                        "职位描述 岗位职责：负责 Agent 工具链评测、提示词优化和数据分析。"
                        "任职要求：熟悉 Python、SQL、React，了解大模型调用和实验记录。"
                    ),
                    "detail_salary_candidates": ["250-350元/天", "4天/周"],
                    "url": "https://www.zhipin.com/job_detail/agent.html",
                    "job_type": "boss_browser",
                }
            ],
            "diagnostics": {
                "matched_selector_counts": {".job-card-wrapper": 1},
                "candidate_card_count": 1,
            },
        }

    monkeypatch.setenv("BROWSER_CDP_URL", "127.0.0.1:9222")
    monkeypatch.setattr(browser_job_extractor_service, "urlopen", lambda url, timeout: FakeCdpResponse())
    monkeypatch.setattr(browser_job_extractor_service.CdpRuntimeClient, "evaluate", fake_evaluate)
    app = create_app(db_path=tmp_path / "agent-business.sqlite3")
    client = TestClient(app)

    response = client.post("/api/platform-jobs/extract", json={"platforms": ["boss"], "limit": 5})

    assert response.status_code == 200
    job = response.json()["extractions"][0]["jobs"][0]
    assert job["salary"] == "250-350元/天"
    assert job["detail_status"] == "detail_fetched"
    assert job["detail_reason"] == "详情页已补全岗位要求。"
    assert "岗位职责" in job["description"]
    assert "提示词优化" in job["description"]
    assert "AI Agent优化工程师实习 - 元/天" not in job["description"]


def test_platform_job_extraction_script_contains_resilient_selectors(tmp_path, monkeypatch):
    class FakeCdpResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return json.dumps(
                [
                    {
                        "type": "page",
                        "url": "https://www.zhipin.com/web/geek/job?query=Python",
                        "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/1",
                    }
                ]
            ).encode("utf-8")

    def fake_evaluate(self, websocket_url, expression):
        assert websocket_url == "ws://127.0.0.1:9222/devtools/page/1"
        assert "fallback_links" in expression
        assert "[data-jobid]" in expression
        assert "[data-job-id]" in expression
        assert "div[class*='job']" in expression
        assert "firstText" in expression
        assert "scriptSalaryCandidates" in expression
        assert "nextElementSibling" in expression
        assert "fetchDetail" in expression
        assert "await Promise.all" in expression
        return {
            "jobs": [
                {
                    "title": "Backend Intern",
                    "company": "Real Company",
                    "city": "Shanghai",
                    "salary": "200-300/day",
                    "description": "Visible browser job card",
                    "url": "https://www.zhipin.com/job_detail/fallback.html",
                    "job_type": "boss_browser",
                }
            ],
            "diagnostics": {
                "matched_selector_counts": {"fallback_links": 2, "[data-jobid]": 1},
                "candidate_card_count": 1,
            },
        }

    monkeypatch.setenv("BROWSER_CDP_URL", "127.0.0.1:9222")
    monkeypatch.setattr(browser_job_extractor_service, "urlopen", lambda url, timeout: FakeCdpResponse())
    monkeypatch.setattr(browser_job_extractor_service.CdpRuntimeClient, "evaluate", fake_evaluate)
    app = create_app(db_path=tmp_path / "agent-business.sqlite3")
    client = TestClient(app)

    response = client.post("/api/platform-jobs/extract", json={"platforms": ["boss"], "limit": 5})

    assert response.status_code == 200
    extraction = response.json()["extractions"][0]
    assert extraction["status"] == "success"
    assert extraction["diagnostics"]["matched_selector_counts"]["fallback_links"] == 2
    assert extraction["diagnostics"]["matched_selector_counts"]["[data-jobid]"] == 1


def test_boss_browser_script_targets_jobs_page_and_waits_for_rendered_cards():
    service = browser_job_extractor_service.BrowserJobExtractorService(cdp_url="http://127.0.0.1:9222")

    search_url = service._search_url("boss", "Python 实习", "上海")
    extract_script = service._extract_script("boss", 10)

    assert "https://www.zhipin.com/web/geek/jobs?" in search_url
    assert "waitForCandidateCards" in extract_script
    assert "setTimeout(resolve, 250)" in extract_script


def test_platform_job_extraction_reports_diagnostics_when_tab_is_missing(tmp_path, monkeypatch):
    class FakeCdpResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return json.dumps(
                [
                    {
                        "type": "page",
                        "url": "https://example.com/",
                    }
                ]
            ).encode("utf-8")

    monkeypatch.setenv("BROWSER_CDP_URL", "127.0.0.1:9222")
    monkeypatch.setattr(browser_job_extractor_service, "urlopen", lambda url, timeout: FakeCdpResponse())
    app = create_app(db_path=tmp_path / "agent-business.sqlite3")
    client = TestClient(app)

    response = client.post("/api/platform-jobs/extract", json={"platforms": ["boss"], "limit": 5})

    assert response.status_code == 200
    extraction = response.json()["extractions"][0]
    assert extraction["status"] == "tab_not_found"
    assert extraction["diagnostics"]["tab_detected"] is False
    assert extraction["diagnostics"]["failure_reason"] == "未检测到平台标签页"
    assert "打开 BOSS" in extraction["diagnostics"]["suggestion"]
