"""Actual A/B controls plus authored responses for the Gemini format correction.

All HTTP uses MockTransport. Passing these tests does not prove live acceptance
of the correction or investment-research quality.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
from openai import BadRequestError, OpenAI
import pytest

from alphalens.providers import GEMINI_BASE_URL, ProviderError, request_structured
from alphalens.research import ResearchAnalysis, validate_analysis
from scripts.evaluate_ai import build_clean_response


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures/gemini_ab"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))


def read(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name,digest", MANIFEST["files"].items())
def test_recorded_diagnostic_integrity(name, digest):
    assert sha256((FIXTURES / name).read_bytes()).hexdigest() == digest


@pytest.mark.parametrize("diagnostic,changed", [("a", "messages"), ("b", "response_format")])
def test_actual_diagnostic_changes_only_its_approved_control(diagnostic, changed):
    original = json.loads((ROOT / "fixtures/gemini_http400/brief.request.json").read_text(encoding="utf-8"))
    actual = read(f"{diagnostic}.request.json")
    assert [key for key in original if original[key] != actual[key]] == [changed]
    assert actual["model"] == original["model"] == "gemini-3.5-flash-lite"
    assert actual["max_tokens"] == 6000 and actual["stream"] is False
    if diagnostic == "b":
        schema = actual["response_format"]["json_schema"]["schema"]
        assert set(schema["properties"]) == {"status"}
        assert schema["properties"]["status"]["type"] == "string"


@pytest.mark.parametrize("diagnostic,status", [("a", 400), ("b", 200)])
def test_exact_diagnostic_wire_and_actual_response_are_replayable(diagnostic, status):
    original = read(f"{diagnostic}.request.json")
    recorded = []

    def handle(request):
        recorded.append(json.loads(request.content))
        return httpx.Response(status, json=read(f"{diagnostic}.complete_response.json"))

    with OpenAI(api_key="offline-ab-fixture", base_url=GEMINI_BASE_URL, max_retries=0,
                http_client=httpx.Client(transport=httpx.MockTransport(handle))) as client:
        if status == 400:
            with pytest.raises(BadRequestError):
                client.chat.completions.create(**original)
        else:
            response = client.chat.completions.create(**original)
            assert json.loads(response.choices[0].message.content) == {"status": "success"}
    assert recorded == [original]


def packet_and_authored_output():
    original = read("b.request.json")
    book = json.loads(original["messages"][1]["content"])["source_catalog"]
    years = sorted({row["fiscal_year"] for row in book.values() if row["kind"] == "financial"})
    result = SimpleNamespace(periods=[SimpleNamespace(fiscal_year=year) for year in years])
    return original, book, build_clean_response(result, book, "brief")


def corrected_request(payload):
    original, _, _ = packet_and_authored_output()
    captured = []

    def handle(request):
        body = json.loads(request.content)
        captured.append(body)
        assert request.url == httpx.URL(GEMINI_BASE_URL + "chat/completions")
        assert body["model"] == original["model"] and body["max_tokens"] == 6000
        assert body["messages"][1:] == original["messages"][1:]
        assert body["messages"][0]["content"].startswith(original["messages"][0]["content"])
        prompt_schema = body["messages"][0]["content"].split("ORIGINAL OUTPUT SCHEMA:\n", 1)[1]
        assert json.loads(prompt_schema) == ResearchAnalysis.model_json_schema()
        wire = body["response_format"]["json_schema"]["schema"]
        assert wire["type"] == "object" and wire["additionalProperties"] is False
        assert set(wire["properties"]) == {"result_json"}
        assert wire["properties"]["result_json"]["type"] == "string"
        assert "$defs" not in wire and "$ref" not in json.dumps(wire)
        assert "minLength" not in json.dumps(wire) and "maxItems" not in json.dumps(wire)
        return httpx.Response(200, json={
            "id": "authored-corrected-format-not-live", "object": "chat.completion", "created": 0,
            "model": original["model"],
            "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": json.dumps({"result_json": json.dumps(payload)})}}],
        })

    with OpenAI(api_key="offline-envelope-fixture", base_url=GEMINI_BASE_URL, max_retries=0,
                http_client=httpx.Client(transport=httpx.MockTransport(handle))) as client:
        try:
            return request_structured(provider="gemini", api_key="offline-envelope-fixture",
                model=original["model"], messages=original["messages"], schema=ResearchAnalysis,
                max_output_tokens=6000, timeout=60, client=client)
        finally:
            assert len(captured) == 1  # Invalid output must not initiate a retry.


def test_corrected_flat_wire_retains_full_inner_schema_and_sources():
    _, book, payload = packet_and_authored_output()
    original = deepcopy(payload)
    result = corrected_request(payload)
    assert result.status == "completed" and result.output_parsed.model_dump() == original
    checked = validate_analysis(result.output_parsed, book)
    assert checked.unsupported_count == 0 and checked.evidence_checked_count > 0


@pytest.mark.parametrize("mutation", ["figure", "period", "invented_source", "invented_quote"])
def test_corrected_wire_does_not_weaken_financial_or_source_guards(mutation):
    _, book, payload = packet_and_authored_output()
    citation = payload["performance"][0]["financial_citations"][0]
    if mutation == "figure":
        citation["value"] += 1_000_000_000
    elif mutation == "period":
        citation["period_end"] = "2026-12-31"
    elif mutation == "invented_source":
        citation["source_id"] = "2099:invented_metric"
    else:
        payload["business_developments"][0]["passage_citations"][0]["quote"] = (
            "This fabricated passage does not appear in the actual SEC filing evidence."
        )
    parsed = corrected_request(payload).output_parsed
    checked = validate_analysis(parsed, book)
    assert checked.unsupported_count == 1
    assert len(checked.claims) > checked.unsupported_count


@pytest.mark.parametrize("mutation", ["extra_field", "boolean_figure", "short_text"])
def test_original_local_pydantic_contract_remains_mandatory(mutation):
    _, _, payload = packet_and_authored_output()
    if mutation == "extra_field":
        payload["price_target"] = "Unsupported model output"
    elif mutation == "boolean_figure":
        payload["performance"][0]["financial_citations"][0]["value"] = True
    else:
        payload["performance"][0]["text"] = "short"
    with pytest.raises(ProviderError, match="required schema"):
        corrected_request(payload)
