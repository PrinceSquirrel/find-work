from __future__ import annotations

import re

from app.schemas import JobMatch, JobPosting, ResumeDraft


IMPORTANT_TERMS = [
    "Python",
    "FastAPI",
    "React",
    "SQL",
    "Agent",
    "RAG",
    "API",
    "数据分析",
    "后端",
    "前端",
    "看板",
    "模型",
    "实习",
]

REQUIREMENT_GAP_TERMS = [
    *IMPORTANT_TERMS,
    "Kubernetes",
    "Prometheus",
    "Docker",
    "微服务",
    "云原生",
]


class JobMatchAgent:
    def match(self, resume: ResumeDraft, job: JobPosting) -> JobMatch:
        resume_text = resume.raw_text.lower()
        job_text = f"{job.title} {job.description} {job.job_type}".lower()
        hits: list[str] = []
        gaps: list[str] = []

        for term in IMPORTANT_TERMS:
            term_lower = term.lower()
            if term_lower in job_text:
                if term_lower in resume_text:
                    hits.append(term)
                else:
                    gaps.append(term)

        keyword_overlap = self._token_overlap(resume.raw_text, f"{job.title} {job.description}")
        score = min(100, 35 + len(hits) * 10 + keyword_overlap * 4)
        if not hits:
            score = min(score, 45)
        if len(gaps) >= 4:
            score -= 10
        score = max(0, score)

        if score >= 80:
            recommendation = "strong_apply"
        elif score >= 60:
            recommendation = "review"
        else:
            recommendation = "skip"

        return JobMatch(
            job_id=job.id,
            score=score,
            hit_reasons=hits,
            gap_reasons=gaps,
            recommendation=recommendation,
        )

    def _token_overlap(self, resume_text: str, job_text: str) -> int:
        resume_tokens = set(re.findall(r"[A-Za-z0-9+#]+|[\u4e00-\u9fa5]{2,}", resume_text.lower()))
        job_tokens = set(re.findall(r"[A-Za-z0-9+#]+|[\u4e00-\u9fa5]{2,}", job_text.lower()))
        stop_words = {"需要", "负责", "参与", "经验", "优先", "岗位", "实习生"}
        return len((resume_tokens & job_tokens) - stop_words)
