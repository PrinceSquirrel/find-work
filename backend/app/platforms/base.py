from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas import JobPosting, ResumeDraft


class JobPlatformAdapter(ABC):
    platform: str

    @abstractmethod
    def search(self, resume: ResumeDraft, keywords: list[str], city: str) -> list[JobPosting]:
        """Return normalized jobs from one recruitment platform."""
