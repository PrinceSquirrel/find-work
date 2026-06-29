from __future__ import annotations

import json
import os
from dataclasses import dataclass
from time import perf_counter
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.schemas import JobPosting, ModelConfig, ResumeDraft


class LLMClientUnavailable(RuntimeError):
    """Raised when the configured external LLM cannot be called safely."""


@dataclass(frozen=True)
class LLMCompletionResult:
    content: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    duration_ms: int
    estimated: bool


class OpenAICompatibleClient:
    def generate_application_materials(
        self,
        config: ModelConfig,
        resume: ResumeDraft,
        job: JobPosting,
    ) -> LLMCompletionResult:
        api_key = self._api_key(config)
        prompt = self._prompt(resume, job)
        payload = {
            "model": config.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是求职材料写作助手。只允许基于用户原始简历改写，"
                        "不得新增不存在的学校、公司、项目、技能或经历。"
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        request = Request(
            f"{config.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        started = perf_counter()
        try:
            with urlopen(request, timeout=config.timeout_ms / 1000) as response:
                raw = response.read().decode("utf-8")
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise LLMClientUnavailable(f"LLM request failed: {exc.__class__.__name__}") from exc
        duration_ms = max(1, int((perf_counter() - started) * 1000))
        return self._parse_response(config, prompt, raw, duration_ms)

    def _api_key(self, config: ModelConfig) -> str:
        if not config.enabled or config.estimation_only:
            raise LLMClientUnavailable("LLM model config is disabled or estimation-only")
        api_key = os.getenv(config.api_key_env_var, "")
        if not api_key:
            raise LLMClientUnavailable(f"API key env var is not configured: {config.api_key_env_var}")
        return api_key

    def _parse_response(
        self,
        config: ModelConfig,
        prompt: str,
        raw: str,
        duration_ms: int,
    ) -> LLMCompletionResult:
        try:
            payload = json.loads(raw)
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise LLMClientUnavailable("LLM response did not contain message content") from exc
        usage = payload.get("usage", {}) if isinstance(payload, dict) else {}
        prompt_tokens = int(usage.get("prompt_tokens") or max(1, len(prompt) // 4))
        completion_tokens = int(usage.get("completion_tokens") or max(1, len(content) // 4))
        estimated = "prompt_tokens" not in usage or "completion_tokens" not in usage
        return LLMCompletionResult(
            content=content,
            provider=config.provider,
            model=config.model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            duration_ms=duration_ms,
            estimated=estimated,
        )

    def _prompt(self, resume: ResumeDraft, job: JobPosting) -> str:
        return (
            "请输出 JSON，字段必须包含：resume_text、greeting_message、diff_summary、"
            "resume_risk_flags、greeting_risk_flags、tone。\n"
            "要求：只基于原简历改写；如果岗位要求原简历没有出现的技能，只能放入风险提示，不要写入简历正文。\n\n"
            f"原简历：\n{resume.raw_text}\n\n"
            f"岗位：{job.company} / {job.title} / {job.city} / {job.salary}\n"
            f"JD：\n{job.description}"
        )
