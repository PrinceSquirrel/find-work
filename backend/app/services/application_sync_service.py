from __future__ import annotations

import json
import os
import re
from collections import deque
from dataclasses import dataclass
from urllib.parse import urlparse

from app.agents.application_tracker import ALLOWED_TRANSITIONS
from app.schemas import (
    ApplicationRecord,
    ApplicationStatus,
    ApplicationSyncDiagnostic,
    ApplicationSyncProposal,
    ApplicationSyncResponse,
)
import app.services.browser_job_extractor_service as browser_job_extractor_service
from app.services.platform_session_service import PLATFORM_HOSTS, resolve_cdp_url
from app.storage import SQLiteStore


@dataclass
class SyncPageItem:
    platform: str
    text: str
    source_url: str


class ApplicationSyncService:
    def __init__(self, store: SQLiteStore, cdp_url: str | None = None):
        self.store = store
        self.cdp_url = resolve_cdp_url(
            cdp_url or os.getenv("BROWSER_CDP_URL", ""),
            opener=browser_job_extractor_service.urlopen,
        )
        self.runtime_client = browser_job_extractor_service.CdpRuntimeClient()

    def sync(self, platforms: list[str], limit: int) -> ApplicationSyncResponse:
        applications = self.store.list_applications()
        if not self.cdp_url:
            return ApplicationSyncResponse(
                status="not_configured",
                diagnostics=[
                    self._diagnostic(
                        platform,
                        "not_configured",
                        failure_reason="未配置 BROWSER_CDP_URL",
                        suggestion="先点击前端的“启动 CDP 浏览器”，并在该浏览器中打开 BOSS/实习僧页面。",
                    )
                    for platform in platforms
                ],
                message="未配置浏览器 CDP，未读取任何平台页面。",
            )

        try:
            tabs = self._load_tabs()
        except (OSError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            return ApplicationSyncResponse(
                status="cdp_unreachable",
                diagnostics=[
                    self._diagnostic(
                        platform,
                        "cdp_unreachable",
                        failure_reason="无法连接浏览器 CDP",
                        suggestion="确认 CDP 浏览器仍在运行，并且端口是 9222。",
                    )
                    for platform in platforms
                ],
                message=str(exc),
            )

        diagnostics: list[ApplicationSyncDiagnostic] = []
        items: list[SyncPageItem] = []
        for platform in platforms:
            platform_items, diagnostic = self._read_platform_items(platform, tabs, limit)
            diagnostics.append(diagnostic)
            items.extend(platform_items)

        proposals = self._build_proposals(applications, items)
        top_status = "completed" if any(diagnostic.status in {"success", "empty"} for diagnostic in diagnostics) else "no_platform_tabs"
        return ApplicationSyncResponse(
            status=top_status,
            proposals=proposals,
            diagnostics=diagnostics,
            message="只读同步完成；返回的是人工确认建议，未覆盖任何投递状态。",
        )

    def _load_tabs(self) -> list[dict[str, str]]:
        with browser_job_extractor_service.urlopen(f"{self.cdp_url}/json", timeout=2) as response:
            payload = response.read().decode("utf-8")
        tabs = json.loads(payload)
        return tabs if isinstance(tabs, list) else []

    def _read_platform_items(
        self,
        platform: str,
        tabs: list[dict[str, str]],
        limit: int,
    ) -> tuple[list[SyncPageItem], ApplicationSyncDiagnostic]:
        hosts = PLATFORM_HOSTS.get(platform)
        if not hosts:
            return [], self._diagnostic(
                platform,
                "unsupported_platform",
                failure_reason="不支持的平台",
                suggestion="当前仅支持 boss 和 shixiseng。",
            )

        tab = self._find_platform_tab(tabs, hosts)
        if tab is None:
            return [], self._diagnostic(
                platform,
                "tab_not_found",
                failure_reason="未检测到平台标签页",
                suggestion=f"请在 CDP 浏览器中打开 {platform} 的投递/沟通页面后再同步。",
            )

        source_url = self._sanitize_url(tab.get("url", ""))
        websocket_url = tab.get("webSocketDebuggerUrl")
        if not websocket_url:
            return [], self._diagnostic(
                platform,
                "websocket_missing",
                source_url=source_url,
                tab_detected=True,
                failure_reason="平台标签页未暴露 webSocketDebuggerUrl",
                suggestion="请重启 CDP 浏览器后再刷新会话。",
            )

        try:
            raw_result = self.runtime_client.evaluate(websocket_url, self._sync_script(limit))
        except (OSError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            return [], self._diagnostic(
                platform,
                "sync_failed",
                source_url=source_url,
                tab_detected=True,
                websocket_detected=True,
                failure_reason="页面同步脚本执行失败",
                suggestion=f"确认页面已加载完成；错误：{exc}",
            )

        raw_items = raw_result.get("items", []) if isinstance(raw_result, dict) else []
        runtime_diagnostics = raw_result.get("diagnostics", {}) if isinstance(raw_result, dict) else {}
        items = [
            SyncPageItem(
                platform=platform,
                text=self._clean(item.get("text", "")),
                source_url=self._sanitize_url(item.get("url", "") or source_url),
            )
            for item in raw_items
            if isinstance(item, dict) and self._clean(item.get("text", ""))
        ][:limit]
        return items, self._diagnostic(
            platform,
            "success" if items else "empty",
            source_url=source_url,
            tab_detected=True,
            websocket_detected=True,
            candidate_item_count=int(runtime_diagnostics.get("candidate_item_count", len(items)) or 0),
            matched_status_keywords=runtime_diagnostics.get("matched_status_keywords", {}),
            failure_reason="" if items else "当前页面没有读到可同步的投递状态文本",
            suggestion="" if items else "请打开平台的投递记录、沟通列表或岗位沟通详情页后再同步。",
        )

    def _build_proposals(
        self,
        applications: list[ApplicationRecord],
        items: list[SyncPageItem],
    ) -> list[ApplicationSyncProposal]:
        best_by_application: dict[int, ApplicationSyncProposal] = {}
        for item in items:
            detected_status = self._infer_status(item.text)
            if detected_status is None:
                continue
            for record in applications:
                if record.id is None or record.platform != item.platform:
                    continue
                confidence = self._match_confidence(record, item.text)
                if confidence < 0.55:
                    continue
                suggested_status = self._next_legal_status(record.current_status, detected_status)
                if suggested_status == record.current_status:
                    continue
                proposal = ApplicationSyncProposal(
                    application_id=record.id,
                    platform=record.platform,
                    company=record.company,
                    title=record.title,
                    current_status=record.current_status,
                    detected_status=detected_status,
                    suggested_status=suggested_status,
                    confidence=confidence,
                    evidence=item.text[:240],
                    source_url=item.source_url,
                    note=(
                        f"只读同步建议：页面检测到 {detected_status.value}，"
                        f"建议人工确认后更新为 {suggested_status.value}。"
                    ),
                )
                previous = best_by_application.get(record.id)
                if previous is None or proposal.confidence > previous.confidence:
                    best_by_application[record.id] = proposal
        return list(best_by_application.values())

    def _infer_status(self, text: str) -> ApplicationStatus | None:
        keyword_groups = [
            (ApplicationStatus.REJECTED, ("不合适", "拒绝", "未通过")),
            (ApplicationStatus.CLOSED, ("已结束", "结束沟通", "关闭")),
            (ApplicationStatus.INTERVIEW, ("面试", "约面", "面邀")),
            (ApplicationStatus.ASSESSMENT, ("笔试", "测评", "测试")),
            (ApplicationStatus.REPLIED, ("已回复", "回复", "沟通", "约聊", "消息")),
            (ApplicationStatus.READ, ("已读", "已查看", "查看了")),
        ]
        for status, keywords in keyword_groups:
            if any(keyword in text for keyword in keywords):
                return status
        return None

    def _next_legal_status(
        self,
        current_status: ApplicationStatus,
        detected_status: ApplicationStatus,
    ) -> ApplicationStatus:
        if current_status == detected_status:
            return current_status
        if detected_status in ALLOWED_TRANSITIONS.get(current_status, set()):
            return detected_status

        queue: deque[tuple[ApplicationStatus, list[ApplicationStatus]]] = deque([(current_status, [current_status])])
        visited = {current_status}
        while queue:
            status, path = queue.popleft()
            for next_status in ALLOWED_TRANSITIONS.get(status, set()):
                if next_status in visited:
                    continue
                next_path = [*path, next_status]
                if next_status == detected_status:
                    return next_path[1] if len(next_path) > 1 else current_status
                visited.add(next_status)
                queue.append((next_status, next_path))
        return current_status

    def _match_confidence(self, record: ApplicationRecord, text: str) -> float:
        normalized_text = self._normalize_for_match(text)
        confidence = 0.1
        if self._normalize_for_match(record.company) in normalized_text:
            confidence += 0.55
        title = self._normalize_for_match(record.title)
        if title and title in normalized_text:
            confidence += 0.35
        else:
            title_terms = [term for term in re.split(r"[-_/\\s]+", record.title) if len(term) >= 2]
            if any(self._normalize_for_match(term) in normalized_text for term in title_terms):
                confidence += 0.15
        return round(min(confidence, 1.0), 4)

    def _sync_script(self, limit: int) -> str:
        return f"""
(() => {{
  const marker = "application-sync-readonly";
  const limit = {limit};
  const text = (node) => (node?.innerText || node?.textContent || "").replace(/\\s+/g, " ").trim();
  const absolute = (href) => {{
    try {{ return new URL(href || location.href, location.href).href; }} catch (_) {{ return href || location.href; }}
  }};
  const keywords = ["已读", "已查看", "查看了", "已回复", "回复", "沟通", "约聊", "消息", "面试", "约面", "面邀", "笔试", "测评", "不合适", "拒绝", "未通过", "已结束", "结束沟通", "关闭"];
  const roots = Array.from(document.querySelectorAll("li,article,section,div[class*='card'],div[class*='job'],div[class*='chat'],div[class*='message'],div[class*='dialog'],div[class*='item']"));
  const seen = new Set();
  const matchedStatusKeywords = {{}};
  const items = [];
  for (const keyword of keywords) matchedStatusKeywords[keyword] = 0;
  for (const root of roots) {{
    const value = text(root);
    if (!value || value.length > 1500) continue;
    const matched = keywords.filter((keyword) => value.includes(keyword));
    if (!matched.length || seen.has(value)) continue;
    seen.add(value);
    for (const keyword of matched) matchedStatusKeywords[keyword] += 1;
    const link = root.matches?.("a[href]") ? root : root.querySelector("a[href]");
    items.push({{ text: value.slice(0, 800), url: absolute(link?.getAttribute("href")) }});
    if (items.length >= limit) break;
  }}
  return {{
    marker,
    items,
    diagnostics: {{
      candidate_item_count: items.length,
      matched_status_keywords: matchedStatusKeywords
    }}
  }};
}})()
"""

    def _find_platform_tab(self, tabs: list[dict[str, str]], hosts: list[str]) -> dict[str, str] | None:
        for tab in tabs:
            parsed = urlparse(tab.get("url", ""))
            hostname = parsed.hostname or ""
            if tab.get("type") == "page" and any(hostname == host or hostname.endswith(f".{host}") for host in hosts):
                return tab
        return None

    def _diagnostic(
        self,
        platform: str,
        status: str,
        *,
        source_url: str | None = None,
        tab_detected: bool = False,
        websocket_detected: bool = False,
        candidate_item_count: int = 0,
        matched_status_keywords: dict[str, int] | None = None,
        failure_reason: str = "",
        suggestion: str = "",
    ) -> ApplicationSyncDiagnostic:
        return ApplicationSyncDiagnostic(
            platform=platform,
            status=status,
            source_url=source_url,
            tab_detected=tab_detected,
            websocket_detected=websocket_detected,
            candidate_item_count=candidate_item_count,
            matched_status_keywords=matched_status_keywords or {},
            failure_reason=failure_reason,
            suggestion=suggestion,
        )

    def _sanitize_url(self, raw_url: str) -> str:
        if not raw_url:
            return ""
        parsed = urlparse(raw_url)
        return parsed._replace(query="", fragment="").geturl()

    def _normalize_cdp_url(self, value: str) -> str | None:
        value = value.strip().rstrip("/")
        if not value:
            return None
        if value.startswith(("http://", "https://")):
            return value
        return f"http://{value}"

    def _normalize_for_match(self, value: str) -> str:
        return "".join(str(value or "").lower().split())

    def _clean(self, value: object) -> str:
        return " ".join(str(value or "").split())
