"""Opt-in flat native Gemini output, exercised only over mocked HTTP."""
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
from openai import OpenAI
import pytest
from pydantic import BaseModel, ConfigDict, Field, create_model

from alphalens.providers import (
    DEFAULT_GEMINI_MODEL, GEMINI_BASE_URL, GeminiJSONEnvelope, ProviderError,
    request_structured,
)


class FlatOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, revalidate_instances="always")
    executive_interpretation: str
    finding_interpretations: list[str]


VALID = {
    "executive_interpretation": "Investment spending requires careful examination.",
    "finding_interpretations": ["Cash generation and reinvestment can diverge."],
}
MESSAGES = [{"role": "system", "content": "Interpret supplied evidence without recalculating it."},
            {"role": "user", "content": "An authored offline research context."}]


def completion(content=None, *, finish_reason="stop", refusal=None, choices=True):
    return {
        "id": "authored-native-gemini", "object": "chat.completion", "created": 0,
        "model": DEFAULT_GEMINI_MODEL,
        "choices": [{"index": 0, "finish_reason": finish_reason,
                     "message": {"role": "assistant", "content": content if content is not None else json.dumps(VALID),
                                 "refusal": refusal}}] if choices else [],
        "usage": {"prompt_tokens": 60, "completion_tokens": 20, "total_tokens": 80},
    }


def request(client=None, **overrides):
    arguments = dict(provider="gemini", api_key="mock-native-key", model=DEFAULT_GEMINI_MODEL,
                     messages=deepcopy(MESSAGES), schema=FlatOutput, max_output_tokens=256,
                     timeout=45, client=client, gemini_native=True)
    arguments.update(overrides)
    return request_structured(**arguments)


def local_client(recorded, response):
    def handle(incoming):
        recorded.append(incoming)
        return response
    return OpenAI(api_key="mock-native-key", base_url=GEMINI_BASE_URL, max_retries=0,
                  http_client=httpx.Client(transport=httpx.MockTransport(handle)))


def test_native_flat_schema_uses_one_direct_response_and_preserves_original_messages(monkeypatch):
    recorded, constructed = [], []

    def factory(**kwargs):
        constructed.append(kwargs)
        def handle(incoming):
            recorded.append(incoming)
            return httpx.Response(200, json=completion())
        return OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handle)))

    monkeypatch.setattr("openai.OpenAI", factory)
    messages = deepcopy(MESSAGES)
    output = request(messages=messages)
    assert len(recorded) == len(constructed) == 1
    assert constructed[0]["max_retries"] == 0
    assert constructed[0]["base_url"] == GEMINI_BASE_URL
    assert constructed[0]["timeout"] == 45
    assert recorded[0].url == httpx.URL(GEMINI_BASE_URL + "chat/completions")
    body = json.loads(recorded[0].content)
    assert body["messages"] == messages == MESSAGES
    assert body["max_tokens"] == 256
    assert set(body) == {"model", "messages", "max_tokens", "response_format", "stream"}
    wire = body["response_format"]["json_schema"]["schema"]
    assert wire == FlatOutput.model_json_schema()
    assert set(wire["properties"]) == set(VALID)
    assert "result_json" not in wire["properties"]
    assert "ORIGINAL OUTPUT SCHEMA" not in json.dumps(body["messages"])
    assert output.output_parsed.model_dump() == VALID
    assert output.status == "completed"
    assert output.diagnostics["parsing_result"] == "passed"
    assert output.diagnostics["schema_validation_result"] == "passed"
    assert output.diagnostics["validation_stage"] == "output_schema"
    assert output.usage == {"input_tokens": 60, "output_tokens": 20, "total_tokens": 80}


@pytest.mark.parametrize("payload, expected_path, expected_type", [
    ({"executive_interpretation": "Missing findings"}, "finding_interpretations", "missing"),
    ({**VALID, "finding_interpretations": "A list is required"}, "finding_interpretations", "list_type"),
    ({**VALID, "executive_interpretation": 7}, "executive_interpretation", "string_type"),
    ({**VALID, "finding_interpretations": [42]}, "finding_interpretations[0]", "string_type"),
    ({**VALID, "untrusted_private_field": "private-model-content"}, "[unrecognized_field]", "extra_forbidden"),
])
def test_native_wrong_shapes_are_rejected_without_repair_or_fallback(payload, expected_path, expected_type):
    recorded = []
    with local_client(recorded, httpx.Response(200, json=completion(json.dumps(payload)))) as client:
        with pytest.raises(ProviderError) as caught:
            request(client=client)
    assert len(recorded) == 1
    diagnostics = caught.value.diagnostics
    assert diagnostics["parsing_result"] == "passed"
    assert diagnostics["schema_validation_result"] == "failed"
    assert diagnostics["validation_stage"] == "output_schema"
    assert {"path": expected_path, "type": expected_type} in diagnostics["validation_issues"]
    assert "private-model-content" not in json.dumps(diagnostics)
    assert "mock-native-key" not in str(caught.value)


