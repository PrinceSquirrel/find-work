from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.services.event_stream_service import AgentEvent, EventStreamService


@dataclass
class OrchestratorStep:
    event_id: int
    agent_name: str
    status: str
    step: str
    input_summary: str = ""
    output_summary: str = ""
    error: str = ""
    total_tokens: int = 0
    cost_usd: float = 0.0


@dataclass
class OrchestratorTask:
    id: int
    task_name: str
    input_summary: str = ""
    status: str = "running"
    error: str = ""
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    steps: list[OrchestratorStep] = field(default_factory=list)


class OrchestratorService:
    def __init__(self, event_stream: EventStreamService, store: Any | None = None, max_tasks: int = 50):
        self.event_stream = event_stream
        self.store = store if self._supports_persistence(store) else None
        self.max_tasks = max_tasks
        self._tasks = self._load_tasks()
        self._next_task_id = max((task.id for task in self._tasks), default=0) + 1

    def start_task(self, task_name: str, input_summary: str = "") -> int:
        task = OrchestratorTask(
            id=self._next_task_id,
            task_name=task_name,
            input_summary=input_summary[:500],
        )
        if self.store is not None:
            task.id = self.store.create_orchestrator_task(
                task.task_name,
                task.input_summary,
                task.status,
                task.error,
                task.started_at,
                task.completed_at,
            )
        self._next_task_id = max(self._next_task_id + 1, task.id + 1)
        self._tasks.append(task)
        self._tasks = self._tasks[-self.max_tasks :]
        return task.id

    def record_step(
        self,
        task_id: int | None,
        agent_name: str,
        status: str,
        step: str,
        input_summary: str = "",
        output_summary: str = "",
        error: str = "",
        total_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> AgentEvent:
        event = self.event_stream.record(
            agent_name=agent_name,
            status=status,
            step=step,
            input_summary=input_summary,
            output_summary=output_summary,
            error=error,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
        )
        task = self._find_task(task_id)
        if task is not None:
            step_record = OrchestratorStep(
                event_id=event.id,
                agent_name=event.agent_name,
                status=event.status,
                step=event.step,
                input_summary=event.input_summary,
                output_summary=event.output_summary,
                error=event.error,
                total_tokens=event.total_tokens,
                cost_usd=event.cost_usd,
            )
            task.steps.append(step_record)
            if self.store is not None and event.created_at is not None:
                self.store.save_orchestrator_step(
                    task.id,
                    event.id,
                    event.agent_name,
                    event.status,
                    event.step,
                    event.input_summary,
                    event.output_summary,
                    event.error,
                    event.total_tokens,
                    event.cost_usd,
                    event.created_at,
                )
        return event

    def finish_task(self, task_id: int | None, status: str = "success", error: str = "") -> None:
        task = self._find_task(task_id)
        if task is None:
            return
        task.status = status
        task.error = error[:500]
        task.completed_at = datetime.now(UTC)
        if self.store is not None:
            self.store.update_orchestrator_task(task.id, task.status, task.error, task.completed_at)

    def snapshot(self) -> dict[str, object]:
        current_task = next((task for task in reversed(self._tasks) if task.status == "running"), None)
        last_task = self._tasks[-1] if self._tasks else None
        return {
            "current_task_id": current_task.id if current_task else None,
            "last_task": self._task_payload(last_task) if last_task else None,
            "tasks": [self._task_payload(task) for task in self._tasks],
        }

    def get_task(self, task_id: int) -> dict[str, object]:
        task = self._find_task(task_id)
        if task is None:
            raise KeyError(f"Orchestrator task {task_id} not found")
        return self._task_payload(task)

    def _find_task(self, task_id: int | None) -> OrchestratorTask | None:
        if task_id is None:
            return None
        return next((task for task in reversed(self._tasks) if task.id == task_id), None)

    def _supports_persistence(self, store: Any | None) -> bool:
        return store is not None and all(
            hasattr(store, method_name)
            for method_name in (
                "create_orchestrator_task",
                "update_orchestrator_task",
                "save_orchestrator_step",
                "list_orchestrator_tasks",
            )
        )

    def _load_tasks(self) -> list[OrchestratorTask]:
        if self.store is None:
            return []
        return [self._task_from_payload(task) for task in self.store.list_orchestrator_tasks(self.max_tasks)]

    def _task_from_payload(self, payload: dict[str, Any]) -> OrchestratorTask:
        return OrchestratorTask(
            id=payload["id"],
            task_name=payload["task_name"],
            input_summary=payload["input_summary"],
            status=payload["status"],
            error=payload["error"],
            started_at=datetime.fromisoformat(payload["started_at"]),
            completed_at=datetime.fromisoformat(payload["completed_at"]) if payload["completed_at"] else None,
            steps=[self._step_from_payload(step) for step in payload["steps"]],
        )

    def _step_from_payload(self, payload: dict[str, Any]) -> OrchestratorStep:
        return OrchestratorStep(
            event_id=payload["event_id"],
            agent_name=payload["agent_name"],
            status=payload["status"],
            step=payload["step"],
            input_summary=payload["input_summary"],
            output_summary=payload["output_summary"],
            error=payload["error"],
            total_tokens=payload["total_tokens"],
            cost_usd=payload["cost_usd"],
        )

    def _task_payload(self, task: OrchestratorTask) -> dict[str, object]:
        payload = asdict(task)
        payload["started_at"] = task.started_at.isoformat()
        payload["completed_at"] = task.completed_at.isoformat() if task.completed_at else None
        payload["retry_suggestion"] = self._retry_suggestion(task)
        return payload

    def _retry_suggestion(self, task: OrchestratorTask) -> dict[str, object]:
        safety_boundary = "系统不会自动投递、不会自动发送招呼语、不会绕过验证码；请人工确认后重新触发原操作。"
        if task.status == "success":
            return {
                "mode": "not_needed",
                "retryable": False,
                "automatic_retry_allowed": False,
                "reason": "任务已成功，无需重试。",
                "next_action": "无需操作；如需刷新结果，请从对应页面入口重新发起。",
                "safety_boundary": safety_boundary,
            }
        if task.status == "running":
            return {
                "mode": "not_available",
                "retryable": False,
                "automatic_retry_allowed": False,
                "reason": "任务仍在运行，暂不提供重试建议。",
                "next_action": "等待当前任务结束后再查看结果。",
                "safety_boundary": safety_boundary,
            }

        reason = task.error or self._last_step_error(task) or "任务失败，未记录更详细错误。"
        return {
            "mode": "manual_only",
            "retryable": True,
            "automatic_retry_allowed": False,
            "reason": reason,
            "next_action": self._manual_retry_action(task),
            "safety_boundary": safety_boundary,
        }

    def _manual_retry_action(self, task: OrchestratorTask) -> str:
        error_text = f"{task.task_name} {task.error} {self._last_step_error(task)}".lower()
        if task.task_name == "job.search" or "cdp" in error_text or "browser" in error_text:
            return "确认已启动 CDP 浏览器、已登录 BOSS/实习僧，并检查关键词和城市后，手动重新点击创建搜索任务。"
        if task.task_name == "application.materials" or "llm" in error_text or "api" in error_text:
            return "检查模型/API 配置和当前岗位信息后，手动重新点击生成材料。"
        if task.task_name == "resume.parse":
            return "检查简历文件格式和内容是否可读后，手动重新上传简历。"
        return "查看错误信息后，从对应页面入口手动重新触发该操作。"

    def _last_step_error(self, task: OrchestratorTask) -> str:
        for step in reversed(task.steps):
            if step.error:
                return step.error
        return ""
