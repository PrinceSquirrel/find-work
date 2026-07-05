from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, datetime
import json
from typing import Any

from app.agents import ApplicationWriterAgent, JobMatchAgent, ResumeParserAgent, ReviewAgent
from app.platforms import BossAdapter, ShixisengAdapter
from app.schemas import (
    ApplicationPlatformProof,
    ApplicationRecord,
    ApplicationStatus,
    ExtractedJobCandidate,
    JobMatch,
    JobPosting,
    LLMUsageEntry,
    LLMUsageSummary,
    ModelConfig,
    SearchRun,
    TailorBundle,
)
from app.services.browser_job_extractor_service import BrowserJobExtractorService
from app.services.event_stream_service import EventStreamService
from app.services.llm_client_service import LLMCompletionResult, OpenAICompatibleClient
from app.services.metrics_service import MetricsService
from app.services.model_router_service import ModelRoute, ModelRouterService
from app.services.orchestrator_service import OrchestratorService
from app.services.platform_session_service import PlatformSessionService
from app.storage import SQLiteStore


BROWSER_CDP_SEARCH_RUN_LIMIT = 8


class LowQualityJobDetailError(ValueError):
    """Raised when a job needs a complete JD before generating application materials."""


class PlatformApplicationNotConfirmedError(RuntimeError):
    """Raised when the platform did not confirm that an application action happened."""


