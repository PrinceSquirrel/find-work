import pytest

from app.schemas import EvidenceCard, EvidenceCardUpdate, EvidenceSource, JobPosting
from app.services.evidence_service import EvidenceService
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


def test_repeated_confirmation_is_normalized_and_does_not_write(tmp_path, monkeypatch) -> None:
    store = SQLiteStore(tmp_path / "confirmation.db")
    service = EvidenceService(store)
    card = store.create_evidence_card(EvidenceCard(
        title="接口测试", actions=["编写测试"], status="draft", provenance_type="user_statement",
    ))
    confirmed = service.update_card(card.id, EvidenceCardUpdate(status="confirmed"))
    assert confirmed.status == "confirmed"
    original_update = store.update_evidence_card
    writes = []

    def record_update(updated):
        writes.append(updated)
        return original_update(updated)

    monkeypatch.setattr(store, "update_evidence_card", record_update)
    repeated = service.update_card(card.id, EvidenceCardUpdate(
        title=" 接口测试 ", actions=[" 编写测试 ", ""], status="confirmed",
    ))
    assert repeated == confirmed
    assert store.get_evidence_card(card.id).updated_at == confirmed.updated_at
    assert writes == []
    changed = service.update_card(card.id, EvidenceCardUpdate(title="接口回归测试", status="confirmed"))
    assert changed.title == "接口回归测试"
    assert len(writes) == 1


def test_repeated_confirmation_still_checks_document_quote(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "quote-confirmation.db")
    source = store.create_evidence_source(EvidenceSource(
        filename="test.txt", file_type="txt", raw_text="实际负责接口测试。",
    ), b"synthetic")
    card = store.create_evidence_card(EvidenceCard(
        source_id=source.id, title="接口测试", status="confirmed", provenance_type="document",
        source_quote="原文不存在的内容", quote_verified=True,
    ))
    with pytest.raises(ValueError, match="原文"):
        EvidenceService(store).update_card(card.id, EvidenceCardUpdate(status="confirmed"))
    assert store.get_evidence_card(card.id).updated_at == card.updated_at
