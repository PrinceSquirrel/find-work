"""Disposable API and extraction-script fixture for the three workspace bug regressions."""
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def main():
    project = Path(__file__).resolve().parent.parent
    scratch = project / "output"
    scratch.mkdir(exist_ok=True)
    sys.path.insert(0, str(project / "backend"))
    with TemporaryDirectory(prefix="workspace-bugs-", dir=scratch) as temporary:
        os.chdir(temporary)
        os.environ["AGENT_BUSINESS_ENV_FILE"] = str(Path(temporary) / "missing.env")
        from app.main import create_app
        from app.services.browser_job_extractor_service import BrowserJobExtractorService
        import uvicorn
        app = create_app(db_path=Path(temporary) / "fixture.sqlite3")

        @app.get("/__workspace_bug_identity")
        def identity():
            return {"fixture": "temporary-workspace-bug-check"}

        @app.get("/__extract_script")
        def script():
            return {"script": BrowserJobExtractorService(cdp_url="http://127.0.0.1:9222")._extract_script("boss", 8)}

        @app.get("/__job_scripts")
        def job_scripts():
            service = BrowserJobExtractorService(cdp_url="http://127.0.0.1:9222")
            url = "http://127.0.0.1:8768/job_detail/synthetic.html"
            return {"detail": service._detail_refresh_script("boss", url), "extract": service._extract_script("boss", 8),
                    "preview": service._application_preview_script("boss", url), "apply": service._application_click_script("boss", url)}

        try:
            uvicorn.run(app, host="127.0.0.1", port=8768, log_level="warning")
        finally:
            os.chdir(project)


if __name__ == "__main__":
    main()
