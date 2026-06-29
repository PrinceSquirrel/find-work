from __future__ import annotations

from app.platforms.base import JobPlatformAdapter
from app.schemas import JobPosting, ResumeDraft


class ShixisengAdapter(JobPlatformAdapter):
    platform = "shixiseng"

    def search(self, resume: ResumeDraft, keywords: list[str], city: str) -> list[JobPosting]:
        keyword = keywords[-1] if keywords else "Agent 实习"
        return [
            JobPosting(
                platform=self.platform,
                company="启明数据实验室",
                title=f"{keyword} - 前后端研发实习生",
                city=city or "上海",
                salary="180-260/天",
                description="负责求职效率工具和可视化工作台，要求 React、Python、SQL、数据分析和模型调用经验。",
                url="https://example.test/shixiseng/demo-agent-business",
                job_type="fullstack",
            )
        ]
