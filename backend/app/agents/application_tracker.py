from __future__ import annotations

from datetime import UTC, datetime

from app.schemas import ApplicationEvent, ApplicationRecord, ApplicationStatus


class InvalidStatusTransition(ValueError):
    """Raised when an application moves through an impossible progress step."""


ALLOWED_TRANSITIONS: dict[ApplicationStatus, set[ApplicationStatus]] = {
    ApplicationStatus.APPLIED: {
        ApplicationStatus.READ,
        ApplicationStatus.REJECTED,
        ApplicationStatus.CLOSED,
    },
    ApplicationStatus.READ: {
        ApplicationStatus.REPLIED,
        ApplicationStatus.REJECTED,
        ApplicationStatus.CLOSED,
    },
    ApplicationStatus.REPLIED: {
        ApplicationStatus.INTERVIEW,
        ApplicationStatus.ASSESSMENT,
        ApplicationStatus.REJECTED,
        ApplicationStatus.CLOSED,
    },
    ApplicationStatus.INTERVIEW: {
        ApplicationStatus.ASSESSMENT,
        ApplicationStatus.REJECTED,
        ApplicationStatus.CLOSED,
    },
    ApplicationStatus.ASSESSMENT: {
        ApplicationStatus.INTERVIEW,
        ApplicationStatus.REJECTED,
        ApplicationStatus.CLOSED,
    },
    ApplicationStatus.REJECTED: {ApplicationStatus.CLOSED},
    ApplicationStatus.CLOSED: set(),
}

STATUS_STAGE_LABELS = {
    ApplicationStatus.APPLIED: "已投递",
    ApplicationStatus.READ: "已读",
    ApplicationStatus.REPLIED: "已回复",
    ApplicationStatus.INTERVIEW: "面试中",
    ApplicationStatus.ASSESSMENT: "笔试/测评",
    ApplicationStatus.REJECTED: "已拒绝",
    ApplicationStatus.CLOSED: "已结束",
}


def assert_transition(current: ApplicationStatus, next_status: ApplicationStatus) -> None:
    if next_status == current:
        return
    if next_status not in ALLOWED_TRANSITIONS.get(current, set()):
        raise InvalidStatusTransition(f"Cannot transition application from {current} to {next_status}")


class ApplicationTrackerAgent:
    def create_record(
        self,
        job_id: int,
        company: str,
        title: str,
        platform: str,
        applied_at: datetime | None = None,
        note: str = "",
    ) -> ApplicationRecord:
        applied_time = applied_at or datetime.now(UTC)
        event = ApplicationEvent(status=ApplicationStatus.APPLIED, occurred_at=applied_time, note=note)
        return ApplicationRecord(
            job_id=job_id,
            company=company,
            title=title,
            platform=platform,
            applied_at=applied_time,
            current_status=ApplicationStatus.APPLIED,
            progress_stage=STATUS_STAGE_LABELS[ApplicationStatus.APPLIED],
            latest_note=note,
            events=[event],
        )

    def transition(
        self,
        record: ApplicationRecord,
        next_status: ApplicationStatus,
        note: str = "",
        occurred_at: datetime | None = None,
    ) -> ApplicationRecord:
        assert_transition(record.current_status, next_status)
        event_time = occurred_at or datetime.now(UTC)
        record.current_status = next_status
        record.progress_stage = STATUS_STAGE_LABELS[next_status]
        record.latest_note = note
        if next_status == ApplicationStatus.READ and record.read_at is None:
            record.read_at = event_time
        if next_status == ApplicationStatus.REPLIED and record.replied_at is None:
            record.replied_at = event_time
        record.events.append(ApplicationEvent(status=next_status, occurred_at=event_time, note=note))
        return record
