"""Keep the module-level FastAPI app, not just test fixtures, out of production data."""
import os
from pathlib import Path
from tempfile import mkdtemp


def pytest_configure(config):
    project = Path(__file__).resolve().parents[2]
    scratch = project / "output"
    scratch.mkdir(exist_ok=True)
    config._agent_business_previous_cwd = Path.cwd()
    config._agent_business_previous_env = os.environ.get("AGENT_BUSINESS_ENV_FILE")
    if config.option.basetemp:
        # Resolve CLI paths before switching cwd so existing verification commands still work.
        config.option.basetemp = str(Path(config.option.basetemp).resolve())
    session = Path(mkdtemp(prefix="pytest-session-", dir=scratch)).resolve()
    os.chdir(session)
    os.environ["AGENT_BUSINESS_ENV_FILE"] = str(session / "missing.env")


def pytest_unconfigure(config):
    if hasattr(config, "_agent_business_previous_cwd"):
        os.chdir(config._agent_business_previous_cwd)
        previous = config._agent_business_previous_env
        if previous is None:
            os.environ.pop("AGENT_BUSINESS_ENV_FILE", None)
        else:
            os.environ["AGENT_BUSINESS_ENV_FILE"] = previous
