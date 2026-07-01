from __future__ import annotations

from io import BytesIO

from app.agents.job_match import IMPORTANT_TERMS
from app.schemas import ResumeDraft


SEARCH_KEYWORD_PRIORITY = ["Python", "FastAPI", "React", "SQL", "数据分析", "后端", "前端", "Agent", "RAG"]
COMMON_CITIES = ["上海", "北京", "深圳", "广州", "杭州", "南京", "苏州", "成都", "武汉", "西安"]


class ResumeParserAgent:
    def parse(self, filename: str, content: bytes) -> ResumeDraft:
        suffix = self._suffix(filename)
        raw_text = self._extract_text(filename, content)
        skills = [term for term in IMPORTANT_TERMS if term.lower() in raw_text.lower()]
        profile = {
            "skills": skills,
            "suggested_keywords": self._suggest_keywords(skills),
            "suggested_city": self._suggest_city(raw_text),
            "text_length": len(raw_text),
        }
        return ResumeDraft(
            filename=filename,
            raw_text=raw_text,
            profile=profile,
            file_type=suffix,
            template_available=suffix == "docx",
        )

    def _suggest_keywords(self, skills: list[str]) -> list[str]:
        skill_set = set(skills)
        suggestions = [f"{term} 实习" for term in SEARCH_KEYWORD_PRIORITY if term in skill_set]
        return suggestions[:4]

    def _suggest_city(self, raw_text: str) -> str:
        for city in COMMON_CITIES:
            if city in raw_text:
                return city
        return ""

    def _extract_text(self, filename: str, content: bytes) -> str:
        suffix = self._suffix(filename)
        if suffix == "pdf":
            return self._extract_pdf(content)
        if suffix == "docx":
            return self._extract_docx(content)
        return content.decode("utf-8", errors="ignore").strip()

    def _suffix(self, filename: str) -> str:
        return filename.lower().rsplit(".", 1)[-1] if "." in filename else "txt"

    def _extract_pdf(self, content: bytes) -> str:
        try:
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(content))
            return "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        except Exception:
            return content.decode("utf-8", errors="ignore").strip()

    def _extract_docx(self, content: bytes) -> str:
        try:
            from docx import Document

            doc = Document(BytesIO(content))
            return "\n".join(paragraph.text for paragraph in doc.paragraphs).strip()
        except Exception:
            return content.decode("utf-8", errors="ignore").strip()
