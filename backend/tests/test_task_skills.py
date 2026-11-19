import json
import pytest
from app.schemas import EvidenceCard, JobPosting, ModelConfig
from app.services.llm_client_service import OpenAICompatibleClient
from app.services.llm_prompt_service import LLMPromptService
from app.services.task_skills import model_skill


def test_each_existing_model_task_selects_its_own_instructions():
    prompts = LLMPromptService()
    assert prompts.job_match_system_message() == model_skill("job.match")
    assert prompts.application_writer_system_message() == model_skill("application.materials.generate")
    assert prompts.evidence_tailor_system_message() == model_skill("application.materials.evidence")
    assert prompts.evidence_card_system_message() == model_skill("evidence.extract")
    with pytest.raises(ValueError, match="本地任务"):
        model_skill("application.apply.platform")


def test_greeting_model_gets_one_jd_and_only_confirmed_minimal_facts(monkeypatch):
    client = OpenAICompatibleClient()
    monkeypatch.setattr(client, "_generate_json", lambda _config, **payload: payload)
    job = JobPosting(platform="boss", company="松果", title="产品岗位", city="上海", salary="未知",
                     url="https://example.invalid/job", description="进行用户调研")
    verified = EvidenceCard(title="调研项目", status="confirmed", provenance_type="user_statement",
                            actions=["设计访谈"], user_note="不发送私密备注")
    draft = EvidenceCard(title="不发送草稿", status="draft")
    payload = client.generate_job_greeting(ModelConfig(), job, [verified, draft])
    assert payload["system_message"] == model_skill("application.greeting")
    assert json.loads(payload["prompt"])["jd"] == "进行用户调研"
    assert "设计访谈" in payload["prompt"]
    assert "私密备注" not in payload["prompt"] and "不发送草稿" not in payload["prompt"]
