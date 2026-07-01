import json
from datetime import UTC, datetime

import pytest

from app.agents.application_tracker import ApplicationTrackerAgent, InvalidStatusTransition
from app.agents.application_writer import ApplicationWriterAgent
from app.agents.greeting import GreetingAgent
from app.agents.job_match import JobMatchAgent
from app.agents.metrics import MetricsAgent, ModelPricing
from app.agents.resume_parser import ResumeParserAgent
from app.agents.resume_tailor import ResumeTailorAgent
from app.agents.review import ReviewAgent
from app.schemas import ApplicationStatus, GreetingMessage, JobPosting, ResumeDraft, TailoredResume
from app.services.llm_client_service import OpenAICompatibleClient


def sample_resume() -> ResumeDraft:
    return ResumeDraft(
        id=1,
        filename="resume.txt",
        raw_text=(
            "张三\n"
            "教育经历: 上海交通大学 软件工程 本科\n"
            "技能: Python, FastAPI, React, SQL, 数据分析\n"
            "项目: 企业知识库 Agent，负责 RAG 检索、API 后端和前端看板。\n"
            "实习: 数据分析实习生，使用 SQL 和 Python 完成业务报表。"
        ),
        profile={
            "skills": ["Python", "FastAPI", "React", "SQL", "数据分析"],
            "projects": ["企业知识库 Agent"],
        },
        created_at=datetime.now(UTC),
    )


def sample_job(**overrides) -> JobPosting:
    data = {
        "id": 10,
        "platform": "boss",
        "company": "量化未来科技",
        "title": "Python 后端实习生",
        "city": "上海",
        "salary": "200-300/天",
        "description": "需要 Python、FastAPI、SQL，参与 AI Agent 后台和数据看板建设。",
        "url": "https://example.test/jobs/10",
        "job_type": "backend",
        "created_at": datetime.now(UTC),
    }
    data.update(overrides)
    return JobPosting(**data)


def test_resume_parser_agent_extracts_plain_text_and_known_skills_locally():
    agent = ResumeParserAgent()
    content = (
        "王五\n"
        "技能: Python, FastAPI, SQL, 数据分析\n"
        "城市: 上海\n"
        "项目: Agent 求职工作台，负责 API 和看板。"
    ).encode("utf-8")

    resume = agent.parse("resume.txt", content)

    assert resume.raw_text.startswith("王五")
    assert resume.profile["text_length"] == len(resume.raw_text)
    assert {"Python", "FastAPI", "SQL", "Agent", "API", "数据分析", "看板"}.issubset(
        set(resume.profile["skills"])
    )
    assert resume.profile["suggested_keywords"] == ["Python 实习", "FastAPI 实习", "SQL 实习", "数据分析 实习"]
    assert resume.profile["suggested_city"] == "上海"


def test_job_match_agent_scores_relevant_jobs_higher_than_irrelevant_jobs():
    agent = JobMatchAgent()
    resume = sample_resume()
    relevant = sample_job()
    irrelevant = sample_job(
        id=11,
        title="视觉设计实习生",
        description="需要品牌视觉、海报排版、C4D、摄影和线下物料制作经验。",
        job_type="design",
    )

    relevant_match = agent.match(resume, relevant)
    irrelevant_match = agent.match(resume, irrelevant)

    assert relevant_match.score >= 80
    assert "Python" in relevant_match.hit_reasons
    assert relevant_match.recommendation == "strong_apply"
    assert irrelevant_match.score < relevant_match.score
    assert irrelevant_match.recommendation in {"skip", "review"}


def test_resume_tailor_agent_does_not_fabricate_missing_skills():
    agent = ResumeTailorAgent()
    resume = sample_resume()
    job = sample_job(
        id=12,
        title="云原生后端实习生",
        description="需要 Python、Kubernetes、微服务、Prometheus，有云原生项目经验优先。",
    )

    tailored = agent.tailor(resume, job)

    assert tailored.resume_rewrite
    assert tailored.project_rewrite
    assert tailored.project_rewrite == tailored.resume_rewrite
    assert "教育经历" not in tailored.resume_rewrite
    assert "上海交通大学" not in tailored.resume_rewrite
    assert "Kubernetes" not in tailored.resume_text
    assert "Prometheus" not in tailored.resume_text
    assert "Kubernetes" in tailored.risk_flags
    assert tailored.truth_check_passed is True


def test_greeting_agent_mentions_supported_strengths_without_adding_missing_requirements():
    agent = GreetingAgent()
    resume = ResumeDraft(
        id=2,
        filename="resume.txt",
        raw_text="技能: Python, SQL。项目: 数据分析报表。",
        profile={"skills": ["Python", "SQL", "数据分析"]},
        created_at=datetime.now(UTC),
    )
    job = sample_job(
        id=13,
        title="后端实习生",
        description="需要 Python、Kubernetes、Prometheus，参与服务稳定性建设。",
    )

    greeting = agent.generate(resume, job)

    assert "Python" in greeting.message
    assert "Kubernetes" not in greeting.message
    assert "Prometheus" not in greeting.message
    assert greeting.tone == "professional"


