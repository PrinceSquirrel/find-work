from app.schemas import EvidenceCard, EvidenceSource, JobPosting
from app.services.llm_prompt_service import LLMPromptService
from app.storage import SQLiteStore


def test_evidence_source_and_card_round_trip(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "evidence-contracts.db")
    source = store.create_evidence_source(
        EvidenceSource(
            filename="project.md",
            file_type="md",
            raw_text="负责求职 Agent 项目，并完成自动化测试。",
            extraction_status="success",
            extraction_method="plain_text",
            extraction_confidence=1.0,
        ),
        b"project source",
    )
    card = store.create_evidence_card(
        EvidenceCard(
            source_id=source.id,
            category="project",
            title="求职 Agent 项目",
            actions=["完成自动化测试"],
            source_quote="负责求职 Agent 项目，并完成自动化测试。",
            quote_verified=True,
        )
    )

    stored_source = store.get_evidence_source(source.id or 0)
    stored_card = store.get_evidence_card(card.id or 0)

    assert stored_source.raw_text == "负责求职 Agent 项目，并完成自动化测试。"
    assert stored_card.source_id == stored_source.id
    assert stored_card.actions == ["完成自动化测试"]
    assert stored_card.quote_verified is True


def test_evidence_prompts_keep_document_untrusted_and_reference_card_ids() -> None:
    prompt_service = LLMPromptService()
    source = EvidenceSource(filename="resume.txt", file_type="txt", raw_text="实际负责接口测试。")
    card = EvidenceCard(id=17, title="接口测试", status="confirmed", actions=["编写回归测试"])
    job = JobPosting(
        id=9,
        platform="demo",
        company="松鼠科技",
        title="测试开发工程师",
        city="远程",
        salary="面议",
        description="负责接口和自动化测试",
        url="https://example.invalid/job/9",
    )

    extraction_prompt = prompt_service.evidence_card_user_prompt(source)
    tailor_prompt = prompt_service.evidence_tailor_user_prompt(job, [card])

    assert "<untrusted_document>" in extraction_prompt
    assert "实际负责接口测试。" in extraction_prompt
    assert '"id": 17' in tailor_prompt
    assert "测试开发工程师" in tailor_prompt
    assert "只能使用输入卡片的 id" in tailor_prompt
