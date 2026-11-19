import pytest

from app.services.browser_job_extractor_service import BrowserJobExtractorService


def test_detail_refresh_navigates_to_correct_platform_job(monkeypatch):
    service = BrowserJobExtractorService(cdp_url="http://127.0.0.1:9222")
    target = "https://www.zhipin.com/job_detail/target.html"
    calls = []
    monkeypatch.setattr(service, "_load_tabs", lambda: [{"type": "page", "url": "https://www.zhipin.com/web/geek/jobs", "webSocketDebuggerUrl": "ws://localhost/test"}])
    monkeypatch.setattr("app.services.browser_job_extractor_service.sleep", lambda _: None)

    def evaluate(ws, expression):
        calls.append(expression)
        return {"title": "产品经理", "description": "岗位职责：" + "负责用户需求和产品设计。" * 15, "detail_description": "岗位职责：" + "负责用户需求和产品设计。" * 15, "detail_status": "detail_fetched", "url": target}

    monkeypatch.setattr(service.runtime_client, "evaluate", evaluate)
    result = service.refresh_job_detail("boss", target)
    assert "location.href = targetUrl" in calls[0]
    assert "pickDetailText(document)" in calls[1]
    assert result.detail_status == "detail_fetched"


def test_detail_refresh_rejects_unrelated_urls_before_browser_access(monkeypatch):
    service = BrowserJobExtractorService(cdp_url="http://127.0.0.1:9222")
    monkeypatch.setattr(service, "_load_tabs", lambda: pytest.fail("Unsafe URL reached browser"))
    for url in ["https://example.com/job", "javascript:alert(1)", "http://www.zhipin.com/job_detail/x"]:
        with pytest.raises(ValueError, match="HTTPS"):
            service.refresh_job_detail("boss", url)


def test_detail_refresh_retries_replaced_navigation_context(monkeypatch):
    service = BrowserJobExtractorService(cdp_url="http://127.0.0.1:9222")
    target = "https://www.zhipin.com/job_detail/target.html"
    monkeypatch.setattr(service, "_load_tabs", lambda: [{"type": "page", "url": target, "webSocketDebuggerUrl": "ws://localhost/test"}])
    monkeypatch.setattr("app.services.browser_job_extractor_service.sleep", lambda _: None)
    calls = []
    def evaluate(*_):
        calls.append(1)
        if len(calls) == 1:
            raise ValueError("CDP Runtime.evaluate failed")
        return {"title": "产品经理", "detail_description": "岗位职责：" + "用户调研和需求分析。" * 12, "detail_status": "detail_fetched", "url": target}
    monkeypatch.setattr(service.runtime_client, "evaluate", evaluate)
    assert service.refresh_job_detail("boss", target).detail_status == "detail_fetched"
    assert len(calls) == 2
