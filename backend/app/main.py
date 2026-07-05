from __future__ import annotations

import html
import json
import os
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.agents.application_tracker import InvalidStatusTransition
from app.schemas import (
    AgentModelRoutesResponse,
    ApplicationSyncRequest,
    ApplyRecordRequest,
    BrowserJobExtractRequest,
    BrowserJobSearchRequest,
    McpToolCallRequest,
    McpToolDescriptor,
    McpServerConfig,
    ModelConfigUpdate,
    ModelProfileCreate,
    ModelProfilesResponse,
    ModelProfileUpdate,
    RagQueryRequest,
    SearchRunRequest,
    SkillDefinition,
    SkillRunRequest,
    StatusPatchRequest,
    TailorRequest,
)
from app.services import JobApplicationService
from app.services.application_sync_service import ApplicationSyncService
from app.services.browser_job_extractor_service import BrowserJobExtractorService
from app.services.job_application_service import LowQualityJobDetailError, PlatformApplicationNotConfirmedError
from app.services.llm_client_service import LLMClientUnavailable, OpenAICompatibleClient
from app.services.pdf_service import TailoredResumePdfService
from app.services.platform_session_service import CdpBrowserLauncher, PlatformSessionService
from app.storage import SQLiteStore


SKILL_REGISTRY = [
    SkillDefinition(
        id="job.search.browser_cdp",
        name="搜索真实岗位",
        description="通过已登录 CDP 浏览器搜索 BOSS/实习僧并读取岗位。",
        risk_level="low",
        input_schema={"platforms": "list[str]", "keywords": "list[str]", "city": "str"},
    ),
    SkillDefinition(
        id="job.detail.refresh",
        name="刷新岗位详情",
        description="只读打开岗位详情页并补全 JD。",
        risk_level="low",
        input_schema={"job_id": "int"},
    ),
    SkillDefinition(
        id="application.materials.generate",
        name="生成申请材料",
        description="基于原简历和岗位 JD 生成简历改写与招呼语。",
        risk_level="medium",
        input_schema={"job_id": "int", "resume_id": "int"},
    ),
    SkillDefinition(
        id="application.apply.preview",
        name="预检投递入口",
        description="只读打开平台岗位页，检测投递/沟通按钮，不点击。",
        risk_level="low",
        input_schema={"job_id": "int"},
    ),
    SkillDefinition(
        id="application.apply.platform",
        name="真实平台投递",
        description="点击平台原生沟通/投递按钮，只有平台确认后才入库。",
        risk_level="high",
        requires_confirmation=True,
        input_schema={"job_id": "int", "note": "str"},
    ),
    SkillDefinition(
        id="application.sync.readonly",
        name="只读同步投递状态",
        description="只读读取平台沟通/投递页面，返回人工确认建议。",
        risk_level="low",
        input_schema={"platforms": "list[str]", "limit": "int"},
    ),
    SkillDefinition(
        id="knowledge.reindex",
        name="重建本地知识库",
        description="从简历、岗位、投递、材料重建 SQLite FTS5 知识库。",
        risk_level="low",
    ),
]


