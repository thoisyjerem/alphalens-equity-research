"""V1.1 economic framing is evidence-bound and never upgrades hypotheses.

Real recorded Microsoft evidence is replayed unchanged. The small alternative
issuer below is explicitly synthetic; it is not a Visa research result.
"""
from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal
import json
from pathlib import Path

import pytest

from alphalens.analytics import build_analytics
from alphalens.evidence import build_evidence_book
from alphalens.financials import extract_annuals
from alphalens.focused_briefing import build_briefing_context, generate_focused_briefing
from alphalens.gemini_briefing import GeminiFindingFields
from alphalens.investment_reasoning import build_investment_reasoning, segment_context_flags
from alphalens.models import ResearchResult
from alphalens.recorded_readout import build_recorded_readout
from alphalens.saved_research import load_saved_briefing
from alphalens.service import load_offline_filing_context, load_research


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "outputs/msft_findings_live_2026-10-18"


@pytest.fixture
def recorded():
    return load_saved_briefing()


def _reasoning(saved):
    return build_investment_reasoning(saved.evidence, saved.analysis, saved.financial_observations)


def _synthetic_result(*, missing_capex=False, immaterial=False):
    """Different, asset-light economics; all amounts are simulated test data."""
    values = {
        "RevenueFromContractWithCustomerExcludingAssessedTax": (200, 240),
        "OperatingIncomeLoss": (60, 50),
        "NetIncomeLoss": (45, 42),
        "NetCashProvidedByUsedInOperatingActivities": (110, 140),
        "PaymentsToAcquirePropertyPlantAndEquipment": (5, 6),
    }
    if immaterial:
        values = {concept: (prior, prior * 1.01) for concept, (prior, _) in values.items()}
    if missing_capex:
        del values["PaymentsToAcquirePropertyPlantAndEquipment"]
    accessions = ("0000000001-25-000001", "0000000001-26-000001")
    facts = {"cik": 1, "entityName": "SYNTHETIC ASSET-LIGHT ISSUER — TEST ONLY", "facts": {"us-gaap": {
        concept: {"units": {"USD": [
            {"val": value, "start": f"{year}-01-01", "end": f"{year}-12-31",
             "filed": f"{year + 1}-02-01", "accn": accession, "form": "10-K", "fy": year, "fp": "FY"}
            for year, value, accession in zip((2024, 2025), amounts, accessions)
        ]}} for concept, amounts in values.items()}}}
    submissions = {"filings": {"recent": {"reportDate": ["2024-12-31", "2025-12-31"],
        "accessionNumber": list(accessions), "form": ["10-K", "10-K"]}}}
    return ResearchResult("TEST", facts["entityName"], "0000000001",
        extract_annuals(facts, submissions, years=2), "offline", "2026-10-21T00:00:00+00:00")


