from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEMO_PATH = PROJECT_ROOT / "outputs" / "squirrel-world-ui-demo-20260903" / "index.html"


def _module_html(document: str, module_name: str, next_module_name: str | None = None) -> str:
    marker = f'data-module-panel="{module_name}"'
    content = document.split(marker, 1)[1]
    if next_module_name is None:
        return content
    return content.split(f'data-module-panel="{next_module_name}"', 1)[0]


def test_demo_navigation_and_homepage_structure() -> None:
    html = DEMO_PATH.read_text(encoding="utf-8")

    sidebar = html.split('<aside class="sidebar"', 1)[1].split("</aside>", 1)[0]
    assert 'class="brand"' in sidebar
    assert 'class="sidebar-tools"' in sidebar
    assert 'class="topbar"' not in html
    assert "translateX(calc(-100% + 14px))" in html
    assert ".sidebar:hover" in html
    assert ".sidebar:focus-within" in html

    assert 'id="feature-search"' in html
    assert "松鼠世界能为你做什么" in html
    assert html.count("data-module-jump=") == 4
    assert "featureSearch.addEventListener(\"input\"" in html
    assert "button.blur();" in html
    assert html.count('data-module="') == 7
    assert html.count("data-module-panel=") == 7


def test_dashboard_content_is_relocated_to_the_right_modules() -> None:
    html = DEMO_PATH.read_text(encoding="utf-8")

    dashboard = _module_html(html, "dashboard", "materials")
    applications = _module_html(html, "applications", "agents")
    agents = _module_html(html, "agents", "settings")

    assert "最近动作" not in dashboard
    assert "求职进度漏斗" not in dashboard
    assert "求职进度漏斗" in applications
    assert "最近动作" in agents


def test_demo_components_have_hover_feedback() -> None:
    html = DEMO_PATH.read_text(encoding="utf-8")

    for selector in (
        ".metric-card:hover",
        ".card:hover",
        ".feature-card:hover",
        ".health-tile:hover",
        ".activity:hover",
        ".funnel-step:hover",
        ".module-card:hover",
    ):
        assert selector in html
