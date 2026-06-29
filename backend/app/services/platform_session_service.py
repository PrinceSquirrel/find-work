from __future__ import annotations

import json
import os
import subprocess
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import urlopen
from pathlib import Path

from app.schemas import PlatformSession, PlatformSessionsResponse


PLATFORM_HOSTS = {
    "boss": ["zhipin.com"],
    "shixiseng": ["shixiseng.com"],
}


class PlatformSessionService:
    def __init__(self, cdp_url: str | None = None):
        self.cdp_url = self._normalize_cdp_url(cdp_url or os.getenv("BROWSER_CDP_URL", ""))

    def inspect(self) -> PlatformSessionsResponse:
        if not self.cdp_url:
            return PlatformSessionsResponse(
                browser_connected=False,
                sessions=[
                    self._session(platform, hosts, "not_configured", "未配置 BROWSER_CDP_URL")
                    for platform, hosts in PLATFORM_HOSTS.items()
                ],
            )

        try:
            tabs = self._load_tabs()
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            return PlatformSessionsResponse(
                cdp_url=self.cdp_url,
                browser_connected=False,
                error=str(exc),
                sessions=[
                    self._session(platform, hosts, "cdp_unreachable", "无法连接浏览器 CDP")
                    for platform, hosts in PLATFORM_HOSTS.items()
                ],
            )

        return PlatformSessionsResponse(
            cdp_url=self.cdp_url,
            browser_connected=True,
            sessions=[self._inspect_platform(platform, hosts, tabs) for platform, hosts in PLATFORM_HOSTS.items()],
        )

    def _load_tabs(self) -> list[dict[str, str]]:
        with urlopen(f"{self.cdp_url}/json", timeout=2) as response:
            payload = response.read().decode("utf-8")
        tabs = json.loads(payload)
        return tabs if isinstance(tabs, list) else []

    def _inspect_platform(
        self,
        platform: str,
        expected_hosts: list[str],
        tabs: list[dict[str, str]],
    ) -> PlatformSession:
        for tab in tabs:
            detected_url = self._matching_tab_url(tab.get("url", ""), expected_hosts)
            if detected_url:
                return self._session(platform, expected_hosts, "tab_detected", "已检测到平台标签页", detected_url)
        return self._session(platform, expected_hosts, "tab_not_found", "浏览器已连接，但未检测到平台标签页")

    def _matching_tab_url(self, raw_url: str, expected_hosts: list[str]) -> str | None:
        parsed = urlparse(raw_url)
        hostname = parsed.hostname or ""
        if not any(hostname == host or hostname.endswith(f".{host}") for host in expected_hosts):
            return None
        return parsed._replace(query="", fragment="").geturl()

    def _session(
        self,
        platform: str,
        expected_hosts: list[str],
        state: str,
        message: str,
        detected_url: str | None = None,
    ) -> PlatformSession:
        return PlatformSession(
            platform=platform,
            expected_hosts=expected_hosts,
            state=state,
            detected_url=detected_url,
            authenticated=None,
            message=message,
        )

    def _normalize_cdp_url(self, value: str) -> str | None:
        value = value.strip().rstrip("/")
        if not value:
            return None
        if value.startswith(("http://", "https://")):
            return value
        return f"http://{value}"


class CdpBrowserLauncher:
    default_urls = [
        "https://www.zhipin.com/web/geek/job",
        "https://www.shixiseng.com/interns",
    ]

    def launch(self, port: int = 9222) -> dict[str, object]:
        browser_name, executable = self._find_browser()
        profile_dir = self._profile_dir(browser_name)
        profile_dir.mkdir(parents=True, exist_ok=True)
        cdp_host = f"127.0.0.1:{port}"
        args = [
            str(executable),
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--new-window",
            *self.default_urls,
        ]
        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.environ["BROWSER_CDP_URL"] = cdp_host
        return {
            "status": "started",
            "browser": browser_name,
            "cdp_url": cdp_host,
            "profile_dir": str(profile_dir),
            "opened_urls": self.default_urls,
            "message": "已启动独立 CDP 浏览器。请在新窗口中登录 BOSS/实习僧，然后回到工作台刷新会话。",
        }

    def _find_browser(self) -> tuple[str, Path]:
        candidates = [
            (
                "edge",
                [
                    Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft/Edge/Application/msedge.exe",
                    Path(os.environ.get("ProgramFiles", "")) / "Microsoft/Edge/Application/msedge.exe",
                    Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/Edge/Application/msedge.exe",
                ],
            ),
            (
                "chrome",
                [
                    Path(os.environ.get("ProgramFiles", "")) / "Google/Chrome/Application/chrome.exe",
                    Path(os.environ.get("ProgramFiles(x86)", "")) / "Google/Chrome/Application/chrome.exe",
                    Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
                ],
            ),
        ]
        for browser_name, paths in candidates:
            for path in paths:
                if path.is_file():
                    return browser_name, path
        raise FileNotFoundError("未找到 Edge 或 Chrome，请先安装任一浏览器。")

    def _profile_dir(self, browser_name: str) -> Path:
        base_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "agent-business"
        return base_dir / f"{browser_name}-cdp-profile"
