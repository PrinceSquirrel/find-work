"""Temporary database for check-bulk-deletion.js; never opens the user's database."""
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory


def main():
    project = Path(__file__).resolve().parent.parent
    scratch = project / "output"
    scratch.mkdir(exist_ok=True)
    sys.path.insert(0, str(project / "backend"))
    with TemporaryDirectory(prefix="bulk-ui-", dir=scratch) as temporary:
        # app.main also creates its default app on import; keep that in the sandbox too.
        os.chdir(temporary)
        os.environ["AGENT_BUSINESS_ENV_FILE"] = str(Path(temporary) / "missing.env")
        from app.main import create_app
        from app.schemas import ApplicationPlatformProof, GreetingMessage, JobMatch, JobPosting, TailoredClaim, TailoredResume
        import uvicorn

        app = create_app(db_path=Path(temporary) / "fixture.sqlite3")
        store = app.state.service.store
        jobs = [store.save_job(JobPosting(platform="boss", company=f"测试公司{index + 1}", title=title, city="上海", salary="面议", description="批量删除测试岗位，Python 开发", url=f"https://example.com/bulk-{index + 1}"), 1, JobMatch(score=80, recommendation="review"))
                for index, title in enumerate(["批删岗位A", "批删岗位B", "已联系岗位", "旧记录岗位"])]
        for job in jobs[2:]:
            record = store.create_application(job, platform_proof=ApplicationPlatformProof(platform="boss", source_url=job.url, action="clicked_apply", status="applied", evidence="测试：已发送招呼", confirmed_at=datetime.now(UTC)))
            if job == jobs[3]:
                # Simulate an older unverified record without weakening production validation.
                with store._connect() as conn:
                    conn.execute("UPDATE applications SET platform_proof_json = '{}' WHERE id = ?", (record.id,))
        material = store.save_tailor_bundle(TailoredResume(job_id=jobs[0].id, resume_id=1, resume_text="测试经历", truth_check_passed=True), GreetingMessage(job_id=jobs[0].id, message="测试招呼"), {})
        store.create_tailored_claim(TailoredClaim(tailored_resume_id=material["id"], text="测试经历"))
        store.reindex_knowledge()

        @app.get("/__bulk_check_identity")
        def identity():
            return {"fixture": "temporary-bulk-deletion-check"}

        @app.get("/__bulk_check_state")
        def state():
            with store._connect() as conn:
                return {table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                        for table in ["jobs", "applications", "application_events", "tailored_resumes", "tailored_claims"]}

        uvicorn.run(app, host="127.0.0.1", port=8766, log_level="info")


if __name__ == "__main__":
    main()
