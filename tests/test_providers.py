"""Provider contracts use mocked responses only; no live API request is made."""
import json
import traceback
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from openai import APIConnectionError, APITimeoutError, OpenAI
from pydantic import BaseModel, ConfigDict, Field

from alphalens import providers
from alphalens.providers import ProviderError, read_ai_config, request_structured


class ExampleOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    observation: str


@pytest.fixture
def config_environment(monkeypatch, tmp_path):
    monkeypatch.setattr(providers, "ROOT", tmp_path)
    for name in ("AI_PROVIDER", "GEMINI_API_KEY", "GEMINI_MODEL", "OPENAI_API_KEY", "OPENAI_MODEL"):
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def test_default_gemini_never_uses_an_openai_key(config_environment, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "unused-openai-secret")
    config = read_ai_config()
    assert config.provider == "gemini"
    assert config.model == "gemini-3.5-flash-lite"
    assert config.key_env == "GEMINI_API_KEY"
    assert config.api_key == ""
    assert not config.configured
    assert "unused-openai-secret" not in repr(config)


def test_explicit_project_dotenv_and_environment_precedence(config_environment, monkeypatch, tmp_path):
    (config_environment / ".env").write_text(
        "AI_PROVIDER=gemini\nGEMINI_API_KEY=local-secret\nGEMINI_MODEL=dotenv-model\n", encoding="utf-8")
    other_directory = tmp_path / "other-directory"
    other_directory.mkdir()
    monkeypatch.chdir(other_directory)
    monkeypatch.setenv("GEMINI_MODEL", "process-model")
    config = read_ai_config()
    assert config.provider == "gemini"
    assert config.model == "process-model"
    assert config.api_key == "local-secret"
    assert config.configured
    assert "local-secret" not in repr(config)


def test_explicit_openai_preserves_optional_support(config_environment, monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", " OpenAI ")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-local-secret")
    monkeypatch.setenv("GEMINI_API_KEY", "unused-gemini-secret")
    config = read_ai_config()
    assert config.provider == "openai"
    assert config.label == "OpenAI"
    assert config.model == "gpt-4.1-mini"
    assert config.api_key == "openai-local-secret"
    assert "secret" not in repr(config)


def test_unknown_provider_is_safe_and_does_not_fallback(config_environment, monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "invalid-secret-value")
    with pytest.raises(ProviderError) as caught:
        read_ai_config()
    assert "invalid-secret-value" not in str(caught.value)
    assert "No alternative provider" in str(caught.value)


def chat_response(*, finish_reason="stop", content=None, refusal=None, choices=True):
    return {
        "id": "mock-gemini-response", "object": "chat.completion", "created": 1,
        "model": providers.DEFAULT_GEMINI_MODEL,
        "choices": [{"index": 0, "finish_reason": finish_reason,
                     "message": {"role": "assistant", "content": content or json.dumps(
                         {"result_json": json.dumps({"observation":
                             "Cash generation requires further investment diligence."})}),
                         "refusal": refusal}}] if choices else [],
        "usage": {"prompt_tokens": 123, "completion_tokens": 34, "total_tokens": 157},
    }


def request(provider="gemini", client=None, **overrides):
    args = dict(provider=provider, api_key="mock-test-key", model="mock-model",
        messages=[{"role": "system", "content": "Use supplied financial evidence only."},
                  {"role": "user", "content": "An explicitly synthetic test request."}],
        schema=ExampleOutput, max_output_tokens=2200, timeout=45, client=client)
    args.update(overrides)
    return request_structured(**args)


def test_gemini_actual_sdk_path_schema_headers_and_single_operation(monkeypatch):
    recorded = []
    created = []

    def handle(req):
        recorded.append(req)
        return httpx.Response(200, json=chat_response())

    def factory(**kwargs):
        created.append(kwargs)
        return OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handle)))

    monkeypatch.setattr("openai.OpenAI", factory)
    output = request()
    assert len(recorded) == len(created) == 1
    assert created[0]["base_url"] == providers.GEMINI_BASE_URL
    assert created[0]["max_retries"] == 0
    assert created[0]["timeout"] == 45
    assert recorded[0].url == httpx.URL(providers.GEMINI_BASE_URL + "chat/completions")
    assert recorded[0].headers["authorization"] == "Bearer mock-test-key"
    assert "mock-test-key" not in str(recorded[0].url)
    body = json.loads(recorded[0].content)
    assert body["model"] == "mock-model"
    assert body["max_tokens"] == 2200
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    wire_schema = body["response_format"]["json_schema"]["schema"]
    assert wire_schema["additionalProperties"] is False
    assert wire_schema["properties"] == {"result_json": {"title": "Result Json", "type": "string"}}
    assert wire_schema["required"] == ["result_json"]
    assert "$defs" not in wire_schema
    assert "ORIGINAL OUTPUT SCHEMA:" in body["messages"][0]["content"]
    assert json.loads(body["messages"][0]["content"].split("ORIGINAL OUTPUT SCHEMA:\n")[1]) == ExampleOutput.model_json_schema()
    assert "tools" not in body and "web_search_options" not in body and "store" not in body
    assert output.provider == "gemini" and output.status == "completed"
    assert isinstance(output.output_parsed, ExampleOutput)
    assert output.usage == {"input_tokens": 123, "output_tokens": 34, "total_tokens": 157}
    assert output.latency_seconds >= 0


