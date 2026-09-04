import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_STYLES = (PROJECT_ROOT / "frontend" / "src" / "styles.css").read_text(encoding="utf-8")


def test_desktop_sidebar_is_persistent_and_reserves_its_width() -> None:
    assert re.search(r"\.squirrel-app\s*\{[^}]*padding-left:\s*248px;", WORKSPACE_STYLES, re.DOTALL)
    assert re.search(r"\.squirrel-sidebar\s*\{[^}]*transform:\s*none;", WORKSPACE_STYLES, re.DOTALL)
    assert "translateX(calc(-100% + 14px))" not in WORKSPACE_STYLES
    assert re.search(
        r"@media \(max-width: 720px\)\s*\{\s*\.squirrel-app\s*\{\s*padding-left:\s*0;",
        WORKSPACE_STYLES,
        re.DOTALL,
    )


def test_dashboard_cost_and_health_panels_share_one_equal_height_row() -> None:
    assert re.search(
        r'\.squirrel-app\[data-active-module="dashboard"\] \.health-panel,\s*'
        r'\.squirrel-app\[data-active-module="dashboard"\] \.cost-panel\s*'
        r"\{[^}]*align-self:\s*stretch;[^}]*height:\s*100%;",
        WORKSPACE_STYLES,
        re.DOTALL,
    )
    assert re.search(
        r'\.squirrel-app\[data-active-module="dashboard"\] \.health-panel\s*'
        r"\{[^}]*grid-row:\s*4;",
        WORKSPACE_STYLES,
        re.DOTALL,
    )
    assert re.search(
        r'\.squirrel-app\[data-active-module="dashboard"\] \.cost-panel\s*'
        r"\{[^}]*grid-row:\s*4;",
        WORKSPACE_STYLES,
        re.DOTALL,
    )
