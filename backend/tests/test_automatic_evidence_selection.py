import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.schemas import EvidenceCard
from app.services.evidence_service import EvidenceConflictError


@pytest.fixture(autouse=True)
def isolated_models(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_BUSINESS_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def context(tmp_path):
    app = create_app(db_path=tmp_path / "auto.db")
    client = TestClient(app)
    resume = client.post("/api/resumes", files={"file": ("synthetic.txt", b"Python FastAPI Agent", "text/plain")}).json()
    client.post("/api/search-runs", json={"resume_id": resume["id"], "keywords": ["Python"], "city": "杭州", "platforms": ["boss"]})
    job = client.get("/api/jobs").json()[0]
    store = app.state.service.store
    related = store.create_evidence_card(EvidenceCard(title="Python接口", actions=["完成 Python 接口测试"], status="confirmed", category="project", provenance_type="user_statement"))
    store.create_evidence_card(EvidenceCard(title="教育", actions=["Python"], status="confirmed", category="education", provenance_type="user_statement"))
    store.create_evidence_card(EvidenceCard(title="未确认", actions=["Python"], status="draft", provenance_type="user_statement"))
    return app.state.evidence_service, store, resume["id"], job["id"], related


def test_empty_selection_automatically_uses_related_confirmed_facts(tmp_path):
    service, store, resume_id, job_id, related = context(tmp_path)
    result = service.generate_trusted_tailor(job_id, resume_id, [])
    assert result["review"]["evidence_selection_mode"] == "automatic_rules"
    assert result["review"]["used_evidence_card_ids"] == [related.id]
    assert result["claims"][0]["user_decision"] == "pending"
    assert store.get_evidence_card(related.id).status == "confirmed"


def test_auto_model_selects_subset_in_one_call_and_records_actual_citations(tmp_path, monkeypatch):
    service, _, resume_id, job_id, related = context(tmp_path)
    monkeypatch.setattr(service.model_router, "route_for_agent", lambda *_: SimpleNamespace(mode="external"))
    calls = []
    def generate(config, job, cards):
        calls.append(cards)
        assert all(card.status == "confirmed" and card.category != "education" for card in cards)
        return SimpleNamespace(content=json.dumps({"claims": [{"text": "完成 Python 接口测试", "evidence_card_ids": [related.id]}], "greeting_message": "您好"}))
    monkeypatch.setattr(service.llm_client, "generate_evidence_tailor", generate)
    monkeypatch.setattr(service, "_record_llm_usage", lambda *_: None)
    result = service.generate_trusted_tailor(job_id, resume_id, [])
    assert len(calls) == 1
    assert result["review"]["evidence_selection_mode"] == "automatic_model"
    assert result["review"]["used_evidence_card_ids"] == [related.id]


def test_no_related_local_facts_is_actionable_and_not_fabricated(tmp_path):
    service, store, resume_id, job_id, related = context(tmp_path)
    store.delete_evidence_card(related.id)
    with pytest.raises(EvidenceConflictError, match="相关"):
        service.generate_trusted_tailor(job_id, resume_id, [])
