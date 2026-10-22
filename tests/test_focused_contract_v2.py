"""Fixed primary coverage and bounded model fields; all SDK responses are authored."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
from openai import OpenAI
from pydantic import ValidationError
import pytest

from alphalens.ai import AiError, generate_research_brief
from alphalens.focused_briefing import (FocusedBriefingInterpretation, assemble_briefing,
    build_briefing_context)
from alphalens.providers import GEMINI_BASE_URL, GeminiJSONEnvelope
from alphalens.gemini_briefing import GeminiBriefingFields
from alphalens.research_exports import export_research_json, export_research_markdown
from alphalens.service import load_offline_filing_context, load_research


@pytest.fixture
def setup():
    result = load_research("MSFT", "offline")
    contexts = [load_offline_filing_context(result)]
    return result, contexts, build_briefing_context(result, contexts)


def authored(context):
    primary = context.packet["primary_observation_id"]
    additional = context.packet["additional_observation_ids"][0]
    passage = next(iter(context.packet["passages"]))
    return {
        "executive_interpretation": {"observation_ids": [primary], "supporting_passage_ids": [],
            "interpretation": "Investment may absorb cash before new capacity demonstrates sustainable cash returns."},
        "primary_finding": {
            "interpretation": "Operating cash flow increased while free cash flow declined, which may reflect investment ahead of monetisation.",
            "supporting_passage_ids": [passage],
            "alternative_explanation": "Payment timing could also affect cash conversion without establishing project economics.",
            "limitations": ["Corporate cash PP&E does not isolate AI investment.", "Incremental returns and utilisation are not established."]},
        "findings": [{"observation_ids": [additional],
            "interpretation": "Operating performance may provide resources for reinvestment without establishing its future return.",
            "supporting_passage_ids": [], "alternative_explanation": "Product mix and expense timing could contribute to operating performance.",
            "limitations": "Consolidated results do not isolate incremental infrastructure economics."}],
        "risks": [{"interpretation": "Disclosed competitive and infrastructure conditions may complicate project economics.",
            "supporting_passage_ids": [passage],
            "limitations": ["A disclosed possibility is not proof of a realised adverse outcome."]}],
        "unanswered_questions": ["Which utilisation and monetisation evidence would distinguish investment timing from lasting cash pressure?",
            "What incremental profit and invested capital would permit a defensible assessment of returns?"]}


def sdk_generate(setup, payload):
    calls = []
    def handle(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "AUTHORED-V2-NOT-LIVE", "object": "chat.completion", "created": 0,
            "model": "gemini-3.5-flash-lite", "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": json.dumps(GeminiBriefingFields.from_compact(payload).model_dump(mode="json")
                    if "primary_finding" in payload else payload)}}]})
    result, contexts, _ = setup
    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        with OpenAI(api_key="offline-v2-key", base_url=GEMINI_BASE_URL, http_client=http, max_retries=0) as client:
            try:
                report = generate_research_brief(result, "offline-v2-key", "gemini-3.5-flash-lite",
                    provider="gemini", filing_contexts=contexts, client=client)
            finally:
                assert len(calls) == 1  # No repair request, retry or fallback on any path.
    return report, calls[0]


def test_primary_binding_preserves_list_content_and_python_financial_sources(setup):
    context = setup[2]
    payload = authored(context)
    original = deepcopy(payload)
    assert context.observations[context.packet["primary_observation_id"]]["type"] == "cash_flow_divergence"
    report, verification = assemble_briefing(FocusedBriefingInterpretation.model_validate(payload), context)
    assert verification.unsupported_count == 0
    assert "observation_ids" not in payload["primary_finding"]
    refs = {ref.source_id for ref in report.what_matters_most[0].financial_citations}
    assert refs == set(context.observations[context.packet["primary_observation_id"]]["source_ids"])
    assert "Operating cash flow increased while free cash flow declined" in report.performance[0].text
    assert all(item in report.investment_considerations[0].text for item in payload["primary_finding"]["limitations"])
    assert payload == original


def test_invalid_limitations_cannot_bypass_bounds_or_text_validation(setup):
    for value in ([], ["short"], [False], {"text": "Unexpected object"}, ["x" * 301],
                  ["x" * 150] * 3, ["An otherwise valid limitation."] * 4):
        payload = authored(setup[2])
        payload["primary_finding"]["limitations"] = value
        with pytest.raises(ValidationError):
            FocusedBriefingInterpretation.model_validate(payload)
    for value in (["Revenue was USD 999 billion in 2020."], ["All corporate capex is entirely AI-specific investment."],
                  ["Read the unapproved source at https://example.com/report."]):
        payload = authored(setup[2])
        payload["primary_finding"]["limitations"] = value
        with pytest.raises(ValueError):
            assemble_briefing(FocusedBriefingInterpretation.model_validate(payload), setup[2])


def test_missing_or_model_assigned_primary_is_not_repaired(setup):
    payload = authored(setup[2])
    del payload["primary_finding"]
    with pytest.raises(ValidationError):
        FocusedBriefingInterpretation.model_validate(payload)
    payload = authored(setup[2])
    payload["primary_finding"]["observation_ids"] = ["2026:cash_investment_tension"]
    with pytest.raises(ValidationError):
        FocusedBriefingInterpretation.model_validate(payload)


def test_unknown_or_duplicate_additional_findings_still_fail(setup):
    for change in ("unknown", "repeat_primary", "duplicate_additional"):
        payload = authored(setup[2])
        if change == "unknown":
            payload["findings"][0]["observation_ids"] = ["invented"]
        elif change == "repeat_primary":
            payload["findings"][0]["observation_ids"] = [setup[2].packet["primary_observation_id"]]
        else:
            payload["findings"].append(deepcopy(payload["findings"][0]))
        with pytest.raises(ValueError):
            assemble_briefing(FocusedBriefingInterpretation.model_validate(payload), setup[2])


def test_primary_selection_depends_on_eligible_observations_without_inventing_divergence(setup, monkeypatch):
    from alphalens import focused_briefing
    result, contexts, _ = setup
    analysis = focused_briefing.build_analytics(result)
    # Unit-test selection with that observation ineligible. Do not alter financial
    # values: the other eligible relationships remain genuine fixture calculations.
    analysis["tensions"] = [row for row in analysis["tensions"] if row["type"] != "cash_flow_divergence"]
    monkeypatch.setattr(focused_briefing, "build_analytics", lambda _: deepcopy(analysis))
    context = build_briefing_context(result, contexts)
    assert all(row["type"] != "cash_flow_divergence" for row in context.observations.values())
    assert context.packet["primary_observation_id"] in context.observations
    assert context.observations[context.packet["primary_observation_id"]]["type"] == "revenue_profit_growth"


def test_executive_disclosures_need_citations_but_valid_ids_do_not_prove_meaning(setup):
    context = setup[2]
    payload = authored(context)
    payload["executive_interpretation"]["interpretation"] = "Operating performance benefited from foreign currency movements and segment performance."
    with pytest.raises(ValueError, match="require supporting passage"):
        assemble_briefing(FocusedBriefingInterpretation.model_validate(payload), context)
    payload["executive_interpretation"]["supporting_passage_ids"] = ["sec:invented"]
    with pytest.raises(ValueError, match="Unknown or unapproved"):
        assemble_briefing(FocusedBriefingInterpretation.model_validate(payload), context)
    # Deliberately do not claim that an arbitrary real passage proves this statement.
    payload["executive_interpretation"]["supporting_passage_ids"] = [next(iter(context.packet["passages"]))]
    report, verification = assemble_briefing(FocusedBriefingInterpretation.model_validate(payload), context)
    executive = next(row for row in verification.claims if row.section == "executive_summary")
    assert executive.status == "interpretation" and executive.semantic_review == "requires_analyst_review"
    assert report.executive_summary[0].passage_citations


def test_default_gemini_sdk_contract_builds_auditable_export_without_losing_raw_lists(setup):
    payload = authored(setup[2])
    report, request = sdk_generate(setup, payload)
    assert report.contract == "focused_v2" and report.verification.unsupported_count == 0
    assert request["max_tokens"] == 3200
    assert set(request["response_format"]["json_schema"]["schema"]["properties"]) == set(GeminiBriefingFields.model_fields)
    assert "result_json" not in request["response_format"]["json_schema"]["schema"]["properties"]
    exported = json.loads(export_research_json(report))
    assert exported["raw_model_output"] == GeminiBriefingFields.from_compact(payload).model_dump(mode="json")
    assert exported["compact_model_interpretation"] == GeminiBriefingFields.from_compact(payload).compact_payload()
    assert exported["metadata"]["contract"] == "focused_v2"
    assert exported["metadata"]["semantic_review"] == "requires_analyst_review"
    assert "business_developments" not in exported["supported_sections"]
    assert "Operating cash flow increased while free cash flow declined" in export_research_markdown(report)
    report.model_interpretation["primary_finding"]["limitations"].append("A changed unvalidated limitation.")
    with pytest.raises(ValueError, match="changed after assembly"):
        export_research_json(report)
    for relabelled_contract in ("legacy", "unknown"):
        report.contract = relabelled_contract
        with pytest.raises(ValueError, match="changed after assembly"):
            export_research_json(report)


def test_actual_saved_rejection_is_not_upgraded_into_required_primary_analysis(setup):
    path = Path(__file__).resolve().parents[1] / "fixtures/gemini_compact_limitations_failure/COMPLETE_RESPONSE.json"
    body = json.loads(path.read_text(encoding="utf-8"))
    raw = json.loads(GeminiJSONEnvelope.model_validate_json(body["choices"][0]["message"]["content"]).result_json)
    original = deepcopy(raw)
    with pytest.raises(ValidationError) as caught:
        FocusedBriefingInterpretation.model_validate(raw)
    paths = {tuple(error["loc"]) for error in caught.value.errors()}
    assert ("primary_finding",) in paths
    assert ("executive_interpretation", "supporting_passage_ids") in paths
    assert not any(path[-1] == "limitations" for path in paths)
    with pytest.raises(AiError) as rejected:
        sdk_generate(setup, raw)
    assert rejected.value.diagnostics["schema_validation_result"] == "failed"
    assert raw == original
    malformed = Path(__file__).resolve().parents[1] / "fixtures/gemini_inner_json_failure/COMPLETE_RESPONSE.json"
    complete = json.loads(malformed.read_text(encoding="utf-8"))
    content = complete["choices"][0]["message"]["content"]
    inner = GeminiJSONEnvelope.model_validate_json(content).result_json
    with pytest.raises(json.JSONDecodeError):
        json.loads(inner)  # Actual {"string":"text"0} defect, not an invented syntax example.
    with pytest.raises(ValidationError):
        GeminiBriefingFields.model_validate_json(content)  # No automatic upgrade/repair.


def test_openai_focused_selection_keeps_original_sdk_and_new_local_contract(setup):
    result, contexts, context = setup
    payload = FocusedBriefingInterpretation.model_validate(authored(context))
    client = Mock()
    client.responses.parse.return_value = SimpleNamespace(status="completed", output_parsed=payload)
    report = generate_research_brief(result, "offline-key", "gpt-4.1-mini", provider="openai", contract="focused",
        filing_contexts=contexts, client=client)
    assert report.contract == "focused_v2" and report.verification.unsupported_count == 0
    assert client.responses.parse.call_args.kwargs["text_format"] is FocusedBriefingInterpretation
    assert client.responses.parse.call_args.kwargs["store"] is False
    client.responses.parse.assert_called_once()
    client.chat.completions.parse.assert_not_called()


def test_native_wire_still_rejects_financial_prose_overclaims_and_unknown_sources(setup):
    for change in ("numeric", "all_ai", "unknown_observation", "unknown_passage"):
        payload = authored(setup[2])
        if change == "numeric":
            payload["primary_finding"]["limitations"] = ["Revenue reached USD 999 billion during the period."]
        elif change == "all_ai":
            payload["primary_finding"]["interpretation"] = "All corporate capex is entirely AI-specific investment."
        elif change == "unknown_observation":
            payload["findings"][0]["observation_ids"] = ["invented"]
        else:
            payload["risks"][0]["supporting_passage_ids"] = ["sec:invented"]
        with pytest.raises(AiError):
            sdk_generate(setup, payload)


def test_flat_conversion_never_discards_extra_findings_or_raw_transport_mutation(setup):
    payload = authored(setup[2])
    payload["findings"].append(deepcopy(payload["findings"][0]))
    with pytest.raises(ValueError, match="requires one primary"):
        GeminiBriefingFields.from_compact(payload)
    report, _ = sdk_generate(setup, authored(setup[2]))
    report.transport_output["primary_interpretation"] = "An altered raw transport interpretation."
    with pytest.raises(ValueError, match="changed after assembly"):
        export_research_json(report)
