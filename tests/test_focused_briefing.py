"""Compact-contract tests use genuine SEC fixtures and authored model prose."""
from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
from openai import OpenAI
from pydantic import ValidationError
import pytest

from alphalens.ai import AiError, generate_research_brief
from alphalens.focused_briefing import (BriefingInterpretation, assemble_briefing,
    build_briefing_context, generate_focused_briefing)
from alphalens.providers import GEMINI_BASE_URL
from alphalens.research_exports import export_research_json, export_research_markdown
from alphalens.service import load_offline_filing_context, load_research


@pytest.fixture
def setup():
    result = load_research("MSFT", "offline")
    contexts = [load_offline_filing_context(result)]
    context = build_briefing_context(result, contexts)
    return result, contexts, context


def authored(context):
    cash = next(k for k, v in context.observations.items() if v["type"] == "cash_flow_divergence")
    positive = next(k for k, v in context.observations.items() if v["type"] == "revenue_profit_growth")
    passage = next(iter(context.packet["passages"]))
    return {
        "executive_interpretation": {"observation_ids": [cash],
            "interpretation": "Investment may absorb cash before the resulting capacity can demonstrate sustainable cash returns."},
        "findings": [
            {"observation_ids": [cash], "interpretation": "The cash divergence may reflect investment ahead of monetisation rather than weak operating demand.",
             "supporting_passage_ids": [passage], "alternative_explanation": "Payment timing could also affect cash conversion without changing long-run project economics.",
             "limitations": "AI-attributable cash flows and invested capital are not isolated in the packet."},
            {"observation_ids": [positive], "interpretation": "Operating performance may provide resources for reinvestment without establishing its future economic return.",
             "supporting_passage_ids": [], "alternative_explanation": "Product mix and expense timing could contribute to the reported operating relationship.",
             "limitations": "Consolidated results do not establish the economics of incremental infrastructure."}],
        "risks": [{"interpretation": "The disclosed infrastructure and competitive conditions may complicate project economics.",
            "supporting_passage_ids": [passage], "limitations": "A disclosed possibility is not proof of a realised adverse outcome."}],
        "unanswered_questions": ["What attributable profit and invested capital would support measurement of incremental ROIC?",
            "Which utilisation and monetisation disclosures could distinguish investment timing from persistent cash-return pressure?"],
    }


def mocked_generate(setup, payload, *, provider="gemini", response_content=None, finish="stop"):
    result, contexts, _ = setup
    captured = []
    def handle(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "AUTHORED-NOT-LIVE", "object": "chat.completion", "created": 0,
            "model": "gemini-3.5-flash-lite", "choices": [{"index": 0, "finish_reason": finish,
            "message": {"role": "assistant", "content": response_content or json.dumps({"result_json": json.dumps(payload)})}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 34, "total_tokens": 46}})
    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        with OpenAI(api_key="offline-focused-mock", base_url=GEMINI_BASE_URL, max_retries=0, http_client=http) as client:
            try:
                report = generate_research_brief(result, "offline-focused-mock", "gemini-3.5-flash-lite",
                    provider=provider, filing_contexts=contexts, client=client, contract="focused_v1")
            finally:
                assert len(captured) == 1  # Including malformed output: no repair call/retry.
    return report, captured[0]


def test_actual_msft_data_supports_cash_divergence_without_hardcoded_rule(setup):
    result, _, context = setup
    divergence = next(v for v in context.observations.values() if v["type"] == "cash_flow_divergence")
    by = {c["metric"]: c for c in divergence["comparisons"]}
    assert by["operating_cash_flow"]["current"]["value"] > by["operating_cash_flow"]["prior"]["value"]
    assert by["capital_expenditure"]["current"]["value"] > by["capital_expenditure"]["prior"]["value"]
    assert by["free_cash_flow"]["current"]["value"] < by["free_cash_flow"]["prior"]["value"]
    assert all(c["formula"] for c in divergence["changes"])
    assert divergence["comparability_warnings"]
    assert divergence["current_period"]["period_end"] == result.periods[-1].end
    assert all(key in context.evidence for key in divergence["source_ids"])


