from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import socket
import ssl
from html import unescape
from time import sleep
from urllib.parse import urlparse
from urllib.request import urlopen

from app.schemas import (
    BrowserExtractionDiagnostics,
    BrowserJobExtractResponse,
    ExtractedJobCandidate,
    PlatformJobExtraction,
)
from app.services.platform_session_service import PLATFORM_HOSTS, resolve_cdp_url


BOSS_CITY_CODES = {
    "北京": "101010100",
    "上海": "101020100",
    "广州": "101280100",
    "深圳": "101280600",
    "杭州": "101210100",
    "成都": "101270100",
    "武汉": "101200100",
    "南京": "101190100",
    "苏州": "101190400",
    "西安": "101110100",
    "重庆": "101040100",
    "天津": "101030100",
}

KNOWN_CITY_NAMES = tuple(BOSS_CITY_CODES.keys())
BOSS_PRIVATE_DIGIT_TRANSLATION = str.maketrans(
    {
        "\ue031": "0",
        "\ue032": "1",
        "\ue033": "2",
        "\ue034": "3",
        "\ue035": "4",
        "\ue036": "5",
        "\ue037": "6",
        "\ue038": "7",
        "\ue039": "8",
        "\ue03a": "9",
    }
)


class SalaryExtractor:
    MONEY_PATTERN = re.compile(
        r"(?P<salary>"
        r"(?:\d+\s*[-~—到]\s*\d+\s*(?:元|块)?\s*/\s*(?:天|日|月))"
        r"|(?:\d+(?:\.\d+)?\s*[-~—到]\s*\d+(?:\.\d+)?\s*[Kk万千元]+(?:\s*[·.]?\s*\d+\s*薪)?)"
        r"|(?:\d+(?:\.\d+)?\s*[Kk万千元]+\s*[-~—到]\s*\d+(?:\.\d+)?\s*[Kk万千元]+(?:\s*[·.]?\s*\d+\s*薪)?)"
        r"|(?:\d+\s*[-~—到]\s*\d+\s*/\s*(?:天|日|月))"
        r"|(?:薪资面议|面议)"
        r")"
    )

    def extract(self, candidates: list[object]) -> str:
        for candidate in candidates:
            text = " ".join(str(candidate or "").translate(BOSS_PRIVATE_DIGIT_TRANSLATION).split())
            if not text:
                continue
            match = self.MONEY_PATTERN.search(text)
            if match:
                return self._normalize(match.group("salary"))
        return ""

    def _normalize(self, salary: str) -> str:
        salary = re.sub(r"\s+", "", salary)
        salary = salary.replace("到", "-").replace("~", "-").replace("—", "-")
        salary = salary.replace(".", "·") if "薪" in salary else salary
        return salary.upper().replace("/日", "/天")


