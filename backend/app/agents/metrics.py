from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.schemas import LLMUsageEntry, LLMUsageSummary


@dataclass(frozen=True)
class ModelPricing:
    input_per_million: float
    output_per_million: float


class MetricsAgent:
    def __init__(self, pricing: dict[str, ModelPricing] | None = None):
        self.pricing = pricing or {
            "local-estimator": ModelPricing(input_per_million=0.20, output_per_million=0.40),
            "deepseek-chat": ModelPricing(input_per_million=1.00, output_per_million=2.00),
        }
        self.entries: list[LLMUsageEntry] = []

    def record_llm_usage(
        self,
        agent_name: str,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        duration_ms: int,
        estimated: bool,
    ) -> LLMUsageEntry:
        pricing = self.pricing.get(model, ModelPricing(input_per_million=0.0, output_per_million=0.0))
        cost = (prompt_tokens / 1_000_000) * pricing.input_per_million
        cost += (completion_tokens / 1_000_000) * pricing.output_per_million
        entry = LLMUsageEntry(
            agent_name=agent_name,
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cost_usd=round(cost, 8),
            duration_ms=duration_ms,
            estimated=estimated,
            created_at=datetime.now(UTC),
        )
        self.entries.append(entry)
        return entry

    def estimate_and_record(self, agent_name: str, prompt: str, completion: str) -> LLMUsageEntry:
        prompt_tokens = max(1, len(prompt) // 4)
        completion_tokens = max(1, len(completion) // 4)
        return self.record_llm_usage(
            agent_name=agent_name,
            provider="local",
            model="local-estimator",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            duration_ms=10,
            estimated=True,
        )

    def summary(self) -> LLMUsageSummary:
        by_agent: dict[str, dict[str, float | int]] = {}
        for entry in self.entries:
            agent_bucket = by_agent.setdefault(
                entry.agent_name,
                {"total_tokens": 0, "total_cost_usd": 0.0, "calls": 0},
            )
            agent_bucket["total_tokens"] += entry.total_tokens
            agent_bucket["total_cost_usd"] += entry.cost_usd
            agent_bucket["calls"] += 1

        return LLMUsageSummary(
            total_prompt_tokens=sum(entry.prompt_tokens for entry in self.entries),
            total_completion_tokens=sum(entry.completion_tokens for entry in self.entries),
            total_tokens=sum(entry.total_tokens for entry in self.entries),
            total_cost_usd=round(sum(entry.cost_usd for entry in self.entries), 8),
            by_agent=by_agent,
        )
