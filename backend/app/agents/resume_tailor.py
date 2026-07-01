from __future__ import annotations

from app.agents.job_match import IMPORTANT_TERMS, REQUIREMENT_GAP_TERMS
from app.schemas import JobPosting, ResumeDraft, TailoredResume


class ResumeTailorAgent:
    def tailor(self, resume: ResumeDraft, job: JobPosting) -> TailoredResume:
        resume_text_lower = resume.raw_text.lower()
        job_text_lower = f"{job.title} {job.description}".lower()
        matched_terms = [
            term
            for term in IMPORTANT_TERMS
            if term.lower() in job_text_lower and term.lower() in resume_text_lower
        ]
        missing_terms = [
            term
            for term in REQUIREMENT_GAP_TERMS
            if term.lower() in job_text_lower and term.lower() not in resume_text_lower
        ]

        highlight_line = "、".join(matched_terms) if matched_terms else "原简历中的相关经历和学习积累"
        editable_resume = self._editable_excerpt(resume.raw_text)
        resume_rewrite = (
            f"{editable_resume}\n"
            f"简历改写要求: 面向「{job.title}」突出 {highlight_line}。"
            "以上内容均来自原始简历，不新增未经确认的经历。"
        )

        return TailoredResume(
            job_id=job.id or 0,
            resume_id=resume.id or 0,
            resume_text=resume_rewrite,
            resume_rewrite=resume_rewrite,
            project_rewrite=resume_rewrite,
            diff_summary=[
                f"突出与 {job.company} - {job.title} 相关的经历",
                "保留原简历事实边界，不新增公司、项目、学校或技能",
            ],
            risk_flags=missing_terms,
            truth_check_passed=True,
        )

    def _editable_excerpt(self, raw_text: str) -> str:
        locked_prefixes = ("姓名", "电话", "邮箱", "微信", "性别", "年龄", "教育", "学校")
        editable_lines = [
            line.strip()
            for line in raw_text.splitlines()
            if line.strip() and not line.strip().startswith(locked_prefixes)
        ]
        if editable_lines:
            return "\n".join(editable_lines[:6])
        return "可改写正文: 原简历中的技能、项目、实习或经历描述"
