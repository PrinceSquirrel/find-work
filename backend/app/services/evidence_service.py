from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.agents.job_match import IMPORTANT_TERMS
from app.agents.resume_parser import ResumeParserAgent
from app.schemas import (
    EvidenceCard,
    EvidenceCardCreate,
    EvidenceCardUpdate,
    EvidenceRecommendation,
    EvidenceSource,
    GreetingMessage,
    TailoredClaim,
    TailoredClaimUpdate,
    TailoredResume,
)
from app.services.llm_client_service import LLMCompletionResult, OpenAICompatibleClient
from app.services.metrics_service import MetricsService
from app.services.model_router_service import ModelRouterService
from app.storage import SQLiteStore


SUPPORTED_SOURCE_TYPES = {"docx", "pdf", "txt", "md", "png", "jpg", "jpeg"}
CARD_STATUSES = {"draft", "confirmed", "rejected"}
CARD_CATEGORIES = {"internship", "project", "education", "competition", "skill", "achievement", "other"}
CLAIM_DECISIONS = {"pending", "accepted", "rejected"}
LOW_QUALITY_JOB_STATUSES = {"card_only", "detail_blocked", "low_quality"}


class EvidenceConflictError(RuntimeError):
    """Raised when an evidence workflow needs an explicit user decision."""


class EvidenceModelError(RuntimeError):
    """Raised when configured AI output cannot satisfy evidence constraints."""


