from __future__ import annotations

from dataclasses import dataclass

from app.services.model_router_service import ModelRoute


@dataclass(frozen=True)
class OrchestratorPlan:
    agents: list[str]
    requires_confirmation: list[str]
    safety_boundaries: list[str]

    def to_output_summary(self, route: ModelRoute) -> str:
        return (
            f"route={route.mode}; provider={route.provider}; model={route.model}; "
            f"plan={' -> '.join(self.agents)}; "
            f"requires_confirmation={','.join(self.requires_confirmation)}; "
            f"safety={','.join(self.safety_boundaries)}"
        )


class OrchestratorPlannerService:
    """Builds bounded workflow plans without granting the model direct tool execution."""

    SAFETY_BOUNDARIES = ["no_auto_apply", "no_captcha_bypass", "no_secret_logging"]

    def plan_for_task(self, task_name: str, input_summary: str) -> OrchestratorPlan:
        agents = self._agents_for_task(task_name)
        confirmations = self._confirmations_for_task(task_name, input_summary)
        return OrchestratorPlan(
            agents=agents,
            requires_confirmation=confirmations,
            safety_boundaries=self.SAFETY_BOUNDARIES,
        )

    def _agents_for_task(self, task_name: str) -> list[str]:
        plans = {
            "resume.parse": ["ResumeParserAgent"],
            "job.search": ["JobSearchAgent", "JobMatchAgent"],
            "job.detail.refresh": ["JobSearchAgent", "JobMatchAgent"],
            "job.detail.manual_update": ["JobSearchAgent", "JobMatchAgent"],
            "application.materials": ["ApplicationWriterAgent", "ReviewAgent"],
        }
        return plans.get(task_name, ["OrchestratorAgent"])

    def _confirmations_for_task(self, task_name: str, input_summary: str) -> list[str]:
        confirmations: list[str] = []
        if "browser_cdp" in input_summary or task_name.startswith("job."):
            confirmations.append("logged_in_browser_session")
        if task_name == "application.materials":
            confirmations.extend(["platform_apply", "platform_message"])
        return confirmations or ["none"]
