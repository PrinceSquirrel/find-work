from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class AgentEvent:
    id: int
    agent_name: str
    status: str
    step: str
    input_summary: str
    output_summary: str = ""
    error: str = ""
    total_tokens: int = 0
    cost_usd: float = 0.0
    created_at: datetime | None = None


class EventStreamService:
    def __init__(self, max_events: int = 200):
        self.max_events = max_events
        self._next_id = 1
        self._events: list[AgentEvent] = []

    def record(
        self,
        agent_name: str,
        status: str,
        step: str,
        input_summary: str = "",
        output_summary: str = "",
        error: str = "",
        total_tokens: int = 0,
        cost_usd: float = 0.0,
    ) -> AgentEvent:
        event = AgentEvent(
            id=self._next_id,
            agent_name=agent_name,
            status=status,
            step=step,
            input_summary=input_summary[:500],
            output_summary=output_summary[:500],
            error=error[:500],
            total_tokens=total_tokens,
            cost_usd=round(cost_usd, 8),
            created_at=datetime.now(UTC),
        )
        self._next_id += 1
        self._events.append(event)
        self._events = self._events[-self.max_events :]
        return event

    def snapshot(self, total_cost_usd: float = 0.0) -> dict[str, object]:
        latest_by_agent: dict[str, AgentEvent] = {}
        for event in self._events:
            latest_by_agent[event.agent_name] = event
        current_running = next(
            (event.agent_name for event in reversed(self._events) if latest_by_agent[event.agent_name].status == "running"),
            None,
        )
        return {
            "current_running_agent": current_running,
            "total_cost_usd": round(total_cost_usd, 8),
            "agents": [self._event_payload(event) for event in latest_by_agent.values()],
            "events": [self._event_payload(event) for event in self._events],
        }

    def _event_payload(self, event: AgentEvent) -> dict[str, object]:
        payload = asdict(event)
        payload["created_at"] = event.created_at.isoformat() if event.created_at else None
        return payload
