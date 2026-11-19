from fastapi.testclient import TestClient

from app.main import create_app
from app.services.llm_client_service import OpenAICompatibleClient


def config(url, secret=""):
    return dict(provider="openai-compatible", model="deepseek-v4-pro", base_url=url,
                api_key_env_var="", api_key=secret, enabled=True, estimation_only=False)


def test_effective_route_and_connection_use_same_provider_secret(tmp_path, monkeypatch):
    client = TestClient(create_app(tmp_path / "test.db"))
    endpoint = "https://model.example"
    client.put("/api/model-config", json=config(endpoint, "synthetic-main-secret"))
    route = "/api/model-routes/ApplicationWriterAgent"
    assert client.put(route, json=config(endpoint)).json()["uses_default_key"]
    calls = []
    monkeypatch.setattr(OpenAICompatibleClient, "test_connection", lambda _, selected: calls.append(selected.api_key) or {"status": "success"})
    response = client.post(route + "/test")
    assert response.json()["status"] == "success"
    assert calls == ["synthetic-main-secret"]
    assert "synthetic-main-secret" not in response.text
    changed = client.put(route, json=config("https://different.example")).json()
    assert not changed["api_key_configured"]
    assert not changed["uses_default_key"]
    assert client.delete(route).json()["inherited"]


def test_server_applies_secret_from_profile_and_clears_previous_secret(tmp_path):
    client = TestClient(create_app(tmp_path / "test.db"))
    route = "/api/model-routes/JobMatchAgent"
    for name, secret in [("with", "synthetic-profile-secret"), ("without", "")]:
        profile = client.post("/api/model-profiles", json={"name": name, **config("https://model.example", secret)}).json()
        response = client.post(f"{route}/profiles/{profile['id']}")
        assert response.json()["api_key_configured"] == bool(secret)
        assert "synthetic-profile-secret" not in response.text
