from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def read_project_file(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_start_script_installs_reuses_and_health_checks_services() -> None:
    script = read_project_file("scripts/start-project.ps1")

    assert "[switch]$SkipInstall" in script
    assert "[switch]$NoBrowser" in script
    assert '"http://127.0.0.1:8000"' in script
    assert '"http://127.0.0.1:5173"' in script
    assert '"$backendUrl/openapi.json"' in script
    assert '"$frontendUrl/api/health"' in script
    assert script.count("-WindowStyle Hidden") == 2
    assert "--strictPort" in script
    assert "dataRoot" in script and "backend.pid" in script and "frontend.pid" in script


def test_stop_script_refuses_to_stop_unrelated_processes() -> None:
    script = read_project_file("scripts/stop-project.ps1")

    assert "ProcessName" in script
    assert "CommandMarker" in script
    assert "CommandLine.Contains($projectRoot)" in script
    assert "refusing to stop an unrelated process" in script
    assert "Get-DescendantProcessIds" in script
    assert "Get-NetTCPConnection" in script


def test_windows_dependency_and_runtime_artifacts_are_declared() -> None:
    requirements = read_project_file("backend/requirements.txt")
    gitignore = read_project_file(".gitignore")

    assert 'pywin32==308; sys_platform == "win32"' in requirements
    assert "data/*.pid" in gitignore
    assert ".playwright-cli/" in gitignore
    assert "output/playwright/" in gitignore