def test_compact_schema_removes_python_owned_fields_and_classifications(setup):
    _, _, context = setup
    parsed = BriefingInterpretation.model_validate(authored(context))
    text = json.dumps(parsed.model_dump())
    assert all(token not in text for token in ('"kind"', '"quote"', '"financial_citations"', '"fiscal_year"'))
    note, verification = assemble_briefing(parsed, context)
    assert verification.unsupported_count == 0
    assert len(note.what_matters_most) == 2
    assert all(c.kind == "inference" for c in note.what_matters_most)
    assert all(c.kind == "question" for c in note.missing_information)
    assert all(citation.value == context.evidence[citation.source_id]["value"] for claim in note.performance
               for citation in claim.financial_citations)
    assert all(len(c.quote) <= 600 and c.quote == context.evidence[c.source_id]["text"]
               for claim in note.what_matters_most for c in claim.passage_citations)


def test_context_is_compact_and_full_provenance_stays_local(setup):
    _, _, context = setup
    packet = json.dumps(context.packet)
    assert "source_catalog" not in context.packet
    assert "sources" not in context.packet
    assert len(packet) < 20000
    assert all(len(p["text"]) <= 600 for p in context.packet["passages"].values())
    assert all("sources" in p for p in context.evidence.values() if p["kind"] == "financial")
    assert len(context.evidence) > len(context.packet["passages"])


def test_executive_can_interpret_a_verified_observation_outside_detailed_findings(setup):
    context = setup[2]
    payload = authored(context)
    key = next(k for k, row in context.observations.items() if row["type"] == "investment_intensity")
    assert key not in {f["observation_ids"][0] for f in payload["findings"]}
    payload["executive_interpretation"] = {"observation_ids": [key],
        "interpretation": "Investment intensity may constrain financial flexibility before new capacity is monetised."}
    report, verification = assemble_briefing(BriefingInterpretation.model_validate(payload), context)
    assert verification.unsupported_count == 0
    assert {ref.source_id for ref in report.executive_summary[0].financial_citations} == set(context.observations[key]["source_ids"])
    assert len(report.what_matters_most) == 2


@pytest.mark.parametrize("change", ["unknown_observation", "incorrect_direction", "invented_figure"])
def test_independent_executive_still_requires_real_support_and_qualitative_prose(setup, change):
    context = setup[2]
    payload = authored(context)
    key = next(k for k, row in context.observations.items() if row["type"] == "investment_intensity")
    payload["executive_interpretation"]["observation_ids"] = [key]
    if change == "unknown_observation":
        payload["executive_interpretation"]["observation_ids"] = ["2020:invented"]
    elif change == "incorrect_direction":
        payload["executive_interpretation"]["interpretation"] = "Capital expenditure declined between the cited annual periods."
    else:
        payload["executive_interpretation"]["interpretation"] = "Capital expenditure reached USD 999 billion in 2024."
    with pytest.raises(ValueError):
        assemble_briefing(BriefingInterpretation.model_validate(payload), context)


def test_post_schema_rejection_is_not_recorded_as_completed(setup):
    payload = authored(setup[2])
    payload["executive_interpretation"]["observation_ids"] = ["fabricated"]
    with pytest.raises(AiError) as caught:
        mocked_generate(setup, payload)
    details = caught.value.diagnostics
    assert details["parsing_result"] == details["schema_validation_result"] == "passed"
    assert details["status"] == "validation_failed"
    assert details["validation_stage"] == "financial_sources"
    assert details["source_validation_result"] == "failed"


