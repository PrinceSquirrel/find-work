from __future__ import annotations

from io import BytesIO
from typing import Any

from app.agents.job_match import IMPORTANT_TERMS
from app.schemas import ResumeDraft


SEARCH_KEYWORD_PRIORITY = ["Python", "FastAPI", "React", "SQL", "数据分析", "后端", "前端", "Agent", "RAG"]
COMMON_CITIES = ["上海", "北京", "深圳", "广州", "杭州", "南京", "苏州", "成都", "武汉", "西安"]
IMAGE_SUFFIXES = {"png", "jpg", "jpeg"}


class ResumeParserAgent:
    def parse(self, filename: str, content: bytes) -> ResumeDraft:
        suffix = self._suffix(filename)
        raw_text, extraction = self._extract_text_with_metadata(filename, content)
        profile = self._build_profile(raw_text, extraction, suffix)
        return ResumeDraft(
            filename=filename,
            raw_text=raw_text,
            profile=profile,
            file_type=suffix,
            template_available=suffix == "docx",
        )

    def apply_manual_text(self, resume: ResumeDraft, manual_text: str) -> ResumeDraft:
        raw_text = manual_text.strip()
        extraction = self._metadata(
            source_type="manual",
            method="manual_text",
            status="success" if raw_text else "manual_required",
            text_length=len(raw_text),
            confidence=1.0 if raw_text else 0.0,
            manual_text_required=not bool(raw_text),
            message="" if raw_text else "Manual resume text is required before generating materials.",
        )
        return resume.model_copy(update={"raw_text": raw_text, "profile": self._build_profile(raw_text, extraction, resume.file_type)})

    def _build_profile(self, raw_text: str, extraction: dict[str, Any], suffix: str) -> dict[str, Any]:
        skills = [term for term in IMPORTANT_TERMS if term.lower() in raw_text.lower()]
        profile = {
            "skills": skills,
            "suggested_keywords": self._suggest_keywords(skills),
            "suggested_city": self._suggest_city(raw_text),
            "text_length": len(raw_text),
            "extraction": extraction,
            "can_generate_materials": bool(raw_text.strip()) and not extraction.get("manual_text_required", False),
        }
        if suffix == "pdf":
            profile["pdf_reading"] = extraction
        if suffix in IMAGE_SUFFIXES:
            profile["image_reading"] = extraction
        return profile

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
        raw_text, _ = self._extract_text_with_metadata(filename, content)
        return raw_text

    def _suffix(self, filename: str) -> str:
        return filename.lower().rsplit(".", 1)[-1] if "." in filename else "txt"

    def _extract_text_with_metadata(self, filename: str, content: bytes) -> tuple[str, dict[str, Any]]:
        suffix = self._suffix(filename)
        if suffix == "pdf":
            return self._extract_pdf(content)
        if suffix == "docx":
            raw_text = self._extract_docx(content)
            return raw_text, self._metadata(
                source_type="docx",
                method="python-docx",
                status="success" if raw_text else "empty",
                text_length=len(raw_text),
                confidence=0.95 if raw_text else 0.0,
                manual_text_required=not bool(raw_text),
            )
        if suffix in IMAGE_SUFFIXES:
            return self._extract_image(content, suffix)
        raw_text = content.decode("utf-8", errors="ignore").strip()
        return raw_text, self._metadata(
            source_type=suffix or "txt",
            method="utf-8",
            status="success" if raw_text else "empty",
            text_length=len(raw_text),
            confidence=0.9 if raw_text else 0.0,
            manual_text_required=not bool(raw_text),
        )

    def _metadata(
        self,
        *,
        source_type: str,
        method: str,
        status: str,
        text_length: int,
        page_count: int = 0,
        empty_page_count: int = 0,
        message: str = "",
        warnings: list[str] | None = None,
        confidence: float = 0.0,
        manual_text_required: bool = False,
    ) -> dict[str, Any]:
        return {
            "source_type": source_type,
            "method": method,
            "status": status,
            "page_count": page_count,
            "empty_page_count": empty_page_count,
            "text_length": text_length,
            "layout_verified": False,
            "message": message,
            "warnings": warnings or [],
            "confidence": confidence,
            "manual_text_required": manual_text_required,
        }

    def _extract_pdf(self, content: bytes) -> tuple[str, dict[str, Any]]:
        try:
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(content))
            page_texts = [(page.extract_text() or "").strip() for page in reader.pages]
            raw_text = "\n".join(text for text in page_texts if text).strip()
            empty_page_count = sum(1 for text in page_texts if not text)
            warnings: list[str] = []
            if empty_page_count:
                warnings.append("Some PDF pages returned no extractable text; scanned pages may need OCR.")
            is_empty = not bool(raw_text)
            return raw_text, self._metadata(
                source_type="pdf_text" if raw_text else "pdf_scan",
                method="pypdf",
                status="success" if raw_text else "needs_ocr",
                page_count=len(reader.pages),
                empty_page_count=empty_page_count,
                text_length=len(raw_text),
                message="" if raw_text else "PDF looks like a scanned/image PDF; OCR or manual text is required.",
                warnings=warnings,
                confidence=0.85 if raw_text else 0.0,
                manual_text_required=is_empty,
            )
        except Exception as exc:
            fallback_text = content.decode("utf-8", errors="ignore").strip()
            return fallback_text, self._metadata(
                source_type="pdf_text" if fallback_text else "pdf_scan",
                method="pypdf",
                status="failed" if fallback_text else "needs_ocr",
                text_length=len(fallback_text),
                message=f"pypdf extraction failed: {type(exc).__name__}",
                confidence=0.2 if fallback_text else 0.0,
                manual_text_required=not bool(fallback_text),
            )

    def _extract_image(self, content: bytes, suffix: str) -> tuple[str, dict[str, Any]]:
        raw_text, ocr_warning = self._try_optional_ocr(content)
        if raw_text:
            return raw_text, self._metadata(
                source_type="image_ocr",
                method="pytesseract",
                status="success",
                text_length=len(raw_text),
                confidence=0.65,
            )
        warnings = ["Image resume uploaded; OCR is unavailable or returned no readable text."]
        if ocr_warning:
            warnings.append(ocr_warning)
        return "", self._metadata(
            source_type=f"image_{suffix}",
            method="image-upload",
            status="manual_required",
            text_length=0,
            message="Please paste resume text manually so agents can generate materials.",
            warnings=warnings,
            confidence=0.0,
            manual_text_required=True,
        )

    def _try_optional_ocr(self, content: bytes) -> tuple[str, str]:
        try:
            from PIL import Image
            import pytesseract

            image = Image.open(BytesIO(content))
            raw_text = pytesseract.image_to_string(image, lang="chi_sim+eng").strip()
            return raw_text, ""
        except Exception as exc:
            return "", f"Optional local OCR failed: {type(exc).__name__}"

    def _extract_docx(self, content: bytes) -> str:
        try:
            from docx import Document

            doc = Document(BytesIO(content))
            return "\n".join(paragraph.text for paragraph in doc.paragraphs).strip()
        except Exception:
            return content.decode("utf-8", errors="ignore").strip()
