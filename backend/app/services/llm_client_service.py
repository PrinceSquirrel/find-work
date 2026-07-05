from __future__ import annotations

import json
import os
from pathlib import Path
from dataclasses import dataclass
from time import perf_counter
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.schemas import JobMatch, JobPosting, ModelConfig, ResumeDraft
from app.services.llm_prompt_service import LLMPromptService


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
    def __init__(self, prompt_service: LLMPromptService | None = None) -> None:
        self.prompt_service = prompt_service or LLMPromptService()

    def test_connection(self, config: ModelConfig) -> dict[str, object]:
        api_key = self._api_key(config)
        payload = {
            "model": config.model,
            "messages": [
                {"role": "system", "content": "You are a connection health check endpoint."},
                {"role": "user", "content": "Reply with ok."},
            ],
            "temperature": 0,
            "max_tokens": 8,
        }
        request = Request(
            f"{config.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "agent-business/0.1",
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
        try:
            payload = json.loads(raw)
            payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise LLMClientUnavailable("LLM response did not contain message content") from exc
        return {
            "status": "success",
            "provider": config.provider,
            "model": config.model,
            "duration_ms": duration_ms,
            "message": "model connection ok",
        }

    def generate_application_materials(
        self,
        config: ModelConfig,
        resume: ResumeDraft,
        job: JobPosting,
    ) -> LLMCompletionResult:
        api_key = self._api_key(config)
        prompt = self.prompt_service.application_writer_user_prompt(resume, job)
        payload = {
            "model": config.model,
            "messages": [
                {
                    "role": "system",
                    "content": self.prompt_service.application_writer_system_message(),
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
                "Accept": "application/json",
                "User-Agent": "agent-business/0.1",
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

    def score_job_matches(
        self,
        config: ModelConfig,
        resume: ResumeDraft,
        jobs: list[JobPosting],
        rule_matches: list[JobMatch],
    ) -> LLMCompletionResult:
        api_key = self._api_key(config)
        prompt = self.prompt_service.job_match_user_prompt(resume, jobs, rule_matches)
        payload = {
            "model": config.model,
            "messages": [
                {
                    "role": "system",
                    "content": self.prompt_service.job_match_system_message(),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        request = Request(
            f"{config.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "agent-business/0.1",
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
        api_key = _env_value(config.api_key_env_var)
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
        return self.prompt_service.application_writer_user_prompt(resume, job)

    def _job_match_prompt(self, resume: ResumeDraft, jobs: list[JobPosting], rule_matches: list[JobMatch]) -> str:
        return self.prompt_service.job_match_user_prompt(resume, jobs, rule_matches)


def _env_value(name: str) -> str:
    value = os.getenv(name, "")
    if value:
        return value
    for path in _candidate_env_files():
        if not path.exists() or not path.is_file():
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                key, separator, raw_value = line.partition("=")
                if not separator or key.strip() != name:
                    continue
                return raw_value.strip().strip('"').strip("'")
        except OSError:
            continue
    return ""


def _candidate_env_files() -> list[Path]:
    configured = os.getenv("AGENT_BUSINESS_ENV_FILE", "").strip()
    if configured:
        return [Path(configured)]
    return [Path(r"D:\code\tourism-opinion-agent\.env")]
