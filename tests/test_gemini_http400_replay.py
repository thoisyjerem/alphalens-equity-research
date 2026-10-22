"""Replay the actual failed bodies through HTTPX mocks; never contact Google.

These tests establish SDK serialization and local safety/validation behavior.
They do not identify the rejected argument or prove remote model acceptance.
"""
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
from openai import OpenAI
import pytest

from alphalens.providers import GEMINI_BASE_URL, ProviderError, request_structured
from alphalens.research import ResearchAnalysis, ThesisChallenge, validate_analysis
from scripts.evaluate_ai import build_clean_response


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "gemini_http400"
SCHEMAS = {"brief": ResearchAnalysis, "challenge": ThesisChallenge}
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))


def saved_body(feature, suffix):
    return json.loads((FIXTURES / f"{feature}.{suffix}.json").read_text(encoding="utf-8"))


def replay(feature, status, response_body):
    """Use the real installed SDK serializer and only an in-memory transport."""
    original = saved_body(feature, "request")
    captured = []

    def handle(request):
        assert request.method == "POST"
        assert request.url == httpx.URL(GEMINI_BASE_URL + "chat/completions")
        captured.append(json.loads(request.content))
        return httpx.Response(status, json=response_body)

    # This is an explicit mock key. No local configuration is loaded or used.
    with httpx.Client(transport=httpx.MockTransport(handle)) as http_client:
        with OpenAI(api_key="mock-replay-key", base_url=GEMINI_BASE_URL,
                    max_retries=0, http_client=http_client) as client:
            try:
                # Freeze the legacy SDK operation, rather than regenerating
                # the old rejected rich schema through the corrected adapter.
                return client.chat.completions.parse(
                    model=original["model"], messages=original["messages"],
                    response_format=SCHEMAS[feature], max_tokens=original["max_tokens"])
            finally:
                # Equality includes every nested JSON Schema field, prompt,
                # evidence entry and model parameter in the failed request.
                assert captured == [original]


@pytest.mark.parametrize("name,expected_hash", MANIFEST["files"].items())
def test_saved_failure_body_integrity(name, expected_hash):
    assert sha256((FIXTURES / name).read_bytes()).hexdigest() == expected_hash


@pytest.mark.parametrize("feature", SCHEMAS)
def test_exact_failed_request_replays_actual_array_error_safely(feature):
    actual_error = saved_body(feature, "complete_response")
    from openai import BadRequestError

    with pytest.raises(BadRequestError) as caught:
        replay(feature, 400, actual_error)
    from alphalens.providers import _safe_error

    message = _safe_error(caught.value, "gemini")
    assert "Gemini rejected" in message
    assert "No billing was enabled or fallback attempted" in message
    assert "mock-replay-key" not in message
    assert "API credentials" not in message
    # Google's generic response does not confirm any specific field or schema
    # defect; the safe UI message must not claim such a diagnosis.
    assert "max_tokens" not in message
    assert "response_format" not in message
    assert "schema caused" not in message.lower()


@pytest.mark.parametrize("feature", SCHEMAS)
def test_exact_request_retains_local_pydantic_and_source_validation(feature):
    original = saved_body(feature, "request")
    packet = json.loads(original["messages"][1]["content"])
    book = packet["source_catalog"]
    years = sorted({source["fiscal_year"] for source in book.values()
                    if source["kind"] == "financial"})
    # The authored-response helper uses only these fiscal labels and the exact
    # saved source book. It performs no financial calculation or retrieval.
    source_periods = SimpleNamespace(periods=[SimpleNamespace(fiscal_year=year) for year in years])
    authored_output = build_clean_response(source_periods, book, feature)
    mock_response = {
        "id": "authored-offline-replay", "object": "chat.completion", "created": 1,
        "model": original["model"],
        "choices": [{"index": 0, "finish_reason": "stop", "message": {
            "role": "assistant", "content": json.dumps(authored_output), "refusal": None}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }
    response = replay(feature, 200, mock_response)
    parsed = response.choices[0].message.parsed
    assert isinstance(parsed, SCHEMAS[feature])
    assert parsed.model_dump() == authored_output
    verification = validate_analysis(parsed, book)
    assert verification.unsupported_count == 0
    assert verification.evidence_checked_count > 0


def test_saved_errors_do_not_identify_a_rejected_argument():
    for feature in SCHEMAS:
        actual_error = saved_body(feature, "complete_response")
        assert isinstance(actual_error, list) and len(actual_error) == 1
        assert actual_error[0]["error"] == {
            "code": 400,
            "message": "Request contains an invalid argument.",
            "status": "INVALID_ARGUMENT",
        }
        assert "details" not in actual_error[0]["error"]
    assert MANIFEST["error_details_available"] is False
    assert MANIFEST["contains_credentials_or_headers"] is False