class CdpRuntimeClient:
    CONNECT_TIMEOUT_SECONDS = 5
    EVALUATE_TIMEOUT_SECONDS = 30

    def evaluate(self, websocket_url: str, expression: str) -> object:
        parsed = urlparse(websocket_url)
        host = parsed.hostname
        if not host:
            raise ValueError("CDP websocket URL missing host")
        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        sock = socket.create_connection((host, port), timeout=self.CONNECT_TIMEOUT_SECONDS)
        if parsed.scheme == "wss":
            sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
        sock.settimeout(self.EVALUATE_TIMEOUT_SECONDS)
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
                        "awaitPromise": True,
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
        self.cdp_url = resolve_cdp_url(cdp_url or os.getenv("BROWSER_CDP_URL", ""), opener=urlopen)
        self.runtime_client = runtime_client or CdpRuntimeClient()
        self.salary_extractor = SalaryExtractor()

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

    def search_and_extract(
        self,
        platforms: list[str],
        keywords: list[str],
        city: str,
        limit: int,
    ) -> BrowserJobExtractResponse:
        if not self.cdp_url:
            return self.extract(platforms, limit)
        try:
            tabs = self._load_tabs()
        except (OSError, TimeoutError, ValueError, json.JSONDecodeError):
            return self.extract(platforms, limit)
        for platform in platforms:
            self._control_platform_search(platform, tabs, keywords, city)
        sleep(1.5)
        response = self.extract(platforms, limit)
        requested_city = city.strip()
        if requested_city:
            for extraction in response.extractions:
                extraction.jobs = [job for job in extraction.jobs if self._city_matches(job.city, requested_city)]
                extraction.diagnostics.extracted_job_count = len(extraction.jobs)
                if not extraction.jobs and extraction.status == "success":
                    extraction.status = "empty"
                    extraction.diagnostics.failure_reason = f"没有提取到 {requested_city} 的岗位"
                    extraction.diagnostics.suggestion = "平台可能仍停留在其他城市，请确认搜索页城市已切换后重试。"
        return response

    def refresh_job_detail(self, platform: str, url: str) -> ExtractedJobCandidate:
        if not self.cdp_url:
            raise ValueError("BROWSER_CDP_URL is not configured.")
        hosts = PLATFORM_HOSTS.get(platform)
        if not hosts:
            raise ValueError(f"Unsupported platform: {platform}")
        tabs = self._load_tabs()
        tab = self._find_platform_tab(tabs, hosts)
        if tab is None:
            raise ValueError(f"No detected {platform} tab in the CDP browser.")
        websocket_url = tab.get("webSocketDebuggerUrl")
        if not websocket_url:
            raise ValueError(f"The detected {platform} tab has no websocket endpoint.")
        raw_result = self.runtime_client.evaluate(websocket_url, self._detail_refresh_script(platform, url))
        return self._normalize_detail_refresh_result(platform, url, raw_result)

    def apply_to_job(self, platform: str, url: str) -> dict[str, object]:
        if not self.cdp_url:
            raise ValueError("BROWSER_CDP_URL is not configured.")
        hosts = PLATFORM_HOSTS.get(platform)
        if not hosts:
            raise ValueError(f"Unsupported platform: {platform}")
        tabs = self._load_tabs()
        tab = self._find_platform_tab(tabs, hosts)
        if tab is None:
            raise ValueError(f"No detected {platform} tab in the CDP browser.")
        websocket_url = tab.get("webSocketDebuggerUrl")
        if not websocket_url:
            raise ValueError(f"The detected {platform} tab has no websocket endpoint.")
        try:
            self.runtime_client.evaluate(websocket_url, self._open_job_script(url))
            sleep(2.5)
            raw_result = self.runtime_client.evaluate(websocket_url, self._application_click_script(platform, url))
        except (OSError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            return {
                "confirmed": False,
                "status": "cdp_failed",
                "action": "none",
                "evidence": str(exc),
                "source_url": self._sanitize_url(url),
            }
        if not isinstance(raw_result, dict):
            return {
                "confirmed": False,
                "status": "invalid_cdp_result",
                "action": "none",
                "evidence": "platform apply script did not return a structured result",
                "source_url": self._sanitize_url(url),
            }
        raw_result["platform"] = platform
        raw_result["source_url"] = self._sanitize_url(str(raw_result.get("source_url") or url))
        return raw_result

    def preview_apply_to_job(self, platform: str, url: str) -> dict[str, object]:
        if not self.cdp_url:
            raise ValueError("BROWSER_CDP_URL is not configured.")
        hosts = PLATFORM_HOSTS.get(platform)
        if not hosts:
            raise ValueError(f"Unsupported platform: {platform}")
        tabs = self._load_tabs()
        tab = self._find_platform_tab(tabs, hosts)
        if tab is None:
            raise ValueError(f"No detected {platform} tab in the CDP browser.")
        websocket_url = tab.get("webSocketDebuggerUrl")
        if not websocket_url:
            raise ValueError(f"The detected {platform} tab has no websocket endpoint.")
        try:
            self.runtime_client.evaluate(websocket_url, self._open_job_script(url))
            sleep(2.5)
            raw_result = self.runtime_client.evaluate(websocket_url, self._application_preview_script(platform, url))
        except (OSError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            return {
                "ready": False,
                "status": "cdp_failed",
                "action": "preview",
                "button_text": "",
                "evidence": str(exc),
                "source_url": self._sanitize_url(url),
            }
        if not isinstance(raw_result, dict):
            return {
                "ready": False,
                "status": "invalid_cdp_result",
                "action": "preview",
                "button_text": "",
                "evidence": "platform preview script did not return a structured result",
                "source_url": self._sanitize_url(url),
            }
        raw_result["platform"] = platform
        raw_result["source_url"] = self._sanitize_url(str(raw_result.get("source_url") or url))
        return raw_result

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
        jobs, text_quality_warnings = self._normalize_jobs(platform, raw_jobs, limit)
        diagnostics = self._diagnostics(
            tab_detected=True,
            websocket_detected=True,
            matched_selector_counts=runtime_diagnostics.get("matched_selector_counts", {}),
            candidate_card_count=int(runtime_diagnostics.get("candidate_card_count", 0) or 0),
            extracted_job_count=len(jobs),
            text_quality_warnings=text_quality_warnings,
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

    def _control_platform_search(
        self,
        platform: str,
        tabs: list[dict[str, str]],
        keywords: list[str],
        city: str,
    ) -> None:
        hosts = PLATFORM_HOSTS.get(platform)
        if not hosts:
            return
        tab = self._find_platform_tab(tabs, hosts)
        websocket_url = tab.get("webSocketDebuggerUrl") if tab else ""
        if not websocket_url:
            return
        try:
            self.runtime_client.evaluate(websocket_url, self._search_script(platform, keywords, city))
        except (OSError, TimeoutError, ValueError, json.JSONDecodeError):
            return

    def _normalize_jobs(
        self,
        platform: str,
        raw_jobs: object,
        limit: int,
    ) -> tuple[list[ExtractedJobCandidate], list[str]]:
        if not isinstance(raw_jobs, list):
            return [], ["runtime did not return a job list"]
        jobs: list[ExtractedJobCandidate] = []
        warnings: list[str] = []
        for index, raw in enumerate(raw_jobs, start=1):
            if not isinstance(raw, dict):
                continue
            title = self._clean(raw.get("title", ""))
            description = self._best_description(raw)
            if not title and not description:
                continue
            if self._is_non_job_candidate(platform, raw, title, description):
                warnings.append(f"dropped non-job candidate #{index}: {title or 'untitled'}")
                continue
            if title and self._is_untrusted_text(title):
                warnings.append(f"dropped polluted job #{index}: title is unreadable")
                continue
            if self._is_untrusted_text(title) and self._is_untrusted_text(description):
                warnings.append(f"dropped polluted job #{index}: title and description are unreadable")
                continue
            company = self._trusted_field(raw.get("company", ""), "company", warnings, index)
            if self._is_unknown_company(company):
                company = self._infer_company(raw) or company
            city = self._trusted_field(raw.get("city", ""), "city", warnings, index)
            if not city:
                city = self._infer_city(raw)
            if not city:
                city = "城市未展示"
            salary = self._extract_salary(raw)
            if not salary:
                salary = "薪资读取失败"
            detail_status, detail_reason = self._detail_diagnostics(raw, description)
            jobs.append(
                ExtractedJobCandidate(
                    platform=platform,
                    company=company,
                    title=title or description[:80],
                    city=city,
                    salary=salary,
                    description=description,
                    url=self._sanitize_url(self._clean(raw.get("url", ""))),
                    job_type=self._clean(raw.get("job_type", "")) or "unknown",
                    detail_status=detail_status,
                    detail_reason=detail_reason,
                )
            )
            if len(jobs) >= limit:
                break
        return jobs, warnings

    def _is_non_job_candidate(
        self,
        platform: str,
        raw: dict[str, object],
        title: str,
        description: str,
    ) -> bool:
        if platform != "boss":
            return False
        company = self._clean(raw.get("company", ""))
        url = self._clean(raw.get("url", ""))
        combined = " ".join(part for part in (title, company, description) if part)
        if title in {"职位搜索", "岗位搜索", "职位"}:
            return True
        if title == "职位搜索" and company in {"加载中", "BOSS直聘APP"}:
            return True
        if "BOSS直聘APP" in company and ("搜索" in title or "工作区域" in combined):
            return True
        nav_markers = ("首页", "职位", "公司", "校园", "海归", "APP", "海外")
        if "搜索" in title and sum(1 for marker in nav_markers if marker in combined) >= 4:
            return True
        has_job_detail_url = "/job_detail" in url or "job_detail" in url
        return not has_job_detail_url and company in {"加载中", "BOSS直聘APP"}

    def _city_matches(self, candidate_city: str, requested_city: str) -> bool:
        candidate = self._clean(candidate_city)
        requested = self._clean(requested_city)
        if not candidate or candidate in {"未知城市", "城市未展示"}:
            return True
        if requested in candidate or candidate in requested:
            return True
        if any(city in candidate for city in KNOWN_CITY_NAMES):
            return False
        return True

    def _infer_city(self, raw: dict[str, object]) -> str:
        values: list[object] = [
            raw.get("title", ""),
            raw.get("company", ""),
            raw.get("description", ""),
            raw.get("detail_description", ""),
        ]
        for key in ("salary_candidates", "detail_salary_candidates"):
            candidates = raw.get(key, [])
            if isinstance(candidates, list):
                values.extend(candidates)
        for value in values:
            text = self._clean(value)
            if not text:
                continue
            for city in KNOWN_CITY_NAMES:
                if city and city in text:
                    return city
        return ""

    def _extract_salary(self, raw: dict[str, object]) -> str:
        candidates: list[object] = []
        for key in ("salary_candidates", "detail_salary_candidates"):
            raw_candidates = raw.get(key, [])
            if isinstance(raw_candidates, list):
                candidates.extend(raw_candidates)
        candidates.extend(
            [
                raw.get("salary", ""),
                raw.get("detail_salary", ""),
                raw.get("detail_description", ""),
                raw.get("description", ""),
            ]
        )
        return self.salary_extractor.extract(candidates)

    def _is_unknown_company(self, company: str) -> bool:
        normalized = self._clean(company)
        return not normalized or normalized in {"未知公司", "公司未展示"}

    def _infer_company(self, raw: dict[str, object]) -> str:
        title = self._clean(raw.get("title", ""))
        values: list[object] = []
        for key in ("company_candidates", "salary_candidates", "detail_salary_candidates"):
            candidates = raw.get(key, [])
            if isinstance(candidates, list):
                values.extend(candidates)
        values.extend([raw.get("description", ""), raw.get("detail_description", "")])

        for value in values:
            text = self._clean(value)
            if not text or self._is_untrusted_text(text):
                continue
            candidate_area = text
            if title and title in candidate_area:
                candidate_area = candidate_area.split(title, 1)[1]
            for city in KNOWN_CITY_NAMES:
                city_index = candidate_area.find(city)
                if city_index > 0:
                    candidate_area = candidate_area[:city_index]
                    break
            for part in re.split(r"[·•|｜,，]+|\s+", candidate_area.strip(" -—:：")):
                candidate = part.strip(" -—:：")
                if self._is_likely_company_name(candidate):
                    return candidate
        return ""

    def _is_likely_company_name(self, candidate: str) -> bool:
        if len(candidate) < 2 or len(candidate) > 30:
            return False
        if self._is_unknown_company(candidate) or self._is_untrusted_text(candidate):
            return False
        if any(city in candidate for city in KNOWN_CITY_NAMES):
            return False
        blocked_fragments = (
            "岗位",
            "职位",
            "要求",
            "薪资",
            "经验",
            "本科",
            "硕士",
            "博士",
            "大专",
            "不限",
            "医疗",
            "健康",
            "制药",
            "生物",
            "互联网",
            "金融",
        )
        return not any(fragment in candidate for fragment in blocked_fragments)

    def _normalize_detail_refresh_result(
        self,
        platform: str,
        url: str,
        raw_result: object,
    ) -> ExtractedJobCandidate:
        raw = raw_result if isinstance(raw_result, dict) else {}
        if isinstance(raw.get("html"), str):
            raw = self._detail_payload_from_html(platform, url, str(raw["html"]))
        else:
            raw = {**raw, "url": self._clean(raw.get("url", "")) or url}
        jobs, _warnings = self._normalize_jobs(platform, [raw], 1)
        if not jobs:
            raise ValueError("The platform detail page did not return a readable job detail.")
        return jobs[0]

    def _detail_payload_from_html(self, platform: str, url: str, html: str) -> dict[str, object]:
        description = self._html_detail_text(html)
        body_text = self._html_to_text(html)
        detail_status = "detail_fetched" if description else "low_quality"
        return {
            "title": self._html_first_text(html, ("job-name", "job-title", "position-name", "position-title", "title")),
            "company": self._html_first_text(html, ("company-name", "company-title", "com-name", "company")),
            "city": self._html_first_text(html, ("job-area", "area", "city", "location", "address")),
            "salary": self._html_first_text(html, ("job-salary", "salary", "wage", "money")),
            "salary_candidates": [body_text, description],
            "detail_description": description,
            "description": description or body_text,
            "url": url,
            "job_type": "boss_browser" if platform == "boss" else "shixiseng_browser",
            "detail_status": detail_status,
            "detail_reason": (
                "Detail page HTML regression sample parsed."
                if detail_status == "detail_fetched"
                else "Detail page HTML was readable, but no JD block was found."
            ),
        }

    def _html_first_text(self, html: str, class_keywords: tuple[str, ...]) -> str:
        for value in self._html_texts_by_class(html, class_keywords):
            if value:
                return value
        return ""

    def _html_detail_text(self, html: str) -> str:
        values = self._html_texts_by_class(
            html,
            (
                "job-sec-text",
                "job-detail-content",
                "job-detail-section",
                "job-detail",
                "detail-content",
                "detail-section",
                "job-description",
                "position-detail",
                "description",
                "detail",
            ),
        )
        detail_markers = ("职位描述", "岗位职责", "任职要求", "工作内容", "岗位要求", "Responsibilities", "Requirements")
        marked_values = [value for value in values if any(marker in value for marker in detail_markers)]
        candidates = marked_values or values
        if candidates:
            return max(candidates, key=len)[:3000]
        body_text = self._html_to_text(html)
        if any(marker in body_text for marker in detail_markers):
            return body_text[:3000]
        return ""

    def _html_texts_by_class(self, html: str, class_keywords: tuple[str, ...]) -> list[str]:
        values: list[str] = []
        for keyword in class_keywords:
            pattern = re.compile(
                r"<(?P<tag>[a-zA-Z0-9]+)\b[^>]*class=[\"'][^\"']*"
                + re.escape(keyword)
                + r"[^\"']*[\"'][^>]*>(?P<body>.*?)</(?P=tag)>",
                re.IGNORECASE | re.DOTALL,
            )
            for match in pattern.finditer(html):
                text = self._html_to_text(match.group("body"))
                if text:
                    values.append(text)
        return list(dict.fromkeys(values))

    def _html_to_text(self, html: str) -> str:
        without_scripts = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", html, flags=re.IGNORECASE | re.DOTALL)
        without_tags = re.sub(r"<[^>]+>", " ", without_scripts)
        return self._clean(unescape(without_tags))

    def _best_description(self, raw: dict[str, object]) -> str:
        card_description = self._clean(raw.get("description", ""))
        detail_description = self._clean(raw.get("detail_description", ""))
        if self._is_better_detail_description(detail_description, card_description):
            return detail_description
        if card_description and not self._is_untrusted_text(card_description):
            return card_description
        if (
            detail_description
            and not self._is_untrusted_text(detail_description)
            and not self._is_loading_or_script_text(detail_description)
        ):
            return detail_description
        return ""

    def _is_better_detail_description(self, detail_description: str, card_description: str) -> bool:
        if (
            not detail_description
            or self._is_untrusted_text(detail_description)
            or self._is_loading_or_script_text(detail_description)
        ):
            return False
        detail_markers = ("职位描述", "岗位职责", "任职要求", "工作内容", "岗位要求", "Responsibilities", "Requirements")
        if any(marker in detail_description for marker in detail_markers) and len(detail_description) > len(card_description):
            return True
        return len(detail_description) >= max(120, len(card_description) + 40)

    def _is_loading_or_script_text(self, value: str) -> bool:
        cleaned = self._clean(value)
        if not cleaned:
            return False
        markers = (
            "BOSS\u6b63\u5728\u52a0\u8f7d\u4e2d",
            "function getCookie",
            "window.Promise",
            "var staticPath",
            "webpack",
            "京ICP",
        )
        return any(marker in cleaned for marker in markers)

    def _detail_diagnostics(self, raw: dict[str, object], description: str) -> tuple[str, str]:
        explicit_status = self._clean(raw.get("detail_status", ""))
        explicit_reason = self._clean(raw.get("detail_reason", ""))
        card_description = self._clean(raw.get("description", ""))
        detail_description = self._clean(raw.get("detail_description", ""))
        if explicit_status:
            if explicit_status == "detail_fetched" and detail_description and description == detail_description:
                return explicit_status, explicit_reason or self._default_detail_reason(explicit_status)
            if explicit_status == "detail_fetched" and (
                self._is_loading_or_script_text(detail_description)
                or not self._is_better_detail_description(detail_description, card_description)
            ):
                if card_description and description == card_description:
                    return "card_only", self._default_detail_reason("card_only")
                return "low_quality", self._default_detail_reason("low_quality")
            return explicit_status, explicit_reason or self._default_detail_reason(explicit_status)

        if self._is_better_detail_description(detail_description, card_description):
            return "detail_fetched", "详情页已补全岗位要求。"
        if detail_description and not self._is_untrusted_text(detail_description):
            return "low_quality", "详情页文本可读，但过短或缺少岗位职责/任职要求等关键词。"
        if card_description and description == card_description:
            return "card_only", "当前只读取到列表卡片，详情页未补全。"
        return "detail_blocked", "详情页没有返回可读内容，可能是未登录、风控、验证码或页面未加载完成。"

    def _default_detail_reason(self, detail_status: str) -> str:
        reasons = {
            "detail_fetched": "详情页已补全岗位要求。",
            "detail_blocked": "详情页没有返回可读内容，可能是未登录、风控、验证码或页面未加载完成。",
            "card_only": "当前只读取到列表卡片，详情页未补全。",
            "low_quality": "详情页或列表文本过短，岗位要求不完整。",
        }
        return reasons.get(detail_status, "详情补全状态未知。")

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
        text_quality_warnings: list[str] | None = None,
        failure_reason: str = "",
        suggestion: str = "",
    ) -> BrowserExtractionDiagnostics:
        return BrowserExtractionDiagnostics(
            tab_detected=tab_detected,
            websocket_detected=websocket_detected,
            matched_selector_counts=matched_selector_counts or {},
            candidate_card_count=candidate_card_count,
            extracted_job_count=extracted_job_count,
            text_quality_warnings=text_quality_warnings or [],
            failure_reason=failure_reason,
            suggestion=suggestion,
        )

    def _search_script(self, platform: str, keywords: list[str], city: str) -> str:
        keyword = " ".join(keyword.strip() for keyword in keywords if keyword.strip()).strip()
        search_url = self._search_url(platform, keyword, city)
        return f"""
(async () => {{
  const keyword = {json.dumps(keyword, ensure_ascii=False)};
  const city = {json.dumps(city.strip(), ensure_ascii=False)};
  const searchUrl = {json.dumps(search_url, ensure_ascii=False)};
  const textInputSelectors = [
    "input[name='query']",
    "input[name='keyword']",
    "input[placeholder*='职位']",
    "input[placeholder*='岗位']",
    "input[placeholder*='搜索']",
    ".search-input input",
    ".search-bar input"
  ];
  const cityInputSelectors = [
    "input[name='city']",
    "input[placeholder*='城市']",
    ".city input",
    ".city-select input"
  ];
  const buttonSelectors = [
    "button[type='submit']",
    ".search-btn",
    ".btn-search",
    "[class*='search-btn']",
    "button"
  ];
  const setValue = (selectors, value) => {{
    if (!value) return false;
    for (const selector of selectors) {{
      const input = document.querySelector(selector);
      if (!input) continue;
      input.focus?.();
      input.value = value;
      input.dispatchEvent(new Event("input", {{ bubbles: true }}));
      input.dispatchEvent(new Event("change", {{ bubbles: true }}));
      return true;
    }}
    return false;
  }};
  const keywordSet = setValue(textInputSelectors, keyword);
  const citySet = setValue(cityInputSelectors, city);
  let clicked = false;
  if ((keywordSet || citySet) && (!city || citySet)) {{
    for (const selector of buttonSelectors) {{
      const button = document.querySelector(selector);
      if (!button) continue;
      const label = (button.innerText || button.textContent || "").trim();
      if (!label || /搜|搜索|查询|确定/.test(label)) {{
        button.click();
        clicked = true;
        break;
      }}
    }}
  }}
  if (!clicked || (city && !citySet)) {{
    location.href = searchUrl;
  }}
  return {{ platform: {json.dumps(platform, ensure_ascii=False)}, keyword, city, clicked, url: searchUrl }};
}})()
"""

    def _search_url(self, platform: str, keyword: str, city: str) -> str:
        from urllib.parse import urlencode

        if platform == "boss":
            city_code = BOSS_CITY_CODES.get(city.strip(), city.strip())
            query = urlencode({"query": keyword, "city": city_code})
            return f"https://www.zhipin.com/web/geek/jobs?{query}"
        if platform == "shixiseng":
            query = urlencode({"keyword": keyword, "city": city})
            return f"https://www.shixiseng.com/interns?{query}"
        return "about:blank"

    def _open_job_script(self, url: str) -> str:
        return f"""
(() => {{
  const targetUrl = {json.dumps(url, ensure_ascii=False)};
  if (!targetUrl) return {{ opened: false, reason: "missing job url" }};
  try {{
    location.href = targetUrl;
    return {{ opened: true, url: targetUrl }};
  }} catch (error) {{
    return {{ opened: false, reason: String(error) }};
  }}
}})()
"""

    def _application_preview_script(self, platform: str, url: str) -> str:
        return f"""
(async () => {{
  const platform = {json.dumps(platform)};
  const targetUrl = {json.dumps(url, ensure_ascii=False)};
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const text = (node) => (node?.innerText || node?.textContent || "").replace(/\\s+/g, " ").trim();
  const absolute = (href) => {{
    try {{ return new URL(href || location.href, location.href).href; }} catch (_) {{ return href || location.href; }}
  }};
  const respond = (ready, status, action, evidence, buttonText = "") => ({{
    ready,
    status,
    action,
    evidence,
    button_text: buttonText,
    source_url: absolute(location.href || targetUrl)
  }});
  const bodyText = () => text(document.body).slice(0, 8000);
  const alreadyPattern = /已沟通|继续沟通|已投递|已申请|已报名|沟通中|投递成功|申请成功|已发送/i;
  const blockerPattern = /验证码|安全验证|请先登录|登录后|登录\\/注册|实名认证|绑定手机|异常访问/i;
  const applyPattern = platform === "boss"
    ? /立即沟通|继续沟通|投递简历|申请职位|立即申请|开聊|沟通/i
    : /投递简历|立即投递|申请职位|立即申请|报名|沟通/i;
  const labelFor = (node) => {{
    const pieces = [
      text(node),
      node?.getAttribute?.("aria-label") || "",
      node?.getAttribute?.("title") || "",
      node?.getAttribute?.("data-title") || "",
      node?.getAttribute?.("data-text") || "",
      node?.value || "",
      ...Object.values(node?.dataset || {{}})
    ];
    return pieces.join(" ").replace(/\\s+/g, " ").trim();
  }};
  await sleep(800);
  const pageText = bodyText();
  if (blockerPattern.test(pageText)) {{
    return respond(false, "blocked_by_platform", "preview", "platform requires login, captcha, or safety verification");
  }}
  if (alreadyPattern.test(pageText)) {{
    return respond(true, "already_applied", "already_confirmed", "platform page already shows applied/contacted state");
  }}
  const nodes = Array.from(document.querySelectorAll("button,a,[role='button'],.btn,[class*='btn'],[class*='button']"));
  for (const node of nodes) {{
    const label = labelFor(node);
    const disabled = node.disabled || node.getAttribute("aria-disabled") === "true" || /disabled/.test(String(node.className || ""));
    const visible = node.offsetParent !== null || node.getClientRects().length > 0;
    if (!label || disabled || !visible || label.length > 120 || !applyPattern.test(label)) continue;
    return respond(true, "ready", "preview", `found platform button: ${{label}}`, label);
  }}
  const chatInput = document.querySelector("textarea,[contenteditable='true'],.chat-input,[class*='chat-input'],[class*='message-input']");
  if (chatInput) {{
    return respond(true, "ready", "preview", "chat/apply panel is already open", "chat/input");
  }}
  return respond(false, "button_not_found", "preview", "no platform apply or chat button was found");
}})()
"""

    def _application_click_script(self, platform: str, url: str) -> str:
        return f"""
(async () => {{
  const platform = {json.dumps(platform)};
  const targetUrl = {json.dumps(url, ensure_ascii=False)};
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const text = (node) => (node?.innerText || node?.textContent || "").replace(/\\s+/g, " ").trim();
  const absolute = (href) => {{
    try {{ return new URL(href || location.href, location.href).href; }} catch (_) {{ return href || location.href; }}
  }};
  const respond = (confirmed, status, action, evidence) => ({{
    confirmed,
    status,
    action,
    evidence,
    source_url: absolute(location.href || targetUrl)
  }});
  const bodyText = () => text(document.body).slice(0, 6000);
  const alreadyPattern = /已沟通|继续沟通|已投递|已申请|已报名|沟通中|投递成功|申请成功|已发送/i;
  const blockerPattern = /验证码|安全验证|请先登录|登录后|登录\\/注册|实名认证|绑定手机|异常访问/i;
  const applyPattern = platform === "boss"
    ? /立即沟通|继续沟通|投递简历|申请职位|立即申请|开聊|沟通/i
    : /投递简历|立即投递|申请职位|立即申请|报名|沟通/i;
  await sleep(800);
  let pageText = bodyText();
  if (blockerPattern.test(pageText)) {{
    return respond(false, "blocked_by_platform", "none", "platform requires login, captcha, or safety verification");
  }}
  if (alreadyPattern.test(pageText)) {{
    return respond(true, "already_applied", "already_confirmed", "platform page already shows applied/contacted state");
  }}
  const nodes = Array.from(document.querySelectorAll("button,a,[role='button'],.btn,[class*='btn'],[class*='button']"));
  for (const node of nodes) {{
    const label = text(node);
    const disabled = node.disabled || node.getAttribute("aria-disabled") === "true" || /disabled/.test(node.className || "");
    const visible = node.offsetParent !== null || node.getClientRects().length > 0;
    if (!label || disabled || !visible || !applyPattern.test(label)) continue;
    node.scrollIntoView?.({{ block: "center", inline: "center" }});
    node.click();
    await sleep(1200);
    pageText = bodyText();
    if (blockerPattern.test(pageText)) {{
      return respond(false, "clicked_but_blocked", "clicked_apply", `clicked "${{label}}", but platform requires verification`);
    }}
    if (alreadyPattern.test(pageText)) {{
      return respond(true, "applied", "clicked_apply", `clicked platform button: ${{label}}`);
    }}
    const chatInput = document.querySelector("textarea,[contenteditable='true'],.chat-input,[class*='chat-input'],[class*='message-input']");
    if (chatInput) {{
      return respond(true, "applied", "clicked_apply", `clicked platform button and opened chat/apply panel: ${{label}}`);
    }}
    return respond(false, "clicked_unconfirmed", "clicked_apply", `clicked "${{label}}", but platform did not show applied/contacted state`);
  }}
  return respond(false, "button_not_found", "none", "no platform apply or chat button was found");
}})()
"""

    def _detail_refresh_script(self, platform: str, url: str) -> str:
        return f"""
(async () => {{
  const platform = {json.dumps(platform)};
  const targetUrl = {json.dumps(url, ensure_ascii=False)};
  const text = (node) => (node?.innerText || node?.textContent || "").replace(/\\s+/g, " ").trim();
  const absolute = (href) => {{
    try {{ return new URL(href || targetUrl, location.href).href; }} catch (_) {{ return href || targetUrl; }}
  }};
  const firstText = (root, selectors) => {{
    for (const selector of selectors) {{
      const value = text(root.querySelector(selector));
      if (value) return value;
    }}
    return "";
  }};
  const salaryRegex = /(?:\\d+(?:\\.\\d+)?\\s*[-~—到]\\s*\\d+(?:\\.\\d+)?\\s*[Kk万千元]+(?:\\s*[·.]?\\s*\\d+\\s*薪)?|\\d+\\s*[-~—到]\\s*\\d+\\s*(?:元|块)?\\s*\\/\\s*(?:天|日|月)|薪资面议|面议)/g;
  const titleSelectors = [
    ".job-name",
    ".job-title",
    ".position-name",
    ".position-title",
    ".name",
    ".title",
    "[class*='job-title']",
    "[class*='position-name']",
    "[class*='position-title']"
  ];
  const companySelectors = [
    ".boss-name",
    ".boss-info .boss-name",
    ".company-name",
    ".company",
    ".com-name",
    ".company-title",
    "[class*='company']",
    "[class*='com-name']"
  ];
  const citySelectors = [
    ".company-location",
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
    ".job-salary",
    ".money",
    ".wage",
    ".red",
    "[class*='salary']",
    "[class*='wage']"
  ];
  const detailSelectors = [
    ".job-sec-text",
    ".job-detail-box",
    ".job-detail-section",
    ".job-detail",
    ".job-detail-content",
    ".detail-section",
    ".detail-content",
    ".job-description",
    ".position-detail",
    ".job_msg",
    "[class*='job-sec']",
    "[class*='description']",
    "[class*='detail']"
  ];
  const isLoadingShellText = (value) => /BOSS\u6b63\u5728\u52a0\u8f7d\u4e2d|function getCookie|window\.Promise|var staticPath|webpack|ICP/i.test(value || "");
  const detailKeywordPattern = /职位描述|岗位职责|任职要求|工作内容|岗位要求|Responsibilities|Requirements|Job Description/i;
  const collectCandidates = (root, selectors) => {{
    const values = [];
    for (const selector of selectors) {{
      for (const node of Array.from(root.querySelectorAll(selector))) {{
        const nodeText = text(node);
        if (nodeText) values.push(nodeText);
        for (const attr of ["title", "aria-label", "data-salary", "data-wage", "data-value"]) {{
          const attrValue = node.getAttribute?.(attr);
          if (attrValue) values.push(attrValue);
        }}
        for (const nearby of [node.parentElement, node.previousElementSibling, node.nextElementSibling]) {{
          const nearbyText = text(nearby);
          if (nearbyText) values.push(nearbyText);
        }}
      }}
    }}
    const fullText = text(root);
    if (fullText) values.push(fullText);
    return [...new Set(values)].slice(0, 24);
  }};
  const pickDetailText = (doc) => {{
    const values = [];
    for (const selector of detailSelectors) {{
      for (const node of Array.from(doc.querySelectorAll(selector))) {{
        const value = text(node);
        if (value) values.push(value);
      }}
    }}
    for (const node of Array.from(doc.body?.querySelectorAll("section,article,div,p") || [])) {{
      const value = text(node);
      if (value && value.length > 50 && detailKeywordPattern.test(value)) values.push(value);
    }}
    const uniqueValues = [...new Set(values)].sort((left, right) => right.length - left.length);
    const picked = uniqueValues.find((value) => value.length > 80) || uniqueValues[0] || text(doc.body);
    const result = (picked || "").slice(0, 3000);
    return isLoadingShellText(result) ? "" : result;
  }};
  const blocked = (reason) => ({{
    title: targetUrl,
    company: "",
    city: "",
    salary: "",
    salary_candidates: [],
    detail_description: "",
    description: "",
    url: absolute(targetUrl),
    job_type: platform === "boss" ? "boss_browser" : "shixiseng_browser",
    detail_status: "detail_blocked",
    detail_reason: reason
  }});
  if (!targetUrl) return blocked("Job has no source URL.");
  try {{
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 3500);
    const response = await fetch(targetUrl, {{ credentials: "include", signal: controller.signal }});
    clearTimeout(timer);
    if (!response.ok) return blocked(`Detail request failed: HTTP ${{response.status}}.`);
    const html = await response.text();
    const doc = new DOMParser().parseFromString(html, "text/html");
    const description = pickDetailText(doc);
    const bodyText = text(doc.body);
    const salaryCandidates = collectCandidates(doc.body || doc, salarySelectors)
      .concat(bodyText.match(salaryRegex) || [])
      .concat(description.match(salaryRegex) || []);
    return {{
      title: firstText(doc, titleSelectors) || doc.title || targetUrl,
      company: firstText(doc, companySelectors),
      city: firstText(doc, citySelectors),
      salary: firstText(doc, salarySelectors),
      salary_candidates: [...new Set(salaryCandidates)].slice(0, 24),
      detail_description: description,
      description,
      url: absolute(targetUrl),
      job_type: platform === "boss" ? "boss_browser" : "shixiseng_browser",
      detail_status: description ? "detail_fetched" : "low_quality",
      detail_reason: description ? "Detail page refreshed for this job." : "Detail page loaded, but no readable JD was found."
    }};
  }} catch (_) {{
    return blocked("Detail page refresh failed; the platform may have blocked the request or the page is still loading.");
  }}
}})()
"""

    def _extract_script(self, platform: str, limit: int) -> str:
        return f"""
(async () => {{
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
  const collectTextCandidates = (root, fieldSelectors) => {{
    const values = [];
    for (const selector of fieldSelectors) {{
      for (const node of Array.from(root.querySelectorAll(selector))) {{
        const nodeText = text(node);
        if (nodeText) values.push(nodeText);
        for (const attr of ["title", "aria-label", "data-salary", "data-wage", "data-value"]) {{
          const attrValue = node.getAttribute?.(attr);
          if (attrValue) values.push(attrValue);
        }}
        for (const nearby of [node.parentElement, node.previousElementSibling, node.nextElementSibling]) {{
          const nearbyText = text(nearby);
          if (nearbyText) values.push(nearbyText);
        }}
      }}
    }}
    for (const attr of ["title", "aria-label", "data-salary", "data-wage", "data-value"]) {{
      const attrValue = root.getAttribute?.(attr);
      if (attrValue) values.push(attrValue);
    }}
    const fullText = text(root);
    if (fullText) values.push(fullText);
    return [...new Set(values)].slice(0, 12);
  }};
  const salaryRegex = /(?:\\d+(?:\\.\\d+)?\\s*[-~—到]\\s*\\d+(?:\\.\\d+)?\\s*[Kk万千元]+(?:\\s*[·.]?\\s*\\d+\\s*薪)?|\\d+\\s*[-~—到]\\s*\\d+\\s*(?:元|块)?\\s*\\/\\s*(?:天|日|月)|薪资面议|面议)/g;
  const scriptSalaryCandidates = (hint) => {{
    const values = [];
    const normalizedHint = (hint || "").slice(0, 32);
    for (const script of Array.from(document.scripts || [])) {{
      const content = script.textContent || "";
      if (!content || (normalizedHint && !content.includes(normalizedHint) && content.length > 20000)) continue;
      values.push(...(content.match(salaryRegex) || []));
    }}
    return [...new Set(values)].slice(0, 20);
  }};
  const selectors = platform === "boss"
    ? [
        ".job-card-wrapper",
        ".job-card-wrap",
        ".job-card-box",
        ".job-card-body",
        ".job-card-container",
        ".job-list-box li",
        ".search-job-result li",
        ".job-list-wrapper li",
        ".rec-job-list li",
        ".job-primary",
        ".job-card-left",
        "[class*='job-card']",
        "[class*='jobCard']",
        "[class*='JobCard']",
        "[class*='job-list'] li",
        "[class*='job-list'] [class*='item']",
        "[class*='jobList'] [class*='item']",
        "[class*='JobList'] [class*='item']",
        "[class*='search-job']",
        "[class*='searchJob']",
        "[class*='SearchJob']",
        "[ka*='search_list']",
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
  const cardSnapshots = [];
  const seenCards = new Set();
  const seenCardKeys = new Set();
  const seenSnapshotKeys = new Set();
  const matchedSelectorCounts = {{}};
  const countCandidateNodes = () => selectors.reduce((total, selector) => total + document.querySelectorAll(selector).length, 0);
  const waitForCandidateCards = async () => {{
    for (let attempt = 0; attempt < 12; attempt += 1) {{
      if (countCandidateNodes() > 0) return true;
      await new Promise((resolve) => setTimeout(resolve, 250));
    }}
    return false;
  }};
  const fallbackLinkSelector = platform === "boss"
    ? "a[href*='job_detail'],a[href*='/job_detail/']"
    : "a[href*='intern'],a[href*='/intern/'],a[href*='job']";
  const hasSalaryText = (value) => {{
    salaryRegex.lastIndex = 0;
    return salaryRegex.test(value || "");
  }};
  const bossCardRootFromLink = (link) => {{
    if (platform !== "boss" || !link) return link;
    let current = link;
    let best = link;
    for (let depth = 0; current && depth < 8; depth += 1) {{
      const value = text(current);
      const hasJobLink = Boolean(current.querySelector?.(fallbackLinkSelector)) || current.matches?.(fallbackLinkSelector);
      const hasSalary = hasSalaryText(value) || Boolean(current.querySelector?.(".salary,.job-salary,.red,[class*='salary'],[class*='wage']"));
      const hasCompany = Boolean(current.querySelector?.(".boss-name,.company-name,.company-text,.company,[class*='company'],[class*='com-name']"));
      const usefulSize = value.length >= 18 && value.length <= 1600;
      if (usefulSize && hasJobLink && (hasSalary || hasCompany)) {{
        best = current;
        break;
      }}
      current = current.parentElement;
    }}
    return best || link;
  }};
  const cardKey = (card) => {{
    const link = card.matches?.(fallbackLinkSelector) ? card : card.querySelector?.(fallbackLinkSelector) || card.querySelector?.("a[href]");
    const href = absolute(link?.getAttribute?.("href") || "");
    return href || text(card).slice(0, 240);
  }};
  const snapshotKey = (payload) => payload.url || (payload.description || "").slice(0, 240);
  const snapshotCandidateCard = (card) => {{
    const link = card.matches?.(fallbackLinkSelector) ? card : card.querySelector?.(fallbackLinkSelector) || card.querySelector?.("a[href]");
    const description = text(card).slice(0, 1200);
    const url = absolute(link?.getAttribute?.("href") || "");
    return {{
      title: text(link) || description.slice(0, 80),
      company: "",
      company_candidates: [description],
      city: "",
      salary: "",
      salary_candidates: [description],
      detail_description: "",
      detail_status: "card_snapshot",
      detail_reason: "滚动过程中已保存岗位卡片快照，避免虚拟列表复用 DOM 节点导致漏抓。",
      detail_salary_candidates: [],
      description,
      url,
      job_type: platform === "boss" ? "boss_browser" : "shixiseng_browser"
    }};
  }};
  const pushCard = (node) => {{
    const recovered = platform === "boss" && node.matches?.(fallbackLinkSelector) ? bossCardRootFromLink(node) : null;
    const card = recovered || node.closest?.(cardRootSelector) || node;
    const key = cardKey(card);
    if (!seenCards.has(card) && (!key || !seenCardKeys.has(key))) {{
      seenCards.add(card);
      if (key) seenCardKeys.add(key);
      cards.push(card);
      const snapshot = snapshotCandidateCard(card);
      const keyForSnapshot = snapshotKey(snapshot);
      if (snapshot.description && (!keyForSnapshot || !seenSnapshotKeys.has(keyForSnapshot))) {{
        if (keyForSnapshot) seenSnapshotKeys.add(keyForSnapshot);
        cardSnapshots.push(snapshot);
      }}
    }}
  }};
  const collectCandidateCards = () => {{
    for (const selector of selectors) {{
      const nodes = Array.from(document.querySelectorAll(selector));
      matchedSelectorCounts[selector] = Math.max(matchedSelectorCounts[selector] || 0, nodes.length);
      for (const node of nodes) pushCard(node);
    }}
    const fallbackLinks = Array.from(document.querySelectorAll(fallbackLinkSelector));
    matchedSelectorCounts.fallback_links = Math.max(matchedSelectorCounts.fallback_links || 0, fallbackLinks.length);
    for (const link of fallbackLinks) pushCard(link);
  }};
  const scrollForMoreCards = async () => {{
    if (platform !== "boss") return;
    const scrollContainers = [
      document.scrollingElement,
      document.documentElement,
      document.body,
      ...Array.from(document.querySelectorAll("[class*='job-list'],[class*='jobList'],[class*='search-job'],[class*='searchJob'],[class*='list'],[class*='scroll']"))
    ].filter(Boolean);
    for (let round = 0; round < 4 && cards.length < limit; round += 1) {{
      collectCandidateCards();
      for (const scroller of scrollContainers) {{
        const maxTop = Math.max(0, (scroller.scrollHeight || 0) - (scroller.clientHeight || 0));
        const currentTop = scroller.scrollTop || 0;
        if (maxTop > currentTop + 20) {{
          scroller.scrollTop = Math.min(maxTop, currentTop + 900);
        }}
      }}
      window.scrollBy?.(0, 900);
      await new Promise((resolve) => setTimeout(resolve, 350));
    }}
    collectCandidateCards();
  }};
  await waitForCandidateCards();
  collectCandidateCards();
  await scrollForMoreCards();
  collectCandidateCards();
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
    ".boss-name",
    ".boss-info .boss-name",
    ".company-name",
    ".company-text",
    ".com-name",
    ".company",
    ".company-title",
    "[class*='company']",
    "[class*='com-name']"
  ];
  const citySelectors = [
    ".company-location",
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
  const detailSelectors = [
    ".job-sec-text",
    ".job-detail-box",
    ".job-detail-section",
    ".job-detail",
    ".job-detail-content",
    ".detail-section",
    ".detail-content",
    ".job-description",
    ".job-sec",
    ".position-detail",
    ".job_msg",
    "[class*='job-sec']",
    "[class*='description']",
    "[class*='detail']"
  ];
  const isLoadingShellText = (value) => /BOSS\u6b63\u5728\u52a0\u8f7d\u4e2d|function getCookie|window\.Promise|var staticPath|webpack|ICP/i.test(value || "");
  const detailKeywordPattern = /职位描述|岗位职责|任职要求|工作内容|岗位要求|Responsibilities|Requirements|Job Description/i;
  const pickDetailText = (doc) => {{
    const values = [];
    for (const selector of detailSelectors) {{
      for (const node of Array.from(doc.querySelectorAll(selector))) {{
        const value = text(node);
        if (value) values.push(value);
      }}
    }}
    for (const node of Array.from(doc.body?.querySelectorAll("section,article,div,p") || [])) {{
      const value = text(node);
      if (value && value.length > 50 && detailKeywordPattern.test(value)) values.push(value);
    }}
    const uniqueValues = [...new Set(values)].sort((left, right) => right.length - left.length);
    const picked = uniqueValues.find((value) => value.length > 80) || uniqueValues[0] || text(doc.body);
    const result = (picked || "").slice(0, 2400);
    return isLoadingShellText(result) ? "" : result;
  }};
  const collectDetailSalaryCandidates = (doc, detailText) => {{
    const values = [];
    if (doc.body) values.push(...collectTextCandidates(doc.body, salarySelectors));
    const bodyText = text(doc.body);
    values.push(...(bodyText.match(salaryRegex) || []));
    values.push(...((detailText || "").match(salaryRegex) || []));
    return [...new Set(values.map((value) => String(value || "").slice(0, 500)))].slice(0, 20);
  }};
  const fetchDetail = async (url) => {{
    if (!url || url === location.href) {{
      return {{ description: "", detail_status: "card_only", detail_reason: "没有可用详情页链接，只能读取列表卡片。", detail_salary_candidates: [] }};
    }}
    try {{
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 1800);
      const response = await fetch(url, {{ credentials: "include", signal: controller.signal }});
      clearTimeout(timer);
      if (!response.ok) {{
        return {{
          description: "",
          detail_status: "detail_blocked",
          detail_reason: `详情页请求失败：HTTP ${{response.status}}。`,
          detail_salary_candidates: []
        }};
      }}
      const html = await response.text();
      const doc = new DOMParser().parseFromString(html, "text/html");
      const description = pickDetailText(doc);
      return {{
        description,
        detail_status: description ? "detail_fetched" : "low_quality",
        detail_reason: description ? "详情页已补全岗位要求。" : "详情页返回成功，但没有找到可读岗位要求。",
        detail_salary_candidates: collectDetailSalaryCandidates(doc, description)
      }};
    }} catch (_) {{
      return {{
        description: "",
        detail_status: "detail_blocked",
        detail_reason: "详情页读取失败，可能被平台拦截或页面仍在加载。",
        detail_salary_candidates: []
      }};
    }}
  }};
  const livePayloads = await Promise.all(cards.slice(0, limit * 4).map(async (card) => {{
    const link = preferredLink(card);
    const url = absolute(link?.getAttribute("href"));
    const cardDescription = text(card).slice(0, 1200);
    const companyCandidates = collectTextCandidates(card, companySelectors).concat([cardDescription]);
    const detail = await fetchDetail(url);
    const description = detail.description || cardDescription;
    return {{
      title: firstText(card, titleSelectors) || text(link) || cardDescription.slice(0, 80),
      company: firstText(card, companySelectors),
      company_candidates: [...new Set(companyCandidates)].slice(0, 24),
      city: firstText(card, citySelectors),
      salary: firstText(card, salarySelectors),
      salary_candidates: collectTextCandidates(card, salarySelectors).concat(detail.detail_salary_candidates || [], scriptSalaryCandidates(description)),
      detail_description: detail.description,
      detail_status: detail.detail_status,
      detail_reason: detail.detail_reason,
      detail_salary_candidates: detail.detail_salary_candidates || [],
      description,
      url,
      job_type: platform === "boss" ? "boss_browser" : "shixiseng_browser"
    }};
  }}));
  const livePayloadByKey = new Map();
  for (const payload of livePayloads) {{
    const key = snapshotKey(payload);
    if (key) livePayloadByKey.set(key, payload);
  }}
  const rawPayloads = [];
  const seenPayloadKeys = new Set();
  for (const payload of cardSnapshots.slice(0, limit * 4)) {{
    const key = snapshotKey(payload);
    if (key && seenPayloadKeys.has(key)) continue;
    if (key) seenPayloadKeys.add(key);
    const livePayload = key ? livePayloadByKey.get(key) : null;
    rawPayloads.push(livePayload ? {{ ...payload, ...livePayload, description: livePayload.description || payload.description }} : payload);
  }}
  for (const payload of livePayloads) {{
    const key = snapshotKey(payload);
    if (key && seenPayloadKeys.has(key)) continue;
    if (key) seenPayloadKeys.add(key);
    rawPayloads.push(payload);
  }}
  const rawJobs = rawPayloads.slice(0, limit * 4);
  const jobs = rawJobs.filter((job) => job.title || job.description).slice(0, limit);
  return {{
    jobs,
    diagnostics: {{
      matched_selector_counts: matchedSelectorCounts,
      candidate_card_count: Math.max(cards.length, cardSnapshots.length)
    }}
  }};
}})()
"""

    def _clean(self, value: object) -> str:
        return " ".join(str(value or "").translate(BOSS_PRIVATE_DIGIT_TRANSLATION).split())

    def _trusted_field(
        self,
        value: object,
        field_name: str,
        warnings: list[str],
        job_index: int,
        fallback: str = "",
    ) -> str:
        cleaned = self._clean(value)
        if not cleaned:
            return fallback
        if self._is_untrusted_text(cleaned):
            warnings.append(f"hid polluted {field_name} for job #{job_index}")
            return fallback
        return cleaned

    def _is_untrusted_text(self, value: str) -> bool:
        cleaned = self._clean(value)
        if not cleaned:
            return True
        visible_chars = [char for char in cleaned if not char.isspace()]
        readable_chars = re.findall(r"[A-Za-z0-9\u4e00-\u9fff]", cleaned)
        has_pollution_marker = bool(re.search(r"[□�\ue000-\uf8ff]", cleaned))
        if not readable_chars:
            return True
        placeholder_count = cleaned.count("口")
        if placeholder_count >= 3 and placeholder_count / max(len(visible_chars), 1) > 0.25:
            return True
        if has_pollution_marker and len(readable_chars) / max(len(visible_chars), 1) < 0.6:
            return True
        question_marks = cleaned.count("?")
        if question_marks >= 2 and question_marks / max(len(visible_chars), 1) > 0.3:
            return True
        return False

    def _sanitize_url(self, raw_url: str) -> str:
        if not raw_url:
            return ""
        parsed = urlparse(raw_url)
        return parsed._replace(query="", fragment="").geturl()

    def _platform_label(self, platform: str) -> str:
        labels = {"boss": "BOSS 直聘", "shixiseng": "实习僧"}
        return labels.get(platform, platform)

    def _normalize_cdp_url(self, value: str) -> str | None:
        return resolve_cdp_url(value, opener=urlopen)