class JobApplicationService:
    def __init__(self, store: SQLiteStore):
        self.store = store
        self.resume_parser = ResumeParserAgent()
        self.job_match = JobMatchAgent()
        self.application_writer = ApplicationWriterAgent()
        self.review = ReviewAgent()
        self.metrics = MetricsService()
        self.event_stream = EventStreamService()
        self.orchestrator = OrchestratorService(self.event_stream, store=store)
        self.model_router = ModelRouterService()
        self.llm_client = OpenAICompatibleClient()
        self.adapters = {
            "boss": BossAdapter(),
            "shixiseng": ShixisengAdapter(),
        }

    def upload_resume(self, filename: str, content: bytes):
        task_id = self.orchestrator.start_task("resume.parse", filename)
        self._record_agent_step(task_id, "ResumeParserAgent", "running", "parse resume", input_summary=filename)
        try:
            parsed = self.resume_parser.parse(filename, content)
            stored = self.store.create_resume(parsed, original_file_bytes=content)
            self._record_usage("ResumeParserAgent", filename, stored.raw_text)
            self._record_agent_step(
                task_id,
                "ResumeParserAgent",
                "success",
                "parse resume",
                input_summary=filename,
                output_summary=self._resume_parse_output_summary(stored),
            )
            self.orchestrator.finish_task(task_id)
            return stored
        except Exception as exc:
            safe_error = self._safe_error(exc)
            self._record_agent_step(
                task_id,
                "ResumeParserAgent",
                "failed",
                "parse resume",
                input_summary=filename,
                error=safe_error,
            )
            self.orchestrator.finish_task(task_id, status="failed", error=safe_error)
            raise

    def update_resume_manual_text(self, resume_id: int, raw_text: str):
        raw_text = raw_text.strip()
        if not raw_text:
            raise ValueError("简历手动文本不能为空")
        resume = self.store.get_resume(resume_id)
        updated = self.resume_parser.apply_manual_text(resume, raw_text)
        stored = self.store.update_resume_manual_text(updated)
        self._record_usage("ResumeParserAgent", f"manual-text:{resume_id}", stored.raw_text)
        return stored

    def create_search_run(
        self,
        resume_id: int,
        keywords: list[str],
        city: str,
        platforms: list[str],
        search_mode: str = "demo",
    ) -> SearchRun:
        resume = self.store.get_resume(resume_id)
        input_summary = (
            f"mode={search_mode}; platforms={','.join(platforms)}; "
            f"city={city}; keywords={','.join(keywords)}"
        )
        task_id = self.orchestrator.start_task("job.search", input_summary)
        unknown_platforms = [platform for platform in platforms if platform not in self.adapters]
        if unknown_platforms:
            error = f"Unsupported platforms: {', '.join(unknown_platforms)}"
            self._record_agent_step(
                task_id,
                "JobSearchAgent",
                "failed",
                "validate search request",
                input_summary=input_summary,
                error=error,
            )
            self.orchestrator.finish_task(task_id, status="failed", error=error)
            raise ValueError(error)
        if search_mode == "browser_cdp":
            self._record_agent_step(
                task_id,
                "JobSearchAgent",
                "running",
                "validate browser tabs",
                input_summary=input_summary,
            )
            try:
                self._ensure_browser_platform_tabs(platforms)
                run = self._create_browser_cdp_search_run(resume, resume_id, keywords, city, platforms, task_id)
                self.orchestrator.finish_task(task_id)
                return run
            except Exception as exc:
                safe_error = self._safe_error(exc)
                self._record_agent_step(
                    task_id,
                    "JobSearchAgent",
                    "failed",
                    "extract browser jobs",
                    input_summary=input_summary,
                    error=safe_error,
                )
                self.orchestrator.finish_task(task_id, status="failed", error=safe_error)
                raise
        self._record_agent_step(
            task_id,
            "JobSearchAgent",
            "running",
            "search jobs",
            input_summary=input_summary,
        )
        try:
            run = self.store.create_search_run(
                SearchRun(
                    resume_id=resume_id,
                    keywords=keywords,
                    city=city,
                    platforms=platforms,
                    status="running",
                )
            )
            saved_count = 0
            jobs_to_save: list[JobPosting] = []
            for platform in platforms:
                adapter = self.adapters.get(platform)
                if adapter is None:
                    continue
                jobs_to_save.extend(adapter.search(resume, keywords, city))
            matches, match_usage, match_route = self._score_jobs(resume, jobs_to_save)
            for job, match in zip(jobs_to_save, matches):
                stored_job = self.store.save_job(job, run.id or 0, match)
                saved_count += 1
                self._record_usage("JobSearchAgent", " ".join(keywords), stored_job.description)
            self._record_job_match_usage(resume, jobs_to_save, matches, match_usage)
            self.store.update_search_run_status(run.id or 0, "completed")
            self._record_agent_step(
                task_id,
                "JobSearchAgent",
                "success",
                "search jobs",
                input_summary=f"mode=demo; platforms={','.join(platforms)}",
                output_summary=f"jobs={saved_count}",
            )
            self._record_agent_step(
                task_id,
                "JobMatchAgent",
                "success",
                "score matched jobs",
                input_summary=f"resume_id={resume_id}; jobs={saved_count}",
                output_summary=self._job_match_output_summary(saved_count, match_route, match_usage),
                total_tokens=match_usage.total_tokens if match_usage else 0,
                cost_usd=match_usage.cost_usd if match_usage else 0.0,
            )
            self.orchestrator.finish_task(task_id)
            return run.model_copy(update={"status": "completed"})
        except Exception as exc:
            safe_error = self._safe_error(exc)
            self._record_agent_step(
                task_id,
                "JobSearchAgent",
                "failed",
                "search jobs",
                input_summary=input_summary,
                error=safe_error,
            )
            self.orchestrator.finish_task(task_id, status="failed", error=safe_error)
            raise

    def _create_browser_cdp_search_run(
        self,
        resume,
        resume_id: int,
        keywords: list[str],
        city: str,
        platforms: list[str],
        task_id: int | None,
    ) -> SearchRun:
        self._record_agent_step(
            task_id,
            "JobSearchAgent",
            "running",
            "extract browser jobs",
            input_summary=f"mode=browser_cdp; platforms={','.join(platforms)}",
        )
        extractor = BrowserJobExtractorService()
        if hasattr(extractor, "search_and_extract"):
            extraction_response = extractor.search_and_extract(
                platforms,
                keywords,
                city,
                limit=BROWSER_CDP_SEARCH_RUN_LIMIT,
            )
        else:
            extraction_response = extractor.extract(platforms, limit=BROWSER_CDP_SEARCH_RUN_LIMIT)
        extracted_jobs = self._collect_extracted_jobs(extraction_response.extractions)
        run = self.store.create_search_run(
            SearchRun(
                resume_id=resume_id,
                keywords=keywords,
                city=city,
                platforms=platforms,
                status="running",
            )
        )
        saved_count = 0
        jobs_to_save = [self._candidate_to_job(candidate, city) for candidate in extracted_jobs]
        matches, match_usage, match_route = self._score_jobs(resume, jobs_to_save)
        for job, match in zip(jobs_to_save, matches):
            stored_job = self.store.save_job(job, run.id or 0, match)
            saved_count += 1
            self._record_usage("JobSearchAgent", " ".join(keywords), stored_job.description)
        self._record_job_match_usage(resume, jobs_to_save, matches, match_usage)
        self.store.update_search_run_status(run.id or 0, "completed")
        self._record_agent_step(
            task_id,
            "JobSearchAgent",
            "success",
            "extract browser jobs",
            input_summary=f"mode=browser_cdp; platforms={','.join(platforms)}",
            output_summary=f"jobs={saved_count}",
        )
        self._record_agent_step(
            task_id,
            "JobMatchAgent",
            "success",
            "score matched jobs",
            input_summary=f"resume_id={resume_id}; jobs={saved_count}",
            output_summary=self._job_match_output_summary(saved_count, match_route, match_usage),
            total_tokens=match_usage.total_tokens if match_usage else 0,
            cost_usd=match_usage.cost_usd if match_usage else 0.0,
        )
        return run.model_copy(update={"status": "completed"})

    def _score_jobs(
        self,
        resume,
        jobs: list[JobPosting],
    ) -> tuple[list[JobMatch], LLMUsageEntry | None, ModelRoute]:
        rule_matches = [self.job_match.match(resume, job) for job in jobs]
        config = self.store.get_agent_model_route("JobMatchAgent")
        route = self.model_router.route_for_agent("JobMatchAgent", config)
        if not jobs or route.mode != "external":
            return rule_matches, None, route
        try:
            result = self.llm_client.score_job_matches(config, resume, jobs, rule_matches)
            matches = self._job_matches_from_llm_result(result.content, rule_matches)
            usage = self.metrics.record_llm_usage(
                agent_name="JobMatchAgent",
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
            return matches, usage, route
        except Exception as exc:
            usage = self.metrics.record_failure(
                agent_name="JobMatchAgent",
                provider=config.provider,
                model=config.model,
                error=self._safe_error(exc),
            )
            return rule_matches, usage, route

    def _job_matches_from_llm_result(self, content: str, rule_matches: list[JobMatch]) -> list[JobMatch]:
        payload = json.loads(content)
        items = payload.get("matches")
        if not isinstance(items, list):
            raise ValueError("JobMatchAgent response did not contain matches")
        matches = list(rule_matches)
        for item in items:
            if not isinstance(item, dict):
                continue
            index = int(item.get("job_index", -1))
            if index < 0 or index >= len(matches):
                continue
            score = max(0, min(100, int(item.get("score", matches[index].score))))
            recommendation = str(item.get("recommendation") or self._recommendation_for_score(score))
            if recommendation not in {"strong_apply", "review", "skip"}:
                recommendation = self._recommendation_for_score(score)
            matches[index] = JobMatch(
                job_id=matches[index].job_id,
                score=score,
                hit_reasons=self._string_list_or_default(item.get("hit_reasons"), matches[index].hit_reasons),
                gap_reasons=self._string_list_or_default(item.get("gap_reasons"), matches[index].gap_reasons),
                recommendation=recommendation,
            )
        return matches

    def _string_list_or_default(self, value: Any, default: list[str]) -> list[str]:
        if not isinstance(value, list):
            return default
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        return cleaned[:8] or default

    def _recommendation_for_score(self, score: int) -> str:
        if score >= 80:
            return "strong_apply"
        if score >= 60:
            return "review"
        return "skip"

    def _record_job_match_usage(
        self,
        resume,
        jobs: list[JobPosting],
        matches: list[JobMatch],
        usage: LLMUsageEntry | None,
    ) -> None:
        if not jobs:
            return
        if usage is not None:
            self.store.save_llm_usage(usage)
            return
        prompt = resume.raw_text + "\n".join(job.description for job in jobs)
        completion = ",".join(str(match.score) for match in matches)
        self._record_usage("JobMatchAgent", prompt, completion)

    def _job_match_output_summary(
        self,
        count: int,
        route: ModelRoute,
        usage: LLMUsageEntry | None,
    ) -> str:
        summary = f"matches={count}; route={route.model}"
        if usage is not None:
            summary += f"; usage_status={usage.status}"
        return summary

    def _collect_extracted_jobs(self, extractions) -> list[ExtractedJobCandidate]:
        failures = [
            f"{extraction.platform}:{extraction.status}:{extraction.error or '未提取到岗位'}"
            for extraction in extractions
            if extraction.status != "success"
        ]
        jobs = [job for extraction in extractions for job in extraction.jobs]
        if failures or not jobs:
            reason = "; ".join(failures) if failures else "没有从浏览器页面提取到岗位"
            raise ValueError(f"browser_cdp extraction failed: {reason}")
        return jobs

    def _candidate_to_job(self, candidate: ExtractedJobCandidate, fallback_city: str) -> JobPosting:
        return JobPosting(
            platform=candidate.platform,
            company=candidate.company or "未知公司",
            title=candidate.title,
            city=candidate.city or fallback_city or "未知城市",
            salary=candidate.salary or "未展示",
            description=candidate.description or candidate.title,
            url=candidate.url,
            job_type=candidate.job_type or "browser_cdp",
            detail_status=candidate.detail_status,
            detail_reason=candidate.detail_reason,
        )

    def _ensure_browser_platform_tabs(self, platforms: list[str]) -> None:
        sessions = PlatformSessionService().inspect().sessions
        detected = {session.platform for session in sessions if session.state == "tab_detected"}
        missing = [platform for platform in platforms if platform not in detected]
        if missing:
            raise ValueError(
                "browser_cdp search requires detected platform tabs: "
                + ", ".join(missing)
            )

    def list_jobs(self, search_run_id: int | None = None) -> list[dict[str, Any]]:
        return self.store.list_jobs(search_run_id=search_run_id)

    def refresh_job_detail(self, job_id: int) -> dict[str, Any]:
        task_input = f"job_id={job_id}"
        task_id = self.orchestrator.start_task("job.detail.refresh", task_input)
        self._record_agent_step(
            task_id,
            "JobSearchAgent",
            "running",
            "refresh job detail",
            input_summary=task_input,
        )
        try:
            job = self.store.get_job(job_id)
            if not job.url:
                raise ValueError("Job has no source URL to refresh.")
            candidate = BrowserJobExtractorService().refresh_job_detail(job.platform, job.url)
            next_salary = self._prefer_refreshed_salary(candidate.salary, job.salary)
            next_description = candidate.description.strip() or job.description
            detail_status = candidate.detail_status or job.detail_status
            detail_reason = candidate.detail_reason or job.detail_reason
            self.store.update_job_detail(
                job_id,
                salary=next_salary,
                description=next_description,
                detail_status=detail_status,
                detail_reason=detail_reason,
            )
            for stored_job in self.store.list_jobs(search_run_id=job.search_run_id):
                if stored_job["id"] == job_id:
                    self._record_agent_step(
                        task_id,
                        "JobSearchAgent",
                        "success",
                        "refresh job detail",
                        input_summary=f"job_id={job_id}; platform={job.platform}",
                        output_summary=f"detail_status={detail_status}; salary={next_salary}",
                    )
                    self.orchestrator.finish_task(task_id)
                    return stored_job
            raise KeyError(f"Job {job_id} not found")
        except Exception as exc:
            safe_error = self._safe_error(exc)
            self._record_agent_step(
                task_id,
                "JobSearchAgent",
                "failed",
                "refresh job detail",
                input_summary=task_input,
                error=safe_error,
            )
            self.orchestrator.finish_task(task_id, status="failed", error=safe_error)
            raise

    def _prefer_refreshed_salary(self, refreshed_salary: str, current_salary: str) -> str:
        cleaned = refreshed_salary.strip()
        if not cleaned:
            return current_salary
        if "读取失败" in cleaned or "未展示" in cleaned:
            return current_salary or cleaned
        return cleaned

    def update_job_detail_manually(self, job_id: int, description: str, note: str = "") -> dict[str, Any]:
        description = description.strip()
        if not description:
            raise ValueError("Job description cannot be empty.")
        task_input = f"job_id={job_id}; chars={len(description)}"
        task_id = self.orchestrator.start_task("job.detail.manual_update", task_input)
        self._record_agent_step(
            task_id,
            "JobMatchAgent",
            "running",
            "manual detail update and rematch",
            input_summary=task_input,
        )
        try:
            job = self.store.get_job(job_id)
            if job.search_run_id is None:
                raise ValueError("Job is not attached to a search run.")
            search_run = self.store.get_search_run(job.search_run_id)
            resume = self.store.get_resume(search_run.resume_id)
            updated_job = job.model_copy(
                update={
                    "description": description,
                    "detail_status": "manual_filled",
                    "detail_reason": note.strip() or "用户手动补全 JD，并重新计算匹配分。",
                }
            )
            match = self.job_match.match(resume, updated_job)
            self.store.update_job_detail(
                job_id,
                salary=job.salary,
                description=updated_job.description,
                detail_status=updated_job.detail_status,
                detail_reason=updated_job.detail_reason,
                match=match,
            )
            for stored_job in self.store.list_jobs(search_run_id=job.search_run_id):
                if stored_job["id"] == job_id:
                    self._record_agent_step(
                        task_id,
                        "JobMatchAgent",
                        "success",
                        "manual detail update and rematch",
                        input_summary=task_input,
                        output_summary=f"score={match.score}; detail_status=manual_filled",
                    )
                    self.orchestrator.finish_task(task_id)
                    return stored_job
            raise KeyError(f"Job {job_id} not found")
        except Exception as exc:
            safe_error = self._safe_error(exc)
            self._record_agent_step(
                task_id,
                "JobMatchAgent",
                "failed",
                "manual detail update and rematch",
                input_summary=task_input,
                error=safe_error,
            )
            self.orchestrator.finish_task(task_id, status="failed", error=safe_error)
            raise

    def tailor_for_job(self, job_id: int, resume_id: int) -> dict[str, Any]:
        resume = self.store.get_resume(resume_id)
        job = self.store.get_job(job_id)
        task_input = f"resume_id={resume_id}; job_id={job_id}; company={job.company}; title={job.title}"
        task_id = self.orchestrator.start_task("application.materials", task_input)
        try:
            self._ensure_job_detail_ready_for_tailor(job)
        except LowQualityJobDetailError as exc:
            safe_error = self._safe_error(exc)
            self._record_agent_step(
                task_id,
                "ApplicationWriterAgent",
                "failed",
                "validate job detail",
                input_summary=task_input,
                error=safe_error,
            )
            self.orchestrator.finish_task(task_id, status="failed", error=safe_error)
            raise
        self._record_agent_step(
            task_id,
            "ApplicationWriterAgent",
            "running",
            "generate application materials",
            input_summary=task_input,
        )
        try:
            writer_bundle, llm_metadata, llm_usage = self._write_application_materials(resume, job)
        except Exception as exc:
            safe_error = self._safe_error(exc)
            self._record_agent_step(
                task_id,
                "ApplicationWriterAgent",
                "failed",
                "generate application materials",
                input_summary=f"resume_id={resume_id}; job_id={job_id}",
                error=safe_error,
            )
            self.orchestrator.finish_task(task_id, status="failed", error=safe_error)
            raise
        writer_status = "failed" if llm_metadata.get("status") == "fallback" else "success"
        self._record_agent_step(
            task_id,
            "ApplicationWriterAgent",
            writer_status,
            "generate application materials",
            input_summary=f"resume_id={resume_id}; job_id={job_id}",
            output_summary=f"status={llm_metadata.get('status', 'unknown')}; model={llm_metadata.get('model', '')}",
            error=llm_metadata.get("error", "") if writer_status == "failed" else "",
            total_tokens=llm_usage.total_tokens if llm_usage is not None else 0,
            cost_usd=llm_usage.cost_usd if llm_usage is not None else 0.0,
        )
        tailored = writer_bundle.tailored_resume
        greeting = writer_bundle.greeting
        self._record_agent_step(
            task_id,
            "ReviewAgent",
            "running",
            "review generated materials",
            input_summary=f"resume_id={resume_id}; job_id={job_id}",
        )
        try:
            review = self.review.review(resume, job, tailored, greeting)
            review_config = self.store.get_agent_model_route("ReviewAgent")
            review_route = self.model_router.route_for_agent("ReviewAgent", review_config)
            review["llm"] = llm_metadata
            if llm_usage is not None:
                review["llm"].update(self._usage_payload(llm_usage))
            review["llm"]["review_route"] = self._route_payload(review_route)
            self._record_agent_step(
                task_id,
                "ReviewAgent",
                "success",
                "review generated materials",
                input_summary=f"resume_id={resume_id}; job_id={job_id}",
                output_summary=f"truth_check_passed={review.get('truth_check_passed', False)}",
            )
            if llm_usage is not None:
                self.store.save_llm_usage(llm_usage)
            else:
                self._record_usage("ApplicationWriterAgent", resume.raw_text + job.description, tailored.resume_text + greeting.message)
            self._record_usage("ReviewAgent", tailored.resume_text + greeting.message, str(review))
            result = self.store.save_tailor_bundle(tailored, greeting, review)
            self.orchestrator.finish_task(task_id)
            return result
        except Exception as exc:
            safe_error = self._safe_error(exc)
            self._record_agent_step(
                task_id,
                "ReviewAgent",
                "failed",
                "review generated materials",
                input_summary=f"resume_id={resume_id}; job_id={job_id}",
                error=safe_error,
            )
            self.orchestrator.finish_task(task_id, status="failed", error=safe_error)
            raise

    def _ensure_job_detail_ready_for_tailor(self, job: JobPosting) -> None:
        low_quality_statuses = {"card_only", "detail_blocked", "low_quality"}
        if job.detail_status not in low_quality_statuses:
            return
        reason = job.detail_reason or "当前岗位详情质量不足。"
        raise LowQualityJobDetailError(f"当前岗位需要先补全 JD 后再生成材料。原因：{reason}")

    def _write_application_materials(
        self,
        resume,
        job: JobPosting,
    ) -> tuple[TailorBundle, dict[str, Any], LLMUsageEntry | None]:
        config = self.store.get_agent_model_route("ApplicationWriterAgent")
        route = self.model_router.route_for_agent("ApplicationWriterAgent", config)
        if route.mode != "external":
            return self.application_writer.write(resume, job), {
                "status": "local",
                "provider": route.provider,
                "model": route.model,
                "reason": route.reason,
                "route": self._route_payload(route),
            }, None
        try:
            result = self.llm_client.generate_application_materials(config, resume, job)
            bundle = self.application_writer.write_from_llm_json(resume, job, result.content)
            return bundle, {
                "status": "success",
                "provider": result.provider,
                "model": result.model,
                "estimated_tokens": result.estimated,
                "route": self._route_payload(route),
            }, self._usage_from_llm_result(result, config)
        except Exception as exc:
            safe_error = self._safe_error(exc)
            return self.application_writer.write(resume, job), {
                "status": "fallback",
                "provider": config.provider,
                "model": config.model,
                "error": safe_error,
                "route": self._route_payload(route),
            }, self.metrics.record_failure(
                agent_name="ApplicationWriterAgent",
                provider=config.provider,
                model=config.model,
                error=safe_error,
            )

    def _usage_from_llm_result(self, result: LLMCompletionResult, config: ModelConfig) -> LLMUsageEntry:
        return self.metrics.record_llm_usage(
            agent_name="ApplicationWriterAgent",
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

    def _route_payload(self, route: ModelRoute) -> dict[str, str]:
        return asdict(route)

    def _usage_payload(self, usage: LLMUsageEntry) -> dict[str, Any]:
        return {
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "total_tokens": usage.total_tokens,
            "cost_usd": usage.cost_usd,
            "duration_ms": usage.duration_ms,
            "usage_status": usage.status,
            "usage_estimated": usage.estimated,
        }

    def _resume_parse_output_summary(self, resume) -> str:
        extraction = resume.profile.get("extraction", {})
        source_type = extraction.get("source_type") or resume.file_type
        status = extraction.get("status") or "unknown"
        page_count = extraction.get("page_count") or 0
        summary = f"resume_id={resume.id}; chars={len(resume.raw_text)}; source={source_type}; extraction={status}"
        if page_count:
            summary += f"; pages={page_count}"
        return summary

    def _safe_error(self, exc: Exception) -> str:
        return str(exc).replace("\n", " ")[:240]

    def create_application(self, job_id: int, note: str = "") -> ApplicationRecord:
        job = self.store.get_job(job_id)
        record = self.store.create_application(job, note=note)
        self._record_usage("ApplicationTrackerAgent", job.title, record.current_status.value)
        return record

    def apply_to_platform(self, job_id: int, note: str = "") -> ApplicationRecord:
        job = self.store.get_job(job_id)
        platform_result = BrowserJobExtractorService().apply_to_job(job.platform, job.url)
        if not platform_result.get("confirmed"):
            evidence = str(platform_result.get("evidence") or platform_result.get("status") or "platform not confirmed")
            raise PlatformApplicationNotConfirmedError(evidence)
        confirmation_note = self._platform_application_note(note, platform_result)
        platform_proof = self._platform_application_proof(job.platform, platform_result)
        record = self.store.create_application(job, note=confirmation_note, platform_proof=platform_proof)
        self._record_usage("ApplicationTrackerAgent", job.title, record.current_status.value)
        return record

    def preview_platform_application(self, job_id: int) -> dict[str, Any]:
        job = self.store.get_job(job_id)
        preview = BrowserJobExtractorService().preview_apply_to_job(job.platform, job.url)
        return {
            "job": job,
            "platform": job.platform,
            **preview,
        }

    def _platform_application_note(self, note: str, platform_result: dict[str, Any]) -> str:
        parts = [note.strip()]
        evidence = str(platform_result.get("evidence") or "").strip()
        source_url = str(platform_result.get("source_url") or "").strip()
        if evidence:
            parts.append(f"平台确认：{evidence}")
        if source_url:
            parts.append(f"平台链接：{source_url}")
        return "；".join(part for part in parts if part)

    def _platform_application_proof(
        self,
        platform: str,
        platform_result: dict[str, Any],
    ) -> ApplicationPlatformProof:
        evidence = str(platform_result.get("evidence") or "").strip()
        status = str(platform_result.get("status") or "").strip()
        action = str(platform_result.get("action") or "").strip()
        page_summary = str(platform_result.get("page_summary") or platform_result.get("page_status_text") or evidence).strip()
        return ApplicationPlatformProof(
            platform=platform,
            source_url=str(platform_result.get("source_url") or "").strip(),
            action=action,
            status=status,
            evidence=evidence,
            button_text=str(platform_result.get("button_text") or self._button_text_from_evidence(evidence)).strip(),
            confirmed_at=datetime.now(UTC),
            page_summary=page_summary[:500],
        )

    def _button_text_from_evidence(self, evidence: str) -> str:
        marker = "clicked platform button:"
        if marker in evidence:
            return evidence.split(marker, 1)[1].strip().strip('"“”')
        return ""

    def update_application_status(
        self,
        application_id: int,
        status: ApplicationStatus,
        note: str,
    ) -> ApplicationRecord:
        record = self.store.update_application_status(application_id, status, note)
        self._record_usage("ApplicationTrackerAgent", str(application_id), status.value)
        return record

    def sync_applications(self) -> dict[str, Any]:
        return {
            "status": "completed",
            "mode": "manual_plus_semiautomatic",
            "message": "第一版保留用户手动状态，真实平台半自动读取由适配器扩展。",
            "updated": 0,
        }

    def list_applications(self) -> list[ApplicationRecord]:
        return self.store.list_applications()

    def application_analytics(self) -> dict[str, Any]:
        records = self.store.list_applications()
        totals = self._rate_bucket(records)
        hourly: dict[str, dict[str, Any]] = {}
        weekday: dict[str, dict[str, Any]] = {}
        platform: dict[str, dict[str, Any]] = {}

        hour_groups: dict[str, list[ApplicationRecord]] = defaultdict(list)
        weekday_groups: dict[str, list[ApplicationRecord]] = defaultdict(list)
        platform_groups: dict[str, list[ApplicationRecord]] = defaultdict(list)
        for record in records:
            hour_groups[f"{record.applied_at.hour:02d}:00"].append(record)
            weekday_groups[record.applied_at.strftime("%A")].append(record)
            platform_groups[record.platform].append(record)

        for key, group in hour_groups.items():
            hourly[key] = self._rate_bucket(group)
        for key, group in weekday_groups.items():
            weekday[key] = self._rate_bucket(group)
        for key, group in platform_groups.items():
            platform[key] = self._rate_bucket(group)

        return {
            "totals": totals,
            "hourly": dict(sorted(hourly.items())),
            "weekday": weekday,
            "platform": platform,
        }

    def llm_usage_summary(self) -> dict[str, Any]:
        entries = self.store.list_llm_usage()
        self.metrics.entries = entries
        return self.metrics.summary().model_dump(mode="json")

    def agent_events_summary(self) -> dict[str, Any]:
        total_cost = sum(entry.cost_usd for entry in self.store.list_llm_usage())
        snapshot = self.event_stream.snapshot(total_cost_usd=total_cost)
        snapshot["orchestrator"] = self.orchestrator.snapshot()
        return snapshot

    def _rate_bucket(self, records: list[ApplicationRecord]) -> dict[str, Any]:
        applications = len(records)
        read = sum(1 for record in records if record.read_at is not None or self._has_event(record, ApplicationStatus.READ))
        replied = sum(
            1 for record in records if record.replied_at is not None or self._has_event(record, ApplicationStatus.REPLIED)
        )
        progressed = sum(
            1
            for record in records
            if record.current_status in {ApplicationStatus.INTERVIEW, ApplicationStatus.ASSESSMENT}
            or self._has_event(record, ApplicationStatus.INTERVIEW)
            or self._has_event(record, ApplicationStatus.ASSESSMENT)
        )
        return {
            "applications": applications,
            "read": read,
            "replied": replied,
            "progressed": progressed,
            "read_rate": round(read / applications, 4) if applications else 0,
            "reply_rate": round(replied / applications, 4) if applications else 0,
            "progress_rate": round(progressed / applications, 4) if applications else 0,
        }

    def _has_event(self, record: ApplicationRecord, status: ApplicationStatus) -> bool:
        return any(event.status == status for event in record.events)

    def _record_usage(self, agent_name: str, prompt: str, completion: str) -> None:
        entry = self.metrics.estimate_and_record(agent_name, prompt, completion)
        self.store.save_llm_usage(entry)

    def _record_agent_step(
        self,
        task_id: int | None,
        agent_name: str,
        status: str,
        step: str,
        input_summary: str = "",
        output_summary: str = "",
        error: str = "",
        total_tokens: int = 0,
        cost_usd: float = 0.0,
    ):
        return self.orchestrator.record_step(
            task_id,
            agent_name,
            status,
            step,
            input_summary=input_summary,
            output_summary=output_summary,
            error=error,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
        )
