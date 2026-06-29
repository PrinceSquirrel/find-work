from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import ssl
from urllib.parse import urlparse
from urllib.request import urlopen

from app.schemas import (
    BrowserExtractionDiagnostics,
    BrowserJobExtractResponse,
    ExtractedJobCandidate,
    PlatformJobExtraction,
)
from app.services.platform_session_service import PLATFORM_HOSTS


class CdpRuntimeClient:
    def evaluate(self, websocket_url: str, expression: str) -> object:
        parsed = urlparse(websocket_url)
        host = parsed.hostname
        if not host:
            raise ValueError("CDP websocket URL missing host")
        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        sock = socket.create_connection((host, port), timeout=3)
        if parsed.scheme == "wss":
            sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
        try:
            self._handshake(sock, host, port, path)
            self._send_json(
                sock,
                {
                    "id": 1,
                    "method": "Runtime.evaluate",
                    "params": {
                        "expression": expression,
                        "returnByValue": True,
                        "awaitPromise": False,
                    },
                },
            )
            while True:
                message = self._recv_json(sock)
                if message.get("id") != 1:
                    continue
                if "exceptionDetails" in message:
                    raise ValueError("CDP Runtime.evaluate failed")
                return message.get("result", {}).get("result", {}).get("value")
        finally:
            sock.close()

    def _handshake(self, sock: socket.socket, host: str, port: int, path: str) -> None:
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        sock.sendall(request.encode("ascii"))
        response = self._recv_until(sock, b"\r\n\r\n")
        accept = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest())
        if b" 101 " not in response or accept not in response:
            raise ValueError("CDP websocket handshake failed")

    def _send_json(self, sock: socket.socket, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        header = bytearray([0x81])
        length = len(body)
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.extend([0x80 | 126, (length >> 8) & 0xFF, length & 0xFF])
        else:
            header.append(0x80 | 127)
            header.extend(length.to_bytes(8, "big"))
        mask = os.urandom(4)
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(body))
        sock.sendall(bytes(header) + mask + masked)

    def _recv_json(self, sock: socket.socket) -> dict[str, object]:
        first, second = self._recv_exact(sock, 2)
        opcode = first & 0x0F
        length = second & 0x7F
        if length == 126:
            length = int.from_bytes(self._recv_exact(sock, 2), "big")
        elif length == 127:
            length = int.from_bytes(self._recv_exact(sock, 8), "big")
        masked = second & 0x80
        mask = self._recv_exact(sock, 4) if masked else b""
        payload = self._recv_exact(sock, length)
        if mask:
            payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        if opcode == 0x8:
            raise ValueError("CDP websocket closed")
        if opcode != 0x1:
            return {}
        return json.loads(payload.decode("utf-8"))

    def _recv_exact(self, sock: socket.socket, length: int) -> bytes:
        chunks = bytearray()
        while len(chunks) < length:
            chunk = sock.recv(length - len(chunks))
            if not chunk:
                raise ValueError("CDP websocket ended unexpectedly")
            chunks.extend(chunk)
        return bytes(chunks)

    def _recv_until(self, sock: socket.socket, delimiter: bytes) -> bytes:
        chunks = bytearray()
        while delimiter not in chunks:
            chunk = sock.recv(4096)
            if not chunk:
                raise ValueError("CDP websocket ended unexpectedly")
            chunks.extend(chunk)
        return bytes(chunks)


