import os
from pathlib import Path

from app.main import app


def test_default_app_import_and_environment_are_isolated_from_user_data():
    project = Path(__file__).resolve().parents[2]
    session = Path.cwd().resolve()
    assert session.is_relative_to(project / "output")
    assert session.name.startswith("pytest-session-")
    assert app.state.service.store.db_path.resolve().is_relative_to(session)
    assert Path(os.environ["AGENT_BUSINESS_ENV_FILE"]).parent == session
    assert not Path(os.environ["AGENT_BUSINESS_ENV_FILE"]).exists()
