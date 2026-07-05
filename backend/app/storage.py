from __future__ import annotations

import json
import os
import re
import sqlite3
import base64
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.agents.application_tracker import ApplicationTrackerAgent
from app.schemas import (
    AgentModelRoute,
    ApplicationEvent,
    ApplicationPlatformProof,
    ApplicationRecord,
    ApplicationStatus,
    GreetingMessage,
    JobMatch,
    JobPosting,
    KnowledgeDocument,
    KnowledgeReindexResponse,
    RetrievalHit,
    LLMUsageEntry,
    ModelConfig,
    ModelConfigUpdate,
    ModelProfile,
    ModelProfileCreate,
    ModelProfileUpdate,
    ResumeDraft,
    SearchRun,
    TailoredResume,
)

MODEL_ROUTE_AGENTS = (
    "OrchestratorAgent",
    "ResumeParserAgent",
    "ApplicationWriterAgent",
    "JobMatchAgent",
    "ReviewAgent",
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
                    file_type TEXT NOT NULL DEFAULT 'txt',
                    template_available INTEGER NOT NULL DEFAULT 0,
                    original_file_bytes BLOB,
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
                    detail_status TEXT NOT NULL DEFAULT '',
                    detail_reason TEXT NOT NULL DEFAULT '',
                    match_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tailored_resumes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL,
                    resume_id INTEGER NOT NULL,
                    resume_text TEXT NOT NULL,
                    resume_rewrite TEXT NOT NULL DEFAULT '',
                    project_rewrite TEXT NOT NULL DEFAULT '',
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
                    latest_note TEXT NOT NULL,
                    platform_proof_json TEXT NOT NULL DEFAULT '{}'
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
                    api_key_ciphertext TEXT NOT NULL DEFAULT '',
                    api_key_masked TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL,
                    estimation_only INTEGER NOT NULL,
                    timeout_ms INTEGER NOT NULL,
                    input_price_per_million REAL NOT NULL,
                    output_price_per_million REAL NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS agent_model_routes (
                    agent_name TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    base_url TEXT NOT NULL,
                    api_key_env_var TEXT NOT NULL,
                    api_key_ciphertext TEXT NOT NULL DEFAULT '',
                    api_key_masked TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL,
                    estimation_only INTEGER NOT NULL,
                    timeout_ms INTEGER NOT NULL,
                    input_price_per_million REAL NOT NULL,
                    output_price_per_million REAL NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS model_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    base_url TEXT NOT NULL,
                    api_key_env_var TEXT NOT NULL,
                    api_key_ciphertext TEXT NOT NULL DEFAULT '',
                    api_key_masked TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL,
                    estimation_only INTEGER NOT NULL,
                    timeout_ms INTEGER NOT NULL,
                    input_price_per_million REAL NOT NULL,
                    output_price_per_million REAL NOT NULL,
                    created_at TEXT NOT NULL,
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
                CREATE TABLE IF NOT EXISTS knowledge_documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_type TEXT NOT NULL,
                    source_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    chunk_count INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    UNIQUE(source_type, source_id)
                );
                CREATE TABLE IF NOT EXISTS knowledge_chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id INTEGER NOT NULL,
                    source_type TEXT NOT NULL,
                    source_id INTEGER NOT NULL,
                    chunk_index INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_chunks_fts USING fts5(
                    content,
                    title,
                    source_type UNINDEXED,
                    source_id UNINDEXED,
                    document_id UNINDEXED,
                    chunk_id UNINDEXED
                );
                """
            )
            self._ensure_llm_usage_columns(conn)
            self._ensure_resume_template_columns(conn)
            self._ensure_tailored_resume_columns(conn)
            self._ensure_job_detail_columns(conn)
            self._ensure_application_proof_columns(conn)
            self._ensure_model_secret_columns(conn)

    def _ensure_llm_usage_columns(self, conn: sqlite3.Connection) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(llm_usage)").fetchall()}
        if "status" not in columns:
            conn.execute("ALTER TABLE llm_usage ADD COLUMN status TEXT NOT NULL DEFAULT 'success'")
        if "error" not in columns:
            conn.execute("ALTER TABLE llm_usage ADD COLUMN error TEXT NOT NULL DEFAULT ''")

    def _ensure_resume_template_columns(self, conn: sqlite3.Connection) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(resumes)").fetchall()}
        if "file_type" not in columns:
            conn.execute("ALTER TABLE resumes ADD COLUMN file_type TEXT NOT NULL DEFAULT 'txt'")
        if "template_available" not in columns:
            conn.execute("ALTER TABLE resumes ADD COLUMN template_available INTEGER NOT NULL DEFAULT 0")
        if "original_file_bytes" not in columns:
            conn.execute("ALTER TABLE resumes ADD COLUMN original_file_bytes BLOB")

    def _ensure_tailored_resume_columns(self, conn: sqlite3.Connection) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(tailored_resumes)").fetchall()}
        if "project_rewrite" not in columns:
            conn.execute("ALTER TABLE tailored_resumes ADD COLUMN project_rewrite TEXT NOT NULL DEFAULT ''")
        if "resume_rewrite" not in columns:
            conn.execute("ALTER TABLE tailored_resumes ADD COLUMN resume_rewrite TEXT NOT NULL DEFAULT ''")

    def _ensure_job_detail_columns(self, conn: sqlite3.Connection) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        if "detail_status" not in columns:
            conn.execute("ALTER TABLE jobs ADD COLUMN detail_status TEXT NOT NULL DEFAULT ''")
        if "detail_reason" not in columns:
            conn.execute("ALTER TABLE jobs ADD COLUMN detail_reason TEXT NOT NULL DEFAULT ''")

    def _ensure_application_proof_columns(self, conn: sqlite3.Connection) -> None:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(applications)").fetchall()}
        if "platform_proof_json" not in columns:
            conn.execute("ALTER TABLE applications ADD COLUMN platform_proof_json TEXT NOT NULL DEFAULT '{}'")

    def _ensure_model_secret_columns(self, conn: sqlite3.Connection) -> None:
        for table in ("model_config", "model_profiles", "agent_model_routes"):
            columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            if "api_key_ciphertext" not in columns:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN api_key_ciphertext TEXT NOT NULL DEFAULT ''")
            if "api_key_masked" not in columns:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN api_key_masked TEXT NOT NULL DEFAULT ''")

    def reindex_knowledge(self) -> KnowledgeReindexResponse:
        now = datetime.now(UTC).isoformat()
        sources = self._knowledge_sources()
        with self._connect() as conn:
            conn.execute("DELETE FROM knowledge_chunks_fts")
            conn.execute("DELETE FROM knowledge_chunks")
            conn.execute("DELETE FROM knowledge_documents")
            document_count = 0
            chunk_count = 0
            for source in sources:
                chunks = self._chunk_text(source["content"])
                if not chunks:
                    continue
                cursor = conn.execute(
                    """
                    INSERT INTO knowledge_documents (
                        source_type, source_id, title, summary, chunk_count, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        source["source_type"],
                        source["source_id"],
                        source["title"],
                        source["summary"],
                        len(chunks),
                        now,
                    ),
                )
                document_id = int(cursor.lastrowid)
                document_count += 1
                for index, content in enumerate(chunks):
                    chunk_cursor = conn.execute(
                        """
                        INSERT INTO knowledge_chunks (
                            document_id, source_type, source_id, chunk_index,
                            title, content, created_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            document_id,
                            source["source_type"],
                            source["source_id"],
                            index,
                            source["title"],
                            content,
                            now,
                        ),
                    )
                    chunk_id = int(chunk_cursor.lastrowid)
                    conn.execute(
                        """
                        INSERT INTO knowledge_chunks_fts (
                            rowid, content, title, source_type, source_id, document_id, chunk_id
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            chunk_id,
                            content,
                            source["title"],
                            source["source_type"],
                            str(source["source_id"]),
                            str(document_id),
                            str(chunk_id),
                        ),
                    )
                    chunk_count += 1
        return KnowledgeReindexResponse(status="completed", documents=document_count, chunks=chunk_count)

    def list_knowledge_documents(self) -> list[KnowledgeDocument]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM knowledge_documents
                ORDER BY updated_at DESC, id DESC
                """
            ).fetchall()
        return [
            KnowledgeDocument(
                id=row["id"],
                source_type=row["source_type"],
                source_id=row["source_id"],
                title=row["title"],
                summary=row["summary"],
                chunk_count=row["chunk_count"],
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
            for row in rows
        ]

    def query_rag(self, query: str, limit: int = 5) -> list[RetrievalHit]:
        fts_query = self._fts_query(query)
        if not fts_query:
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    CAST(fts.document_id AS INTEGER) AS document_id,
                    CAST(fts.chunk_id AS INTEGER) AS chunk_id,
                    fts.source_type,
                    CAST(fts.source_id AS INTEGER) AS source_id,
                    fts.title,
                    fts.content,
                    bm25(knowledge_chunks_fts) AS rank
                FROM knowledge_chunks_fts AS fts
                WHERE knowledge_chunks_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (fts_query, limit),
            ).fetchall()
        return [
            RetrievalHit(
                document_id=row["document_id"],
                chunk_id=row["chunk_id"],
                source_type=row["source_type"],
                source_id=row["source_id"],
                title=row["title"],
                content=row["content"],
                score=float(row["rank"]),
            )
            for row in rows
        ]

    def _knowledge_sources(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            resume_rows = conn.execute("SELECT id, filename, raw_text FROM resumes ORDER BY id").fetchall()
            job_rows = conn.execute(
                """
                SELECT id, platform, company, title, city, salary, description, url
                FROM jobs
                ORDER BY id
                """
            ).fetchall()
            application_rows = conn.execute(
                """
                SELECT id, company, title, platform, current_status, latest_note, platform_proof_json
                FROM applications
                ORDER BY id
                """
            ).fetchall()
            tailored_rows = conn.execute(
                """
                SELECT tr.id, tr.resume_rewrite, tr.resume_text, tr.greeting_json, j.company, j.title
                FROM tailored_resumes AS tr
                LEFT JOIN jobs AS j ON j.id = tr.job_id
                ORDER BY tr.id
                """
            ).fetchall()

        sources: list[dict[str, Any]] = []
        for row in resume_rows:
            sources.append(
                {
                    "source_type": "resume",
                    "source_id": row["id"],
                    "title": f"简历：{row['filename']}",
                    "summary": self._summary(row["raw_text"]),
                    "content": row["raw_text"],
                }
            )
        for row in job_rows:
            content = "\n".join(
                part
                for part in [
                    f"{row['platform']} {row['company']} {row['title']}",
                    f"{row['city']} {row['salary']}",
                    row["description"],
                    row["url"],
                ]
                if part
            )
            sources.append(
                {
                    "source_type": "job",
                    "source_id": row["id"],
                    "title": f"岗位：{row['company']} - {row['title']}",
                    "summary": self._summary(content),
                    "content": content,
                }
            )
        for row in application_rows:
            proof = self._safe_json(row["platform_proof_json"])
            content = "\n".join(
                part
                for part in [
                    f"{row['platform']} {row['company']} {row['title']} {row['current_status']}",
                    row["latest_note"],
                    json.dumps(proof, ensure_ascii=False),
                ]
                if part
            )
            sources.append(
                {
                    "source_type": "application",
                    "source_id": row["id"],
                    "title": f"投递：{row['company']} - {row['title']}",
                    "summary": self._summary(content),
                    "content": content,
                }
            )
        for row in tailored_rows:
            content = "\n".join(
                part
                for part in [
                    row["resume_rewrite"] or row["resume_text"],
                    row["greeting_json"],
                ]
                if part
            )
            if not content.strip():
                continue
            title = f"材料：{row['company'] or '未知公司'} - {row['title'] or '未知岗位'}"
            sources.append(
                {
                    "source_type": "tailored_resume",
                    "source_id": row["id"],
                    "title": title,
                    "summary": self._summary(content),
                    "content": content,
                }
            )
        return sources

    def _chunk_text(self, text: str, size: int = 900) -> list[str]:
        normalized = "\n".join(line.strip() for line in (text or "").splitlines() if line.strip())
        if not normalized:
            return []
        chunks: list[str] = []
        start = 0
        while start < len(normalized):
            chunks.append(normalized[start : start + size])
            start += size
        return chunks

    def _summary(self, text: str, limit: int = 180) -> str:
        return " ".join((text or "").split())[:limit]

    def _safe_json(self, value: str | None) -> dict[str, Any]:
        try:
            payload = json.loads(value or "{}")
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _fts_query(self, query: str) -> str:
        terms = re.findall(r"[A-Za-z0-9_+#.-]+|[\u4e00-\u9fff]{2,}", query)
        safe_terms = [term.replace('"', "") for term in terms[:8] if term.strip()]
        return " OR ".join(f'"{term}"' for term in safe_terms)

    def get_model_config(self) -> ModelConfig:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM model_config WHERE id = 1").fetchone()
        if row is None:
            return self._default_model_config()
        return self._model_config_from_row(row)

    def save_model_config(self, update: ModelConfigUpdate) -> ModelConfig:
        update_payload = update.model_dump()
        update_payload["model"] = _normalize_model_name(update_payload["model"])
        update_payload.pop("api_key", None)
        api_key_ciphertext, api_key_masked = self._resolve_model_secret(
            update.api_key,
            self._current_model_secret("model_config", "id = 1"),
        )
        api_key = self._decrypt_api_key(api_key_ciphertext)
        config = ModelConfig(
            **update_payload,
            api_key=api_key,
            api_key_secret_id="model_config:1" if api_key_ciphertext else "",
            api_key_masked=api_key_masked,
            api_key_configured=bool(api_key) or self._is_env_configured(update.api_key_env_var),
            updated_at=datetime.now(UTC),
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO model_config (
                    id, provider, model, base_url, api_key_env_var, api_key_ciphertext,
                    api_key_masked, enabled, estimation_only, timeout_ms,
                    input_price_per_million, output_price_per_million, updated_at
                )
                VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    provider = excluded.provider,
                    model = excluded.model,
                    base_url = excluded.base_url,
                    api_key_env_var = excluded.api_key_env_var,
                    api_key_ciphertext = excluded.api_key_ciphertext,
                    api_key_masked = excluded.api_key_masked,
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
                    api_key_ciphertext,
                    api_key_masked,
                    1 if config.enabled else 0,
                    1 if config.estimation_only else 0,
                    config.timeout_ms,
                    config.input_price_per_million,
                    config.output_price_per_million,
                    config.updated_at.isoformat(),
                ),
            )
        return config

    def delete_model_config_api_key(self) -> ModelConfig:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM model_config WHERE id = 1").fetchone()
            if row is None:
                return self._default_model_config()
            conn.execute(
                """
                UPDATE model_config
                SET api_key_ciphertext = '', api_key_masked = '', updated_at = ?
                WHERE id = 1
                """,
                (datetime.now(UTC).isoformat(),),
            )
            row = conn.execute("SELECT * FROM model_config WHERE id = 1").fetchone()
        if row is None:
            return self._default_model_config()
        return self._model_config_from_row(row)

    def list_model_profiles(self) -> list[ModelProfile]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM model_profiles ORDER BY id").fetchall()
        return [self._model_profile_from_row(row) for row in rows]

    def create_model_profile(self, update: ModelProfileCreate) -> ModelProfile:
        now = datetime.now(UTC)
        update_payload = update.model_dump()
        update_payload["model"] = _normalize_model_name(update_payload["model"])
        api_key_ciphertext, api_key_masked = self._resolve_model_secret(update.api_key, None)
        update_payload.pop("api_key", None)
        with self._connect() as conn:
            try:
                cursor = conn.execute(
                    """
                    INSERT INTO model_profiles (
                        name, provider, model, base_url, api_key_env_var, api_key_ciphertext,
                        api_key_masked, enabled, estimation_only, timeout_ms,
                        input_price_per_million, output_price_per_million, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        update_payload["name"],
                        update_payload["provider"],
                        update_payload["model"],
                        update_payload["base_url"],
                        update_payload["api_key_env_var"],
                        api_key_ciphertext,
                        api_key_masked,
                        1 if update_payload["enabled"] else 0,
                        1 if update_payload["estimation_only"] else 0,
                        update_payload["timeout_ms"],
                        update_payload["input_price_per_million"],
                        update_payload["output_price_per_million"],
                        now.isoformat(),
                        now.isoformat(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"Model profile already exists: {update.name}") from exc
            row = conn.execute("SELECT * FROM model_profiles WHERE id = ?", (cursor.lastrowid,)).fetchone()
        if row is None:
            raise KeyError("Model profile was not created")
        return self._model_profile_from_row(row)

    def update_model_profile(self, profile_id: int, update: ModelProfileUpdate) -> ModelProfile:
        now = datetime.now(UTC)
        update_payload = update.model_dump()
        update_payload["model"] = _normalize_model_name(update_payload["model"])
        api_key_ciphertext, api_key_masked = self._resolve_model_secret(
            update.api_key,
            self._current_model_secret("model_profiles", "id = ?", (profile_id,)),
        )
        update_payload.pop("api_key", None)
        with self._connect() as conn:
            try:
                cursor = conn.execute(
                    """
                    UPDATE model_profiles SET
                        name = ?,
                        provider = ?,
                        model = ?,
                        base_url = ?,
                        api_key_env_var = ?,
                        api_key_ciphertext = ?,
                        api_key_masked = ?,
                        enabled = ?,
                        estimation_only = ?,
                        timeout_ms = ?,
                        input_price_per_million = ?,
                        output_price_per_million = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        update_payload["name"],
                        update_payload["provider"],
                        update_payload["model"],
                        update_payload["base_url"],
                        update_payload["api_key_env_var"],
                        api_key_ciphertext,
                        api_key_masked,
                        1 if update_payload["enabled"] else 0,
                        1 if update_payload["estimation_only"] else 0,
                        update_payload["timeout_ms"],
                        update_payload["input_price_per_million"],
                        update_payload["output_price_per_million"],
                        now.isoformat(),
                        profile_id,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"Model profile already exists: {update.name}") from exc
            if cursor.rowcount == 0:
                raise KeyError(f"Model profile not found: {profile_id}")
            row = conn.execute("SELECT * FROM model_profiles WHERE id = ?", (profile_id,)).fetchone()
        if row is None:
            raise KeyError(f"Model profile not found: {profile_id}")
        return self._model_profile_from_row(row)

    def delete_model_profile(self, profile_id: int) -> None:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM model_profiles WHERE id = ?", (profile_id,))
        if cursor.rowcount == 0:
            raise KeyError(f"Model profile not found: {profile_id}")

    def apply_model_profile(self, profile_id: int) -> ModelConfig:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM model_profiles WHERE id = ?", (profile_id,)).fetchone()
        if row is None:
            raise KeyError(f"Model profile not found: {profile_id}")
        profile = self._model_profile_from_row(row)
        return self.save_model_config(
            ModelConfigUpdate(
                provider=profile.provider,
                model=profile.model,
                base_url=profile.base_url,
                api_key_env_var=profile.api_key_env_var,
                api_key=profile.api_key,
                enabled=profile.enabled,
                estimation_only=profile.estimation_only,
                timeout_ms=profile.timeout_ms,
                input_price_per_million=profile.input_price_per_million,
                output_price_per_million=profile.output_price_per_million,
            )
        )

    def list_agent_model_routes(self) -> list[AgentModelRoute]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM agent_model_routes").fetchall()
        stored = {row["agent_name"]: self._agent_model_route_from_row(row) for row in rows}
        return [stored.get(agent_name) or self._default_agent_model_route(agent_name) for agent_name in MODEL_ROUTE_AGENTS]

    def get_agent_model_route(self, agent_name: str) -> AgentModelRoute:
        self._validate_model_route_agent(agent_name)
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM agent_model_routes WHERE agent_name = ?", (agent_name,)).fetchone()
        if row is None:
            return self._default_agent_model_route(agent_name)
        return self._agent_model_route_from_row(row)

    def save_agent_model_route(self, agent_name: str, update: ModelConfigUpdate) -> AgentModelRoute:
        self._validate_model_route_agent(agent_name)
        update_payload = update.model_dump()
        update_payload["model"] = _normalize_model_name(update_payload["model"])
        api_key_ciphertext, api_key_masked = self._resolve_model_secret(
            update.api_key,
            self._current_model_secret("agent_model_routes", "agent_name = ?", (agent_name,)),
        )
        api_key = self._decrypt_api_key(api_key_ciphertext)
        update_payload.pop("api_key", None)
        route = AgentModelRoute(
            agent_name=agent_name,
            **update_payload,
            api_key=api_key,
            api_key_secret_id=f"agent_model_route:{agent_name}" if api_key_ciphertext else "",
            api_key_masked=api_key_masked,
            api_key_configured=bool(api_key) or self._is_env_configured(update.api_key_env_var),
            updated_at=datetime.now(UTC),
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO agent_model_routes (
                    agent_name, provider, model, base_url, api_key_env_var, api_key_ciphertext,
                    api_key_masked, enabled, estimation_only, timeout_ms,
                    input_price_per_million, output_price_per_million, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(agent_name) DO UPDATE SET
                    provider = excluded.provider,
                    model = excluded.model,
                    base_url = excluded.base_url,
                    api_key_env_var = excluded.api_key_env_var,
                    api_key_ciphertext = excluded.api_key_ciphertext,
                    api_key_masked = excluded.api_key_masked,
                    enabled = excluded.enabled,
                    estimation_only = excluded.estimation_only,
                    timeout_ms = excluded.timeout_ms,
                    input_price_per_million = excluded.input_price_per_million,
                    output_price_per_million = excluded.output_price_per_million,
                    updated_at = excluded.updated_at
                """,
                (
                    route.agent_name,
                    route.provider,
                    route.model,
                    route.base_url,
                    route.api_key_env_var,
                    api_key_ciphertext,
                    api_key_masked,
                    1 if route.enabled else 0,
                    1 if route.estimation_only else 0,
                    route.timeout_ms,
                    route.input_price_per_million,
                    route.output_price_per_million,
                    route.updated_at.isoformat(),
                ),
            )
        return route

    def create_resume(self, resume: ResumeDraft, original_file_bytes: bytes | None = None) -> ResumeDraft:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO resumes (
                    filename, raw_text, profile_json, file_type,
                    template_available, original_file_bytes, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    resume.filename,
                    resume.raw_text,
                    json.dumps(resume.profile, ensure_ascii=False),
                    resume.file_type,
                    1 if resume.template_available else 0,
                    original_file_bytes if self._should_store_resume_file(resume) else None,
                    resume.created_at.isoformat(),
                ),
            )
            return resume.model_copy(update={"id": cursor.lastrowid})

    def update_resume_manual_text(self, resume: ResumeDraft) -> ResumeDraft:
        if resume.id is None:
            raise ValueError("Resume id is required")
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE resumes
                SET raw_text = ?, profile_json = ?
                WHERE id = ?
                """,
                (
                    resume.raw_text,
                    json.dumps(resume.profile, ensure_ascii=False),
                    resume.id,
                ),
            )
        if cursor.rowcount == 0:
            raise KeyError(f"Resume {resume.id} not found")
        return self.get_resume(resume.id)

    def _should_store_resume_file(self, resume: ResumeDraft) -> bool:
        return resume.template_available or resume.file_type in {"png", "jpg", "jpeg"}

    def get_resume(self, resume_id: int) -> ResumeDraft:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM resumes WHERE id = ?", (resume_id,)).fetchone()
        if row is None:
            raise KeyError(f"Resume {resume_id} not found")
        return self._resume_from_row(row)

    def get_latest_resume(self) -> ResumeDraft | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM resumes ORDER BY created_at DESC, id DESC LIMIT 1").fetchone()
        if row is None:
            return None
        return self._resume_from_row(row)

    def _resume_from_row(self, row: sqlite3.Row) -> ResumeDraft:
        return ResumeDraft(
            id=row["id"],
            filename=row["filename"],
            raw_text=row["raw_text"],
            profile=json.loads(row["profile_json"]),
            file_type=row["file_type"],
            template_available=bool(row["template_available"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def get_resume_template_bytes(self, resume_id: int) -> bytes:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT template_available, original_file_bytes FROM resumes WHERE id = ?",
                (resume_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Resume {resume_id} not found")
        if not row["template_available"] or row["original_file_bytes"] is None:
            raise ValueError("请重新上传 DOCX 简历以保留模板")
        return bytes(row["original_file_bytes"])

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

    def get_search_run(self, run_id: int) -> SearchRun:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM search_runs WHERE id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(f"Search run {run_id} not found")
        return SearchRun(
            id=row["id"],
            resume_id=row["resume_id"],
            keywords=json.loads(row["keywords_json"]),
            city=row["city"],
            platforms=json.loads(row["platforms_json"]),
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def update_search_run_status(self, run_id: int, status: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE search_runs SET status = ? WHERE id = ?", (status, run_id))

    def save_job(self, job: JobPosting, search_run_id: int, match: JobMatch) -> JobPosting:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO jobs (
                    search_run_id, platform, company, title, city, salary, description,
                    url, job_type, detail_status, detail_reason, match_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    job.detail_status,
                    job.detail_reason,
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
            return job.model_copy(update={"id": job_id, "search_run_id": search_run_id})

    def list_jobs(self, search_run_id: int | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if search_run_id is None:
                rows = conn.execute("SELECT * FROM jobs ORDER BY id DESC").fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM jobs WHERE search_run_id = ? ORDER BY id DESC",
                    (search_run_id,),
                ).fetchall()
        return [self._job_row_to_dict(row) for row in rows]

    def get_job(self, job_id: int) -> JobPosting:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise KeyError(f"Job {job_id} not found")
        return JobPosting(
            id=row["id"],
            search_run_id=row["search_run_id"],
            platform=row["platform"],
            company=row["company"],
            title=row["title"],
            city=row["city"],
            salary=row["salary"],
            description=row["description"],
            url=row["url"],
            job_type=row["job_type"],
            detail_status=row["detail_status"],
            detail_reason=row["detail_reason"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def update_job_detail(
        self,
        job_id: int,
        *,
        salary: str,
        description: str,
        detail_status: str,
        detail_reason: str,
        match: JobMatch | None = None,
    ) -> None:
        match_json = None
        if match is not None:
            stored_match = match.model_copy(update={"job_id": job_id})
            match_json = json.dumps(stored_match.model_dump(mode="json"), ensure_ascii=False)
        with self._connect() as conn:
            if match_json is None:
                cursor = conn.execute(
                    """
                    UPDATE jobs
                    SET salary = ?, description = ?, detail_status = ?, detail_reason = ?
                    WHERE id = ?
                    """,
                    (salary, description, detail_status, detail_reason, job_id),
                )
            else:
                cursor = conn.execute(
                    """
                    UPDATE jobs
                    SET salary = ?, description = ?, detail_status = ?, detail_reason = ?, match_json = ?
                    WHERE id = ?
                    """,
                    (salary, description, detail_status, detail_reason, match_json, job_id),
                )
        if cursor.rowcount == 0:
            raise KeyError(f"Job {job_id} not found")

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
                    job_id, resume_id, resume_text, resume_rewrite, project_rewrite, diff_summary_json,
                    risk_flags_json, truth_check_passed, greeting_json, review_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    tailored.job_id,
                    tailored.resume_id,
                    tailored.resume_text,
                    tailored.resume_rewrite,
                    tailored.project_rewrite,
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

    def get_tailor_bundle(self, tailored_resume_id: int) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM tailored_resumes WHERE id = ?",
                (tailored_resume_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"Tailored resume {tailored_resume_id} not found")
        return {
            "id": row["id"],
            "job_id": row["job_id"],
            "resume_id": row["resume_id"],
            "resume_text": row["resume_text"],
            "resume_rewrite": row["resume_rewrite"],
            "project_rewrite": row["project_rewrite"],
            "diff_summary": json.loads(row["diff_summary_json"]),
            "risk_flags": json.loads(row["risk_flags_json"]),
            "truth_check_passed": bool(row["truth_check_passed"]),
            "greeting": json.loads(row["greeting_json"]),
            "review": json.loads(row["review_json"]),
            "created_at": row["created_at"],
        }

    def get_tailored_resume_revision(self, tailored_resume_id: int) -> dict[str, Any]:
        bundle = self.get_tailor_bundle(tailored_resume_id)
        editable_text = (
            str(bundle.get("resume_rewrite") or "")
            or str(bundle.get("project_rewrite") or "")
            or str(bundle.get("resume_text") or "")
        )
        return {
            "id": bundle["id"],
            "job_id": bundle["job_id"],
            "resume_id": bundle["resume_id"],
            "editable_text": editable_text,
            "resume_rewrite": str(bundle.get("resume_rewrite") or ""),
            "project_rewrite": str(bundle.get("project_rewrite") or ""),
            "resume_text": str(bundle.get("resume_text") or ""),
            "created_at": bundle["created_at"],
        }

    def update_tailored_resume_revision(self, tailored_resume_id: int, resume_rewrite: str) -> dict[str, Any]:
        resume_rewrite = resume_rewrite.strip()
        if not resume_rewrite:
            raise ValueError("简历改写正文不能为空")
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE tailored_resumes
                SET resume_text = ?, resume_rewrite = ?, project_rewrite = ?
                WHERE id = ?
                """,
                (resume_rewrite, resume_rewrite, resume_rewrite, tailored_resume_id),
            )
        if cursor.rowcount == 0:
            raise KeyError(f"Tailored resume {tailored_resume_id} not found")
        return self.get_tailored_resume_revision(tailored_resume_id)

    def create_application(
        self,
        job: JobPosting,
        note: str = "",
        platform_proof: ApplicationPlatformProof | None = None,
    ) -> ApplicationRecord:
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
        if platform_proof is not None:
            record = record.model_copy(update={"platform_proof": platform_proof})
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO applications (
                    job_id, company, title, platform, applied_at, current_status,
                    read_at, replied_at, progress_stage, latest_note, platform_proof_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    json.dumps(record.platform_proof.model_dump(mode="json"), ensure_ascii=False),
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
            platform_proof=self._platform_proof_from_json(row["platform_proof_json"]),
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
        default_key_env = "DEEPSEEK_API_KEY" if self._env_value("DEEPSEEK_API_KEY") else "OPENAI_API_KEY"
        api_key_env_var = os.getenv("OPENAI_API_KEY_ENV_VAR", os.getenv("LLM_API_KEY_ENV_VAR", default_key_env))
        has_api_key = self._is_env_configured(api_key_env_var)
        return ModelConfig(
            provider=os.getenv("LLM_PROVIDER", "openai-compatible" if has_api_key else "local"),
            model=_normalize_model_name(
                os.getenv("OPENAI_MODEL", os.getenv("LLM_USAGE_MODEL", "deepseek-v4-pro" if has_api_key else "local-estimator"))
            ),
            base_url=os.getenv("OPENAI_BASE_URL", os.getenv("LLM_BASE_URL", "https://api.deepseek.com")),
            api_key_env_var=api_key_env_var,
            api_key_configured=has_api_key,
            enabled=self._env_bool("LLM_ENABLED", has_api_key),
            estimation_only=self._env_bool("LLM_ESTIMATION_ONLY", not has_api_key),
            timeout_ms=self._env_int("LLM_TIMEOUT_MS", 90000),
            input_price_per_million=self._env_float("LLM_INPUT_PRICE_PER_MILLION", 0.0),
            output_price_per_million=self._env_float("LLM_OUTPUT_PRICE_PER_MILLION", 0.0),
        )

    def _model_config_from_row(self, row: sqlite3.Row) -> ModelConfig:
        api_key_env_var = row["api_key_env_var"]
        api_key_ciphertext = row["api_key_ciphertext"]
        api_key = self._decrypt_api_key(api_key_ciphertext)
        return ModelConfig(
            provider=row["provider"],
            model=_normalize_model_name(row["model"]),
            base_url=row["base_url"],
            api_key_env_var=api_key_env_var,
            api_key=api_key,
            api_key_secret_id="model_config:1" if api_key_ciphertext else "",
            api_key_masked=row["api_key_masked"],
            api_key_configured=bool(api_key) or self._is_env_configured(api_key_env_var),
            enabled=bool(row["enabled"]),
            estimation_only=bool(row["estimation_only"]),
            timeout_ms=row["timeout_ms"],
            input_price_per_million=row["input_price_per_million"],
            output_price_per_million=row["output_price_per_million"],
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _model_profile_from_row(self, row: sqlite3.Row) -> ModelProfile:
        api_key_env_var = row["api_key_env_var"]
        api_key_ciphertext = row["api_key_ciphertext"]
        api_key = self._decrypt_api_key(api_key_ciphertext)
        return ModelProfile(
            id=row["id"],
            name=row["name"],
            provider=row["provider"],
            model=_normalize_model_name(row["model"]),
            base_url=row["base_url"],
            api_key_env_var=api_key_env_var,
            api_key=api_key,
            api_key_secret_id=f"model_profile:{row['id']}" if api_key_ciphertext else "",
            api_key_masked=row["api_key_masked"],
            api_key_configured=bool(api_key) or self._is_env_configured(api_key_env_var),
            enabled=bool(row["enabled"]),
            estimation_only=bool(row["estimation_only"]),
            timeout_ms=row["timeout_ms"],
            input_price_per_million=row["input_price_per_million"],
            output_price_per_million=row["output_price_per_million"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _default_agent_model_route(self, agent_name: str) -> AgentModelRoute:
        self._validate_model_route_agent(agent_name)
        if agent_name in {"OrchestratorAgent", "ApplicationWriterAgent"}:
            config = self.get_model_config()
            payload = config.model_dump()
            payload["api_key"] = config.api_key
            return AgentModelRoute(agent_name=agent_name, **payload)
        return AgentModelRoute(
            agent_name=agent_name,
            provider="local",
            model="local-rule",
            base_url="local",
            api_key_env_var="DEEPSEEK_API_KEY",
            api_key_configured=self._is_env_configured("DEEPSEEK_API_KEY"),
            enabled=False,
            estimation_only=True,
            timeout_ms=30000,
            input_price_per_million=0.0,
            output_price_per_million=0.0,
            updated_at=datetime.now(UTC),
        )

    def _agent_model_route_from_row(self, row: sqlite3.Row) -> AgentModelRoute:
        api_key_env_var = row["api_key_env_var"]
        api_key_ciphertext = row["api_key_ciphertext"]
        api_key = self._decrypt_api_key(api_key_ciphertext)
        return AgentModelRoute(
            agent_name=row["agent_name"],
            provider=row["provider"],
            model=_normalize_model_name(row["model"]),
            base_url=row["base_url"],
            api_key_env_var=api_key_env_var,
            api_key=api_key,
            api_key_secret_id=f"agent_model_route:{row['agent_name']}" if api_key_ciphertext else "",
            api_key_masked=row["api_key_masked"],
            api_key_configured=bool(api_key) or self._is_env_configured(api_key_env_var),
            enabled=bool(row["enabled"]),
            estimation_only=bool(row["estimation_only"]),
            timeout_ms=row["timeout_ms"],
            input_price_per_million=row["input_price_per_million"],
            output_price_per_million=row["output_price_per_million"],
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def _validate_model_route_agent(self, agent_name: str) -> None:
        if agent_name not in MODEL_ROUTE_AGENTS:
            raise ValueError(f"Unsupported model route agent: {agent_name}")

    def _current_model_secret(
        self,
        table: str,
        where_clause: str,
        parameters: tuple[Any, ...] = (),
    ) -> tuple[str, str] | None:
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT api_key_ciphertext, api_key_masked FROM {table} WHERE {where_clause}",
                parameters,
            ).fetchone()
        if row is None:
            return None
        return row["api_key_ciphertext"], row["api_key_masked"]

    def _resolve_model_secret(
        self,
        api_key: str,
        current_secret: tuple[str, str] | None,
    ) -> tuple[str, str]:
        secret = api_key.strip()
        if secret:
            return self._encrypt_api_key(secret), _mask_api_key(secret)
        if current_secret is not None:
            return current_secret
        return "", ""

    def _encrypt_api_key(self, api_key: str) -> str:
        encrypted = self._xor_secret(api_key.encode("utf-8"))
        return "v1:" + base64.urlsafe_b64encode(encrypted).decode("ascii")

    def _decrypt_api_key(self, ciphertext: str) -> str:
        if not ciphertext:
            return ""
        if not ciphertext.startswith("v1:"):
            return ""
        try:
            encrypted = base64.urlsafe_b64decode(ciphertext[3:].encode("ascii"))
            return self._xor_secret(encrypted).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return ""

    def _xor_secret(self, payload: bytes) -> bytes:
        key = self._local_secret_key()
        stream = bytearray()
        counter = 0
        while len(stream) < len(payload):
            stream.extend(hashlib.sha256(key + counter.to_bytes(4, "big")).digest())
            counter += 1
        return bytes(value ^ stream[index] for index, value in enumerate(payload))

    def _local_secret_key(self) -> bytes:
        seed = "|".join(
            [
                "agent-business-local-secret-v1",
                os.getenv("AGENT_BUSINESS_SECRET_SALT", ""),
                os.getenv("USERNAME", os.getenv("USER", "")),
                os.getenv("COMPUTERNAME", ""),
            ]
        )
        return hashlib.sha256(seed.encode("utf-8")).digest()

    def _is_env_configured(self, name: str) -> bool:
        if not name:
            return False
        return bool(self._env_value(name))

    def _env_value(self, name: str) -> str:
        if not name:
            return ""
        value = os.getenv(name, "")
        if value:
            return value
        return _env_file_value(name)

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
            "search_run_id": row["search_run_id"],
            "platform": row["platform"],
            "company": row["company"],
            "title": row["title"],
            "city": row["city"],
            "salary": row["salary"],
            "description": row["description"],
            "url": row["url"],
            "job_type": row["job_type"],
            "detail_status": row["detail_status"],
            "detail_reason": row["detail_reason"],
            "created_at": row["created_at"],
            "match": json.loads(row["match_json"]),
        }

    def _platform_proof_from_json(self, value: str | None) -> ApplicationPlatformProof:
        if not value:
            return ApplicationPlatformProof()
        try:
            payload = json.loads(value)
        except json.JSONDecodeError:
            return ApplicationPlatformProof()
        if not isinstance(payload, dict):
            return ApplicationPlatformProof()
        return ApplicationPlatformProof(**payload)

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


def _env_file_value(name: str) -> str:
    for path in _candidate_env_files():
        if not path.exists() or not path.is_file():
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                key, separator, value = line.partition("=")
                if not separator or key.strip() != name:
                    continue
                return value.strip().strip('"').strip("'")
        except OSError:
            continue
    return ""


def _candidate_env_files() -> list[Path]:
    configured = os.getenv("AGENT_BUSINESS_ENV_FILE", "").strip()
    if configured:
        return [Path(configured)]
    return [Path(r"D:\code\tourism-opinion-agent\.env")]


def _mask_api_key(api_key: str) -> str:
    if not api_key:
        return ""
    if len(api_key) <= 4:
        return "*" * len(api_key)
    return "*" * min(12, max(4, len(api_key) - 4)) + api_key[-4:]


def _normalize_model_name(model: str) -> str:
    aliases = {
        "v4pro": "deepseek-v4-pro",
        "deepseek-v4pro": "deepseek-v4-pro",
        "v4flash": "deepseek-v4-flash",
        "deepseek-v4flash": "deepseek-v4-flash",
    }
    return aliases.get(model.strip().lower(), model)