def test_openai_keeps_existing_responses_parse_contract():
    client = Mock()
    client.responses.parse.return_value = SimpleNamespace(status="completed",
        output_parsed=ExampleOutput(observation="Qualitative interpretation of cited financial evidence."))
    output = request(provider="openai", client=client)
    client.responses.parse.assert_called_once()
    client.chat.completions.parse.assert_not_called()
    kwargs = client.responses.parse.call_args.kwargs
    assert kwargs["store"] is False
    assert kwargs["text_format"] is ExampleOutput
    assert kwargs["max_output_tokens"] == 2200
    assert output.provider == "openai"
    assert output.usage == {}  # Mock attributes are not reported as invented usage.


def test_gemini_preserves_supplied_prompts_and_does_not_mutate_them():
    messages = [{"role": "system", "content": "Original financial and citation safeguards."},
        {"role": "user", "content": "Exact original SEC evidence and research task."}]
    original = [dict(message) for message in messages]
    client = Mock()
    client.chat.completions.parse.return_value = SimpleNamespace(
        choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(
            parsed=providers.GeminiJSONEnvelope(result_json=json.dumps(
                {"observation": "A supported qualitative research observation."})), refusal=None))])
    output = request(client=client, messages=messages)
    kwargs = client.chat.completions.parse.call_args.kwargs
    assert kwargs["response_format"] is providers.GeminiJSONEnvelope
    assert kwargs["messages"][0]["content"].startswith(original[0]["content"] + "\n\n")
    assert kwargs["messages"][1] == original[1]
    assert kwargs["messages"] is not messages
    assert all(new is not old for new, old in zip(kwargs["messages"], messages))
    assert messages == original
    assert output.output_parsed.observation == "A supported qualitative research observation."
    client.chat.completions.parse.assert_called_once()
    client.responses.parse.assert_not_called()


def test_gemini_adds_transport_system_instructions_when_original_has_none():
    original = [{"role": "user", "content": "Original evidence-only task."}]
    transformed = providers._gemini_messages(original, ExampleOutput)
    assert transformed[0]["role"] == "system"
    assert transformed[1] == original[0]
    assert original == [{"role": "user", "content": "Original evidence-only task."}]


@pytest.mark.parametrize("content", [
    json.dumps({"result_json": "{}", "extra": "must not be accepted"}),
    json.dumps({"result_json": {"observation": "Incorrect outer type"}}),
    json.dumps({"observation": "Missing transport envelope"}),
    json.dumps({"result_json": "not JSON: private-inner-output"}),
    json.dumps({"result_json": json.dumps({"observation": "Valid text", "extra": "not allowed"})}),
    json.dumps({"result_json": json.dumps({"different_field": "Missing required field"})}),
    json.dumps({"result_json": "```json\n{\"observation\":\"No arbitrary code fences\"}\n```"}),
])
def test_gemini_rejects_invalid_outer_and_inner_json_without_raw_text(content):
    requests = []

    def handle(req):
        requests.append(req)
        return httpx.Response(200, json=chat_response(content=content))

    client = OpenAI(api_key="mock-test-key", base_url=providers.GEMINI_BASE_URL,
        max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(handle)))
    with pytest.raises(ProviderError) as caught:
        request(client=client)
    if caught.value.diagnostics["validation_stage"] == "inner_json":
        assert "malformed JSON inside its response envelope" in str(caught.value)
        assert caught.value.diagnostics["schema_validation_result"] == "not_run"
    else:
        assert "valid structured" in str(caught.value)
    rendered = "".join(traceback.format_exception(caught.value))
    assert "private-inner-output" not in rendered
    assert "mock-test-key" not in rendered
    assert len(requests) == 1


def test_gemini_preserves_rich_inner_constraints_with_simple_wire_schema():
    class ConstrainedOutput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        observation: str = Field(min_length=12, max_length=900)
        evidence_ids: list[str] = Field(min_length=1, max_length=6)

    requests = []

    def handle(req):
        requests.append(json.loads(req.content))
        invalid_inner = {"observation": "short", "evidence_ids": []}
        return httpx.Response(200, json=chat_response(content=json.dumps(
            {"result_json": json.dumps(invalid_inner)})))

    client = OpenAI(api_key="mock-test-key", base_url=providers.GEMINI_BASE_URL,
        max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(handle)))
    with pytest.raises(ProviderError, match="valid structured"):
        request(client=client, schema=ConstrainedOutput)
    assert len(requests) == 1
    body = requests[0]
    wire = body["response_format"]["json_schema"]["schema"]
    assert set(wire["properties"]) == {"result_json"}
    assert "minLength" not in json.dumps(wire)
    assert "maxItems" not in json.dumps(wire)
    assert "minLength" in body["messages"][0]["content"]
    assert "maxItems" in body["messages"][0]["content"]