def test_application_writer_agent_combines_resume_and_greeting_generation():
    writer = ApplicationWriterAgent()
    resume = sample_resume()
    job = sample_job(
        id=15,
        title="Python Agent 实习生",
        description="需要 Python、FastAPI、Agent，不需要虚构 Kubernetes 经历。",
    )

    bundle = writer.write(resume, job)

    assert bundle.tailored_resume.job_id == job.id
    assert bundle.greeting.job_id == job.id
    assert "Kubernetes" not in bundle.tailored_resume.resume_text
    assert "Kubernetes" in bundle.tailored_resume.risk_flags
    assert bundle.greeting.message


def test_application_writer_prefers_resume_rewrite_from_llm_json():
    writer = ApplicationWriterAgent()
    resume = sample_resume()
    job = sample_job(id=16, title="数据分析实习生", description="需要 Python、SQL、数据分析。")
    content = json.dumps(
        {
            "resume_rewrite": "简历改写要求: 突出 Python、SQL 和数据分析经历。",
            "greeting_message": "您好，我对数据分析实习岗位很感兴趣。",
            "diff_summary": ["突出数据分析经历"],
            "resume_risk_flags": [],
            "greeting_risk_flags": [],
            "tone": "professional",
        },
        ensure_ascii=False,
    )

    bundle = writer.write_from_llm_json(resume, job, content)

    assert bundle.tailored_resume.resume_rewrite == "简历改写要求: 突出 Python、SQL 和数据分析经历。"
    assert bundle.tailored_resume.project_rewrite == bundle.tailored_resume.resume_rewrite
    assert bundle.tailored_resume.resume_text == bundle.tailored_resume.resume_rewrite


def test_llm_prompt_locks_identity_and_education_while_rewriting_resume_body():
    prompt = OpenAICompatibleClient()._prompt(
        sample_resume(),
        sample_job(id=17, title="Agent 实习生", description="需要 Python、Agent、数据分析。"),
    )

    assert "resume_rewrite" in prompt
    assert "锁定" in prompt
    assert "身份信息" in prompt
    assert "教育经历" in prompt
    assert "技能、项目、实习、经历描述、自我评价、摘要" in prompt


def test_review_agent_blocks_tailored_resume_when_missing_requirement_was_added():
    resume = sample_resume()
    job = sample_job(
        id=14,
        title="云原生后端实习生",
        description="需要 Python、Kubernetes，有云原生项目经验优先。",
    )
    tailored = TailoredResume(
        job_id=job.id or 0,
        resume_id=resume.id or 0,
        resume_text=f"{resume.raw_text}\n补充: 熟悉 Kubernetes 集群运维。",
        resume_rewrite="简历改写要求: 补充 Kubernetes 集群运维。",
        diff_summary=["错误新增未在原简历出现的技能"],
        risk_flags=["Kubernetes"],
        truth_check_passed=True,
    )
    greeting = GreetingMessage(job_id=job.id or 0, message="您好，我想投递该岗位。")

    review = ReviewAgent().review(resume, job, tailored, greeting)

    assert review["truth_check_passed"] is False
    assert review["risk_flags"] == ["Kubernetes"]


def test_application_tracker_rejects_illegal_status_jump():
    tracker = ApplicationTrackerAgent()
    record = tracker.create_record(
        job_id=10,
        company="量化未来科技",
        title="Python 后端实习生",
        platform="boss",
        applied_at=datetime(2026, 6, 29, 9, 30, tzinfo=UTC),
    )

    with pytest.raises(InvalidStatusTransition):
        tracker.transition(record, ApplicationStatus.REPLIED, note="不能跳过已读直接回复")

    tracker.transition(record, ApplicationStatus.READ, note="招聘方已读")
    tracker.transition(record, ApplicationStatus.REPLIED, note="招聘方回复")

    assert record.current_status == ApplicationStatus.REPLIED
    assert [event.status for event in record.events] == [
        ApplicationStatus.APPLIED,
        ApplicationStatus.READ,
        ApplicationStatus.REPLIED,
    ]


def test_metrics_agent_calculates_cost_from_token_usage():
    metrics = MetricsAgent(
        pricing={
            "deepseek-chat": ModelPricing(input_per_million=1.0, output_per_million=2.0)
        }
    )

    entry = metrics.record_llm_usage(
        agent_name="JobMatchAgent",
        provider="deepseek",
        model="deepseek-chat",
        prompt_tokens=1000,
        completion_tokens=500,
        duration_ms=320,
        estimated=False,
    )

    assert entry.total_tokens == 1500
    assert entry.cost_usd == pytest.approx(0.002)
    assert metrics.summary().total_cost_usd == pytest.approx(0.002)


def test_metrics_agent_estimates_local_usage_without_external_llm_api():
    metrics = MetricsAgent()

    entry = metrics.estimate_and_record(
        agent_name="GreetingAgent",
        prompt="基于简历和岗位生成招呼语",
        completion="您好，我对该岗位很感兴趣。",
    )
    summary = metrics.summary()

    assert entry.provider == "local"
    assert entry.model == "local-estimator"
    assert entry.estimated is True
    assert entry.prompt_tokens >= 1
    assert entry.completion_tokens >= 1
    assert summary.by_agent["GreetingAgent"]["calls"] == 1