class EvidenceService:
    def __init__(self, store: SQLiteStore):
        self.store = store
        self.parser = ResumeParserAgent()
        self.model_router = ModelRouterService()
        self.llm_client = OpenAICompatibleClient()
        self.metrics = MetricsService()

    def upload_source(self, filename: str, content: bytes) -> EvidenceSource:
        suffix = Path(filename).suffix.lower().lstrip(".") or "txt"
        if suffix not in SUPPORTED_SOURCE_TYPES:
            raise ValueError("第一版仅支持 DOCX、PDF、TXT、MD、PNG、JPG、JPEG")
        parsed = self.parser.parse(filename, content)
        extraction = dict(parsed.profile.get("extraction") or {})
        source = EvidenceSource(
            filename=filename,
            file_type=suffix,
            raw_text=parsed.raw_text,
            extraction_status=str(extraction.get("status") or "pending"),
            extraction_method=str(extraction.get("method") or ""),
            extraction_confidence=float(extraction.get("confidence") or 0.0),
            manual_text_required=bool(extraction.get("manual_text_required")),
            warnings=[str(item) for item in extraction.get("warnings") or []],
        )
        return self.store.create_evidence_source(source, original_file_bytes=content)

    def update_source_manual_text(self, source_id: int, raw_text: str) -> EvidenceSource:
        raw_text = raw_text.strip()
        if not raw_text:
            raise ValueError("资料手动文本不能为空")
        if self.store.list_evidence_cards(source_id=source_id):
            raise EvidenceConflictError("该资料已经生成经历卡片，请先删除卡片或重新上传资料")
        return self.store.update_evidence_source_manual_text(source_id, raw_text)

    def extract_cards(self, source_id: int) -> list[EvidenceCard]:
        source = self.store.get_evidence_source(source_id)
        existing = self.store.list_evidence_cards(source_id=source_id)
        if existing:
            return existing
        if source.manual_text_required or not source.raw_text.strip():
            raise EvidenceConflictError("资料没有可用正文，请先补全文本再提取经历卡片")
        config = self.store.get_agent_model_route("ApplicationWriterAgent")
        route = self.model_router.route_for_agent("ApplicationWriterAgent", config)
        if route.mode == "external":
            try:
                result = self.llm_client.generate_evidence_cards(config, source)
                candidates = self._cards_from_llm(source, result.content)
                self._record_llm_usage("EvidenceCardAgent", result, config)
            except Exception as exc:
                if isinstance(exc, EvidenceModelError):
                    raise
                raise EvidenceModelError(f"经历卡片模型调用失败：{self._safe_error(exc)}") from exc
        else:
            candidates = self._local_candidate_cards(source)
        cards = [self.store.create_evidence_card(card) for card in candidates]
        if not cards:
            raise ValueError("没有识别到足够完整的经历片段，请手工新增经历卡片")
        return cards

    def create_manual_card(self, payload: EvidenceCardCreate) -> EvidenceCard:
        title = payload.title.strip()
        if not title:
            raise ValueError("经历卡片标题不能为空")
        self._validate_category(payload.category)
        card = EvidenceCard(
            source_id=None,
            category=payload.category,
            title=title,
            organization=payload.organization.strip(),
            time_range=payload.time_range.strip(),
            situation=payload.situation.strip(),
            actions=self._clean_list(payload.actions),
            results=self._clean_list(payload.results),
            skills=self._clean_list(payload.skills),
            status="draft",
            provenance_type="user_statement",
            source_quote="",
            quote_verified=False,
            user_note=payload.user_note.strip(),
        )
        return self.store.create_evidence_card(card)

    def update_card(self, card_id: int, payload: EvidenceCardUpdate) -> EvidenceCard:
        card = self.store.get_evidence_card(card_id)
        updates = payload.model_dump(exclude_none=True)
        if "category" in updates:
            self._validate_category(str(updates["category"]))
        if "status" in updates and updates["status"] not in CARD_STATUSES:
            raise ValueError("经历卡片状态只能是 draft、confirmed 或 rejected")
        for field in ("title", "organization", "time_range", "situation", "source_quote", "user_note"):
            if field in updates:
                updates[field] = str(updates[field]).strip()
        for field in ("actions", "results", "skills"):
            if field in updates:
                updates[field] = self._clean_list(updates[field])
        if not str(updates.get("title", card.title)).strip():
            raise ValueError("经历卡片标题不能为空")

        if card.provenance_type == "document":
            source = self.store.get_evidence_source(card.source_id or 0)
            quote = str(updates.get("source_quote", card.source_quote)).strip()
            start = source.raw_text.find(quote) if quote else -1
            updates.update(
                {
                    "source_quote": quote,
                    "source_start": start if start >= 0 else None,
                    "source_end": start + len(quote) if start >= 0 else None,
                    "quote_verified": start >= 0,
                }
            )
            if updates.get("status", card.status) == "confirmed" and start < 0:
                raise ValueError("文件证据引用必须能在资料原文中找到，当前卡片不能确认")

        updated = card.model_copy(update={**updates, "updated_at": datetime.now(UTC)})
        return self.store.update_evidence_card(updated)

    def delete_card(self, card_id: int) -> None:
        self.store.delete_evidence_card(card_id)

    def recommend_cards(self, job_id: int) -> list[EvidenceRecommendation]:
        job = self.store.get_job(job_id)
        self._ensure_job_detail_ready(job.detail_status, job.detail_reason)
        cards = self.store.list_evidence_cards(status="confirmed")
        job_text = f"{job.title} {job.description}".lower()
        requirements = [term for term in IMPORTANT_TERMS if term.lower() in job_text]
        recommendations: list[EvidenceRecommendation] = []
        for card in cards:
            card_text = self._card_text(card).lower()
            hits = [term for term in requirements if term.lower() in card_text]
            score = min(100, 20 + len(hits) * 20)
            recommendations.append(
                EvidenceRecommendation(
                    card=card,
                    score=score,
                    hit_reasons=[f"经历中包含 {term}" for term in hits] or ["已确认经历，可人工判断与JD的相关性"],
                    jd_requirements=hits,
                )
            )
        return sorted(recommendations, key=lambda item: (item.score, item.card.id or 0), reverse=True)

    def generate_trusted_tailor(
        self,
        job_id: int,
        resume_id: int,
        evidence_card_ids: list[int],
    ) -> dict[str, Any]:
        resume = self.store.get_resume(resume_id)
        job = self.store.get_job(job_id)
        self._ensure_job_detail_ready(job.detail_status, job.detail_reason)
        cards = self._confirmed_cards(evidence_card_ids)
        config = self.store.get_agent_model_route("ApplicationWriterAgent")
        route = self.model_router.route_for_agent("ApplicationWriterAgent", config)
        if route.mode == "external":
            try:
                result = self.llm_client.generate_evidence_tailor(config, job, cards)
                claim_specs, greeting_message = self._claims_from_llm(result.content, cards)
                generation_mode = "external_ai"
                self._record_llm_usage("EvidenceTailorAgent", result, config)
            except Exception as exc:
                if isinstance(exc, EvidenceModelError):
                    raise
                raise EvidenceModelError(f"可信简历模型调用失败：{self._safe_error(exc)}") from exc
        else:
            claim_specs = [
                {"text": self._safe_claim_text(card), "evidence_card_ids": [card.id or 0]}
                for card in cards
            ]
            greeting_message = f"您好，我对贵公司的{job.title}岗位很感兴趣，已根据真实项目和实践经历准备了定制材料。"
            generation_mode = "local_safe"
        resume_rewrite = "\n".join(f"- {item['text']}" for item in claim_specs)
        tailored = TailoredResume(
            job_id=job_id,
            resume_id=resume_id,
            resume_text=resume_rewrite,
            resume_rewrite=resume_rewrite,
            project_rewrite=resume_rewrite,
            diff_summary=["只使用用户已确认的经历卡片", "每条内容保留可追溯证据引用"],
            risk_flags=[],
            truth_check_passed=False,
        )
        greeting = GreetingMessage(
            job_id=job_id,
            message=greeting_message,
            risk_flags=[],
        )
        review = {
            "job_id": job_id,
            "truth_check_passed": False,
            "trusted_evidence_finalized": False,
            "traceability_coverage": 1.0,
            "generation_mode": generation_mode,
            "summary": "内容均来自已确认经历卡片，仍需用户逐条接受后定稿",
        }
        bundle = self.store.save_tailor_bundle(tailored, greeting, review)
        tailored_resume_id = int(bundle["id"])
        claims = [
            self.store.create_tailored_claim(
                TailoredClaim(
                    tailored_resume_id=tailored_resume_id,
                    text=str(item["text"]),
                    evidence_card_ids=[int(value) for value in item["evidence_card_ids"]],
                    support_status="supported",
                    user_decision="pending",
                )
            )
            for item in claim_specs
        ]
        return {
            **bundle,
            "claims": [claim.model_dump(mode="json") for claim in claims],
            "generation_mode": generation_mode,
            "source_resume_filename": resume.filename,
        }

    def get_trusted_tailor(self, tailored_resume_id: int) -> dict[str, Any]:
        bundle = self.store.get_tailor_bundle(tailored_resume_id)
        claims = self.store.list_tailored_claims(tailored_resume_id)
        if not claims:
            raise KeyError(f"Trusted tailor {tailored_resume_id} not found")
        return {**bundle, "claims": [claim.model_dump(mode="json") for claim in claims]}

    def update_claim(self, claim_id: int, payload: TailoredClaimUpdate) -> TailoredClaim:
        claim = self.store.get_tailored_claim(claim_id)
        text = payload.text.strip() if payload.text is not None else claim.text
        if not text:
            raise ValueError("生成内容不能为空")
        decision = payload.user_decision or claim.user_decision
        if decision not in CLAIM_DECISIONS:
            raise ValueError("内容决定只能是 pending、accepted 或 rejected")
        evidence_ids = payload.evidence_card_ids if payload.evidence_card_ids is not None else claim.evidence_card_ids
        text_changed = text != claim.text

        if decision == "rejected":
            support_status = "rejected"
        else:
            self._confirmed_cards(evidence_ids)
            support_status = "supported"
            if text_changed and not payload.confirm_support:
                support_status = "needs_review"
                decision = "pending"
            elif decision == "accepted" and not evidence_ids:
                raise ValueError("接受内容前必须关联至少一张已确认经历卡片")

        updated = claim.model_copy(
            update={
                "text": text,
                "evidence_card_ids": evidence_ids,
                "support_status": support_status,
                "user_decision": decision,
                "edit_version": claim.edit_version + (1 if text_changed else 0),
                "updated_at": datetime.now(UTC),
            }
        )
        return self.store.update_tailored_claim(updated)

    def finalize(self, tailored_resume_id: int) -> dict[str, Any]:
        claims = self.store.list_tailored_claims(tailored_resume_id)
        included = [claim for claim in claims if claim.user_decision != "rejected"]
        if not included:
            raise EvidenceConflictError("至少保留并接受一条生成内容后才能定稿")
        pending = [
            claim for claim in included
            if claim.support_status != "supported" or claim.user_decision != "accepted"
        ]
        if pending:
            raise EvidenceConflictError("仍有内容待核验或待接受，不能定稿导出")
        resume_rewrite = "\n".join(f"- {claim.text}" for claim in included)
        return self.store.finalize_trusted_tailor(tailored_resume_id, resume_rewrite)

    def _local_candidate_cards(self, source: EvidenceSource) -> list[EvidenceCard]:
        paragraphs = [item.strip() for item in re.split(r"\n\s*\n", source.raw_text) if item.strip()]
        if len(paragraphs) <= 1:
            paragraphs = [line.strip() for line in source.raw_text.splitlines() if len(line.strip()) >= 8]
        cards: list[EvidenceCard] = []
        cursor = 0
        for paragraph in paragraphs[:12]:
            start = source.raw_text.find(paragraph, cursor)
            if start < 0:
                start = source.raw_text.find(paragraph)
            if start < 0:
                continue
            cursor = start + len(paragraph)
            category = self._category_for_text(paragraph)
            title = self._title_for_text(paragraph)
            skills = [term for term in IMPORTANT_TERMS if term.lower() in paragraph.lower()]
            cards.append(
                EvidenceCard(
                    source_id=source.id,
                    category=category,
                    title=title,
                    situation=paragraph,
                    actions=[paragraph],
                    results=[],
                    skills=skills,
                    status="draft",
                    provenance_type="document",
                    source_quote=paragraph,
                    source_start=start,
                    source_end=start + len(paragraph),
                    quote_verified=True,
                )
            )
        return cards

    def _cards_from_llm(self, source: EvidenceSource, content: str) -> list[EvidenceCard]:
        payload = self._json_object(content, "经历卡片")
        items = payload.get("cards")
        if not isinstance(items, list) or not items:
            raise EvidenceModelError("经历卡片模型输出缺少非空 cards 数组")
        cards: list[EvidenceCard] = []
        for item in items[:12]:
            if not isinstance(item, dict):
                raise EvidenceModelError("经历卡片模型输出包含非对象项")
            title = str(item.get("title") or "").strip()
            category = str(item.get("category") or "other").strip()
            quote = str(item.get("source_quote") or "").strip()
            if not title or category not in CARD_CATEGORIES or not quote:
                raise EvidenceModelError("经历卡片缺少标题、合法类别或原文引用")
            start = source.raw_text.find(quote)
            if start < 0:
                raise EvidenceModelError("模型返回的 source_quote 无法在资料原文中逐字定位")
            cards.append(
                EvidenceCard(
                    source_id=source.id,
                    category=category,
                    title=title,
                    organization=str(item.get("organization") or "").strip(),
                    time_range=str(item.get("time_range") or "").strip(),
                    situation=str(item.get("situation") or "").strip(),
                    actions=self._json_string_list(item.get("actions"), "actions"),
                    results=self._json_string_list(item.get("results"), "results"),
                    skills=self._json_string_list(item.get("skills"), "skills"),
                    status="draft",
                    provenance_type="document",
                    source_quote=quote,
                    source_start=start,
                    source_end=start + len(quote),
                    quote_verified=True,
                    user_note="由已配置模型抽取，需用户确认",
                )
            )
        return cards

    def _claims_from_llm(
        self,
        content: str,
        cards: list[EvidenceCard],
    ) -> tuple[list[dict[str, Any]], str]:
        payload = self._json_object(content, "可信简历")
        raw_claims = payload.get("claims")
        greeting_message = str(payload.get("greeting_message") or "").strip()
        if not isinstance(raw_claims, list) or not raw_claims or not greeting_message:
            raise EvidenceModelError("可信简历模型输出缺少 claims 或 greeting_message")
        allowed_ids = {card.id for card in cards if card.id is not None}
        claims: list[dict[str, Any]] = []
        for item in raw_claims:
            if not isinstance(item, dict):
                raise EvidenceModelError("可信简历 claims 包含非对象项")
            text = str(item.get("text") or "").strip()
            raw_ids = item.get("evidence_card_ids")
            if not isinstance(raw_ids, list) or not text:
                raise EvidenceModelError("每条可信简历内容必须包含 text 和 evidence_card_ids")
            try:
                evidence_ids = list(dict.fromkeys(int(value) for value in raw_ids))
            except (TypeError, ValueError) as exc:
                raise EvidenceModelError("evidence_card_ids 必须为整数数组") from exc
            if not evidence_ids or not set(evidence_ids).issubset(allowed_ids):
                raise EvidenceModelError("模型引用了未选择、未确认或不存在的经历卡片")
            claims.append({"text": text, "evidence_card_ids": evidence_ids})
        return claims, greeting_message

    def _json_object(self, content: str, label: str) -> dict[str, Any]:
        stripped = content.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            if stripped.lower().startswith("json"):
                stripped = stripped[4:].strip()
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise EvidenceModelError(f"{label}模型输出不是合法 JSON") from exc
        if not isinstance(payload, dict):
            raise EvidenceModelError(f"{label}模型输出必须是 JSON 对象")
        return payload

    def _json_string_list(self, value: object, field: str) -> list[str]:
        if not isinstance(value, list):
            raise EvidenceModelError(f"经历卡片字段 {field} 必须是数组")
        return self._clean_list([str(item) for item in value])

    def _record_llm_usage(self, agent_name: str, result: LLMCompletionResult, config: Any) -> None:
        usage = self.metrics.record_llm_usage(
            agent_name=agent_name,
            provider=result.provider,
            model=result.model,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            duration_ms=result.duration_ms,
            estimated=result.estimated,
            status="success",
            input_price_per_million=config.input_price_per_million,
            output_price_per_million=config.output_price_per_million,
        )
        self.store.save_llm_usage(usage)

    def _safe_error(self, exc: Exception) -> str:
        return str(exc).replace("\n", " ")[:240]

    def _confirmed_cards(self, card_ids: list[int]) -> list[EvidenceCard]:
        unique_ids = list(dict.fromkeys(int(value) for value in card_ids))
        if not unique_ids:
            raise ValueError("请至少选择一张已确认经历卡片")
        cards: list[EvidenceCard] = []
        for card_id in unique_ids:
            card = self.store.get_evidence_card(card_id)
            if card.status != "confirmed":
                raise ValueError(f"经历卡片 {card_id} 尚未确认，不能用于生成")
            if card.provenance_type == "document" and not card.quote_verified:
                raise ValueError(f"经历卡片 {card_id} 的文件引用未验证")
            cards.append(card)
        return cards

    def _safe_claim_text(self, card: EvidenceCard) -> str:
        details = self._clean_list([card.situation, *card.actions, *card.results])
        compact_details = list(dict.fromkeys(details))
        body = "；".join(compact_details[:3])
        return f"{card.title}：{body}" if body else card.title

    def _card_text(self, card: EvidenceCard) -> str:
        return " ".join(
            [
                card.title,
                card.organization,
                card.time_range,
                card.situation,
                *card.actions,
                *card.results,
                *card.skills,
            ]
        )

    def _category_for_text(self, text: str) -> str:
        mapping = (
            ("internship", ("实习", "工作经历", "公司")),
            ("project", ("项目", "系统", "平台", "产品")),
            ("education", ("教育", "学校", "课程")),
            ("competition", ("比赛", "竞赛", "获奖")),
            ("achievement", ("成果", "提升", "降低", "%")),
            ("skill", ("技能", "熟悉", "掌握")),
        )
        for category, markers in mapping:
            if any(marker in text for marker in markers):
                return category
        return "other"

    def _title_for_text(self, text: str) -> str:
        first_line = text.splitlines()[0].strip()
        prefix = re.split(r"[:：]", first_line, maxsplit=1)[0].strip()
        return (prefix if 2 <= len(prefix) <= 36 else first_line[:36]).strip("- •") or "未命名经历"

    def _ensure_job_detail_ready(self, detail_status: str, detail_reason: str) -> None:
        if detail_status in LOW_QUALITY_JOB_STATUSES:
            reason = detail_reason or "当前岗位详情质量不足。"
            raise EvidenceConflictError(f"当前岗位需要先补全 JD 后再生成材料。原因：{reason}")

    def _validate_category(self, category: str) -> None:
        if category not in CARD_CATEGORIES:
            raise ValueError("经历类别不受支持")

    def _clean_list(self, values: list[str]) -> list[str]:
        return [str(value).strip() for value in values if str(value).strip()]
