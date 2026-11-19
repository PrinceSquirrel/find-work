import json

import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.services import platform_session_service as module


@pytest.mark.parametrize("platform,other", [("boss", "shixiseng"), ("shixiseng", "boss")])
def test_new_browser_opens_only_selected_platform(tmp_path, monkeypatch, platform, other):
    launcher = module.CdpBrowserLauncher()
    monkeypatch.setattr(launcher, "_detect_existing_cdp_host", lambda _: None)
    monkeypatch.setattr(launcher, "_find_browser", lambda: ("chrome", tmp_path / "chrome.exe"))
    monkeypatch.setattr(launcher, "_profile_dir", lambda _: tmp_path / "profile")
    calls = []
    monkeypatch.setattr(module.subprocess, "Popen", lambda args, **_: calls.append(args))
    result = launcher.launch(platforms=[platform])
    host = module.PLATFORM_HOSTS[platform][0]
    assert len(result["opened_urls"]) == 1 and host in result["opened_urls"][0]
    assert not any(module.PLATFORM_HOSTS[other][0] in arg for arg in calls[0])


def test_reused_browser_opens_only_missing_selected_tab(monkeypatch):
    launcher = module.CdpBrowserLauncher()
    monkeypatch.setattr(launcher, "_detect_existing_cdp_host", lambda _: "127.0.0.1:9222")
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self): return json.dumps([{"type": "page", "url": "https://www.zhipin.com/job_detail/1.html"}]).encode()
    requests = []
    def open_url(request, **_):
        requests.append(request)
        return Response()
    monkeypatch.setattr(module, "urlopen", open_url)
    assert launcher.launch(platforms=["boss"])["opened_urls"] == []
    result = launcher.launch(platforms=["shixiseng"])
    assert len(result["opened_urls"]) == 1 and "shixiseng.com" in result["opened_urls"][0]
    assert requests[-1].method == "PUT" and "shixiseng" in requests[-1].full_url


def test_launch_api_rejects_no_selection_and_unknown_platform(tmp_path):
    client = TestClient(create_app(db_path=tmp_path / "launch.db"))
    for platforms in [[], ["unknown"]]:
        assert client.post("/api/browser/launch-cdp", json={"platforms": platforms}).status_code == 422
