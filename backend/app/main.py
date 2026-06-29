from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from app.agents.application_tracker import InvalidStatusTransition
from app.schemas import (
    ApplicationSyncRequest,
    ApplyRecordRequest,
    BrowserJobExtractRequest,
    ModelConfigUpdate,
    SearchRunRequest,
    StatusPatchRequest,
    TailorRequest,
)
from app.services import JobApplicationService
from app.services.application_sync_service import ApplicationSyncService
from app.services.browser_job_extractor_service import BrowserJobExtractorService
from app.services.platform_session_service import CdpBrowserLauncher, PlatformSessionService
from app.storage import SQLiteStore


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

    @app.post("/api/resumes", status_code=201)
    async def upload_resume(file: Annotated[UploadFile, File()]):
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="简历文件不能为空")
        return app.state.service.upload_resume(file.filename or "resume.txt", content)

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
    def list_jobs():
        return app.state.service.list_jobs()

    @app.post("/api/jobs/{job_id}/tailor", status_code=201)
    def tailor_job(job_id: int, payload: TailorRequest):
        try:
            return app.state.service.tailor_for_job(job_id=job_id, resume_id=payload.resume_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/jobs/{job_id}/apply-record", status_code=201)
    def create_application(job_id: int, payload: ApplyRecordRequest):
        try:
            return app.state.service.create_application(job_id, note=payload.note)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

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

    return app


app = create_app()