@pytest.mark.parametrize("provider,key_name", [("gemini", "GEMINI_API_KEY"), ("openai", "OPENAI_API_KEY")])
def test_missing_key_is_optional_and_never_calls_transport(provider, key_name):
    client = Mock()
    with pytest.raises(ProviderError, match=key_name):
        request(provider, client, api_key=" ")
    client.responses.parse.assert_not_called()
    client.chat.completions.parse.assert_not_called()


@pytest.mark.parametrize("overrides", [
    {"provider": "invalid"}, {"model": " "}, {"max_output_tokens": 0},
    {"max_output_tokens": 6001}, {"max_output_tokens": True}, {"timeout": 0}, {"timeout": True},
])
def test_bad_configuration_is_rejected_before_any_request(overrides):
    client = Mock()
    with pytest.raises(ProviderError):
        request(client=client, **overrides)
    client.responses.parse.assert_not_called()
    client.chat.completions.parse.assert_not_called()


@pytest.mark.parametrize("response", [chat_response(finish_reason="length"),
    chat_response(finish_reason="content_filter"), chat_response(refusal="Not available"),
    chat_response(choices=False)])
def test_gemini_incomplete_refused_and_empty_choices_are_not_displayed(response):
    client = OpenAI(api_key="mock-test-key", base_url=providers.GEMINI_BASE_URL,
        max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(
            lambda req: httpx.Response(200, json=response))))
    output = request(client=client)
    assert output.output_parsed is None
    assert output.status == "incomplete"


@pytest.mark.parametrize("status,error,expected", [
    (400, {"status": "INVALID_ARGUMENT", "details": [{"reason": "API_KEY_INVALID"}]}, "credentials"),
    (401, {"code": "invalid_api_key"}, "credentials"),
    (403, {"status": "PERMISSION_DENIED"}, "denied access"),
    (429, {"status": "RESOURCE_EXHAUSTED"}, "free quota"),
    (404, {"status": "NOT_FOUND"}, "selected model"),
    (400, {"status": "INVALID_ARGUMENT"}, "structured-output"),
    (503, {"status": "UNAVAILABLE"}, "temporarily unavailable"),
])
def test_gemini_error_categories_no_retry_fallback_or_secret_leak(status, error, expected):
    requests = []
    secret = "private-error-content-should-never-appear"
    error["message"] = secret

    def handle(req):
        requests.append(req)
        return httpx.Response(status, json={"error": error})

    client = OpenAI(api_key="mock-test-key", base_url=providers.GEMINI_BASE_URL,
        max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(handle)))
    with pytest.raises(ProviderError) as caught:
        request(client=client)
    assert expected in str(caught.value)
    assert len(requests) == 1
    rendered = "".join(traceback.format_exception(caught.value))
    assert secret not in rendered
    assert "mock-test-key" not in rendered


@pytest.mark.parametrize("error_class,expected", [
    (APITimeoutError, "timed out"), (APIConnectionError, "Could not connect"),
])
def test_connection_errors_are_safe_and_no_retry(error_class, expected):
    client = Mock()
    client.chat.completions.parse.side_effect = error_class(request=httpx.Request(
        "POST", providers.GEMINI_BASE_URL, headers={"Authorization": "private-secret"}))
    with pytest.raises(ProviderError, match=expected) as caught:
        request(client=client)
    assert "private-secret" not in "".join(traceback.format_exception(caught.value))
    client.chat.completions.parse.assert_called_once()
    client.responses.parse.assert_not_called()


def test_invalid_structured_json_is_rejected_and_raw_model_text_hidden():
    secret_text = "private-unstructured-provider-text"
    client = OpenAI(api_key="mock-test-key", base_url=providers.GEMINI_BASE_URL,
        max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(
            lambda req: httpx.Response(200, json=chat_response(content=secret_text)))))
    with pytest.raises(ProviderError, match="valid structured") as caught:
        request(client=client)
    assert secret_text not in "".join(traceback.format_exception(caught.value))


def test_openai_quota_error_is_distinct_from_gemini_free_quota():
    client = OpenAI(api_key="mock-test-key", max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(429,
            json={"error": {"code": "insufficient_quota", "message": "raw-private-text"}}))))
    with pytest.raises(ProviderError, match="credits are unavailable") as caught:
        request(provider="openai", client=client)
    assert "raw-private-text" not in "".join(traceback.format_exception(caught.value))
