from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.agents.application_tracker import ApplicationTrackerAgent
from app.schemas import (
    ApplicationEvent,
    ApplicationRecord,
    ApplicationStatus,
    GreetingMessage,
    JobMatch,
    JobPosting,
    LLMUsageEntry,
    ModelConfig,
    ModelConfigUpdate,
    ResumeDraft,
    SearchRun,
    TailoredResume,
)


class SQLiteStore:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS resumes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT NOT NULL,
                    raw_text TEXT NOT NULL,
                    profile_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS search_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    resume_id INTEGER NOT NULL,
                    keywords_json TEXT NOT NULL,
                    city TEXT NOT NULL,
                    platforms_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    search_run_id INTEGER,
                    platform TEXT NOT NULL,
                    company TEXT NOT NULL,
                    title TEXT NOT NULL,
                    city TEXT NOT NULL,
                    salary TEXT NOT NULL,
                    description TEXT NOT NULL,
                    url TEXT NOT NULL,
                    job_type TEXT NOT NULL,
                    match_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tailored_resumes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL,
                    resume_id INTEGER NOT NULL,
                    resume_text TEXT NOT NULL,
                    diff_summary_json TEXT NOT NULL,
                    risk_flags_json TEXT NOT NULL,
                    truth_check_passed INTEGER NOT NULL,
                    greeting_json TEXT NOT NULL,
                    review_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL,
                    company TEXT NOT NULL,
                    title TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    applied_at TEXT NOT NULL,
                    current_status TEXT NOT NULL,
                    read_at TEXT,
                    replied_at TEXT,
                    progress_stage TEXT NOT NULL,
                    latest_note TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS application_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    application_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    note TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS llm_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_name TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    prompt_tokens INTEGER NOT NULL,
                    completion_tokens INTEGER NOT NULL,
                    total_tokens INTEGER NOT NULL,
                    cost_usd REAL NOT NULL,
                    duration_ms INTEGER NOT NULL,
                    estimated INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'success',
                    error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS model_config (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    base_url TEXT NOT NULL,
                    api_key_env_var TEXT NOT NULL,
                    enabled INTEGER NOT NULL,
                    estimation_only INTEGER NOT NULL,
                    timeout_ms INTEGER NOT NULL,
                    input_price_per_million REAL NOT NULL,
                    output_price_per_million REAL NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS orchestrator_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_name TEXT NOT NULL,
                    input_summary TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS orchestrator_steps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER NOT NULL,
                    event_id INTEGER NOT NULL,
                    agent_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    step TEXT NOT NULL,
                    input_summary TEXT NOT NULL,
                    output_summary TEXT NOT NULL,
                    error TEXT NOT NULL,
                    total_tokens INTEGER NOT NULL,
                    cost_usd REAL NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            self._ensure_llm_usage_columns(conn)

    def _ensure_llm_usage_columns(self, conn: sqlite3.Connection) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(llm_usage)").fetchall()}
        if "status" not in columns:
            conn.execute("ALTER TABLE llm_usage ADD COLUMN status TEXT NOT NULL DEFAULT 'success'")
        if "error" not in columns:
            conn.execute("ALTER TABLE llm_usage ADD COLUMN error TEXT NOT NULL DEFAULT ''")

    def get_model_config(self) -> ModelConfig:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM model_config WHERE id = 1").fetchone()
        if row is None:
            return self._default_model_config()
        return self._model_config_from_row(row)

    def save_model_config(self, update: ModelConfigUpdate) -> ModelConfig:
        config = ModelConfig(
            **update.model_dump(),
            api_key_configured=self._is_env_configured(update.api_key_env_var),
            updated_at=datetime.now(UTC),
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO model_config (
                    id, provider, model, base_url, api_key_env_var, enabled,
                    estimation_only, timeout_ms, input_price_per_million,
                    output_price_per_million, updated_at
                )
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    provider = excluded.provider,
                    model = excluded.model,
                    base_url = excluded.base_url,
                    api_key_env_var = excluded.api_key_env_var,
                    enabled = excluded.enabled,
                    estimation_only = excluded.estimation_only,
                    timeout_ms = excluded.timeout_ms,
                    input_price_per_million = excluded.input_price_per_million,
                    output_price_per_million = excluded.output_price_per_million,
                    updated_at = excluded.updated_at
                """,
                (
                    config.provider,
                    config.model,
                    config.base_url,
                    config.api_key_env_var,
                    1 if config.enabled else 0,
                    1 if config.estimation_only else 0,
                    config.timeout_ms,
                    config.input_price_per_million,
                    config.output_price_per_million,
                    config.updated_at.isoformat(),
                ),
            )
        return config

    def create_resume(self, resume: ResumeDraft) -> ResumeDraft:
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO resumes (filename, raw_text, profile_json, created_at) VALUES (?, ?, ?, ?)",
                (
                    resume.filename,
                    resume.raw_text,
                    json.dumps(resume.profile, ensure_ascii=False),
                    resume.created_at.isoformat(),
                ),
            )
            return resume.model_copy(update={"id": cursor.lastrowid})

    def get_resume(self, resume_id: int) -> ResumeDraft:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM resumes WHERE id = ?", (resume_id,)).fetchone()
        if row is None:
            raise KeyError(f"Resume {resume_id} not found")
        return ResumeDraft(
            id=row["id"],
            filename=row["filename"],
            raw_text=row["raw_text"],
            profile=json.loads(row["profile_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def create_search_run(self, run: SearchRun) -> SearchRun:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO search_runs (resume_id, keywords_json, city, platforms_json, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run.resume_id,
                    json.dumps(run.keywords, ensure_ascii=False),
                    run.city,
                    json.dumps(run.platforms, ensure_ascii=False),
                    run.status,
                    run.created_at.isoformat(),
                ),
            )
            return run.model_copy(update={"id": cursor.lastrowid})

    def update_search_run_status(self, run_id: int, status: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE search_runs SET status = ? WHERE id = ?", (status, run_id))

    def save_job(self, job: JobPosting, search_run_id: int, match: JobMatch) -> JobPosting:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO jobs (
                    search_run_id, platform, company, title, city, salary, description,
                    url, job_type, match_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    search_run_id,
                    job.platform,
                    job.company,
                    job.title,
                    job.city,
                    job.salary,
                    job.description,
                    job.url,
                    job.job_type,
                    json.dumps(match.model_dump(mode="json"), ensure_ascii=False),
                    job.created_at.isoformat(),
                ),
            )
            job_id = cursor.lastrowid
            stored_match = match.model_copy(update={"job_id": job_id})
            conn.execute(
                "UPDATE jobs SET match_json = ? WHERE id = ?",
                (json.dumps(stored_match.model_dump(mode="json"), ensure_ascii=False), job_id),
            )
            return job.model_copy(update={"id": job_id})

    def list_jobs(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM jobs ORDER BY id DESC").fetchall()
        return [self._job_row_to_dict(row) for row in rows]

    def get_job(self, job_id: int) -> JobPosting:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(f"Job {job_id} not found")
        return JobPosting(
            id=row["id"],
            platform=row["platform"],
            company=row["company"],
            title=row["title"],
            city=row["city"],
            salary=row["salary"],
            description=row["description"],
            url=row["url"],
            job_type=row["job_type"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def save_tailor_bundle(
        self,
        tailored: TailoredResume,
        greeting: GreetingMessage,
        review: dict[str, Any],
    ) -> dict[str, Any]:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO tailored_resumes (
                    job_id, resume_id, resume_text, diff_summary_json, risk_flags_json,
                    truth_check_passed, greeting_json, review_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tailored.job_id,
                    tailored.resume_id,
                    tailored.resume_text,
                    json.dumps(tailored.diff_summary, ensure_ascii=False),
                    json.dumps(tailored.risk_flags, ensure_ascii=False),
                    1 if tailored.truth_check_passed else 0,
                    json.dumps(greeting.model_dump(mode="json"), ensure_ascii=False),
                    json.dumps(review, ensure_ascii=False),
                    tailored.created_at.isoformat(),
                ),
            )
            tailored = tailored.model_copy(update={"id": cursor.lastrowid})
        return {
            **tailored.model_dump(mode="json"),
            "greeting": greeting.model_dump(mode="json"),
            "review": review,
        }

    def create_application(self, job: JobPosting, note: str = "") -> ApplicationRecord:
        now = datetime.now(UTC)
        tracker = ApplicationTrackerAgent()
        record = tracker.create_record(
            job_id=job.id or 0,
            company=job.company,
            title=job.title,
            platform=job.platform,
            applied_at=now,
            note=note,
        )
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO applications (
                    job_id, company, title, platform, applied_at, current_status,
                    read_at, replied_at, progress_stage, latest_note
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.job_id,
                    record.company,
                    record.title,
                    record.platform,
                    record.applied_at.isoformat(),
                    record.current_status.value,
                    record.read_at.isoformat() if record.read_at else None,
                    record.replied_at.isoformat() if record.replied_at else None,
                    record.progress_stage,
                    record.latest_note,
                ),
            )
            application_id = cursor.lastrowid
            event = record.events[-1]
            conn.execute(
                """
                INSERT INTO application_events (application_id, status, occurred_at, note)
                VALUES (?, ?, ?, ?)
                """,
                (application_id, event.status.value, event.occurred_at.isoformat(), event.note),
            )
        return self.get_application(application_id)

    def get_application(self, application_id: int) -> ApplicationRecord:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM applications WHERE id = ?", (application_id,)).fetchone()
            event_rows = conn.execute(
                "SELECT * FROM application_events WHERE application_id = ? ORDER BY id",
                (application_id,),
            ).fetchall()
        if row is None:
            raise KeyError(f"Application {application_id} not found")
        events = [
            ApplicationEvent(
                id=event["id"],
                application_id=event["application_id"],
                status=ApplicationStatus(event["status"]),
                occurred_at=datetime.fromisoformat(event["occurred_at"]),
                note=event["note"],
            )
            for event in event_rows
        ]
        return ApplicationRecord(
            id=row["id"],
            job_id=row["job_id"],
            company=row["company"],
            title=row["title"],
            platform=row["platform"],
            applied_at=datetime.fromisoformat(row["applied_at"]),
            current_status=ApplicationStatus(row["current_status"]),
            read_at=datetime.fromisoformat(row["read_at"]) if row["read_at"] else None,
            replied_at=datetime.fromisoformat(row["replied_at"]) if row["replied_at"] else None,
            progress_stage=row["progress_stage"],
            latest_note=row["latest_note"],
            events=events,
        )

    def update_application_status(
        self,
        application_id: int,
        next_status: ApplicationStatus,
        note: str,
    ) -> ApplicationRecord:
        record = self.get_application(application_id)
        now = datetime.now(UTC)
        tracker = ApplicationTrackerAgent()
        updated = tracker.transition(record, next_status, note=note, occurred_at=now)
        event = updated.events[-1]
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE applications
                SET current_status = ?, read_at = ?, replied_at = ?, progress_stage = ?, latest_note = ?
                WHERE id = ?
                """,
                (
                    updated.current_status.value,
                    updated.read_at.isoformat() if updated.read_at else None,
                    updated.replied_at.isoformat() if updated.replied_at else None,
                    updated.progress_stage,
                    updated.latest_note,
                    application_id,
                ),
            )
            conn.execute(
                """
                INSERT INTO application_events (application_id, status, occurred_at, note)
                VALUES (?, ?, ?, ?)
                """,
                (application_id, event.status.value, event.occurred_at.isoformat(), event.note),
            )
        return self.get_application(application_id)

    def list_applications(self) -> list[ApplicationRecord]:
        with self._connect() as conn:
            rows = conn.execute("SELECT id FROM applications ORDER BY applied_at DESC").fetchall()
        return [self.get_application(row["id"]) for row in rows]

    def save_llm_usage(self, entry: LLMUsageEntry) -> LLMUsageEntry:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO llm_usage (
                    agent_name, provider, model, prompt_tokens, completion_tokens,
                    total_tokens, cost_usd, duration_ms, estimated, status, error, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.agent_name,
                    entry.provider,
                    entry.model,
                    entry.prompt_tokens,
                    entry.completion_tokens,
                    entry.total_tokens,
                    entry.cost_usd,
                    entry.duration_ms,
                    1 if entry.estimated else 0,
                    entry.status,
                    entry.error,
                    entry.created_at.isoformat(),
                ),
            )
            return entry.model_copy(update={"id": cursor.lastrowid})

    def list_llm_usage(self) -> list[LLMUsageEntry]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM llm_usage ORDER BY id").fetchall()
        return [
            LLMUsageEntry(
                id=row["id"],
                agent_name=row["agent_name"],
                provider=row["provider"],
                model=row["model"],
                prompt_tokens=row["prompt_tokens"],
                completion_tokens=row["completion_tokens"],
                total_tokens=row["total_tokens"],
                cost_usd=row["cost_usd"],
                duration_ms=row["duration_ms"],
                estimated=bool(row["estimated"]),
                status=row["status"],
                error=row["error"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    def create_orchestrator_task(
        self,
        task_name: str,
        input_summary: str,
        status: str,
        error: str,
        started_at: datetime,
        completed_at: datetime | None,
    ) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO orchestrator_tasks (
                    task_name, input_summary, status, error, started_at, completed_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    task_name,
                    input_summary,
                    status,
                    error,
                    started_at.isoformat(),
                    completed_at.isoformat() if completed_at else None,
                ),
            )
            return int(cursor.lastrowid)

    def update_orchestrator_task(
        self,
        task_id: int,
        status: str,
        error: str,
        completed_at: datetime | None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE orchestrator_tasks
                SET status = ?, error = ?, completed_at = ?
                WHERE id = ?
                """,
                (status, error, completed_at.isoformat() if completed_at else None, task_id),
            )

    def save_orchestrator_step(
        self,
        task_id: int,
        event_id: int,
        agent_name: str,
        status: str,
        step: str,
        input_summary: str,
        output_summary: str,
        error: str,
        total_tokens: int,
        cost_usd: float,
        created_at: datetime,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO orchestrator_steps (
                    task_id, event_id, agent_name, status, step, input_summary,
                    output_summary, error, total_tokens, cost_usd, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    event_id,
                    agent_name,
                    status,
                    step,
                    input_summary,
                    output_summary,
                    error,
                    total_tokens,
                    cost_usd,
                    created_at.isoformat(),
                ),
            )

    def list_orchestrator_tasks(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            task_rows = conn.execute(
                "SELECT * FROM orchestrator_tasks ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
            tasks = [self._orchestrator_task_row_to_dict(row) for row in reversed(task_rows)]
            for task in tasks:
                step_rows = conn.execute(
                    "SELECT * FROM orchestrator_steps WHERE task_id = ? ORDER BY id",
                    (task["id"],),
                ).fetchall()
                task["steps"] = [self._orchestrator_step_row_to_dict(row) for row in step_rows]
        return tasks

    def _default_model_config(self) -> ModelConfig:
        api_key_env_var = os.getenv("OPENAI_API_KEY_ENV_VAR", "OPENAI_API_KEY")
        return ModelConfig(
            provider=os.getenv("LLM_PROVIDER", "local"),
            model=os.getenv("OPENAI_MODEL", os.getenv("LLM_USAGE_MODEL", "local-estimator")),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            api_key_env_var=api_key_env_var,
            api_key_configured=self._is_env_configured(api_key_env_var),
            enabled=self._env_bool("LLM_ENABLED", False),
            estimation_only=self._env_bool("LLM_ESTIMATION_ONLY", True),
            timeout_ms=self._env_int("LLM_TIMEOUT_MS", 30000),
            input_price_per_million=self._env_float("LLM_INPUT_PRICE_PER_MILLION", 0.0),
            output_price_per_million=self._env_float("LLM_OUTPUT_PRICE_PER_MILLION", 0.0),
        )

    def _model_config_from_row(self, row: sqlite3.Row) -> ModelConfig:
        api_key_env_var = row["api_key_env_var"]
        return ModelConfig(
            provider=row["provider"],
            model=row["model"],
            base_url=row["base_url"],
            api_key_env_var=api_key_env_var,
            api_key_configured=self._is_env_configured(api_key_env_var),
            enabled=bool(row["enabled"]),
            estimation_only=bool(row["estimation_only"]),
            timeout_ms=row["timeout_ms"],
            input_price_per_million=row["input_price_per_million"],
            output_price_per_million=row["output_price_per_million"],
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _is_env_configured(self, name: str) -> bool:
        return bool(os.getenv(name))

    def _env_bool(self, name: str, default: bool) -> bool:
        value = os.getenv(name)
        if value is None:
            return default
        return value.strip().lower() in {"1", "true", "yes", "on"}

    def _env_int(self, name: str, default: int) -> int:
        try:
            return int(os.getenv(name, str(default)))
        except ValueError:
            return default

    def _env_float(self, name: str, default: float) -> float:
        try:
            return float(os.getenv(name, str(default)))
        except ValueError:
            return default

    def _job_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "platform": row["platform"],
            "company": row["company"],
            "title": row["title"],
            "city": row["city"],
            "salary": row["salary"],
            "description": row["description"],
            "url": row["url"],
            "job_type": row["job_type"],
            "created_at": row["created_at"],
            "match": json.loads(row["match_json"]),
        }

    def _orchestrator_task_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "task_name": row["task_name"],
            "input_summary": row["input_summary"],
            "status": row["status"],
            "error": row["error"],
            "started_at": row["started_at"],
            "completed_at": row["completed_at"],
            "steps": [],
        }

    def _orchestrator_step_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "event_id": row["event_id"],
            "agent_name": row["agent_name"],
            "status": row["status"],
            "step": row["step"],
            "input_summary": row["input_summary"],
            "output_summary": row["output_summary"],
            "error": row["error"],
            "total_tokens": row["total_tokens"],
            "cost_usd": row["cost_usd"],
        }
