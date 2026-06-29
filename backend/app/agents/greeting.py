from __future__ import annotations

from app.agents.job_match import IMPORTANT_TERMS
from app.schemas import GreetingMessage, JobPosting, ResumeDraft


class GreetingAgent:
    def generate(self, resume: ResumeDraft, job: JobPosting) -> GreetingMessage:
        resume_text_lower = resume.raw_text.lower()
        matched_terms = [
            term for term in IMPORTANT_TERMS if term.lower() in resume_text_lower and term.lower() in job.description.lower()
        ]
        strength = "、".join(matched_terms[:4]) if matched_terms else "项目实践和学习能力"
        message = (
            f"您好，我对贵公司「{job.title}」岗位很感兴趣。"
            f"我的经历中有 {strength} 相关积累，已经根据岗位要求准备了定制简历。"
            "如果方便，期待进一步沟通实习机会，谢谢。"
        )
        return GreetingMessage(job_id=job.id or 0, message=message)
