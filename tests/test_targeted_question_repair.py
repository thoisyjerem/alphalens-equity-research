"""Actual legacy failure replay plus one bounded local metadata repair.

No live requests: SDK runs against saved or explicitly authored HTTP responses.
"""
from copy import deepcopy
import json
from pathlib import Path

import httpx
from openai import OpenAI
from pydantic import ValidationError
import pytest

from alphalens.ai import generate_research_brief
from alphalens.observability import _audit_record
from alphalens.providers import GEMINI_BASE_URL, ProviderError, request_structured
from alphalens.quality import evaluate_output, load_source_catalog
from alphalens.research import ResearchAnalysis, repair_missing_question_kind
from scripts.evaluate_ai import build_clean_response, load_evaluation_sources

ROOT = Path(__file__).resolve().parents[1]


def _actual():
    response = json.loads((ROOT / "fixtures/gemini_schema_failure/brief.complete_response.json").read_text(encoding="utf-8"))
    return response, json.loads(json.loads(response["choices"][0]["message"]["content"])["result_json"])


def _repair(payload):
    try:
        ResearchAnalysis.model_validate(payload)
    except ValidationError as error:
        return repair_missing_question_kind(payload, ResearchAnalysis, error)
    pytest.fail("The regression requires a missing field")


def test_saved_missing_kind_has_one_local_metadata_repair_but_not_financial_approval():
    _, payload = _actual()
    unchanged = deepcopy(payload)
    repaired, paths = _repair(payload)
    assert paths == ["missing_information[0].kind"]
    assert repaired.missing_information[0].kind == "question"
    expected = deepcopy(payload)
    expected["missing_information"][0]["kind"] = "question"
    assert ResearchAnalysis.model_validate(expected) == repaired
    assert payload == unchanged  # Historical evidence never rewritten.
    book = load_source_catalog(ROOT / "fixtures/gemini_http400/brief.request.json")
    check = evaluate_output(repaired.model_dump(mode="json"), book)
    assert check["schema_passed"] and not check["complete_local_validation_passed"]
    assert any("Comparative completeness" in issue for row in check["claims"] for issue in row["issues"])


@pytest.mark.parametrize("corruption", ["statement", "wrong_kind", "missing_text", "extra_field", "multiple_missing"])
def test_repair_does_not_invent_substance_or_change_an_existing_classification(corruption):
    _, payload = _actual()
    if corruption == "statement":
        payload["missing_information"][0]["text"] = "The available evidence establishes sustainable cash returns."
    elif corruption == "wrong_kind":
        payload["missing_information"][0]["kind"] = "unknown"
    elif corruption == "missing_text":
        del payload["missing_information"][0]["text"]
    elif corruption == "extra_field":
        payload["missing_information"][0]["invented"] = "Do not drop me to make this pass"
    else:
        payload["missing_information"].append({"text": "Which evidence would establish future cash returns?"})
    original = deepcopy(payload)
    with pytest.raises(ValidationError):
        _repair(payload)
    assert payload == original


def test_legacy_pipeline_discloses_repair_uses_one_mock_http_call_and_still_quarantines_bad_figures():
    result, contexts, book = load_evaluation_sources()
    payload = build_clean_response(result, book, "brief")
    del payload["missing_information"][0]["kind"]
    payload["performance"][0]["financial_citations"][0]["value"] += 1234
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(200, json={"id": "AUTHORED-OFFLINE", "object": "chat.completion", "created": 0,
            "model": "mock-model", "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": json.dumps({"result_json": json.dumps(payload)})}}]})
    with OpenAI(api_key="mock-only", base_url=GEMINI_BASE_URL, max_retries=0,
                http_client=httpx.Client(transport=httpx.MockTransport(respond))) as client:
        report = generate_research_brief(result, "mock-only", "mock-model", provider="gemini", contract="legacy",
            filing_contexts=contexts, client=client)
    assert len(calls) == 1
    assert report.diagnostics["local_repair_paths"] == ["missing_information[0].kind"]
    assert any("derived locally" in warning for warning in report.warnings)
    assert report.verification.unsupported_count == 1
    assert any("Financial figure mismatch" in issue for row in report.verification.claims for issue in row.issues)
    record = _audit_record(report.diagnostics, [], "")
    assert record["local_repair_paths"] == ["missing_information[0].kind"]
    from alphalens.research_exports import export_research_json
    exported = json.loads(export_research_json(report))
    assert "not original provider bytes" in exported["raw_output_notice"]
    assert exported["metadata"]["diagnostics"]["local_repair_paths"] == ["missing_information[0].kind"]


def test_metadata_repair_cannot_be_enabled_on_openai_or_flat_gemini():
    for provider, native in (("openai", False), ("gemini", True)):
        with pytest.raises(ProviderError, match="legacy Gemini envelope"):
            request_structured(provider=provider, api_key="mock-only", model="mock-model", messages=[],
                schema=ResearchAnalysis, max_output_tokens=256, timeout=5,
                repair_question_kind=True, gemini_native=native)
