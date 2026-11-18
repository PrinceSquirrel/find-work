from urllib.parse import parse_qs, urlparse

import pytest

from app.schemas import BrowserJobExtractResponse, ExtractedJobCandidate, PlatformJobExtraction
from app.services.browser_job_extractor_service import BrowserJobExtractorService
from app.services.job_application_service import JobApplicationService
from app.storage import SQLiteStore


def test_multiple_city_search_uses_separate_supported_codes(monkeypatch):
    service = BrowserJobExtractorService(cdp_url="http://127.0.0.1:9222")
    calls = []
    monkeypatch.setattr(service, "_load_tabs", lambda: [])
    monkeypatch.setattr("app.services.browser_job_extractor_service.sleep", lambda _: None)
    def control(platform, tabs, keywords, city):
        calls.append((city, service._search_url(platform, "AI产品经理实习生", city)))
    monkeypatch.setattr(service, "_control_platform_search", control)
    def extract(platforms, limit):
        city = calls[-1][0]
        job = ExtractedJobCandidate(platform="boss", title="产品实习生", company="合成公司", city=city, salary="面议", description="合成岗位要求", url=f"https://example.com/{city}")
        return BrowserJobExtractResponse(cdp_url=service.cdp_url, extractions=[PlatformJobExtraction(platform="boss", status="success", jobs=[job])])
    monkeypatch.setattr(service, "extract", extract)
    result = service.search_and_extract(["boss"], ["AI产品经理实习生"], "上海，杭州,上海", 8)
    assert [city for city, _ in calls] == ["上海", "杭州"]
    assert [parse_qs(urlparse(url).query)["city"][0] for _, url in calls] == ["101020100", "101210100"]
    assert [job.city for job in result.extractions[0].jobs] == ["上海", "杭州"]


def test_city_validation_and_zero_result_are_not_fabricated_jobs(monkeypatch):
    service = BrowserJobExtractorService(cdp_url="http://127.0.0.1:9222")
    for city in ["上海，杭州", "未知城市"]:
        with pytest.raises(ValueError):
            service._search_url("boss", "产品", city)
    assert "101020100" in service._search_url("boss", "产品", "上海市")
    tabs = [{"type": "page", "url": "https://www.zhipin.com/web/geek/jobs", "webSocketDebuggerUrl": "ws://localhost/test"}]
    monkeypatch.setattr(service.runtime_client, "evaluate", lambda *_: {"jobs": [], "diagnostics": {"page_state": "empty_results", "candidate_card_count": 0}})
    empty = service._extract_platform("boss", tabs, 8)
    assert empty.status == "no_results" and not empty.jobs
    assert JobApplicationService(None)._collect_extracted_jobs([empty]) == []
    # An actual extraction/login/verification failure must still fail, without demo jobs.
    with pytest.raises(ValueError, match="extraction failed"):
        JobApplicationService(None)._collect_extracted_jobs([PlatformJobExtraction(platform="boss", status="empty")])


def test_empty_page_guard_and_bounded_city_count(monkeypatch):
    service = BrowserJobExtractorService(cdp_url="http://127.0.0.1:9222")
    script = service._extract_script("boss", 8)
    assert 'page_state: state' in script and 'candidate_card_count: 0' in script
    assert script.index('if (state) return') < script.index('await scrollForMoreCards()')
    with pytest.raises(ValueError, match="5 个城市"):
        service.search_and_extract(["boss"], ["产品"], "北京,上海,杭州,深圳,广州,武汉", 8)


def test_search_stops_before_second_city_on_connection_or_verification_failure(monkeypatch):
    service = BrowserJobExtractorService(cdp_url="http://127.0.0.1:9222")
    calls = []
    monkeypatch.setattr(service, "_load_tabs", lambda: [])
    monkeypatch.setattr("app.services.browser_job_extractor_service.sleep", lambda _: None)
    monkeypatch.setattr(service, "_control_platform_search", lambda *args: calls.append(args[-1]))
    monkeypatch.setattr(service, "extract", lambda *_: BrowserJobExtractResponse(extractions=[PlatformJobExtraction(platform="boss", status="cdp_unreachable")]))
    result = service.search_and_extract(["boss"], ["产品"], "上海,杭州", 8)
    assert calls == ["上海"] and result.extractions[0].status == "cdp_unreachable"


def test_explicit_no_results_completes_a_zero_job_run_without_model_or_demo(tmp_path, monkeypatch):
    service = JobApplicationService(SQLiteStore(tmp_path / "search.sqlite3"))
    resume = service.upload_resume("synthetic.txt", "真实合成经历：Python，需求分析".encode())
    class EmptyExtractor:
        def search_and_extract(self, *_args, **_kwargs):
            return BrowserJobExtractResponse(extractions=[PlatformJobExtraction(platform="boss", status="no_results")])
    monkeypatch.setattr("app.services.job_application_service.BrowserJobExtractorService", EmptyExtractor)
    monkeypatch.setattr(service.llm_client, "score_job_matches", lambda *_: pytest.fail("No jobs must not call a model"))
    run = service._create_browser_cdp_search_run(resume, resume.id, ["产品"], "上海", ["boss"], None)
    assert run.status == "completed" and service.store.list_jobs(run.id) == []
