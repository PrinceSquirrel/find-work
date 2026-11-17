import json
from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest

from app.schemas import EvidenceSource, ModelConfig
from app.services import llm_client_service
from app.services.llm_client_service import LLMClientUnavailable, OpenAICompatibleClient, request_failure


@pytest.mark.parametrize("status,code,hint", [(401, "authentication_error", "Key 无效"), (402, "", "余额"), (403, "", "无权访问"), (404, "", "模型地址"), (429, "rate_limit_exceeded", "过于频繁"), (429, "insufficient_quota", "额度不足"), (500, "", "暂时异常")])
def test_http_errors_explain_next_step_without_leaking_provider_body(status, code, hint):
    body = json.dumps({"error": {"code": code, "message": "secret-key-and-private-prompt"}}).encode()
    failure = request_failure(HTTPError("https://example.com/chat/completions", status, "private reason", {}, BytesIO(body)))
    assert hint in str(failure)
    assert f"HTTP {status}" in str(failure)
    assert "secret-key" not in str(failure) and "private" not in str(failure)


def test_non_json_errors_and_transport_failures_are_safe():
    assert "HTTP 429" in str(request_failure(HTTPError("https://example.com", 429, "private", {}, BytesIO(b"<html>bad gateway</html>"))))
    assert "超时" in str(request_failure(URLError(TimeoutError())))
    assert "网络" in str(request_failure(URLError("private network details")))


@pytest.mark.parametrize("operation", ["connection", "cards"])
def test_client_surfaces_authentication_failure_for_connection_and_card_extraction(monkeypatch, operation):
    def denied(*args, **kwargs):
        raise HTTPError("https://example.com/chat/completions", 401, "secret-test-key", {}, BytesIO(b"private provider response"))
    monkeypatch.setattr(llm_client_service, "urlopen", denied)
    config = ModelConfig(enabled=True, estimation_only=False, api_key="secret-test-key", api_key_configured=True)
    client = OpenAICompatibleClient()
    with pytest.raises(LLMClientUnavailable, match="HTTP 401") as caught:
        if operation == "connection":
            client.test_connection(config)
        else:
            client.generate_evidence_cards(config, EvidenceSource(id=1, filename="test.txt", file_type="txt", raw_text="项目：真实开发经历"))
    assert "secret-test-key" not in str(caught.value)
