from datetime import UTC, datetime

from app.schemas import ApplicationEvent, ApplicationRecord, ApplicationStatus
from app.services import JobApplicationService


class StubStore:
    def __init__(self, records: list[ApplicationRecord]):
        self.records = records

    def list_applications(self) -> list[ApplicationRecord]:
        return self.records


def application_record(
    *,
    record_id: int,
    status: ApplicationStatus,
    platform: str,
    applied_at: datetime,
    read_at: datetime | None = None,
    replied_at: datetime | None = None,
) -> ApplicationRecord:
    events = [
        ApplicationEvent(
            application_id=record_id,
            status=ApplicationStatus.APPLIED,
            occurred_at=applied_at,
            note="用户确认投递",
        )
    ]
    if read_at is not None:
        events.append(
            ApplicationEvent(
                application_id=record_id,
                status=ApplicationStatus.READ,
                occurred_at=read_at,
                note="招聘方已读",
            )
        )
    if replied_at is not None:
        events.append(
            ApplicationEvent(
                application_id=record_id,
                status=ApplicationStatus.REPLIED,
                occurred_at=replied_at,
                note="招聘方回复",
            )
        )
    if status not in {ApplicationStatus.APPLIED, ApplicationStatus.READ, ApplicationStatus.REPLIED}:
        events.append(
            ApplicationEvent(
                application_id=record_id,
                status=status,
                occurred_at=replied_at or read_at or applied_at,
                note="进入后续状态",
            )
        )

    return ApplicationRecord(
        id=record_id,
        job_id=record_id,
        company=f"公司 {record_id}",
        title="Python 后端实习生",
        platform=platform,
        applied_at=applied_at,
        current_status=status,
        read_at=read_at,
        replied_at=replied_at,
        events=events,
    )


def test_application_analytics_defines_rates_and_visualization_buckets():
    records = [
        application_record(
            record_id=1,
            status=ApplicationStatus.INTERVIEW,
            platform="boss",
            applied_at=datetime(2026, 6, 29, 9, 30, tzinfo=UTC),
            read_at=datetime(2026, 6, 29, 10, 0, tzinfo=UTC),
            replied_at=datetime(2026, 6, 29, 11, 0, tzinfo=UTC),
        ),
        application_record(
            record_id=2,
            status=ApplicationStatus.REJECTED,
            platform="shixiseng",
            applied_at=datetime(2026, 6, 30, 15, 45, tzinfo=UTC),
        ),
    ]
    service = JobApplicationService(StubStore(records))

    analytics = service.application_analytics()

    assert analytics["totals"] == {
        "applications": 2,
        "read": 1,
        "replied": 1,
        "progressed": 1,
        "read_rate": 0.5,
        "reply_rate": 0.5,
        "progress_rate": 0.5,
    }
    assert set(analytics["hourly"]) == {"09:00", "15:00"}
    assert analytics["hourly"]["09:00"]["progressed"] == 1
    assert analytics["hourly"]["15:00"]["read"] == 0
    assert set(analytics["weekday"]) == {"Monday", "Tuesday"}
    assert set(analytics["platform"]) == {"boss", "shixiseng"}
    assert analytics["platform"]["boss"]["reply_rate"] == 1.0
    assert analytics["platform"]["shixiseng"]["reply_rate"] == 0
