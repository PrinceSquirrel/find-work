import json

from app.schemas import JobMatch, JobPosting, ModelConfig, ResumeDraft
from app.services import llm_client_service
from app.services.llm_client_service import OpenAICompatibleClient
from app.services.llm_prompt_service import LLMPromptService


def sample_resume() -> ResumeDraft:
    return ResumeDraft(
        id=1,
        filename="resume.docx",
        raw_text="胡俊\n电话: 15800000000\n教育经历: 吉林大学\n技能: Python, SQL\n项目: 数据看板",
    )


def sample_job() -> JobPosting:
    return JobPosting(
        id=7,
        platform="boss",
        company="启明数据",
        title="Agent 实习生",
        city="上海",
        salary="200-300/天",
        description="需要 Python、SQL、Agent 工具和数据分析经验。",
        url="https://example.test/job/7",
    )


def sample_model_config() -> ModelConfig:
    return ModelConfig(
        provider="openai-compatible",
        model="deepseek-v4-pro",
        base_url="https://api.deepseek.com",
        api_key_env_var="AGENT_BUSINESS_TEST_API_KEY",
        api_key_configured=True,
        enabled=True,
        estimation_only=False,
        timeout_ms=30000,
    )


def test_application_writer_prompt_locks_identity_and_rewrites_resume_body():
    service = LLMPromptService()
    prompt = service.application_writer_user_prompt(sample_resume(), sample_job())
    system_message = service.application_writer_system_message()

    assert "不得新增不存在的学校、公司、项目、技能或经历" in system_message
    assert "resume_rewrite" in prompt
    assert "greeting_message" in prompt
    assert "锁定身份信息和教育经历" in prompt
    assert "技能、项目、实习、经历描述、自我评价、摘要等简历正文" in prompt
    assert "只输出可替换正文" in prompt
    assert "Agent 实习生" in prompt
    assert "需要 Python、SQL、Agent 工具和数据分析经验" in prompt


def test_job_match_prompt_is_scoring_only_and_includes_rule_context():
    service = LLMPromptService()
    prompt = service.job_match_user_prompt(
        sample_resume(),
        [sample_job()],
        [JobMatch(job_id=7, score=65, hit_reasons=["Python"], gap_reasons=["Agent"], recommendation="review")],
    )
    system_message = service.job_match_system_message()

    assert "岗位匹配评分器" in system_message
    assert "不要改写简历" in system_message
    assert "不要生成求职材料" in system_message
    assert "matches" in prompt
    assert "job_index" in prompt
    assert "rule_score" in prompt
    assert "recommendation" in prompt


def test_openai_client_uses_injected_prompt_service_for_application_writer(monkeypatch):
    captured_payload = {}

    class FakePromptService:
        def application_writer_system_message(self):
            return "SYSTEM-WRITER"

        def application_writer_user_prompt(self, resume, job):
            assert resume.id == 1
            assert job.id == 7
            return "USER-WRITER"

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def read(self):
            return b'{"choices":[{"message":{"content":"{}"}}],"usage":{"prompt_tokens":2,"completion_tokens":3}}'

    def fake_urlopen(request, timeout):
        captured_payload.update(json.loads(request.data.decode("utf-8")))
        return FakeResponse()

    monkeypatch.setenv("AGENT_BUSINESS_TEST_API_KEY", "secret")
    monkeypatch.setattr(llm_client_service, "urlopen", fake_urlopen)

    OpenAICompatibleClient(prompt_service=FakePromptService()).generate_application_materials(
        sample_model_config(),
        sample_resume(),
        sample_job(),
    )

    assert captured_payload["messages"] == [
        {"role": "system", "content": "SYSTEM-WRITER"},
        {"role": "user", "content": "USER-WRITER"},
    ]
