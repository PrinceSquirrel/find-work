import json
import subprocess

import pytest

from app.services.browser_job_extractor_service import BrowserJobExtractorService, CdpRuntimeClient


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


def test_search_navigates_to_explicit_url_instead_of_hidden_controls():
    service = BrowserJobExtractorService(cdp_url="http://127.0.0.1:9222")
    script = service._search_script("boss", ["产品经理"], "上海")
    harness = "globalThis.location={href:'https://www.zhipin.com/job_detail/old.html'};globalThis.document={querySelector:()=>{throw Error('Hidden control used')}};"
    result = subprocess.run(["node", "--input-type=module", "-e", harness + "await " + script + ";console.log(JSON.stringify(location.href));"], capture_output=True, text=True, encoding="utf-8", check=True)
    assert json.loads(result.stdout) == service._search_url("boss", "产品经理", "上海")
    script = service._extract_script("boss", 50)
    assert "Math.min(limit, 8)" in script
    assert "link => !/职位订阅|职位搜索|岗位搜索/" in script
    assert script.index("const html = await response.text()") < script.index("clearTimeout(timer)")


def test_runtime_activates_target_before_waiting_for_timers(monkeypatch):
    class Socket:
        def settimeout(self, *_): pass
        def close(self): pass
    monkeypatch.setattr("app.services.browser_job_extractor_service.socket.create_connection", lambda *_args, **_kwargs: Socket())
    client = CdpRuntimeClient()
    sent = []
    monkeypatch.setattr(client, "_handshake", lambda *_: None)
    monkeypatch.setattr(client, "_send_json", lambda _sock, message: sent.append(message))
    replies = iter([{"id": 0, "result": {}}, {"id": 1, "result": {"result": {"value": "ready"}}}])
    monkeypatch.setattr(client, "_recv_json", lambda _: next(replies))
    assert client.evaluate("ws://127.0.0.1/test", "expression") == "ready"
    assert [item["method"] for item in sent] == ["Page.bringToFront", "Runtime.evaluate"]
