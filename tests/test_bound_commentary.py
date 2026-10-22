"""Model interpretation over Python-bound annual observations; offline HTTP only."""
from copy import deepcopy
import json
from unittest.mock import Mock

import httpx
from openai import OpenAI
import pytest

from alphalens.ai import AiError, ResearchBrief, generate_brief
from alphalens.providers import GEMINI_BASE_URL
from alphalens.service import load_research


MODEL = "gemini-3.5-flash-lite"
KEY = "authored-bound-commentary-key-not-real"


@pytest.fixture
def result(monkeypatch, tmp_path):
    from alphalens import observability
    monkeypatch.setattr(observability, "ROOT", tmp_path)
    return load_research("MSFT", "offline")


def authored():
    return {
        "primary_interpretation": (
            "Operating cash flow rose while free cash flow declined; the investment schedule may warrant closer scrutiny."),
        "additional_interpretation": (
            "Revenue and operating income increased, which may provide resources for continued investment."),
        "questions": ["How could capacity utilisation affect subsequent cash generation?"],
        "caveats": ["Historical financial comparisons do not establish future investment returns."],
    }


def invoke(result, payload, calls, *, content=None, status=200, finish="stop", after_request=None):
    def handle(request):
        calls.append(request)
        if after_request is not None:
            after_request()
        response = {
            "id": "AUTHORED-BOUND-COMMENTARY", "object": "chat.completion", "created": 0, "model": MODEL,
            "choices": [{"index": 0, "finish_reason": finish, "message": {
                "role": "assistant", "content": json.dumps(payload) if content is None else content}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        }
        return httpx.Response(status, json=response if status == 200 else {
            "error": {"message": "private-provider-text", "type": "invalid_request_error"}})
    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        with OpenAI(api_key=KEY, base_url=GEMINI_BASE_URL, max_retries=0, http_client=http) as client:
            return generate_brief(result, KEY, MODEL, provider="gemini", contract="bound_v1", client=client)


def test_native_commentary_attaches_exact_latest_python_sources_without_model_ids(result):
    from alphalens.commentary import build_commentary_context
    context = build_commentary_context(result)
    payload, calls = authored(), []
    output = invoke(result, payload, calls)
    assert isinstance(output, ResearchBrief)
    assert [item.text for item in output.observations] == [payload["primary_interpretation"], payload["additional_interpretation"]]
    assert [item.evidence_ids for item in output.observations] == [row["source_ids"] for row in context.observations]
    assert len(context.observations) == 2
    assert {row["current_period"]["fiscal_year"] for row in context.observations} == {2026}
    assert {row["prior_period"]["fiscal_year"] for row in context.observations} == {2025}
    assert context.observations[0]["type"] == "cash_flow_divergence"
    assert context.observations[1]["type"] == "revenue_profit_growth"
    for item in output.observations:
        assert 1 <= len(item.evidence_ids) <= 6
        assert len(item.evidence_ids) == len(set(item.evidence_ids))
        assert all(key in context.evidence and key in context.catalog for key in item.evidence_ids)
    assert len(calls) == 1 and calls[0].url.host == "generativelanguage.googleapis.com"
    body = json.loads(calls[0].content)
    schema = body["response_format"]["json_schema"]["schema"]
    assert set(schema["properties"]) == set(payload)
    assert "$defs" not in schema and "result_json" not in schema["properties"]
    assert json.loads(body["messages"][1]["content"]) == context.packet
    assert "ORIGINAL OUTPUT SCHEMA:" not in body["messages"][0]["content"]
    assert KEY not in json.dumps(body)


@pytest.mark.parametrize("extra", [
    {"evidence_ids": ["2026:invented-source"]},
    {"primary_evidence_ids": ["2026:revenue"]},
    {"source_id": "2026:total_debt"},
])
def test_model_cannot_choose_or_invent_financial_source_ids(result, extra):
    payload = {**authored(), **extra}
    original, calls = deepcopy(payload), []
    with pytest.raises(AiError) as caught:
        invoke(result, payload, calls)
    assert payload == original and len(calls) == 1
    assert caught.value.diagnostics["schema_validation_result"] == "failed"
    assert any(item["type"] == "extra_forbidden" for item in caught.value.diagnostics["validation_issues"])
    assert KEY not in str(caught.value)


@pytest.mark.parametrize("text", [
    "Operating cash flow grew by 100 percent in the latest period.",
    "Free cash flow increased significantly in the latest annual period.",
    "FCF increased significantly in the latest annual period.",
    "AI infrastructure ROIC is attractive and guarantees future economic returns.",
    "The company is undervalued and merits a buy rating.",
])
def test_bound_interpretation_still_faces_numerical_comparative_and_overclaim_checks(result, text):
    payload = authored()
    payload["primary_interpretation"] = text
    original, calls = deepcopy(payload), []
    with pytest.raises(AiError) as caught:
        invoke(result, payload, calls)
    assert len(calls) == 1 and payload == original
    # Correct JSON has already parsed: a later claim failure must not be
    # diagnosed as invalid transport JSON, the original user-facing confusion.
    assert caught.value.diagnostics["parsing_result"] == "passed"
    assert caught.value.diagnostics["schema_validation_result"] == "passed"
    if text.startswith(("Free cash flow", "FCF")):
        assert caught.value.diagnostics["source_validation_result"] == "passed"
        assert caught.value.diagnostics["numerical_validation_result"] == "failed"
        assert caught.value.diagnostics["validation_stage"] == "financial_sources"
    assert KEY not in str(caught.value)


def test_required_interpretation_is_not_synthesised_when_missing(result):
    payload, calls = authored(), []
    del payload["primary_interpretation"]
    with pytest.raises(AiError) as caught:
        invoke(result, payload, calls)
    assert len(calls) == 1
    assert any(item == {"path": "primary_interpretation", "type": "missing"}
               for item in caught.value.diagnostics["validation_issues"])


def test_truncated_json_fails_safely_without_repair_retry_or_fallback(result):
    calls = []
    with pytest.raises(AiError) as caught:
        invoke(result, authored(), calls, content='{"primary_interpretation":"unfinished')
    assert len(calls) == 1
    assert caught.value.diagnostics["parsing_result"] == "failed"
    assert caught.value.diagnostics["schema_validation_result"] == "not_run"
    assert "unfinished" not in str(caught.value) and KEY not in str(caught.value)


def test_insufficient_comparable_observations_abstains_before_request(result):
    result.periods = result.periods[-1:]
    client = Mock()
    with pytest.raises(AiError, match="(?i)observations?|comparable|annual"):
        generate_brief(result, KEY, MODEL, provider="gemini", contract="bound_v1", client=client)
    assert not client.mock_calls


def test_single_independent_development_uses_smaller_wire_without_inventing_second_claim(result):
    from alphalens.commentary import build_commentary_context
    # Preserve real OCF/cash-PP&E evidence but remove operating-performance
    # inputs. Related cash-investment rules are not independent developments.
    for period in result.periods:
        for key in ("revenue", "operating_income", "operating_margin", "net_income"):
            metric = period.metrics[key]
            metric.value, metric.sources, metric.reason = None, [], "Unavailable in this authored edge-case input."
    context = build_commentary_context(result)
    assert len(context.observations) == 1
    payload, calls = authored(), []
    del payload["additional_interpretation"]
    output = invoke(result, payload, calls)
    assert len(output.observations) == 1
    assert output.observations[0].evidence_ids == context.observations[0]["source_ids"]
    assert output.observations[0].text == payload["primary_interpretation"]
    assert len(calls) == 1
    body = json.loads(calls[0].content)
    assert set(body["response_format"]["json_schema"]["schema"]["properties"]) == set(payload)
    assert len(payload) == 3


@pytest.mark.parametrize("status", [429, 503])
def test_bound_commentary_does_not_retry_or_switch_provider_when_request_fails(result, status):
    calls = []
    with pytest.raises(AiError) as caught:
        invoke(result, authored(), calls, status=status)
    assert len(calls) == 1 and calls[0].url.host == "generativelanguage.googleapis.com"
    assert caught.value.diagnostics["http_status"] == status
    assert "private-provider-text" not in str(caught.value)


def test_openai_cannot_be_selected_through_explicit_gemini_bound_contract(result):
    client = Mock()
    with pytest.raises(AiError):
        generate_brief(result, KEY, MODEL, provider="openai", contract="bound_v1", client=client)
    assert not client.mock_calls


@pytest.mark.parametrize("text", [
    "Net income increased significantly over the latest annual period.",
    "Diluted EPS improved, which may indicate stronger profitability.",
])
def test_primary_interpretation_cannot_import_unassigned_earnings_metrics(result, text):
    payload, calls = authored(), []
    payload["primary_interpretation"] = text
    with pytest.raises(AiError, match="outside its assigned observation"):
        invoke(result, payload, calls)
    assert len(calls) == 1


@pytest.mark.parametrize("text", [
    "The company invested one billion dollars in infrastructure.",
    "All capital expenditure is entirely AI investment.",
    "ROIC is attractive despite uncertainty about timing.",
])
def test_caveat_field_is_not_a_bypass_for_numbers_capex_attribution_or_return_claims(result, text):
    payload, calls = authored(), []
    payload["caveats"] = [text]
    with pytest.raises(AiError) as caught:
        invoke(result, payload, calls)
    assert len(calls) == 1
    assert caught.value.diagnostics["parsing_result"] == "passed"
    assert caught.value.diagnostics["numerical_validation_result"] == "failed"


def test_context_mutation_during_response_is_rejected_instead_of_rebinding_sources(result, monkeypatch):
    from alphalens import commentary
    context = commentary.build_commentary_context(result)
    monkeypatch.setattr(commentary, "build_commentary_context", lambda _: context)
    calls = []
    def mutate():
        context.packet["company"]["name"] = "Changed after outbound request"
    with pytest.raises(AiError, match="context changed during generation"):
        invoke(result, authored(), calls, after_request=mutate)
    assert len(calls) == 1


def test_overfull_python_dependencies_abstain_without_dropping_a_source(result, monkeypatch):
    from alphalens import commentary
    analysis = commentary.build_analytics(result)
    row = next(item for item in analysis["tensions"]
               if item["id"] == "2026:cash_flow_divergence")
    book = commentary.build_evidence_book(result)
    additions = [key for key in book if key not in row["source_ids"]]
    row["source_ids"].extend(additions[:7 - len(row["source_ids"])] )
    assert len(row["source_ids"]) == 7 and all(key in book for key in row["source_ids"])
    monkeypatch.setattr(commentary, "build_analytics", lambda _: analysis)
    client = Mock()
    with pytest.raises(AiError, match="source dependencies"):
        generate_brief(result, KEY, MODEL, provider="gemini", contract="bound_v1", client=client)
    assert not client.mock_calls and len(row["source_ids"]) == 7


def test_valid_ocf_fcf_abbreviations_are_checked_without_rewriting_returned_model_text(result):
    payload, calls = authored(), []
    payload["primary_interpretation"] = (
        "OCF rose while FCF declined; the investment schedule may warrant closer scrutiny.")
    output = invoke(result, payload, calls)
    assert len(calls) == 1
    assert output.observations[0].text == payload["primary_interpretation"]


def test_streamlit_native_bound_commentary_uses_sdk_once_and_displays_python_sources(result, monkeypatch):
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    from alphalens import commentary

    context = commentary.build_commentary_context(result)
    payload, calls = authored(), []
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "ui-bound-mock-key")
    monkeypatch.setenv("GEMINI_MODEL", MODEL)
    original_request = commentary.request_structured

    def handle(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={
            "id": "AUTHORED-BOUND-UI", "object": "chat.completion", "created": 0, "model": MODEL,
            "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": json.dumps(payload)}}],
        })
    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        with OpenAI(api_key=KEY, base_url=GEMINI_BASE_URL, max_retries=0, http_client=http) as client:
            def injected(**kwargs):
                return original_request(**{**kwargs, "client": client})
            monkeypatch.setattr(commentary, "request_structured", injected)
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(timeout=30)
            assert not app.exception and not calls
            consent = next(item for item in app.checkbox if item.key.startswith("ai_consent_"))
            consent.check().run(timeout=30)
            app.button(key="generate_ai").click().run(timeout=30)
            assert not app.exception and len(calls) == 1
            output = app.session_state["ai_brief"]
            assert output is not None
            assert [item.evidence_ids for item in output.observations] == [row["source_ids"] for row in context.observations]
            assert set(calls[0]["response_format"]["json_schema"]["schema"]["properties"]) == set(payload)
            source_tables = [item.value for item in app.dataframe if "Evidence ID" in item.value.columns]
            assert len(source_tables) == 2
            assert {key for table in source_tables for key in table["Evidence ID"]} == {
                key for row in context.observations for key in row["source_ids"]}
            assert app.button(key="generate_ai").disabled
            assert len(app.metric) == 4 and len(app.get("download_button")) == 2
            app.run(timeout=30)
            assert not app.exception and len(calls) == 1
