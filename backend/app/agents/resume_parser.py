from __future__ import annotations

from io import BytesIO

from app.agents.job_match import IMPORTANT_TERMS
from app.schemas import ResumeDraft


class ResumeParserAgent:
    def parse(self, filename: str, content: bytes) -> ResumeDraft:
        raw_text = self._extract_text(filename, content)
        profile = {
            "skills": [term for term in IMPORTANT_TERMS if term.lower() in raw_text.lower()],
            "text_length": len(raw_text),
        }
        return ResumeDraft(filename=filename, raw_text=raw_text, profile=profile)

    def _extract_text(self, filename: str, content: bytes) -> str:
        suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else "txt"
        if suffix == "pdf":
            return self._extract_pdf(content)
        if suffix == "docx":
            return self._extract_docx(content)
        return content.decode("utf-8", errors="ignore").strip()

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
