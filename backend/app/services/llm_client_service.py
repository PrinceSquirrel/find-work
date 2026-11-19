from __future__ import annotations

import json
import os
from pathlib import Path
from dataclasses import dataclass
from time import perf_counter
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.schemas import EvidenceCard, EvidenceSource, JobMatch, JobPosting, ModelConfig, ResumeDraft
from app.services.llm_prompt_service import LLMPromptService
from app.services.task_skills import model_skill


class LLMClientUnavailable(RuntimeError):
    """Raised when the configured external LLM cannot be called safely."""


def request_failure(exc: Exception) -> LLMClientUnavailable:
    """Keep actionable status information without returning provider bodies or credentials."""
    if isinstance(exc, HTTPError):
        code = ""
        if exc.code == 429:
            try:
                error = json.loads(exc.read(16384)).get("error", {})
                code = str(error.get("code", "")).lower()
            except (ValueError, TypeError, AttributeError, OSError):
                pass
        if exc.code == 401:
            hint = "模型认证失败：API Key 无效或已失效，请到系统设置更新该服务商的 Key。"
        elif exc.code == 402 or code in {"insufficient_quota", "insufficient_balance"}:
            hint = "模型账户余额或额度不足，请在服务商账户检查余额和用量限制。"
        elif exc.code == 403:
            hint = "当前账户无权访问该模型，请检查服务商、模型权限和 Key 所属账户。"
        elif exc.code == 429:
            hint = "模型请求过于频繁，请稍后重试。"
        elif exc.code in {400, 404}:
            hint = "模型地址、名称或请求参数不被服务商接受，请检查系统设置。"
        elif exc.code >= 500:
            hint = "模型服务暂时异常，请稍后重试；已上传资料仍保存在本地。"
        else:
            hint = "模型服务拒绝请求，请检查模型连接设置。"
        return LLMClientUnavailable(f"{hint}（HTTP {exc.code}）")
    if isinstance(exc, TimeoutError) or isinstance(getattr(exc, "reason", None), TimeoutError):
        return LLMClientUnavailable("模型请求超时，请稍后重试或检查系统设置中的超时时间。")
    return LLMClientUnavailable("无法连接模型服务，请检查服务地址、网络或代理；已上传资料仍保存在本地。")


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
            raise request_failure(exc) from exc
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
            raise request_failure(exc) from exc
        duration_ms = max(1, int((perf_counter() - started) * 1000))
        return self._parse_response(config, prompt, raw, duration_ms)

    def generate_evidence_cards(
        self,
        config: ModelConfig,
        source: EvidenceSource,
    ) -> LLMCompletionResult:
        return self._generate_json(
            config,
            system_message=self.prompt_service.evidence_card_system_message(),
            prompt=self.prompt_service.evidence_card_user_prompt(source),
            temperature=0,
        )

    def generate_evidence_tailor(
        self,
        config: ModelConfig,
        job: JobPosting,
        cards: list[EvidenceCard],
    ) -> LLMCompletionResult:
        return self._generate_json(
            config,
            system_message=self.prompt_service.evidence_tailor_system_message(),
            prompt=self.prompt_service.evidence_tailor_user_prompt(job, cards),
            temperature=0.1,
        )

    def generate_job_greeting(self, config: ModelConfig, job: JobPosting, cards: list[EvidenceCard]) -> LLMCompletionResult:
        # No identity fields, private source text, or tool access are needed for this task.
        data = {
            "title": job.title, "company": job.company, "jd": job.description[:5000],
            "facts": [
                {"title": card.title[:120], "actions": [item[:180] for item in card.actions[:3]], "skills": card.skills[:8]}
                for card in cards[:6] if card.status == "confirmed"
                and (card.provenance_type != "document" or card.quote_verified)
            ],
        }
        return self._generate_json(config, system_message=model_skill("application.greeting"),
                                   prompt=json.dumps(data, ensure_ascii=False), temperature=0.2)

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
            raise request_failure(exc) from exc
        duration_ms = max(1, int((perf_counter() - started) * 1000))
        return self._parse_response(config, prompt, raw, duration_ms)

    def _api_key(self, config: ModelConfig) -> str:
        if not config.enabled or config.estimation_only:
            raise LLMClientUnavailable("LLM model config is disabled or estimation-only")
        if config.api_key:
            return config.api_key
        api_key = _env_value(config.api_key_env_var)
        if not api_key:
            target = config.api_key_env_var or "saved API key"
            raise LLMClientUnavailable(f"API key is not configured: {target}")
        return api_key

    def _generate_json(
        self,
        config: ModelConfig,
        *,
        system_message: str,
        prompt: str,
        temperature: float,
    ) -> LLMCompletionResult:
        api_key = self._api_key(config)
        payload = {
            "model": config.model,
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
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
            raise request_failure(exc) from exc
        duration_ms = max(1, int((perf_counter() - started) * 1000))
        return self._parse_response(config, prompt, raw, duration_ms)

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