def create_app(db_path: str | Path = "data/agent-business.sqlite3") -> FastAPI:
    store = SQLiteStore(db_path)
    service = JobApplicationService(store)
    app = FastAPI(title="agent-business", version="0.1.0")
    app.state.service = service
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/model-config")
    def get_model_config():
        return app.state.service.store.get_model_config()

    @app.put("/api/model-config")
    def update_model_config(payload: ModelConfigUpdate):
        return app.state.service.store.save_model_config(payload)

    @app.delete("/api/model-config/api-key")
    def delete_model_config_api_key():
        return app.state.service.store.delete_model_config_api_key()

    @app.get("/api/model-profiles")
    def list_model_profiles():
        return ModelProfilesResponse(profiles=app.state.service.store.list_model_profiles())

    @app.post("/api/model-profiles", status_code=201)
    def create_model_profile(payload: ModelProfileCreate):
        try:
            return app.state.service.store.create_model_profile(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.put("/api/model-profiles/{profile_id}")
    def update_model_profile(profile_id: int, payload: ModelProfileUpdate):
        try:
            return app.state.service.store.update_model_profile(profile_id, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.delete("/api/model-profiles/{profile_id}", status_code=204)
    def delete_model_profile(profile_id: int):
        try:
            app.state.service.store.delete_model_profile(profile_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return Response(status_code=204)

    @app.post("/api/model-profiles/{profile_id}/apply")
    def apply_model_profile(profile_id: int):
        try:
            return app.state.service.store.apply_model_profile(profile_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/model-config/test")
    def test_model_config_connection():
        config = app.state.service.store.get_model_config()
        try:
            result = OpenAICompatibleClient().test_connection(config)
            result["api_key_configured"] = config.api_key_configured
            return result
        except LLMClientUnavailable as exc:
            return {
                "status": "failed",
                "provider": config.provider,
                "model": config.model,
                "duration_ms": 0,
                "api_key_configured": config.api_key_configured,
                "error": _sanitize_model_error(str(exc), config.api_key_env_var),
            }

    @app.get("/api/model-routes")
    def list_model_routes():
        return AgentModelRoutesResponse(routes=app.state.service.store.list_agent_model_routes())

    @app.put("/api/model-routes/{agent_name}")
    def update_model_route(agent_name: str, payload: ModelConfigUpdate):
        try:
            return app.state.service.store.save_agent_model_route(agent_name, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/platform-sessions")
    def platform_sessions():
        return PlatformSessionService().inspect()

    @app.post("/api/browser/launch-cdp")
    def launch_cdp_browser():
        try:
            return CdpBrowserLauncher().launch()
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"启动浏览器失败：{exc}") from exc

    @app.post("/api/platform-jobs/extract")
    def extract_platform_jobs(payload: BrowserJobExtractRequest):
        return BrowserJobExtractorService().extract(payload.platforms, payload.limit)

    @app.post("/api/platform-jobs/search")
    def search_platform_jobs(payload: BrowserJobSearchRequest):
        return BrowserJobExtractorService().search_and_extract(
            payload.platforms,
            payload.keywords,
            payload.city,
            payload.limit,
        )

    @app.post("/api/resumes", status_code=201)
    async def upload_resume(file: Annotated[UploadFile, File()]):
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="简历文件不能为空")
        return app.state.service.upload_resume(file.filename or "resume.txt", content)

    @app.get("/api/resumes/latest")
    def latest_resume():
        return app.state.service.store.get_latest_resume()

    @app.patch("/api/resumes/{resume_id}/manual-text")
    def update_resume_manual_text(resume_id: int, payload: dict[str, str]):
        try:
            return app.state.service.update_resume_manual_text(resume_id, payload.get("raw_text", ""))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/search-runs", status_code=201)
    def create_search_run(payload: SearchRunRequest):
        try:
            return app.state.service.create_search_run(
                resume_id=payload.resume_id,
                keywords=payload.keywords,
                city=payload.city,
                platforms=payload.platforms,
                search_mode=payload.search_mode,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/jobs")
    def list_jobs(search_run_id: int | None = None):
        return app.state.service.list_jobs(search_run_id=search_run_id)

    @app.post("/api/jobs/{job_id}/refresh-detail")
    def refresh_job_detail(job_id: int):
        try:
            return app.state.service.refresh_job_detail(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.patch("/api/jobs/{job_id}/manual-detail")
    def update_job_detail_manually(job_id: int, payload: dict[str, str]):
        try:
            return app.state.service.update_job_detail_manually(
                job_id=job_id,
                description=payload.get("description", ""),
                note=payload.get("note", ""),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/jobs/{job_id}/tailor", status_code=201)
    def tailor_job(job_id: int, payload: TailorRequest):
        try:
            return app.state.service.tailor_for_job(job_id=job_id, resume_id=payload.resume_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except LowQualityJobDetailError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/tailored-resumes/{tailored_resume_id}/pdf")
    def download_tailored_resume_pdf(tailored_resume_id: int):
        try:
            tailored_bundle = app.state.service.store.get_tailor_bundle(tailored_resume_id)
            template_bytes = app.state.service.store.get_resume_template_bytes(int(tailored_bundle["resume_id"]))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        try:
            pdf_bytes = TailoredResumePdfService().render(tailored_bundle, template_bytes)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except RuntimeError as exc:
            status_code = 409 if "超过 1 页" in str(exc) else 503
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="tailored-resume-{tailored_resume_id}.pdf"',
            },
        )

    @app.get("/api/tailored-resumes/{tailored_resume_id}/revision")
    def get_tailored_resume_revision(tailored_resume_id: int):
        try:
            return app.state.service.store.get_tailored_resume_revision(tailored_resume_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.patch("/api/tailored-resumes/{tailored_resume_id}/revision")
    def update_tailored_resume_revision(tailored_resume_id: int, payload: dict[str, str]):
        try:
            return app.state.service.store.update_tailored_resume_revision(
                tailored_resume_id,
                payload.get("resume_rewrite", ""),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/tailored-resumes/{tailored_resume_id}/preview")
    def preview_tailored_resume_revision(tailored_resume_id: int):
        try:
            revision = app.state.service.store.get_tailored_resume_revision(tailored_resume_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        plain_text = str(revision["editable_text"])
        escaped_lines = [html.escape(line) for line in plain_text.splitlines()]
        return {
            "id": revision["id"],
            "plain_text": plain_text,
            "html": "<article class=\"resume-preview\">" + "<br />".join(escaped_lines) + "</article>",
        }

    @app.post("/api/jobs/{job_id}/apply-record", status_code=201)
    def create_application(job_id: int, payload: ApplyRecordRequest):
        raise HTTPException(
            status_code=409,
            detail=(
                "Local-only application records are disabled. "
                "Use POST /api/jobs/{job_id}/platform-apply so the platform confirms the application first."
            ),
        )

    @app.post("/api/jobs/{job_id}/platform-apply", status_code=201)
    def apply_to_platform(job_id: int, payload: ApplyRecordRequest):
        try:
            return app.state.service.apply_to_platform(job_id, note=payload.note)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PlatformApplicationNotConfirmedError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/jobs/{job_id}/platform-apply-preview")
    def preview_platform_apply(job_id: int):
        try:
            return app.state.service.preview_platform_application(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.patch("/api/applications/{application_id}/status")
    def update_application_status(application_id: int, payload: StatusPatchRequest):
        try:
            return app.state.service.update_application_status(application_id, payload.status, payload.note)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except InvalidStatusTransition as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/applications/sync")
    def sync_applications(payload: ApplicationSyncRequest | None = None):
        request = payload or ApplicationSyncRequest()
        return ApplicationSyncService(app.state.service.store).sync(request.platforms, request.limit)

    @app.get("/api/applications")
    def list_applications():
        return app.state.service.list_applications()

    @app.get("/api/analytics/applications")
    def application_analytics():
        return app.state.service.application_analytics()

    @app.get("/api/metrics/llm-usage")
    def llm_usage():
        return app.state.service.llm_usage_summary()

    @app.get("/api/knowledge/documents")
    def list_knowledge_documents():
        return app.state.service.store.list_knowledge_documents()

    @app.post("/api/knowledge/reindex")
    def reindex_knowledge():
        return app.state.service.store.reindex_knowledge()

    @app.post("/api/rag/query")
    def query_rag(payload: RagQueryRequest):
        hits = app.state.service.store.query_rag(payload.query, payload.limit)
        if not hits:
            return {
                "query": payload.query,
                "answer": "未找到带来源的知识库内容，无法生成可靠回答。",
                "hits": [],
            }
        source_lines = [
            f"[{index}] {hit.title}（{hit.source_type}#{hit.source_id}）: {hit.content[:220]}"
            for index, hit in enumerate(hits, start=1)
        ]
        return {
            "query": payload.query,
            "answer": "基于本地知识库检索到以下来源：\n" + "\n".join(source_lines),
            "hits": hits,
        }

    @app.get("/api/skills")
    def list_skills():
        return SKILL_REGISTRY

    @app.post("/api/skills/{skill_id}/run")
    def run_skill(skill_id: str, payload: SkillRunRequest | None = None):
        request = payload or SkillRunRequest()
        skill = next((item for item in SKILL_REGISTRY if item.id == skill_id), None)
        if skill is None:
            raise HTTPException(status_code=404, detail=f"Unknown skill: {skill_id}")
        if skill.requires_confirmation and not request.confirmed:
            return {
                "skill_id": skill.id,
                "status": "requires_confirmation",
                "requires_confirmation": True,
                "message": "该技能会影响真实平台或投递记录，需要用户明确确认后才能执行。",
                "result": {},
            }
        if skill.id == "knowledge.reindex":
            result = app.state.service.store.reindex_knowledge()
            return {
                "skill_id": skill.id,
                "status": "success",
                "requires_confirmation": False,
                "message": "知识库已重建。",
                "result": result.model_dump(),
            }
        return {
            "skill_id": skill.id,
            "status": "registered",
            "requires_confirmation": False,
            "message": "该技能已进入 allowlist，执行器将在后续阶段接入。",
            "result": {"arguments": request.arguments},
        }

    @app.get("/api/mcp/servers")
    def list_mcp_servers():
        return _mcp_server_configs()

    @app.get("/api/mcp/tools")
    def list_mcp_tools():
        tools: list[McpToolDescriptor] = []
        for server in _mcp_server_configs():
            if not server.enabled:
                continue
            tools.extend(
                McpToolDescriptor(
                    server_id=server.id,
                    name=tool_name,
                    description="Configured MCP tool descriptor; live stdio introspection is planned for the next stage.",
                )
                for tool_name in server.allowed_tools
            )
        return tools

    @app.post("/api/mcp/tools/{server_id}/{tool_name}/call")
    def call_mcp_tool(server_id: str, tool_name: str, payload: McpToolCallRequest | None = None):
        request = payload or McpToolCallRequest()
        server = next((item for item in _mcp_server_configs() if item.id == server_id and item.enabled), None)
        if server is None or tool_name not in server.allowed_tools:
            raise HTTPException(status_code=403, detail="MCP server or tool is not in the allowlist.")
        if not request.confirmed:
            return {
                "server_id": server_id,
                "tool_name": tool_name,
                "status": "requires_confirmation",
                "output": {},
                "error": "MCP tool calls require explicit user confirmation.",
                "duration_ms": 0,
            }
        return {
            "server_id": server_id,
            "tool_name": tool_name,
            "status": "not_implemented",
            "output": {"arguments": request.arguments},
            "error": "Stdio MCP execution will be connected in 7C-2.",
            "duration_ms": 0,
        }

    @app.get("/api/agent-events")
    def agent_events():
        return app.state.service.agent_events_summary()

    @app.get("/api/orchestrator/tasks/{task_id}")
    def orchestrator_task(task_id: int):
        try:
            return app.state.service.orchestrator.get_task(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return app


def _sanitize_model_error(message: str, api_key_env_var: str) -> str:
    api_key = os.getenv(api_key_env_var, "")
    safe_message = message.replace("\n", " ")
    if api_key:
        safe_message = safe_message.replace(api_key, "[redacted]")
    return safe_message[:240]


def _mcp_server_configs() -> list[McpServerConfig]:
    raw = os.getenv("AGENT_BUSINESS_MCP_SERVERS", "").strip()
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    servers: list[McpServerConfig] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            servers.append(McpServerConfig(**item))
        except ValueError:
            continue
    return servers


app = create_app()
