"""Prospective model findings, deterministic executive and genuine failure replay."""
from copy import deepcopy
import json
from pathlib import Path

import httpx
from openai import OpenAI
from pydantic import ValidationError
import pytest

from alphalens.ai import AiError, generate_research_brief
from alphalens.focused_briefing import FindingInterpretations, build_briefing_context
from alphalens.gemini_briefing import GeminiFindingFields
from alphalens.providers import GEMINI_BASE_URL
from alphalens.research_exports import export_research_json
from alphalens.service import load_offline_filing_context, load_research
from scripts.prepare_msft_briefing import authored_shape


def generate(payload=None, *, change=None):
    result = load_research("MSFT", "offline")
    contexts = [load_offline_filing_context(result)]
    context = build_briefing_context(result, contexts)
    wire = GeminiFindingFields.from_compact(authored_shape(context, "focused_v3")).model_dump(mode="json")
    if payload is not None:
        wire = payload
    if change:
        change(wire)
    requests = []
    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "AUTHORED-NOT-LIVE", "object": "chat.completion", "created": 0,
            "model": "gemini-3.5-flash-lite", "choices": [{"index": 0, "finish_reason": "stop",
            "message": {"role": "assistant", "content": json.dumps(wire)}}]})
    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        with OpenAI(api_key="mock-only", base_url=GEMINI_BASE_URL, http_client=http, max_retries=0) as client:
            try:
                report = generate_research_brief(result, "mock-only", "gemini-3.5-flash-lite", provider="gemini",
                    contract="focused_v3", filing_contexts=contexts, client=client)
            finally:
                assert len(requests) == 1
    return report, requests[0]


def test_python_executive_preserves_separate_validated_findings_and_raw_contract():
    report, request = generate()
    assert report.contract == "focused_v3" and report.verification.unsupported_count == 0
    assert len(report.output.executive_summary) == len(report.output.what_matters_most) == 2
    assert report.output.executive_summary == report.output.what_matters_most
    assert all(a is not b for a, b in zip(report.output.executive_summary, report.output.what_matters_most))
    assert len(report.transport_output) == 13
    assert not any("executive" in key for key in report.transport_output)
    assert "executive_interpretation" not in report.model_interpretation
    assert set(request["response_format"]["json_schema"]["schema"]["properties"]) == set(GeminiFindingFields.model_fields)
    exported = json.loads(export_research_json(report))
    assert exported["metadata"]["contract"] == "focused_v3"
    assert exported["raw_model_output"] == report.transport_output
    assert exported["metadata"]["semantic_review"] == "requires_analyst_review"
    report.output.executive_summary[0].text = "A changed and unvalidated statement."
    with pytest.raises(ValueError, match="changed after assembly"):
        export_research_json(report)


@pytest.mark.parametrize("change", [
    lambda wire: wire.pop("primary_alternative_explanation"),
    lambda wire: wire.update(executive_interpretation="An unnecessary additional claim."),
    lambda wire: wire.update(primary_passage_ids=["sec:invented"]),
    lambda wire: wire.update(primary_interpretation="Revenue reached USD 999 billion in 2020."),
    lambda wire: wire.update(additional_observation_id="invented"),
    lambda wire: wire.update(primary_interpretation="All corporate capital expenditure is entirely AI-specific investment."),
])
def test_invalid_findings_fail_without_retry_repair_or_paid_fallback(change):
    with pytest.raises(AiError):
        generate(change=change)


def test_saved_rejected_v2_response_is_never_silently_reinterpreted_as_v3():
    root = Path(__file__).resolve().parents[1]
    saved = json.loads((root / "outputs/msft_recovery_live_2026-10-18/COMPLETE_RESPONSE.json").read_text(encoding="utf-8"))
    raw = json.loads(saved["choices"][0]["message"]["content"])
    unchanged = deepcopy(raw)
    with pytest.raises(ValidationError) as caught:
        GeminiFindingFields.model_validate(raw)
    assert {row["loc"][0] for row in caught.value.errors()} == {
        "executive_observation_id", "executive_interpretation", "executive_passage_ids"}
    with pytest.raises(AiError):
        generate(raw)
    assert raw == unchanged
    with pytest.raises(ValidationError):
        FindingInterpretations.model_validate({})
