from __future__ import annotations

from app.schemas import GreetingMessage, JobPosting, ResumeDraft, TailoredResume


class ReviewAgent:
    def review(
        self,
        resume: ResumeDraft,
        job: JobPosting,
        tailored: TailoredResume,
        greeting: GreetingMessage,
    ) -> dict[str, object]:
        generated_text = f"{tailored.resume_text}\n{tailored.resume_rewrite}\n{tailored.project_rewrite}".lower()
        forbidden_additions = [term for term in tailored.risk_flags if term.lower() in generated_text]
        return {
            "job_id": job.id,
            "truth_check_passed": not forbidden_additions and tailored.truth_check_passed,
            "greeting_length": len(greeting.message),
            "risk_flags": forbidden_additions,
            "summary": "审核通过，待用户人工确认后发送" if not forbidden_additions else "存在疑似新增事实，需要人工修改",
        }
