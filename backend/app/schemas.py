from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def now_utc() -> datetime:
    return datetime.now(UTC)


class ApplicationStatus(str, Enum):
    DISCOVERED = "discovered"
    MATCHED = "matched"
    GENERATED = "generated"
    APPLIED = "applied"
    READ = "read"
    REPLIED = "replied"
    INTERVIEW = "interview"
    ASSESSMENT = "assessment"
    REJECTED = "rejected"
    CLOSED = "closed"


class ResumeDraft(BaseModel):
    id: int | None = None
    filename: str
    raw_text: str
    profile: dict[str, Any] = Field(default_factory=dict)
    file_type: str = "txt"
    template_available: bool = False
    created_at: datetime = Field(default_factory=now_utc)


class JobPosting(BaseModel):
    id: int | None = None
    search_run_id: int | None = None
    platform: str
    company: str
    title: str
    city: str
    salary: str
    description: str
    url: str
    job_type: str = "internship"
    detail_status: str = ""
    detail_reason: str = ""
    created_at: datetime = Field(default_factory=now_utc)


class JobMatch(BaseModel):
    job_id: int | None = None
    score: int
    hit_reasons: list[str] = Field(default_factory=list)
    gap_reasons: list[str] = Field(default_factory=list)
    recommendation: str


class SearchRun(BaseModel):
    id: int | None = None
    resume_id: int
    keywords: list[str]
    city: str
    platforms: list[str]
    status: str = "pending"
    created_at: datetime = Field(default_factory=now_utc)


class TailoredResume(BaseModel):
    id: int | None = None
    job_id: int
    resume_id: int
    resume_text: str
    resume_rewrite: str = ""
    project_rewrite: str = ""
    diff_summary: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    truth_check_passed: bool
    created_at: datetime = Field(default_factory=now_utc)


class GreetingMessage(BaseModel):
    id: int | None = None
    job_id: int
    message: str
    tone: str = "professional"
    risk_flags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=now_utc)


class TailorBundle(BaseModel):
    tailored_resume: TailoredResume
    greeting: GreetingMessage
    review: dict[str, Any] = Field(default_factory=dict)


class ApplicationEvent(BaseModel):
    id: int | None = None
    application_id: int | None = None
    status: ApplicationStatus
    occurred_at: datetime = Field(default_factory=now_utc)
    note: str = ""


class ApplicationPlatformProof(BaseModel):
    platform: str = ""
    source_url: str = ""
    action: str = ""
    status: str = ""
    evidence: str = ""
    button_text: str = ""
    confirmed_at: datetime | None = None
    page_summary: str = ""


class ApplicationRecord(BaseModel):
    id: int | None = None
    job_id: int
    company: str
    title: str
    platform: str
    applied_at: datetime = Field(default_factory=now_utc)
    current_status: ApplicationStatus = ApplicationStatus.APPLIED
    read_at: datetime | None = None
    replied_at: datetime | None = None
    progress_stage: str = "已投递"
    latest_note: str = ""
    platform_proof: ApplicationPlatformProof = Field(default_factory=ApplicationPlatformProof)
    events: list[ApplicationEvent] = Field(default_factory=list)


class LLMUsageEntry(BaseModel):
    id: int | None = None
    agent_name: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    duration_ms: int
    estimated: bool
    status: str = "success"
    error: str = ""
    created_at: datetime = Field(default_factory=now_utc)


class LLMUsageSummary(BaseModel):
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    total_cost_usd: float
    by_agent: dict[str, dict[str, float | int]] = Field(default_factory=dict)


class ModelConfig(BaseModel):
    provider: str = "local"
    model: str = "local-estimator"
    base_url: str = "https://api.openai.com/v1"
    api_key_env_var: str = "OPENAI_API_KEY"
    api_key_configured: bool = False
    enabled: bool = False
    estimation_only: bool = True
    timeout_ms: int = 30000
    input_price_per_million: float = 0.0
    output_price_per_million: float = 0.0
    updated_at: datetime = Field(default_factory=now_utc)


