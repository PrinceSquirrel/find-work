from __future__ import annotations

import json

from app.agents.greeting import GreetingAgent
from app.agents.resume_tailor import ResumeTailorAgent
from app.schemas import GreetingMessage, JobPosting, ResumeDraft, TailorBundle, TailoredResume


class ApplicationWriterAgent:
    """Generate application materials for one user-selected job."""

    def __init__(self) -> None:
        self.resume_tailor = ResumeTailorAgent()
        self.greeting = GreetingAgent()

    def write(self, resume: ResumeDraft, job: JobPosting) -> TailorBundle:
        tailored_resume = self.resume_tailor.tailor(resume, job)
        greeting = self.greeting.generate(resume, job)
        return TailorBundle(tailored_resume=tailored_resume, greeting=greeting)

    def write_from_llm_json(self, resume: ResumeDraft, job: JobPosting, content: str) -> TailorBundle:
        payload = self._parse_json(content)
        resume_rewrite = (
            self._optional_text(payload, "resume_rewrite")
            or self._optional_text(payload, "project_rewrite")
            or self._required_text(payload, "resume_text")
        )
        project_rewrite = self._optional_text(payload, "project_rewrite") or resume_rewrite
        resume_text = self._optional_text(payload, "resume_text") or resume_rewrite
        greeting_message = self._required_text(payload, "greeting_message")
        tailored_resume = TailoredResume(
            job_id=job.id or 0,
            resume_id=resume.id or 0,
            resume_text=resume_text,
            resume_rewrite=resume_rewrite,
            project_rewrite=project_rewrite,
            diff_summary=self._string_list(payload.get("diff_summary")),
            risk_flags=self._string_list(payload.get("resume_risk_flags")),
            truth_check_passed=True,
        )
        greeting = GreetingMessage(
            job_id=job.id or 0,
            message=greeting_message,
            tone=str(payload.get("tone") or "professional"),
            risk_flags=self._string_list(payload.get("greeting_risk_flags")),
        )
        return TailorBundle(tailored_resume=tailored_resume, greeting=greeting)

    def _parse_json(self, content: str) -> dict[str, object]:
        stripped = content.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            if stripped.lower().startswith("json"):
                stripped = stripped[4:].strip()
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError("LLM output is not valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("LLM output must be a JSON object")
        return payload

    def _required_text(self, payload: dict[str, object], key: str) -> str:
        value = str(payload.get(key) or "").strip()
        if not value:
            raise ValueError(f"LLM output missing required field: {key}")
        return value

    def _optional_text(self, payload: dict[str, object], key: str) -> str:
        return str(payload.get(key) or "").strip()

    def _string_list(self, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]
