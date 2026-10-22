"""Authored mock commentary over genuine cached Amazon accounting evidence.

The actual rejected Gemini prose was not retained. These are targeted regression
examples of a demonstrated lexical false positive, not replays of that prose.
No test contacts SEC, Google or OpenAI.
"""
from dataclasses import replace
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import httpx
from openai import OpenAI
import pytest

from alphalens.ai import AiError, generate_brief
from alphalens.commentary import build_commentary_context
from alphalens.evidence import evidence_fingerprint
from alphalens.models import AnnualPeriod, MetricValue, ResearchResult, SourceFact
from alphalens.providers import GEMINI_BASE_URL


FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/commentary_amzn_2026-10-19"
MODEL = "gemini-3.5-flash-lite"
KEY = "authored-amazon-commentary-key-not-real"


@pytest.fixture
def amazon(monkeypatch, tmp_path):
    from alphalens import observability

    monkeypatch.setattr(observability, "ROOT", tmp_path)
    raw = (FIXTURE / "AMZN_SNAPSHOT.json").read_bytes()
    manifest = json.loads((FIXTURE / "MANIFEST.json").read_text(encoding="utf-8"))
    assert hashlib.sha256(raw).hexdigest() == manifest["snapshot_sha256"]
    data = json.loads(raw)
    data["periods"] = [AnnualPeriod(**{
        **period, "metrics": {key: MetricValue(**{
            **metric, "sources": [SourceFact(**source) for source in metric["sources"]]
        }) for key, metric in period["metrics"].items()}
    }) for period in data["periods"]]
    return ResearchResult(**data)


def authored(question):
    return {
        "primary_interpretation": (
            "Revenue and operating income increased; the operating margin improvement "
            "may provide additional capacity to fund future investment."),
        "questions": [question],
        "caveats": [
            "Consolidated financial evidence does not establish the causes or durability of profitability gains."],
    }


def invoke(amazon, payload, calls):
    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={
            "id": "AUTHORED-AMAZON-COMMENTARY", "object": "chat.completion",
            "created": 0, "model": MODEL,
            "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": json.dumps(payload)}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        })

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        with OpenAI(api_key=KEY, base_url=GEMINI_BASE_URL, max_retries=0, http_client=http) as client:
            return generate_brief(amazon, KEY, MODEL, provider="gemini", contract="bound_v1", client=client)


def test_cached_amazon_reproduces_actual_failed_issuer_context_without_imputing_capex(amazon):
    manifest = json.loads((FIXTURE / "MANIFEST.json").read_text(encoding="utf-8"))
    assert amazon.ticker == "AMZN" and amazon.cik == "0001018724"
    assert amazon.mode == "offline" and "TEST-ONLY CACHED SEC SNAPSHOT" in amazon.warnings[0]
    assert [period.fiscal_year for period in amazon.periods] == [2023, 2024, 2025]
    context = build_commentary_context(amazon)
    assert evidence_fingerprint(context.evidence) == manifest["offline_evidence_fingerprint"]
    original_context = build_commentary_context(replace(amazon, mode="live"))
    assert evidence_fingerprint(original_context.evidence) == manifest["original_live_evidence_fingerprint"]
    assert manifest["original_live_evidence_fingerprint"] == (
        "73f299853876d31b1f81fe5d314e6b86936b2e428ac2e1d096b297c33771c936")
    assert manifest["original_model_text_available"] is False
    assert manifest["selected_source_components_checked"] == 48
    assert [row["id"] for row in context.observations] == ["2025:revenue_profit_growth"]
    for period in amazon.periods:
        for metric in ("capital_expenditure", "free_cash_flow"):
            assert period.metrics[metric].value is None
            assert period.metrics[metric].reason
            assert f"{period.fiscal_year}:{metric}" not in context.evidence
        assert not period.metrics["capital_expenditure"].sources
        # The unavailable derived FCF retains its available OCF dependency for
        # inspection; this must not turn the missing FCF into a usable amount.
        assert period.metrics["free_cash_flow"].sources == period.metrics["operating_cash_flow"].sources
    assert amazon.periods[-1].metrics["revenue"].value == 716_924_000_000
    assert amazon.periods[-1].metrics["operating_income"].value == 79_975_000_000


@pytest.mark.parametrize("question", [
    "What evidence would distinguish recurring profitability gains from one-off items?",
    "Could one-time items explain part of the profitability improvement?",
    "What percentage of reported operating income might reflect non-recurring items?",
])
def test_qualitative_amazon_diligence_questions_do_not_require_financial_quantities(amazon, question):
    context = build_commentary_context(amazon)
    before = evidence_fingerprint(context.evidence)
    payload, calls = authored(question), []
    output = invoke(amazon, payload, calls)
    assert len(calls) == 1 and calls[0].url.host == "generativelanguage.googleapis.com"
    assert output.questions == [question]  # No prose repair or quantity deletion.
    assert len(output.observations) == 1
    assert output.observations[0].text == payload["primary_interpretation"]
    assert output.observations[0].evidence_ids == context.observations[0]["source_ids"]
    assert evidence_fingerprint(build_commentary_context(amazon).evidence) == before
    body = json.loads(calls[0].content)
    assert "additional_interpretation" not in body["response_format"]["json_schema"]["schema"]["properties"]
    assert KEY not in json.dumps(body)


@pytest.mark.parametrize("question", [
    "Could one billion dollars of non-recurring gains explain the improvement?",
    "Could forty percent of operating income reflect non-recurring items?",
    "What explains the profitability improvement in 2025?",
    "Why has operating income doubled in the latest reporting period?",
    "Could a one-off gain of one billion dollars explain the improvement?",
])
def test_amazon_question_language_cannot_smuggle_financial_amounts_or_periods(amazon, question):
    payload, calls = authored(question), []
    original = deepcopy(payload)
    with pytest.raises(AiError) as caught:
        invoke(amazon, payload, calls)
    assert len(calls) == 1
    assert caught.value.diagnostics["parsing_result"] == "passed"
    assert caught.value.diagnostics["schema_validation_result"] == "passed"
    assert caught.value.diagnostics["numerical_validation_result"] == "failed"
    assert caught.value.diagnostics["validation_issues"] == [
        {"path": "questions[0]", "type": "numerical_prose"}]
    audit_text = Path(caught.value.diagnostics["audit_path"]).read_text(encoding="utf-8")
    assert json.loads(audit_text)["validation_issues"] == [
        {"path": "questions[0]", "type": "numerical_prose"}]
    assert question not in audit_text and KEY not in audit_text
    assert payload == original
    assert KEY not in str(caught.value)

