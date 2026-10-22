"""Strict output failures and safe attempt metadata, using offline responses.

The historical fixture was a real rejected live response. Other responses below
are explicitly authored tests; none establishes current live model reliability.
"""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import traceback
from types import SimpleNamespace
from typing import Literal
from unittest.mock import Mock

import httpx
from openai import OpenAI
from pydantic import BaseModel, ConfigDict
import pytest

from alphalens.providers import GEMINI_BASE_URL, ProviderError, request_structured
from alphalens.research import ResearchAnalysis, ResearchNote


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/gemini_schema_failure"
TEST_KEY = "offline-key-never-log"


class ClassifiedItem(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    text: str
    kind: Literal["fact", "question"]


class ClassifiedOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    items: list[ClassifiedItem]


def wire(inner, *, finish_reason="stop"):
    return {
        "id": "authored-offline-response", "object": "chat.completion", "created": 0,
        "model": "offline-model", "usage": {"prompt_tokens": 123, "completion_tokens": 45, "total_tokens": 168},
        "choices": [{"index": 0, "finish_reason": finish_reason, "message": {"role": "assistant",
            "content": json.dumps({"result_json": inner if isinstance(inner, str) else json.dumps(inner)})}}],
    }


def run(response, *, schema=ClassifiedOutput, operation="research_briefing", status=200):
    calls = []

    def handle(request):
        calls.append(json.loads(request.content))
        return httpx.Response(status, json=response)

    with OpenAI(api_key=TEST_KEY, base_url=GEMINI_BASE_URL, max_retries=0,
                http_client=httpx.Client(transport=httpx.MockTransport(handle))) as client:
        try:
            return request_structured(provider="gemini", api_key=TEST_KEY, model="offline-model",
                messages=[{"role": "system", "content": "Authored offline contract test."},
                          {"role": "user", "content": "Use supplied evidence only."}],
                schema=schema, max_output_tokens=256, timeout=5, client=client, operation=operation)
        finally:
            assert len(calls) == 1  # Includes invalid output and transport errors: no retry or fallback.


def test_actual_http200_missing_kind_is_rejected_with_exact_safe_location_and_usage():
    manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    path = FIXTURES / "brief.complete_response.json"
    assert sha256(path.read_bytes()).hexdigest() == manifest["files"][path.name]
    response = json.loads(path.read_text(encoding="utf-8"))
    original = deepcopy(response)
    with pytest.raises(ProviderError) as caught:
        run(response, schema=ResearchAnalysis)
    details = caught.value.diagnostics
    assert {"path": "missing_information[0].kind", "type": "missing"} in details["validation_issues"]
    assert details["parsing_result"] == "passed"
    assert details["schema_validation_result"] == "failed"
    assert details["validation_stage"] == "output_schema"
    assert details["status"] == "rejected"
    assert details["usage"] == {"input_tokens": 19786, "output_tokens": 1117, "total_tokens": 20903}
    assert response == original
    inner = json.loads(json.loads(response["choices"][0]["message"]["content"])["result_json"])
    assert "kind" not in inner["missing_information"][0]  # No repair or substantive classification.


@pytest.mark.parametrize("inner,stage,path,error_type", [
    ({"items": [{"text": "A required classification is absent."}]}, "output_schema", "items[0].kind", "missing"),
    ("{not valid JSON: private-model-prose}", "inner_json", "$", "json_invalid"),
    ({"items": "private-model-prose"}, "output_schema", "items", "list_type"),
    ({"items": [{"text": "Invalid enum must not become a fact.", "kind": "unsupported-private-enum"}]},
        "output_schema", "items[0].kind", "literal_error"),
    ({"items": [{"text": "Extra fields must remain invalid.", "kind": "fact", "private-model-prose": "secret"}]},
        "output_schema", "items[0].[unrecognized_field]", "extra_forbidden"),
])
def test_invalid_shapes_have_precise_bounded_issues_without_model_input(inner, stage, path, error_type):
    with pytest.raises(ProviderError) as caught:
        run(wire(inner))
    details = caught.value.diagnostics
    assert details["validation_stage"] == stage
    assert {"path": path, "type": error_type} in details["validation_issues"]
    rendered = json.dumps(details) + "".join(traceback.format_exception(caught.value))
    assert "private-model-prose" not in rendered
    assert "unsupported-private-enum" not in rendered
    assert "offline-key-never-log" not in rendered
    assert "secret" not in rendered


def test_success_metadata_is_json_safe_and_does_not_claim_financial_verification():
    output = run(wire({"items": [{"text": "What evidence is needed?", "kind": "question"}]}))
    details = output.diagnostics
    assert details["operation"] == "research_briefing"
    assert details["provider"] == "gemini" and details["model"] == "offline-model"
    assert details["status"] == "completed"
    assert details["parsing_result"] == details["schema_validation_result"] == "passed"
    assert details["validation_issues"] == [] and not details["issues_truncated"]
    assert details["http_status"] is None  # SDK parsed object does not expose an HTTP status.
    assert details["usage"] == {"input_tokens": 123, "output_tokens": 45, "total_tokens": 168}
    assert details["latency_seconds"] == output.latency_seconds >= 0
    assert datetime.fromisoformat(details["timestamp_utc"]).utcoffset().total_seconds() == 0
    assert "financial_validation_result" not in details and "source_validation_result" not in details
    assert "offline-key-never-log" not in json.dumps(details)


def test_inner_json_failure_is_distinguished_from_schema_rejection_without_retry():
    # Authored malformed response: actual screenshot attempts saved metadata only.
    with pytest.raises(ProviderError) as caught:
        run(wire('{"items": [private-unquoted-text]}'), operation="ai_commentary")
    assert "malformed JSON inside its response envelope" in str(caught.value)
    assert "schema and source checks were not run" in str(caught.value)
    assert "private-unquoted-text" not in str(caught.value)
    assert caught.value.diagnostics["validation_stage"] == "inner_json"
    assert caught.value.diagnostics["schema_validation_result"] == "not_run"
    with pytest.raises(ProviderError) as schema_failure:
        run(wire({"items": "wrong-shape"}), operation="ai_commentary")
    assert "malformed JSON" not in str(schema_failure.value)
    assert schema_failure.value.diagnostics["validation_stage"] == "output_schema"


def test_schema_error_details_are_bounded_even_for_many_untrusted_extra_fields():
    payload = {"items": []}
    payload.update({f"untrusted-extra-field-{index}": f"private-value-{index}" for index in range(30)})
    with pytest.raises(ProviderError) as caught:
        run(wire(payload))
    details = caught.value.diagnostics
    assert len(details["validation_issues"]) == 12 and details["issues_truncated"]
    assert {issue["path"] for issue in details["validation_issues"]} == {"[unrecognized_field]"}
    assert "untrusted-extra-field" not in json.dumps(details)
    assert "private-value" not in json.dumps(details)


def test_provider_failure_records_known_http_status_without_raw_error_or_usage():
    error = {"error": {"message": "private-provider-error offline-key-never-log", "status": "RESOURCE_EXHAUSTED"}}
    with pytest.raises(ProviderError) as caught:
        run(error, status=429)
    details = caught.value.diagnostics
    assert details["http_status"] == 429
    assert details["status"] == "request_error" and details["usage"] == {}
    assert details["parsing_result"] == details["schema_validation_result"] == "not_run"
    assert details["validation_stage"] == "provider_response"
    assert "private-provider-error" not in json.dumps(details) + str(caught.value)


def test_truncation_is_incomplete_and_never_claimed_to_pass_schema():
    response = run(wire({"items": []}, finish_reason="length"))
    assert response.output_parsed is None and response.status == "incomplete"
    assert response.diagnostics["schema_validation_result"] == "not_run"
    assert response.diagnostics["usage"] == {"input_tokens": 123, "output_tokens": 45, "total_tokens": 168}


def test_openai_responses_path_keeps_contract_and_attaches_same_safe_metadata():
    client = Mock()
    valid = ClassifiedOutput(items=[ClassifiedItem(text="A source-bound qualitative observation.", kind="fact")])
    client.responses.parse.return_value = SimpleNamespace(status="completed", output_parsed=valid,
        usage=SimpleNamespace(input_tokens=50, output_tokens=20, total_tokens=70))
    response = request_structured(provider="openai", api_key="offline-key-never-log", model="offline-openai-model",
        messages=[{"role": "user", "content": "Offline contract test."}], schema=ClassifiedOutput,
        max_output_tokens=256, timeout=5, client=client, operation="ai_commentary")
    assert response.output_parsed == valid
    assert response.diagnostics["operation"] == "ai_commentary"
    assert response.diagnostics["schema_validation_result"] == "passed"
    client.responses.parse.assert_called_once()
    assert client.responses.parse.call_args.kwargs["store"] is False
    assert client.responses.parse.call_args.kwargs["text_format"] is ClassifiedOutput
    client.chat.completions.parse.assert_not_called()


def test_unknown_operation_and_misconfigured_model_cannot_log_private_content():
    client = Mock()
    client.responses.parse.return_value = SimpleNamespace(status="completed",
        output_parsed=ClassifiedOutput(items=[]), usage=None)
    response = request_structured(provider="openai", api_key="offline-key-never-log",
        model="offline-key-never-log", messages=[], schema=ClassifiedOutput,
        max_output_tokens=256, timeout=5, client=client, operation=["private-operation"])
    assert response.diagnostics["model"] == "[redacted model identifier]"
    assert response.diagnostics["operation"] == "structured_response"
    assert "offline-key-never-log" not in json.dumps(response.diagnostics)


def test_actual_upgraded_http200_overlong_quote_is_rejected_without_truncation_and_retains_usage():
    directory = FIXTURES.parent / "gemini_quote_failure"
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    path = directory / "brief.complete_response.json"
    assert sha256(path.read_bytes()).hexdigest() == manifest["files"][path.name]
    response = json.loads(path.read_text(encoding="utf-8"))
    original = deepcopy(response)
    with pytest.raises(ProviderError) as caught:
        run(response, schema=ResearchNote)
    details = caught.value.diagnostics
    assert details["validation_issues"] == [{"path": "what_matters_most[0].passage_citations[0].quote",
                                              "type": "string_too_long"}]
    assert details["parsing_result"] == "passed" and details["schema_validation_result"] == "failed"
    assert details["validation_stage"] == "output_schema" and details["status"] == "rejected"
    assert details["usage"] == {"input_tokens": 33277, "output_tokens": 3030, "total_tokens": 36307}
    inner = json.loads(json.loads(response["choices"][0]["message"]["content"])["result_json"])
    quote = inner["what_matters_most"][0]["passage_citations"][0]["quote"]
    assert len(quote) == 978 and response == original
    assert all("kind" in claim for section in inner.values() for claim in section)
