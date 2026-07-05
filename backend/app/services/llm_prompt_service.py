from __future__ import annotations

import json

from app.schemas import JobMatch, JobPosting, ResumeDraft


class LLMPromptService:
    def application_writer_system_message(self) -> str:
        return "你是求职材料写作助手。只允许基于用户原始简历改写，不得新增不存在的学校、公司、项目、技能或经历。"

    def application_writer_user_prompt(self, resume: ResumeDraft, job: JobPosting) -> str:
        return (
            "请输出 JSON，字段必须包含：resume_rewrite、greeting_message、diff_summary、"
            "resume_risk_flags、greeting_risk_flags、tone。\n"
            "要求：锁定身份信息和教育经历，不要改姓名、电话、邮箱、头像、年龄、性别、学校、学历或教育时间；"
            "可以基于原简历事实改写技能、项目、实习、经历描述、自我评价、摘要等简历正文。"
            "如果岗位要求原简历没有出现的技能、公司、学校、项目事实或证书，只能放入风险提示，不要写入简历正文。"
            "resume_rewrite 只输出可替换正文，不要输出锁定的身份信息和教育经历。\n\n"
            f"原简历：\n{resume.raw_text}\n\n"
            f"岗位：{job.company} / {job.title} / {job.city} / {job.salary}\n"
            f"JD：\n{job.description}"
        )

    def job_match_system_message(self) -> str:
        return "你是低成本岗位匹配评分器。只根据候选人原简历和岗位 JD 评分，不要改写简历，不要生成求职材料。"

    def job_match_user_prompt(
        self,
        resume: ResumeDraft,
        jobs: list[JobPosting],
        rule_matches: list[JobMatch],
    ) -> str:
        job_payload = []
        for index, (job, match) in enumerate(zip(jobs, rule_matches)):
            job_payload.append(
                {
                    "job_index": index,
                    "company": job.company,
                    "title": job.title,
                    "city": job.city,
                    "salary": job.salary,
                    "job_type": job.job_type,
                    "description": job.description[:1600],
                    "rule_score": match.score,
                    "rule_hit_reasons": match.hit_reasons,
                    "rule_gap_reasons": match.gap_reasons,
                }
            )
        return (
            "请输出 JSON，字段必须为 matches。matches 是数组，每项包含："
            "job_index、score、hit_reasons、gap_reasons、recommendation。\n"
            "score 为 0-100 整数；recommendation 只能是 strong_apply、review、skip。"
            "只根据原简历事实和岗位 JD 判断，不要编造候选人经历。"
            "如果岗位 JD 信息不足，请降低分数并在 gap_reasons 说明。\n\n"
            f"原简历：\n{resume.raw_text[:3000]}\n\n"
            f"岗位列表：\n{json.dumps(job_payload, ensure_ascii=False)}"
        )