@pytest.mark.parametrize("change", ["missing", "wrong_type", "extra_kind", "extra_figure", "empty", "question_object"])
def test_malformed_model_owned_contract_is_rejected_without_substantive_repair(setup, change):
    payload = authored(setup[2])
    if change == "missing":
        del payload["findings"][0]["alternative_explanation"]
    elif change == "wrong_type":
        payload["findings"][0]["limitations"] = []
    elif change == "extra_kind":
        payload["findings"][0]["kind"] = "fact"
    elif change == "extra_figure":
        payload["findings"][0]["revenue"] = 1
    elif change == "empty":
        payload["findings"] = []
    else:
        payload["unanswered_questions"][0] = {"text": "What information is missing?"}
    before = deepcopy(payload)
    with pytest.raises(ValidationError):
        BriefingInterpretation.model_validate(payload)
    assert payload == before


@pytest.mark.parametrize("change", ["bad_obs", "wrong_year", "bad_source", "missing_prefix", "duplicate", "omit_divergence", "numeric", "all_ai", "roic", "wrong_comparison"])
def test_invalid_provenance_numbers_and_overclaims_are_not_accepted(setup, change):
    context = setup[2]
    payload = authored(context)
    if change == "bad_obs":
        payload["findings"][0]["observation_ids"] = ["fabricated"]
    elif change == "wrong_year":
        payload["findings"][0]["observation_ids"] = ["2020:cash_flow_divergence"]
    elif change == "bad_source":
        payload["findings"][0]["supporting_passage_ids"] = ["sec:invented"]
    elif change == "missing_prefix":
        payload["findings"][0]["supporting_passage_ids"][0] = payload["findings"][0]["supporting_passage_ids"][0][4:]
    elif change == "duplicate":
        payload["findings"][1]["observation_ids"] = payload["findings"][0]["observation_ids"]
    elif change == "omit_divergence":
        other = next(k for k, v in context.observations.items() if v["type"] == "investment_intensity")
        payload["findings"][0]["observation_ids"] = [other]
        payload["executive_interpretation"]["observation_ids"] = [other]
    else:
        payload["findings"][0]["interpretation"] = {
            "numeric": "Operating cash flow was USD 999 billion in 2024.",
            "all_ai": "All corporate capex is entirely AI-specific investment.",
            "roic": "Infrastructure investment has improved ROIC materially.",
            "wrong_comparison": "Operating cash flow declined between the cited annual periods.",
        }[change]
    with pytest.raises(ValueError):
        assemble_briefing(BriefingInterpretation.model_validate(payload), context)


def test_gemini_real_sdk_mock_uses_envelope_and_builds_exportable_report(setup):
    report, request = mocked_generate(setup, authored(setup[2]))
    assert set(request["response_format"]["json_schema"]["schema"]["properties"]) == {"result_json"}
    assert request["max_tokens"] == 3200
    assert report.contract == "focused_v1" and report.verification.unsupported_count == 0
    exported = json.loads(export_research_json(report))
    assert exported["raw_model_output"] == authored(setup[2])
    assert "kind" not in json.dumps(exported["raw_model_output"])
    assert exported["assembled_report"]["missing_information"][0]["kind"] == "question"
    assert exported["financial_observations"]
    assert exported["metadata"]["semantic_review"] == "requires_analyst_review"
    assert "OFFLINE DEMONSTRATION" in export_research_markdown(report)


@pytest.mark.parametrize("content,finish", [("{}", "stop"), ('{"result_json":"{broken"}', "stop"), ('{"result_json":"{}"}', "length")])
def test_malformed_or_truncated_envelopes_fail_safely_without_retry(setup, content, finish):
    with pytest.raises(AiError):
        mocked_generate(setup, {}, response_content=content, finish=finish)


def test_context_or_output_mutation_invalidates_assembly_and_exports(setup):
    context = deepcopy(setup[2])
    context.packet["annual_comparison"][0]["values"][0]["value"] = 1
    with pytest.raises(ValueError, match="changed"):
        assemble_briefing(BriefingInterpretation.model_validate(authored(setup[2])), context)
    report, _ = mocked_generate(setup, authored(setup[2]))
    report.model_interpretation["findings"][0]["interpretation"] = "Changed and unvalidated interpretation."
    with pytest.raises(ValueError, match="changed"):
        export_research_json(report)


