from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_agents_requires_tested_commits_and_github_pushes() -> None:
    policy = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")

    required_rules = (
        "每个完成并通过验证的逻辑改动都必须创建一个语义清晰、可追踪和可回滚的 `git commit`",
        "每个本地提交完成后必须立即推送到当前分支对应的 GitHub 远程分支",
        "每次功能、行为、接口或界面改动都必须同时新增或更新能够覆盖本次变化的相关测试",
        "只有全部通过后才能提交和推送",
    )

    for rule in required_rules:
        assert rule in policy
