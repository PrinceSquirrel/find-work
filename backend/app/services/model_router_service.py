from __future__ import annotations

from dataclasses import dataclass

from app.schemas import ModelConfig


@dataclass(frozen=True)
class ModelRoute:
    agent_name: str
    mode: str
    provider: str
    model: str
    reason: str


class ModelRouterService:
    def route_for_agent(self, agent_name: str, config: ModelConfig) -> ModelRoute:
        if agent_name in {"ApplicationWriterAgent", "JobMatchAgent"}:
            if config.enabled and not config.estimation_only and config.api_key_configured:
                return ModelRoute(
                    agent_name=agent_name,
                    mode="external",
                    provider=config.provider,
                    model=config.model,
                    reason=f"{agent_name} uses its enabled model route.",
                )
            return ModelRoute(
                agent_name=agent_name,
                mode="local_estimate",
                provider="local",
                model="local-estimator",
                reason="Model config is disabled, estimation-only, or missing API key.",
            )
        if agent_name == "ReviewAgent":
            if config.enabled and not config.estimation_only and config.api_key_configured:
                return ModelRoute(
                    agent_name=agent_name,
                    mode="local_rule",
                    provider=config.provider,
                    model=config.model,
                    reason="ReviewAgent route is configured; deterministic fact review still runs locally.",
                )
            return ModelRoute(
                agent_name=agent_name,
                mode="local_rule",
                provider="local",
                model="local-rule",
                reason="ReviewAgent stays on deterministic local rules because its route is disabled or missing API key.",
            )
        return ModelRoute(
            agent_name=agent_name,
            mode="local_estimate",
            provider="local",
            model="local-estimator",
            reason="No external model route is configured for this agent.",
        )
