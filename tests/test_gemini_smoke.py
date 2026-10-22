"""The approval-gated diagnostic defaults to a harmless offline mock."""
import json
from unittest.mock import Mock

import httpx
import pytest
from pydantic import ValidationError

from scripts import gemini_smoke
from alphalens.providers import ProviderError


def test_smoke_preparation_is_offline_and_contains_no_research_or_credentials(tmp_path, monkeypatch):
    def no_model_network(*args, **kwargs):
        pytest.fail("Smoke preparation must never use a real HTTP transport")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", no_model_network)
    plan = gemini_smoke.prepare_offline(tmp_path / "plan.json")
    body = plan["request_body"]
    assert body["model"] == "gemini-3.5-flash-lite"
    assert body["max_tokens"] == 256 and body["stream"] is False
    assert body["messages"][0]["content"].startswith(gemini_smoke.MESSAGES[0]["content"])
    assert body["messages"][1:] == gemini_smoke.MESSAGES[1:]
    assert plan["maximum_live_requests"] == 1 and not plan["automatic_retries"]
    assert not plan["provider_fallback"]
    assert body["response_format"]["type"] == "json_schema"
    schema = body["response_format"]["json_schema"]["schema"]
    assert list(schema["properties"]) == ["result_json"]
    assert schema["properties"]["result_json"]["type"] == "string"
    assert "$defs" not in schema and "minLength" not in json.dumps(schema)
    assert "maxLength" not in json.dumps(schema)
    assert "source_catalog" not in json.dumps(body) and "investment_hypothesis" not in json.dumps(body)
    assert "offline-placeholder" not in json.dumps(plan)


@pytest.mark.parametrize("status", ["not ok", "", None, 123])
def test_smoke_response_must_equal_expected_value(status):
    with pytest.raises(ValidationError):
        gemini_smoke.SmokeOutput(status=status)


def test_default_cli_never_executes_live_test(monkeypatch):
    execute = Mock(side_effect=AssertionError("Live test must need an explicit opt-in"))
    prepare = Mock(return_value={"model": "configured-model"})
    monkeypatch.setattr(gemini_smoke, "prepare_offline", prepare)
    monkeypatch.setattr(gemini_smoke, "execute_approved_one", execute)
    monkeypatch.setattr("sys.argv", ["gemini_smoke.py"])
    assert gemini_smoke.main() == 0
    prepare.assert_called_once()
    execute.assert_not_called()


def test_live_smoke_cannot_switch_provider_or_model(monkeypatch, tmp_path):
    from types import SimpleNamespace

    monkeypatch.setattr(gemini_smoke, "read_ai_config", lambda: SimpleNamespace(
        provider="openai", model="gpt-4.1-mini", configured=True))
    with pytest.raises(ProviderError, match="No request was made"):
        gemini_smoke.execute_approved_one(tmp_path)
    assert not (tmp_path / "REQUEST_LEDGER.json").exists()


def test_live_smoke_cannot_be_accidentally_repeated(monkeypatch, tmp_path):
    from types import SimpleNamespace

    monkeypatch.setattr(gemini_smoke, "read_ai_config", lambda: SimpleNamespace(
        provider="gemini", model="gemini-3.5-flash-lite", configured=True))
    (tmp_path / "REQUEST_LEDGER.json").write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError):
        gemini_smoke.execute_approved_one(tmp_path)