class ModelConfigUpdate(BaseModel):
    provider: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=120)
    base_url: str = Field(min_length=1, max_length=300)
    api_key_env_var: str = Field(default="OPENAI_API_KEY", pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    enabled: bool = False
    estimation_only: bool = True
    timeout_ms: int = Field(default=30000, ge=1000, le=300000)
    input_price_per_million: float = Field(default=0.0, ge=0)
    output_price_per_million: float = Field(default=0.0, ge=0)


class ModelProfile(ModelConfig):
    id: int
    name: str
    created_at: datetime = Field(default_factory=now_utc)


class ModelProfileCreate(ModelConfigUpdate):
    name: str = Field(min_length=1, max_length=120)


class ModelProfileUpdate(ModelConfigUpdate):
    name: str = Field(min_length=1, max_length=120)


class ModelProfilesResponse(BaseModel):
    profiles: list[ModelProfile]


class AgentModelRoute(ModelConfig):
    agent_name: str


class AgentModelRoutesResponse(BaseModel):
    routes: list[AgentModelRoute]


class PlatformSession(BaseModel):
    platform: str
    expected_hosts: list[str]
    state: str
    detected_url: str | None = None
    authenticated: bool | None = None
    message: str = ""


class PlatformSessionsResponse(BaseModel):
    cdp_url: str | None = None
    browser_connected: bool
    sessions: list[PlatformSession]
    error: str = ""


class ExtractedJobCandidate(BaseModel):
    platform: str
    company: str = ""
    title: str
    city: str = ""
    salary: str = ""
    description: str = ""
    url: str = ""
    job_type: str = "unknown"
    detail_status: str = ""
    detail_reason: str = ""


class BrowserExtractionDiagnostics(BaseModel):
    tab_detected: bool = False
    websocket_detected: bool = False
    matched_selector_counts: dict[str, int] = Field(default_factory=dict)
    candidate_card_count: int = 0
    extracted_job_count: int = 0
    text_quality_warnings: list[str] = Field(default_factory=list)
    failure_reason: str = ""
    suggestion: str = ""


class PlatformJobExtraction(BaseModel):
    platform: str
    status: str
    source_url: str | None = None
    jobs: list[ExtractedJobCandidate] = Field(default_factory=list)
    error: str = ""
    diagnostics: BrowserExtractionDiagnostics = Field(default_factory=BrowserExtractionDiagnostics)


class BrowserJobExtractRequest(BaseModel):
    platforms: list[str] = Field(default_factory=lambda: ["boss", "shixiseng"])
    limit: int = Field(default=20, ge=1, le=50)


class BrowserJobSearchRequest(BrowserJobExtractRequest):
    keywords: list[str] = Field(default_factory=list)
    city: str = ""


class BrowserJobExtractResponse(BaseModel):
    cdp_url: str | None = None
    extractions: list[PlatformJobExtraction]


class ApplicationSyncRequest(BaseModel):
    platforms: list[str] = Field(default_factory=lambda: ["boss", "shixiseng"])
    limit: int = Field(default=50, ge=1, le=200)


class ApplicationSyncDiagnostic(BaseModel):
    platform: str
    status: str
    source_url: str | None = None
    tab_detected: bool = False
    websocket_detected: bool = False
    candidate_item_count: int = 0
    matched_status_keywords: dict[str, int] = Field(default_factory=dict)
    failure_reason: str = ""
    suggestion: str = ""


class ApplicationSyncProposal(BaseModel):
    application_id: int
    platform: str
    company: str
    title: str
    current_status: ApplicationStatus
    detected_status: ApplicationStatus
    suggested_status: ApplicationStatus
    confidence: float
    evidence: str
    source_url: str = ""
    note: str = ""
    requires_manual_confirmation: bool = True


class ApplicationSyncResponse(BaseModel):
    status: str
    mode: str = "browser_cdp_readonly"
    updated: int = 0
    proposals: list[ApplicationSyncProposal] = Field(default_factory=list)
    diagnostics: list[ApplicationSyncDiagnostic] = Field(default_factory=list)
    message: str = ""


class KnowledgeDocument(BaseModel):
    id: int
    source_type: str
    source_id: int
    title: str
    summary: str = ""
    chunk_count: int = 0
    updated_at: datetime = Field(default_factory=now_utc)


class KnowledgeChunk(BaseModel):
    id: int
    document_id: int
    source_type: str
    source_id: int
    chunk_index: int
    title: str
    content: str


class RetrievalHit(BaseModel):
    document_id: int
    chunk_id: int
    source_type: str
    source_id: int
    title: str
    content: str
    score: float = 0.0


class KnowledgeReindexResponse(BaseModel):
    status: str
    documents: int
    chunks: int


class RagQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=5, ge=1, le=20)


class RagQueryResponse(BaseModel):
    query: str
    answer: str
    hits: list[RetrievalHit] = Field(default_factory=list)


class SkillDefinition(BaseModel):
    id: str
    name: str
    description: str
    risk_level: str = "low"
    requires_confirmation: bool = False
    input_schema: dict[str, Any] = Field(default_factory=dict)


class SkillRunRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)
    confirmed: bool = False


class SkillRunResult(BaseModel):
    skill_id: str
    status: str
    requires_confirmation: bool = False
    message: str = ""
    result: dict[str, Any] = Field(default_factory=dict)


class McpServerConfig(BaseModel):
    id: str
    command: str
    args: list[str] = Field(default_factory=list)
    enabled: bool = False
    allowed_tools: list[str] = Field(default_factory=list)


class McpToolDescriptor(BaseModel):
    server_id: str
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)


class McpToolCallRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)
    confirmed: bool = False


class McpToolCallResult(BaseModel):
    server_id: str
    tool_name: str
    status: str
    output: dict[str, Any] = Field(default_factory=dict)
    error: str = ""
    duration_ms: int = 0


class SearchRunRequest(BaseModel):
    resume_id: int
    keywords: list[str] = Field(default_factory=list)
    city: str = ""
    platforms: list[str] = Field(default_factory=lambda: ["boss", "shixiseng"])
    search_mode: str = Field(default="demo", pattern=r"^(demo|browser_cdp)$")


class TailorRequest(BaseModel):
    resume_id: int


class ApplyRecordRequest(BaseModel):
    note: str = ""


class StatusPatchRequest(BaseModel):
    status: ApplicationStatus
    note: str = ""
