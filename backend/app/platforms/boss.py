from __future__ import annotations

from app.platforms.base import JobPlatformAdapter
from app.schemas import JobPosting, ResumeDraft


class BossAdapter(JobPlatformAdapter):
    platform = "boss"

    def search(self, resume: ResumeDraft, keywords: list[str], city: str) -> list[JobPosting]:
        keyword = keywords[0] if keywords else "Python 实习"
        return [
            JobPosting(
                platform=self.platform,
                company="星河智能科技",
                title=f"{keyword} - 后端 Agent 实习生",
                city=city or "上海",
                salary="200-300/天",
                description="参与 AI Agent 平台后端开发，需要 Python、FastAPI、SQL、API 设计和数据看板经验。",
                url="https://example.test/boss/demo-agent-business",
                job_type="backend",
            )
        ]