class BrowserJobExtractorService:
    def __init__(self, cdp_url: str | None = None, runtime_client: CdpRuntimeClient | None = None):
        self.cdp_url = self._normalize_cdp_url(cdp_url or os.getenv("BROWSER_CDP_URL", ""))
        self.runtime_client = runtime_client or CdpRuntimeClient()

    def extract(self, platforms: list[str], limit: int) -> BrowserJobExtractResponse:
        if not self.cdp_url:
            return BrowserJobExtractResponse(
                extractions=[
                    PlatformJobExtraction(
                        platform=platform,
                        status="not_configured",
                        error="未配置 BROWSER_CDP_URL",
                        diagnostics=self._diagnostics(
                            failure_reason="未配置 BROWSER_CDP_URL",
                            suggestion="点击前端的“启动 CDP 浏览器”，或在后端环境变量中设置 BROWSER_CDP_URL。",
                        ),
                    )
                    for platform in platforms
                ],
            )

        try:
            tabs = self._load_tabs()
        except (OSError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            return BrowserJobExtractResponse(
                cdp_url=self.cdp_url,
                extractions=[
                    PlatformJobExtraction(
                        platform=platform,
                        status="cdp_unreachable",
                        error=str(exc),
                        diagnostics=self._diagnostics(
                            failure_reason="无法连接浏览器 CDP",
                            suggestion="确认 CDP 浏览器仍在运行，并且端口是 9222。",
                        ),
                    )
                    for platform in platforms
                ],
            )
        return BrowserJobExtractResponse(
            cdp_url=self.cdp_url,
            extractions=[self._extract_platform(platform, tabs, limit) for platform in platforms],
        )

    def _load_tabs(self) -> list[dict[str, str]]:
        with urlopen(f"{self.cdp_url}/json", timeout=2) as response:
            payload = response.read().decode("utf-8")
        tabs = json.loads(payload)
        return tabs if isinstance(tabs, list) else []

    def _extract_platform(
        self,
        platform: str,
        tabs: list[dict[str, str]],
        limit: int,
    ) -> PlatformJobExtraction:
        hosts = PLATFORM_HOSTS.get(platform)
        if not hosts:
            return PlatformJobExtraction(
                platform=platform,
                status="unsupported_platform",
                error="不支持的平台",
                diagnostics=self._diagnostics(
                    failure_reason="不支持的平台",
                    suggestion="当前仅支持 boss 和 shixiseng。",
                ),
            )

        tab = self._find_platform_tab(tabs, hosts)
        if tab is None:
            return PlatformJobExtraction(
                platform=platform,
                status="tab_not_found",
                error="未检测到平台标签页",
                diagnostics=self._diagnostics(
                    failure_reason="未检测到平台标签页",
                    suggestion=f"请在 CDP 浏览器中打开 {self._platform_label(platform)} 岗位列表页后刷新会话。",
                ),
            )

        source_url = self._sanitize_url(tab.get("url", ""))
        websocket_url = tab.get("webSocketDebuggerUrl")
        if not websocket_url:
            return PlatformJobExtraction(
                platform=platform,
                status="websocket_missing",
                source_url=source_url,
                error="平台标签页未暴露 webSocketDebuggerUrl",
                diagnostics=self._diagnostics(
                    tab_detected=True,
                    failure_reason="平台标签页未暴露 webSocketDebuggerUrl",
                    suggestion="请重启 CDP 浏览器后再刷新会话。",
                ),
            )

        try:
            raw_result = self.runtime_client.evaluate(websocket_url, self._extract_script(platform, limit))
        except (OSError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            return PlatformJobExtraction(
                platform=platform,
                status="extract_failed",
                source_url=source_url,
                error=str(exc),
                diagnostics=self._diagnostics(
                    tab_detected=True,
                    websocket_detected=True,
                    failure_reason="页面提取脚本执行失败",
                    suggestion="确认页面已加载完成；如果仍失败，平台 DOM 结构可能已经变化。",
                ),
            )

        raw_jobs, runtime_diagnostics = self._split_runtime_result(raw_result)
        jobs = self._normalize_jobs(platform, raw_jobs, limit)
        diagnostics = self._diagnostics(
            tab_detected=True,
            websocket_detected=True,
            matched_selector_counts=runtime_diagnostics.get("matched_selector_counts", {}),
            candidate_card_count=int(runtime_diagnostics.get("candidate_card_count", 0) or 0),
            extracted_job_count=len(jobs),
            failure_reason="" if jobs else "没有从当前页面提取到岗位",
            suggestion="" if jobs else "确认当前页面是岗位列表页、已登录且没有验证码或空结果提示。",
        )
        return PlatformJobExtraction(
            platform=platform,
            status="success" if jobs else "empty",
            source_url=source_url,
            jobs=jobs,
            diagnostics=diagnostics,
        )

    def _find_platform_tab(self, tabs: list[dict[str, str]], hosts: list[str]) -> dict[str, str] | None:
        for tab in tabs:
            parsed = urlparse(tab.get("url", ""))
            hostname = parsed.hostname or ""
            if tab.get("type") == "page" and any(hostname == host or hostname.endswith(f".{host}") for host in hosts):
                return tab
        return None

    def _normalize_jobs(self, platform: str, raw_jobs: object, limit: int) -> list[ExtractedJobCandidate]:
        if not isinstance(raw_jobs, list):
            return []
        jobs: list[ExtractedJobCandidate] = []
        for raw in raw_jobs:
            if not isinstance(raw, dict):
                continue
            title = self._clean(raw.get("title", ""))
            description = self._clean(raw.get("description", ""))
            if not title and not description:
                continue
            jobs.append(
                ExtractedJobCandidate(
                    platform=platform,
                    company=self._clean(raw.get("company", "")),
                    title=title or description[:80],
                    city=self._clean(raw.get("city", "")),
                    salary=self._clean(raw.get("salary", "")),
                    description=description,
                    url=self._sanitize_url(self._clean(raw.get("url", ""))),
                    job_type=self._clean(raw.get("job_type", "")) or "unknown",
                )
            )
            if len(jobs) >= limit:
                break
        return jobs

    def _split_runtime_result(self, raw_result: object) -> tuple[object, dict[str, object]]:
        if isinstance(raw_result, dict):
            diagnostics = raw_result.get("diagnostics", {})
            return raw_result.get("jobs", []), diagnostics if isinstance(diagnostics, dict) else {}
        return raw_result, {}

    def _diagnostics(
        self,
        *,
        tab_detected: bool = False,
        websocket_detected: bool = False,
        matched_selector_counts: dict[str, int] | None = None,
        candidate_card_count: int = 0,
        extracted_job_count: int = 0,
        failure_reason: str = "",
        suggestion: str = "",
    ) -> BrowserExtractionDiagnostics:
        return BrowserExtractionDiagnostics(
            tab_detected=tab_detected,
            websocket_detected=websocket_detected,
            matched_selector_counts=matched_selector_counts or {},
            candidate_card_count=candidate_card_count,
            extracted_job_count=extracted_job_count,
            failure_reason=failure_reason,
            suggestion=suggestion,
        )

    def _extract_script(self, platform: str, limit: int) -> str:
        return f"""
(() => {{
  const limit = {limit};
  const platform = {json.dumps(platform)};
  const text = (node) => (node?.innerText || node?.textContent || "").replace(/\\s+/g, " ").trim();
  const absolute = (href) => {{
    try {{ return new URL(href || location.href, location.href).href; }} catch (_) {{ return href || location.href; }}
  }};
  const firstText = (root, fieldSelectors) => {{
    for (const selector of fieldSelectors) {{
      const value = text(root.querySelector(selector));
      if (value) return value;
    }}
    return "";
  }};
  const selectors = platform === "boss"
    ? [
        ".job-card-wrapper",
        ".job-card-box",
        ".job-list-box li",
        ".job-primary",
        ".job-card-left",
        "[data-jobid]",
        "[data-job-id]",
        "a[href*='job_detail']",
        "a[href*='/job_detail/']"
      ]
    : [
        ".job-item",
        ".intern-wrap",
        ".position-list-item",
        ".job-list li",
        ".intern-item",
        ".position-item",
        "[data-positionid]",
        "[data-position-id]",
        "[data-internid]",
        "[data-intern-id]",
        "a[href*='intern']",
        "a[href*='/intern/']",
        "a[href*='job']"
      ];
  const cardRootSelector = [
    "li",
    "article",
    "section",
    ".job-card-wrapper",
    ".job-card-box",
    ".job-primary",
    ".job-item",
    ".intern-wrap",
    ".position-list-item",
    "div[class*='job']",
    "div[class*='position']",
    "div[class*='intern']",
    "div[class*='card']"
  ].join(",");
  const cards = [];
  const seenCards = new Set();
  const matchedSelectorCounts = {{}};
  const pushCard = (node) => {{
    const card = node.closest?.(cardRootSelector) || node;
    if (!seenCards.has(card)) {{
      seenCards.add(card);
      cards.push(card);
    }}
  }};
  for (const selector of selectors) {{
    const nodes = Array.from(document.querySelectorAll(selector));
    matchedSelectorCounts[selector] = nodes.length;
    for (const node of nodes) pushCard(node);
  }}
  const fallbackLinkSelector = platform === "boss"
    ? "a[href*='job_detail'],a[href*='/job_detail/']"
    : "a[href*='intern'],a[href*='/intern/'],a[href*='job']";
  const fallbackLinks = Array.from(document.querySelectorAll(fallbackLinkSelector));
  matchedSelectorCounts.fallback_links = fallbackLinks.length;
  for (const link of fallbackLinks) pushCard(link);
  const titleSelectors = [
    ".job-name",
    ".job-title",
    ".position-name",
    ".position-title",
    ".job-card-name",
    ".name",
    ".title",
    "[class*='job-title']",
    "[class*='position-name']",
    "[class*='position-title']"
  ];
  const companySelectors = [
    ".company-name",
    ".company-text",
    ".com-name",
    ".company",
    ".company-title",
    "[class*='company']",
    "[class*='com-name']"
  ];
  const citySelectors = [
    ".job-area",
    ".area",
    ".city",
    ".location",
    ".address",
    "[class*='area']",
    "[class*='city']",
    "[class*='location']"
  ];
  const salarySelectors = [
    ".salary",
    ".red",
    ".job-salary",
    ".money",
    ".wage",
    "[class*='salary']",
    "[class*='wage']"
  ];
  const preferredLink = (card) => {{
    if (card.matches?.("a[href]")) return card;
    return card.querySelector(fallbackLinkSelector) || card.querySelector("a[href]");
  }};
  const jobs = cards.slice(0, limit * 4).map((card) => {{
    const link = preferredLink(card);
    const description = text(card).slice(0, 1200);
    return {{
      title: firstText(card, titleSelectors) || text(link) || description.slice(0, 80),
      company: firstText(card, companySelectors),
      city: firstText(card, citySelectors),
      salary: firstText(card, salarySelectors),
      description,
      url: absolute(link?.getAttribute("href")),
      job_type: platform === "boss" ? "boss_browser" : "shixiseng_browser"
    }};
  }}).filter((job) => job.title || job.description).slice(0, limit);
  return {{
    jobs,
    diagnostics: {{
      matched_selector_counts: matchedSelectorCounts,
      candidate_card_count: cards.length
    }}
  }};
}})()
"""

    def _clean(self, value: object) -> str:
        return " ".join(str(value or "").split())

    def _sanitize_url(self, raw_url: str) -> str:
        if not raw_url:
            return ""
        parsed = urlparse(raw_url)
        return parsed._replace(query="", fragment="").geturl()

    def _platform_label(self, platform: str) -> str:
        labels = {"boss": "BOSS 直聘", "shixiseng": "实习僧"}
        return labels.get(platform, platform)

    def _normalize_cdp_url(self, value: str) -> str | None:
        value = value.strip().rstrip("/")
        if not value:
            return None
        if value.startswith(("http://", "https://")):
            return value
        return f"http://{value}"