def test_optional_openai_adapter_supports_explicit_focused_contract(setup):
    result, contexts, context = setup
    client = Mock()
    client.responses.parse.return_value = SimpleNamespace(status="completed",
        output_parsed=BriefingInterpretation.model_validate(authored(context)))
    report = generate_research_brief(result, "mock-no-network", "gpt-4.1-mini", provider="openai",
        contract="focused_v1", filing_contexts=contexts, client=client)
    assert report.verification.unsupported_count == 0
    assert client.responses.parse.call_args.kwargs["text_format"] is BriefingInterpretation
    assert client.responses.parse.call_args.kwargs["store"] is False
    assert not client.chat.completions.parse.called


def test_missing_key_or_missing_financial_inputs_never_invent_findings(setup):
    result, contexts, _ = setup
    with pytest.raises(AiError, match="API key"):
        generate_focused_briefing(result, "", "configured-model", filing_contexts=contexts)
    missing = deepcopy(result)
    for p in missing.periods:
        for metric in p.metrics.values():
            metric.value = None
    with pytest.raises(ValueError, match="Insufficient"):
        build_briefing_context(missing, contexts)


def test_real_historical_failures_remain_rejected_and_are_not_relabelled_as_success():
    root = Path(__file__).resolve().parents[1]
    for name in ("gemini_schema_failure", "gemini_quote_failure"):
        body = json.loads((root / "fixtures" / name / "brief.complete_response.json").read_text(encoding="utf-8"))
        inner = json.loads(json.loads(body["choices"][0]["message"]["content"])["result_json"])
        with pytest.raises(ValidationError):
            BriefingInterpretation.model_validate(inner)


def test_streamlit_focused_sdk_workflow_displays_and_exports_without_extra_generation(setup, monkeypatch):
    from streamlit.testing.v1 import AppTest
    from alphalens import providers
    from alphalens.gemini_briefing import GeminiFindingFields
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "ui-mock-no-real-key")
    payload, calls = authored(setup[2]), []
    # Authored fixture for the revised production contract; never a live-output repair.
    primary = payload["findings"].pop(0)
    del primary["observation_ids"]
    payload["primary_finding"] = primary
    # The production v3 UI requests findings only; Python assembles the
    # executive from those same validated claims without a model summary.
    del payload["executive_interpretation"]
    def handle(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "AUTHORED-UI-NOT-LIVE", "object": "chat.completion", "created": 0,
            "model": "gemini-3.5-flash-lite", "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": GeminiFindingFields.from_compact(payload).model_dump_json()}}]})
    real_request = providers.request_structured
    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        with OpenAI(api_key="mock-client-key", base_url=GEMINI_BASE_URL, http_client=http, max_retries=0) as client:
            def injected(**kwargs):
                return real_request(**{**kwargs, "client": client})
            monkeypatch.setattr(providers, "request_structured", injected)
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(timeout=30)
            assert not app.exception and not calls
            consent = next(c for c in app.checkbox if c.key.startswith("research_brief_consent_"))
            consent.check().run(timeout=30)
            app.button(key="generate_research_brief").click().run(timeout=30)
            assert not app.exception
            assert len(calls) == 1
            validated = app.session_state["research_brief_result"]
            assert validated.contract == "focused_v3"
            assert len(calls[0]["response_format"]["json_schema"]["schema"]["properties"]) == 13
            assert not any(key.startswith("executive_") for key in validated.transport_output)
            assert validated.output.executive_summary == validated.output.what_matters_most
            assert validated.output.executive_summary[0] is not validated.output.what_matters_most[0]
            assert any("Python assembles figures" in c.value for c in app.caption)
            assert any(e.label == "Inspect Python financial observations" for e in app.expander)
            app.toggle(key="research_brief_export_toggle").set_value(True).run(timeout=30)
            assert not app.exception and len(calls) == 1
            assert len(app.get("download_button")) == 4
