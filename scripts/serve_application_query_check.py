"""Isolated real API fixture for application query UI; never touches user data."""
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


def main():
    project = Path(__file__).resolve().parent.parent
    scratch = project / "output"
    scratch.mkdir(exist_ok=True)
    sys.path.insert(0, str(project / "backend"))
    with TemporaryDirectory(prefix="application-query-ui-", dir=scratch) as temporary:
        os.chdir(temporary)
        os.environ["AGENT_BUSINESS_ENV_FILE"] = str(Path(temporary) / "missing.env")
        from app.main import create_app
        import uvicorn

        app = create_app(db_path=Path(temporary) / "fixture.sqlite3")
        store = app.state.service.store
        with store._connect() as conn:
            for number in range(137):
                title = "Python 实习" if number % 2 else "产品 实习"
                city = "上海张江" if number % 2 else "北京"
                conn.execute("""INSERT INTO applications (job_id,company,title,platform,applied_at,current_status,progress_stage,latest_note,platform_proof_json,job_city_snapshot,job_description_snapshot,job_snapshot_origin)
                    VALUES (?,?,?,'boss','2026-11-18T00:00:00+00:00','applied','已投递',?,'{}',?,?,'at_application')""",
                    (number + 1, f"分页测试公司{number}", title, "100%_匹配" if number == 1 else "备注", city, "SQL 可视化" if number % 3 else "产品需求"))
                conn.execute("INSERT INTO application_events (application_id,status,occurred_at,note) VALUES (?,'applied','2026-11-18T00:00:00+00:00','合成记录')", (number + 1,))

        @app.get("/__application_query_identity")
        def identity():
            return {"fixture": "temporary-application-query-check", "initial_count": 137}

        uvicorn.run(app, host="127.0.0.1", port=8767, log_level="warning")


if __name__ == "__main__":
    main()