@pytest.mark.parametrize("content", [
    '{"executive_interpretation":"Unfinished',
    '{"executive_interpretation": "text"0}',
    '```json\n{"executive_interpretation":"text"}\n```',
])
def test_native_malformed_json_is_rejected_as_syntax_failure_without_retry(content):
    recorded = []
    with local_client(recorded, httpx.Response(200, json=completion(content))) as client:
        with pytest.raises(ProviderError) as caught:
            request(client=client)
    assert len(recorded) == 1
    assert caught.value.diagnostics["parsing_result"] == "failed"
    assert caught.value.diagnostics["schema_validation_result"] == "not_run"
    assert caught.value.diagnostics["validation_stage"] == "native_json"
    assert caught.value.diagnostics["validation_issues"] == [{"path": "$", "type": "json_invalid"}]


@pytest.mark.parametrize("options", [
    {"finish_reason": "length"}, {"finish_reason": "content_filter"},
    {"finish_reason": "tool_calls"}, {"refusal": "I cannot comply"}, {"choices": False},
])
def test_native_refused_or_incomplete_response_is_never_accepted(options):
    recorded = []
    with local_client(recorded, httpx.Response(200, json=completion(**options))) as client:
        output = request(client=client)
    assert len(recorded) == 1
    assert output.status == "incomplete"
    assert output.output_parsed is None
    assert output.diagnostics["schema_validation_result"] == "not_run"


@pytest.mark.parametrize("status", [400, 401, 429, 503])
def test_native_api_failure_makes_one_request_and_no_fallback(status):
    recorded = []
    response = httpx.Response(status, json={"error": {"message": "private provider text",
                                                    "type": "invalid_request_error"}})
    with local_client(recorded, response) as client:
        with pytest.raises(ProviderError) as caught:
            request(client=client)
    assert len(recorded) == 1
    assert caught.value.diagnostics["status"] == "request_error"
    assert caught.value.diagnostics["http_status"] == status
    assert caught.value.diagnostics["schema_validation_result"] == "not_run"
    assert "private provider text" not in str(caught.value)


UNSUPPORTED_SCHEMAS = [
    create_model("Nested", __config__=ConfigDict(extra="forbid"), child=(FlatOutput, ...)),
    create_model("OptionalValue", __config__=ConfigDict(extra="forbid"), value=(str | None, ...)),
    create_model("Number", __config__=ConfigDict(extra="forbid"), value=(int, ...)),
    create_model("Defaulted", __config__=ConfigDict(extra="forbid"), value=(str, "default")),
    create_model("Constrained", __config__=ConfigDict(extra="forbid"), value=(str, Field(min_length=1))),
    create_model("ConstrainedList", __config__=ConfigDict(extra="forbid"), value=(list[str], Field(max_length=2))),
    create_model("ListObjects", __config__=ConfigDict(extra="forbid"), value=(list[FlatOutput], ...)),
    create_model("ExtraAllowed", value=(str, ...)),
]


@pytest.mark.parametrize("schema", UNSUPPORTED_SCHEMAS, ids=lambda model: model.__name__)
def test_native_rejects_complex_or_nonrequired_schema_before_any_request(schema):
    client = Mock()
    with pytest.raises(ProviderError, match="flat object of required strings"):
        request(client=client, schema=schema)
    assert not client.mock_calls


@pytest.mark.parametrize("native", [None, 1, "true"])
def test_native_opt_in_requires_boolean(native):
    client = Mock()
    with pytest.raises(ProviderError, match="boolean"):
        request(client=client, gemini_native=native)
    assert not client.mock_calls


def test_openai_cannot_silently_accept_gemini_native_mode():
    client = Mock()
    with pytest.raises(ProviderError, match="only by Gemini"):
        request(provider="openai", client=client)
    assert not client.mock_calls


def test_default_gemini_envelope_remains_unchanged():
    recorded = []
    with local_client(recorded, httpx.Response(200, json=completion(json.dumps(
            {"result_json": json.dumps(VALID)})))) as client:
        output = request(client=client, gemini_native=False)
    body = json.loads(recorded[0].content)
    assert set(body["response_format"]["json_schema"]["schema"]["properties"]) == {"result_json"}
    assert "ORIGINAL OUTPUT SCHEMA" in body["messages"][0]["content"]
    assert output.output_parsed.model_dump() == VALID


def test_default_openai_responses_contract_remains_unchanged():
    client = Mock()
    client.responses.parse.return_value = SimpleNamespace(status="completed", output_parsed=FlatOutput(**VALID))
    output = request(provider="openai", client=client, gemini_native=False)
    assert output.output_parsed.model_dump() == VALID
    client.responses.parse.assert_called_once()
    client.chat.completions.parse.assert_not_called()
    assert client.responses.parse.call_args.kwargs["text_format"] is FlatOutput
    assert client.responses.parse.call_args.kwargs["store"] is False
