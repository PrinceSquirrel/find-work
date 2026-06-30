from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from typing import Any

from app.agents import ApplicationWriterAgent, JobMatchAgent, ResumeParserAgent, ReviewAgent
from app.platforms import BossAdapter, ShixisengAdapter
from app.schemas import (
    ApplicationRecord,
    ApplicationStatus,
    ExtractedJobCandidate,
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


class JobApplicationService:
    def __init__(self, store: SQLiteStore):
        self.store = store
        self.resume_parser = ResumeParserAgent()
        self.job_match = JobMatchAgent()
        self.application_writer = ApplicationWriterAgent()
        self.review = ReviewAgent()
        self.metrics = MetricsService()
        self.event_stream = EventStreamService()
        self.orchestrator = OrchestratorService(self.event_stream)
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
            stored = self.store.create_resume(parsed)
            self._record_usage("ResumeParserAgent", filename, stored.raw_text)
            self._record_agent_step(
                task_id,
                "ResumeParserAgent",
                "success",
                "parse resume",
                input_summary=filename,
                output_summary=f"resume_id={stored.id}; chars={len(stored.raw_text)}",
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
            for platform in platforms:
                adapter = self.adapters.get(platform)
                if adapter is None:
                    continue
                for job in adapter.search(resume, keywords, city):
                    match = self.job_match.match(resume, job)
                    stored_job = self.store.save_job(job, run.id or 0, match)
                    saved_count += 1
                    self._record_usage("JobSearchAgent", " ".join(keywords), stored_job.description)
                    self._record_usage("JobMatchAgent", resume.raw_text + job.description, str(match.score))
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
                output_summary=f"matches={saved_count}",
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
        extraction_response = BrowserJobExtractorService().extract(platforms, limit=20)
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
        for candidate in extracted_jobs:
            job = self._candidate_to_job(candidate, city)
            match = self.job_match.match(resume, job)
            stored_job = self.store.save_job(job, run.id or 0, match)
            saved_count += 1
            self._record_usage("JobSearchAgent", " ".join(keywords), stored_job.description)
            self._record_usage("JobMatchAgent", resume.raw_text + stored_job.description, str(match.score))
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
            output_summary=f"matches={saved_count}",
        )
        return run.model_copy(update={"status": "completed"})

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

    def list_jobs(self) -> list[dict[str, Any]]:
        return self.store.list_jobs()

    def tailor_for_job(self, job_id: int, resume_id: int) -> dict[str, Any]:
        resume = self.store.get_resume(resume_id)
        job = self.store.get_job(job_id)
        task_input = f"resume_id={resume_id}; job_id={job_id}; company={job.company}; title={job.title}"
        task_id = self.orchestrator.start_task("application.materials", task_input)
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
            review_route = self.model_router.route_for_agent("ReviewAgent", self.store.get_model_config())
            review["llm"] = llm_metadata
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

    def _write_application_materials(
        self,
        resume,
        job: JobPosting,
    ) -> tuple[TailorBundle, dict[str, Any], LLMUsageEntry | None]:
        config = self.store.get_model_config()
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
        )

    def _route_payload(self, route: ModelRoute) -> dict[str, str]:
        return asdict(route)

    def _safe_error(self, exc: Exception) -> str:
        return str(exc).replace("\n", " ")[:240]

    def create_application(self, job_id: int, note: str = "") -> ApplicationRecord:
        job = self.store.get_job(job_id)
        record = self.store.create_application(job, note=note)
        self._record_usage("ApplicationTrackerAgent", job.title, record.current_status.value)
        return record

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