def test_real_msft_reasoning_selects_three_distinct_developments_and_reconciled_cash_sources(recorded, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Investment framing must not contact a model or retrieve new evidence")

    monkeypatch.setattr("alphalens.providers.request_structured", forbidden)
    monkeypatch.setattr("httpx.Client.send", forbidden)
    monkeypatch.setattr("requests.Session.request", forbidden)
    before = deepcopy((recorded.evidence, recorded.analysis, recorded.financial_observations,
                       recorded.model_interpretation, recorded.transport_output))
    reasoning = _reasoning(recorded)
    ids = [row["observation_id"] for row in reasoning["findings"]]
    assert ids == ["2026:cash_flow_divergence", "2026:revenue_profit_growth", "2026:earnings_conversion_tension"]
    assert reasoning["available_distinct_developments"] == 3
    cash = reasoning["findings"][0]
    comparisons = {row["metric"]: row for row in cash["comparisons"]}
    expected = {"operating_cash_flow": (136162000000, 182935000000),
                "capital_expenditure": (64551000000, 115948000000),
                "free_cash_flow": (71611000000, 66987000000)}
    changes = {}
    for metric, (prior, current) in expected.items():
        assert (comparisons[metric]["prior"]["value"], comparisons[metric]["current"]["value"]) == (prior, current)
        changes[metric] = current - prior
    assert changes["operating_cash_flow"] - changes["capital_expenditure"] == changes["free_cash_flow"] == -4624000000
    for finding in reasoning["findings"]:
        source = recorded.financial_observations[finding["observation_id"]]
        assert finding["comparisons"] == source["comparisons"]
        assert finding["source_ids"] == source["source_ids"]
        assert finding["prior_period"] == source["prior_period"]
        assert finding["current_period"] == source["current_period"]
        assert all(recorded.evidence[key]["kind"] == "financial" for key in finding["source_ids"])
    assert (recorded.evidence, recorded.analysis, recorded.financial_observations,
            recorded.model_interpretation, recorded.transport_output) == before
    # Even presentation mutations must not leak back into verified records.
    cash["comparisons"][0]["current"]["value"] = -1
    assert recorded.financial_observations[ids[0]]["comparisons"][0]["current"]["value"] == 182935000000


def test_competing_mechanisms_have_evidence_discriminators_but_remain_hypotheses(recorded):
    reasoning = _reasoning(recorded)
    assert "not Gemini" in reasoning["findings"][0]["origin"]
    implications = set()
    for finding in reasoning["findings"]:
        assert finding["category"] == "Deterministic calculation" and finding["requires_analyst_review"]
        assert finding["economic_significance"] and finding["unresolved_question"] and finding["missing_evidence"]
        implications.add(finding["investment_implication"])
        cases = finding["competing_explanations"]
        assert len(cases) == 2 and cases[0]["mechanism"] != cases[1]["mechanism"]
        for case in cases:
            assert case["category"] == "Unverified hypothesis"
            assert case["observation_basis_ids"] == [finding["observation_id"]]
            assert case["supporting_financial_ids"] == finding["source_ids"]
            assert case["support_limit"]
            assert case["strengthening_condition"] and case["weakening_condition"]
            assert case["strengthening_condition"] != case["weakening_condition"]
        assert cases[0]["strengthening_condition"] == cases[1]["weakening_condition"]
        assert cases[0]["weakening_condition"] == cases[1]["strengthening_condition"]
    assert len(implications) == 3  # No universal generic implication repeated for different developments.


@pytest.mark.parametrize("defect", ["missing_source", "comparison_amount", "period", "dependency"])
def test_reasoning_refuses_corrupt_comparisons_instead_of_building_plausible_mechanisms(recorded, defect):
    observation = recorded.financial_observations["2026:cash_flow_divergence"]
    if defect == "missing_source":
        del recorded.evidence["2026:operating_cash_flow"]
    elif defect == "comparison_amount":
        observation["comparisons"][0]["current"]["value"] += 1_000_000
    elif defect == "period":
        observation["prior_period"]["period_end"] = "2025-06-29"
    else:
        observation["source_ids"][0] = "2026:invented"
    with pytest.raises(ValueError, match="Financial observation integrity failed"):
        _reasoning(recorded)


def test_different_synthetic_characteristics_produce_margin_questions_not_a_msft_cash_story():
    result = _synthetic_result()
    before = asdict(result)
    analysis, book = build_analytics(result), build_evidence_book(result)
    reasoning = build_investment_reasoning(book, analysis)
    assert [finding["observation_id"] for finding in reasoning["findings"]] == ["2025:growth_margin_tension"]
    finding = reasoning["findings"][0]
    comparisons = {row["metric"]: row for row in finding["comparisons"]}
    assert comparisons["revenue"]["current"]["value"] == 240
    assert comparisons["operating_margin"]["prior"]["value"] == pytest.approx(0.30)
    assert comparisons["operating_margin"]["current"]["value"] == pytest.approx(50 / 240)
    assert all(name not in json.dumps(reasoning) for name in ("Microsoft", "Intelligent Cloud", "Azure"))
    assert all(case["category"] == "Unverified hypothesis" for case in finding["competing_explanations"])
    assert asdict(result) == before


def test_missing_capex_abstains_from_cash_investment_explanation_without_discarding_valid_margin_evidence():
    result = _synthetic_result(missing_capex=True)
    analysis = build_analytics(result)
    reasoning = build_investment_reasoning(build_evidence_book(result), analysis)
    assert [row["observation_id"] for row in reasoning["findings"]] == ["2025:growth_margin_tension"]
    assert all(not key.endswith(":capital_expenditure") for row in reasoning["findings"] for key in row["source_ids"])
    fcf = next(row for row in analysis["metrics"] if row["source_id"] == "2025:analytics.free_cash_flow")
    assert fcf["value"] is None and fcf["reason"]
    assert result.periods[-1].metrics["capital_expenditure"].value is None


def test_immaterial_movements_do_not_force_three_research_developments_or_invent_explanations():
    result = _synthetic_result(immaterial=True)
    analysis = build_analytics(result)
    assert not analysis["tensions"]
    reasoning = build_investment_reasoning(build_evidence_book(result), analysis)
    assert reasoning["findings"] == [] and reasoning["available_distinct_developments"] == 0


def test_segment_flag_uses_the_checked_table_and_does_not_promote_a_causal_conclusion(recorded):
    readout = build_recorded_readout(recorded)
    before = deepcopy(readout)
    flag, = segment_context_flags(readout)
    consolidated, cloud = readout["margins"]
    assert consolidated["prior_pct"] == Decimal(128528) / Decimal(281724) * 100
    assert cloud["current_pct"] == Decimal(56972) / Decimal(137791) * 100
    assert consolidated["change_pp"] > 0 > cloud["change_pp"]
    assert flag["code"] == "segment_consolidated_divergence"
    assert flag["category"] == "Deterministic calculation" and flag["requires_analyst_review"]
    assert flag["source_ids"] == ["sec:3eb3eccc7d1065f444ebdf69"]
    assert readout == before
    aligned = deepcopy(readout)
    aligned["margins"][1]["change_pp"] = abs(aligned["margins"][1]["change_pp"])
    assert not segment_context_flags(aligned)


def test_context_and_mocked_gemini_request_retain_flat_contract_with_new_unverified_framework(monkeypatch):
    """Inspect the request boundary with an authored response, never a live call."""
    from alphalens import providers
    from alphalens.providers import StructuredResponse

    result = load_research("MSFT", "offline")
    contexts = [load_offline_filing_context(result)]
    context = build_briefing_context(result, contexts)
    framework = context.packet["research_framework"]
    assert len(framework) == 3
    assert all(finding["observation_id"] in context.observations for finding in framework)
    local = build_investment_reasoning(context.evidence, context.analysis, context.observations)
    for finding, local_finding in zip(framework, local["findings"]):
        assert finding["hypotheses_not_disclosures"] == [case["mechanism"] for case in local_finding["competing_explanations"]]
        assert finding["unresolved_question"] == local_finding["unresolved_question"]
        assert finding["missing_evidence"] == local_finding["missing_evidence"]
    expected_fields = {"primary_interpretation", "primary_passage_ids", "primary_alternative_explanation", "primary_limitations",
        "additional_observation_id", "additional_interpretation", "additional_passage_ids", "additional_alternative_explanation",
        "additional_limitations", "risk_interpretation", "risk_passage_ids", "risk_limitations", "unanswered_questions"}
    assert set(GeminiFindingFields.model_fields) == expected_fields
    # Source windows are bound to this newly built packet. Reusing a genuine
    # historical ID absent from the new selection must remain rejectable; the
    # genuine replay is covered separately, without editing its model output.
    risk_id = next(key for key, source in context.packet["passages"].items()
                   if "intense competition" in source["text"].lower())
    body = {
        "primary_interpretation": "Operating cash flow rose while free cash flow declined as cash investment increased.",
        "primary_passage_ids": [],
        "primary_alternative_explanation": "Cash timing could contribute; its effect is not established by this packet.",
        "primary_limitations": ["A cash-tax and collection bridge is needed to assess recurring operating cash generation."],
        "additional_observation_id": context.packet["required_additional_observation_id"],
        "additional_interpretation": "Revenue and operating income grew; whether this progress persists remains an open research question.",
        "additional_passage_ids": [],
        "additional_alternative_explanation": "Changes in business mix could contribute, but the effect is not established by this packet.",
        "additional_limitations": ["A comparable operating-growth bridge is needed before attributing the change to a specific mechanism."],
        "risk_interpretation": "Intense competition could affect future operating results; the magnitude is not established by this packet.",
        "risk_passage_ids": [risk_id],
        "risk_limitations": ["The disclosure describes a conditional risk and does not quantify realized losses."],
        "unanswered_questions": ["Which cash-tax and collection effects recur?", "What evidence links deployed assets to incremental cash generation?"],
    }
    calls = []

    def mock_request(**kwargs):
        calls.append(kwargs)
        return StructuredResponse(output_parsed=GeminiFindingFields.model_validate(body), status="completed",
            provider="gemini", model="mock-model", usage={}, latency_seconds=0.0, diagnostics={})

    monkeypatch.setattr(providers, "request_structured", mock_request)
    monkeypatch.setattr("alphalens.ai._audit_attempt", lambda diagnostics, evidence: diagnostics)
    validated = generate_focused_briefing(result, "mock-not-a-real-key", "mock-model",
        filing_contexts=contexts, provider="gemini", contract="focused_v3")
    assert len(calls) == 1
    call = calls[0]
    assert call["schema"] is GeminiFindingFields and call["gemini_native"] is True
    assert call["max_output_tokens"] == 3200 and call["provider"] == "gemini"
    assert json.loads(call["messages"][1]["content"])["research_framework"] == framework
    instructions = call["messages"][0]["content"]
    assert "research_framework" in instructions and "hypothesis" in instructions
    assert "untrusted" in instructions and "net-income" in instructions
    assert validated.transport_output == body
    assert len(validated.output.what_matters_most) == 2  # Three deterministic developments are not three new model findings.


def test_annual_analysis_ui_withholds_corrupt_reasoning_without_crashing_dashboard():
    from streamlit.testing.v1 import AppTest

    result = _synthetic_result()
    analysis = build_analytics(result)
    analysis["tensions"][0]["comparisons"][0]["current"]["value"] += 1

    def view(result, analysis):
        from alphalens.analysis_ui import show_financial_analysis
        show_financial_analysis(result, analysis)

    app = AppTest.from_function(view, args=(result, analysis)).run(timeout=30)
    assert not app.exception
    assert any("withheld" in row.value for row in app.warning)
    assert any(row.label == "Inspect annual calculated metrics and comparison periods" for row in app.expander)
    assert not any(row.label == "Investment reasoning — hypotheses and evidence" for row in app.expander)


def test_recorded_msft_ui_and_exports_add_separate_review_without_rewriting_genuine_output(monkeypatch):
    """A genuine saved output stays inspectable with zero provider/network access."""
    from streamlit.testing.v1 import AppTest
    from alphalens import research_exports

    def forbidden(*args, **kwargs):
        raise AssertionError("The V1.1 recorded demonstration must not invoke a provider or network request")

    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr("alphalens.providers.load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr("openai.OpenAI", forbidden)
    monkeypatch.setattr("alphalens.providers.request_structured", forbidden)
    monkeypatch.setattr("httpx.Client.send", forbidden)
    monkeypatch.setattr("requests.Session.request", forbidden)
    saved = load_saved_briefing()
    original_json_export = research_exports.export_research_json(saved)
    original_model = deepcopy(saved.model_interpretation)
    original_wire = deepcopy(saved.transport_output)
    historical = {name: (BUNDLE / name).read_bytes() for name in
                  ("MODEL_INTERPRETATION.json", "TRANSPORT_OUTPUT.json", "ASSEMBLED_REPORT.json", "SOURCE_CATALOG.json")}
    exports = {}
    export_json, export_markdown = research_exports.export_research_json, research_exports.export_research_markdown

    def record_json(validated):
        exports["json"] = export_json(validated)
        return exports["json"]

    def record_markdown(validated):
        exports["markdown"] = export_markdown(validated)
        return exports["markdown"]

    monkeypatch.setattr(research_exports, "export_research_json", record_json)
    monkeypatch.setattr(research_exports, "export_research_markdown", record_markdown)
    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
    app.button(key="load_saved_msft_briefing").click().run(timeout=30)
    assert not app.exception
    labels = [row.label for row in app.expander]
    assert "Investment reasoning — hypotheses and evidence" in labels
    assert "Analytical evidence review — flags and limitations" in labels
    captions = "\n".join(row.value for row in app.caption)
    text = "\n".join(row.value for row in app.text)
    assert "Unverified hypothesis" in captions
    assert "WORKING_CAPITAL_PREMISE_UNSUPPORTED" in text
    assert "NET_VS_OPERATING_SCOPE" in text
    assert original_model["primary_finding"]["interpretation"] in text
    assert any("opposite direction" in row.value for row in app.warning)
    for key in ("generate_ai", "generate_research_brief", "generate_thesis"):
        assert app.button(key=key).disabled
    app.toggle(key="saved_msft_export_toggle").set_value(True).run(timeout=30)
    assert not app.exception and len(app.metric) == 4
    assert len(app.get("download_button")) == 4
    assert exports["json"] == original_json_export
    assert json.loads(exports["json"])["raw_model_output"] == original_wire
    note = exports["markdown"]
    assert "Economic implications and competing explanations" in note
    assert "Analytical evidence review" in note
    assert "not additional Gemini findings" in note
    assert "WORKING_CAPITAL_PREMISE_UNSUPPORTED" in note and "NET_VS_OPERATING_SCOPE" in note
    for source_id in ("2026:cash_flow_divergence", "2026:revenue_profit_growth", "2026:earnings_conversion_tension"):
        assert research_exports._text(source_id) in note
    assert "human investment review remains pending" in note
    displayed = app.session_state["saved_msft_briefing"]
    assert displayed.model_interpretation == original_model and displayed.transport_output == original_wire
    assert all((BUNDLE / name).read_bytes() == data for name, data in historical.items())
