"""Bounded greeting preparation and a separate, user-approved platform action queue."""
from __future__ import annotations

import json
import re
import sqlite3
from threading import Lock
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from app.services.boss_greeting_service import BossGreetingService, ORIGIN
from app.services.llm_client_service import LLMClientUnavailable
from app.services.platform_session_service import PLATFORM_HOSTS


class BatchJobsRequest(BaseModel):
    job_ids: list[Annotated[int, Field(strict=True, gt=0)]] = Field(min_length=1, max_length=8)


class BatchPlatformRequest(BatchJobsRequest):
    confirmed: Literal[True]


class ReviewedGreeting(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: Annotated[int, Field(strict=True, gt=0)]
    text: Annotated[str, Field(strict=True, min_length=1, max_length=180)]

    @field_validator("text")
    @classmethod
    def exact_reviewed_text(cls, value: str) -> str:
        if value != value.strip() or re.search(r"[\x00-\x09\x0b-\x1f\x7f]", value):
            raise ValueError("招呼语不能有首尾空白或不可打印控制字符。")
        return value


class BatchGreetingSendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[ReviewedGreeting] = Field(min_length=1, max_length=8)
    confirmed: StrictBool

    @model_validator(mode="after")
    def approved_distinct_jobs(self):
        if self.confirmed is not True or len({row.job_id for row in self.items}) != len(self.items):
            raise ValueError("发送前必须确认，且同一岗位不能重复提交。")
        return self


def is_platform_job(job) -> bool:
    url = urlparse(job.url)
    expected = {"boss": "/job_detail/", "shixiseng": "/intern/"}.get(job.platform)
    return bool(expected and url.scheme == "https" and url.username is None and url.password is None
                and any(url.hostname == host or (url.hostname or "").endswith("." + host)
                        for host in PLATFORM_HOSTS[job.platform])
                and url.path.startswith(expected) and url.path != expected)


class JobBatchService:
    def __init__(self, jobs, evidence):
        self.jobs = jobs
        self.evidence = evidence
        self.lock = Lock()

    def prepare(self, job_ids: list[int]) -> dict:
        with self.lock:
            config = self.jobs.store.get_agent_model_route("ApplicationWriterAgent")
            route = self.jobs.model_router.route_for_agent("ApplicationWriterAgent", config)
            return {"items": [self._greeting(job_id, config, route.mode) for job_id in dict.fromkeys(job_ids)]}

    def _greeting(self, job_id, config, mode) -> dict:
        base = {"job_id": job_id, "skill_id": "application.greeting"}
        try:
            job = self.jobs.store.get_job(job_id)
            if job.detail_status not in {"detail_fetched", "manual_filled"} or not job.description.strip():
                if is_platform_job(job):
                    self.jobs.refresh_job_detail(job_id)
                    job = self.jobs.store.get_job(job_id)
            if job.detail_status not in {"detail_fetched", "manual_filled"} or not job.description.strip():
                return {**base, "status": "needs_jd", "message": "缺少完整 JD，请在岗位详情中刷新或补充正文。"}
            recommendations = self.evidence.recommend_cards(job_id)
            cards = [item.card for item in recommendations if item.score >= 40 and item.card.category != "education"
                     and (item.card.provenance_type != "document" or item.card.quote_verified)]
            if mode == "external":
                result = self.jobs.llm_client.generate_job_greeting(config, job, cards[:6])
                payload = json.loads(result.content)
                text = payload.get("greeting_message") if isinstance(payload, dict) else None
                if not isinstance(text, str) or not text.strip() or len(text.strip()) > 180:
                    return {**base, "status": "failed", "message": "模型没有返回有效招呼语，请重试。"}
                self.evidence._record_llm_usage("ApplicationWriterAgent", result, config)
                return {**base, "status": "ready", "text": text.strip(), "mode": "model", "model": config.model}
            sentences = re.split(r"[。；\n]", job.description)
            focus = next((" ".join(s.split()).strip(" ：:、-") for s in sentences if len(s.strip()) >= 8), "")
            focus = (focus or " ".join(job.description.split()))[:42]
            title = job.title.strip()[:42]
            text = f"您好，我对贵司的「{title}」岗位感兴趣，尤其想了解 JD 中提到的「{focus}」。方便交流一下具体工作内容吗？"
            return {**base, "status": "ready", "text": text, "mode": "local"}
        except LLMClientUnavailable as exc:
            return {**base, "status": "failed", "message": str(exc)}
        except KeyError:
            return {**base, "status": "failed", "message": "岗位已不存在，请刷新岗位列表。"}
        except (OSError, RuntimeError, ValueError):
            return {**base, "status": "failed", "message": "招呼语未生成，请检查岗位详情或模型连接后重试。"}

    def apply_native(self, job_ids: list[int]) -> dict:
        with self.lock:
            ids = list(dict.fromkeys(job_ids))
            sent = {record.job_id for record in self.jobs.store.list_applications()}
            items = []
            held = False
            for job_id in ids:
                if held:
                    items.append({"job_id": job_id, "status": "not_attempted", "message": "前一项待核对，本项未操作。"})
                    continue
                try:
                    if job_id in sent:
                        items.append({"job_id": job_id, "status": "skipped", "message": "已有记录，未重复操作。"})
                        continue
                    job = self.jobs.store.get_job(job_id)
                    if not is_platform_job(job):
                        items.append({"job_id": job_id, "status": "skipped", "message": "不是可核验的平台岗位。"})
                        continue
                    preview = self.jobs.preview_platform_application(job_id)
                    entry = preview.get("button_text")
                    if not preview.get("ready") or preview.get("status") != "ready" or entry not in {"立即沟通", "投递简历", "立即投递", "申请职位", "立即申请"}:
                        held = True
                        items.append({"job_id": job_id, "status": "blocked", "message": "未取得可用的原生按钮，请在平台核对，后续岗位未操作。"})
                        continue
                    self.jobs.apply_to_platform(job_id, note="用户确认本批次平台原生操作（不包含自定义招呼语）", expected_button=entry)
                    sent.add(job_id)
                    items.append({"job_id": job_id, "status": "confirmed", "message": "平台已确认，已记入投递。"})
                except (KeyError, OSError, RuntimeError, ValueError):
                    held = True
                    items.append({"job_id": job_id, "status": "unknown", "message": "未取得该岗位的发送证明，已暂停。请核对平台，不要直接重发。"})
            return {"items": items}

    def send_reviewed_greetings(self, reviewed: list[ReviewedGreeting]) -> dict:
        with self.lock:
            store = self.jobs.store
            sent = {record.job_id for record in store.list_applications()}
            results = []
            held = False
            for row in reviewed:
                base = {"job_id": row.job_id}
                if held:
                    results.append({**base, "status": "not_attempted", "message": "前项待核对，这一项未操作。"})
                    continue
                try:
                    job = store.get_job(row.job_id)
                    if row.job_id in sent:
                        results.append({**base, "status": "skipped", "message": "已有投递记录，没有重复发送。"})
                        continue
                    url = urlparse(job.url)
                    if (job.platform != "boss" or not is_platform_job(job) or f"{url.scheme}://{url.netloc}" != ORIGIN
                            or not url.path.endswith(".html")):
                        results.append({**base, "status": "skipped", "message": "自定义发送仅支持可核验的 BOSS 岗位；可复制后手动发送。"})
                        continue
                    if not store.reserve_boss_greeting(url.path):
                        held = True
                        results.append({**base, "status": "unknown", "message": "此平台岗位已有发送尝试，请核对原会话，系统不会重发。"})
                        continue
                    outcome = BossGreetingService().send(job, row.text)
                    status = outcome.get("status")
                    message = outcome.get("message", "未获得平台回执，请核对聊天记录，不要直接重发。")
                    if status in {"confirmed", "already_confirmed"}:
                        proof = self.jobs._platform_application_proof(job.platform, {
                            "evidence": message, "source_url": ORIGIN + url.path,
                            "action": "sent_custom_greeting", "status": "applied", "button_text": "发送",
                        })
                        store.create_application(job, note="平台已确认自定义招呼语；未操作简历附件。", platform_proof=proof)
                        sent.add(row.job_id)
                        results.append({**base, "status": "confirmed", "message": message})
                    else:
                        if status == "blocked":
                            store.release_unsent_boss_greeting(url.path)
                        held = True
                        results.append({**base, "status": "blocked" if status == "blocked" else "unknown", "message": message})
                except KeyError:
                    held = True
                    results.append({**base, "status": "unknown", "message": "岗位无法核对，请刷新并检查平台状态。"})
                except (OSError, RuntimeError, ValueError, sqlite3.Error):
                    held = True
                    results.append({**base, "status": "unknown", "message": "发送或本地保存未能确认，请核对平台，不要直接重发。"})
            return {"items": results}
