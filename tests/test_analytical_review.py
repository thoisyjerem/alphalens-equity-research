"""Bounded attribution checks, not a claim of semantic or investment accuracy."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from alphalens.analytical_review import review_claim, review_research
from alphalens.research import Claim
from alphalens.saved_research import load_saved_briefing


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "outputs/msft_findings_live_2026-10-18"


@pytest.fixture
def genuine():
    return load_saved_briefing()


def _codes(review):
    return {flag["code"] for flag in review["flags"]}


def _claim(text, *, kind="inference", citations=(), passages=()):
    return Claim(text=text, kind=kind, financial_citations=list(citations), passage_citations=list(passages))


def _cash_claim(genuine, text, *, kind="inference"):
    original = genuine.output.executive_summary[0]
    return _claim(text, kind=kind, citations=original.financial_citations, passages=original.passage_citations)


def test_actual_saved_response_review_is_separate_and_preserves_all_original_records(genuine):
    paths = [path for path in BUNDLE.iterdir() if path.is_file()]
    hashes = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    before = deepcopy((genuine.output, genuine.verification, genuine.evidence, genuine.model_interpretation))
    reviewed = review_research(genuine)
    assert len(reviewed) == len(genuine.verification.claims)
    assert all(row["requires_analyst_review"] for row in reviewed)
    assert reviewed[0]["claim_text"] == genuine.verification.claims[0].claim.text
    assert (genuine.output, genuine.verification, genuine.evidence, genuine.model_interpretation) == before
    assert {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths} == hashes
    json.dumps(reviewed, allow_nan=False)
    question = next(row for row in reviewed if row["section"] == "missing_information" and row["index"] == 0)
    assert "WORKING_CAPITAL_PREMISE_UNSUPPORTED" in _codes(question)
    assert question["category"] == "Unverified hypothesis"
    alternative = next(row for row in reviewed if row["section"] == "investment_considerations" and row["index"] == 1)
    assert "NET_VS_OPERATING_SCOPE" in _codes(alternative)
    assert alternative["category"] == "Unverified hypothesis"


def test_disclosed_customer_receipts_and_cash_tax_drivers_have_only_bounded_support(genuine):
    claim = genuine.output.executive_summary[0]
    review = review_claim(claim, genuine.evidence)
    assert review["category"] == "Supported interpretation"
    assert "not its persistence" in review["support_basis"]
    assert review["requires_analyst_review"] is True
    extended = claim.model_copy(update={"text": claim.text + " This guarantees a durable economic moat."})
    result = review_claim(extended, genuine.evidence)
    assert result["category"] != "Supported interpretation"
    assert "CAUSAL_SUPPORT_REQUIRES_REVIEW" in _codes(result)


def test_receipts_and_tax_disclosure_does_not_prove_working_capital_benefits(genuine):
    claim = _cash_claim(genuine, "Operating cash flow increased due to working capital benefits.")
    reviewed = review_claim(claim, genuine.evidence)
    assert reviewed["category"] == "Unsupported claim"
    assert "WORKING_CAPITAL_PREMISE_UNSUPPORTED" in _codes(reviewed)
    conditional = _cash_claim(genuine, "Operating cash flow could reflect temporary working capital timing effects.")
    result = review_claim(conditional, genuine.evidence)
    assert result["category"] == "Unverified hypothesis"
    assert "WORKING_CAPITAL_RECONCILIATION_NEEDED" in _codes(result)
    denial = _cash_claim(genuine, "The available evidence does not establish working capital benefits.")
    assert review_claim(denial, genuine.evidence)["category"] != "Unsupported claim"
    evidence = deepcopy(genuine.evidence)
    data = claim.model_dump()
    citation = data["passage_citations"][0]
    citation["quote"] = "Operating cash flow had no improvement in working capital; it did not benefit from favorable working capital changes."
    evidence[citation["source_id"]]["text"] = citation["quote"]
    denied_support = review_claim(data, evidence)
    assert "WORKING_CAPITAL_PREMISE_UNSUPPORTED" in _codes(denied_support)
    assert denied_support["category"] == "Unsupported claim"


def test_operating_profit_cannot_be_explained_by_cited_net_income_investment_gains(genuine):
    original = genuine.output.executive_summary[1]
    claim = _claim("Operating income increased because of investment gains from OpenAI.",
                   citations=original.financial_citations, passages=original.passage_citations)
    result = review_claim(claim, genuine.evidence)
    assert result["category"] == "Unsupported claim"
    assert "NET_VS_OPERATING_SCOPE" in _codes(result)
    claim = claim.model_copy(update={"text": "Operating income could reflect non-recurring items; an operating reconciliation is needed."})
    assert review_claim(claim, genuine.evidence)["category"] == "Unverified hypothesis"


def test_net_income_disclosure_is_not_automatically_an_operating_income_error(genuine):
    original = genuine.output.executive_summary[1]
    claim = _claim("Net income benefited from investment gains from OpenAI.", passages=original.passage_citations)
    result = review_claim(claim, genuine.evidence)
    assert "NET_VS_OPERATING_SCOPE" not in _codes(result)
    assert result["category"] == "Unverified hypothesis"  # No blanket semantic certification.


def test_corporate_capex_must_not_be_relabelled_as_ai_specific(genuine):
    original = genuine.output.performance[0]
    claim = _claim("AI capital expenditure increased materially.", citations=original.financial_citations)
    result = review_claim(claim, genuine.evidence)
    assert result["category"] == "Unsupported claim"
    assert "AGGREGATE_CAPEX_SCOPE" in _codes(result)
    question = _claim("What portion of company capital expenditure supports AI infrastructure?", kind="question")
    question_result = review_claim(question, genuine.evidence, section="missing_information")
    assert question_result["category"] == "Unverified hypothesis"
    assert "AGGREGATE_CAPEX_SCOPE" not in _codes(question_result)


def test_future_investment_returns_are_not_proven_by_historical_capex(genuine):
    original = genuine.output.performance[0]
    claim = _claim("The investment program will generate attractive long-term returns.", citations=original.financial_citations)
    result = review_claim(claim, genuine.evidence, section="bull_case")
    assert result["category"] == "Unsupported claim"
    assert "FUTURE_RETURN_UNSUPPORTED" in _codes(result)
    hypothesis = claim.model_copy(update={"text": "If utilization improves, the investment program could generate attractive long-term returns."})
    assert review_claim(hypothesis, genuine.evidence, section="bull_case")["category"] == "Unverified hypothesis"


@pytest.mark.parametrize("section", ["bull_case", "bear_case"])
def test_uncited_conditional_investor_argument_is_flagged_and_not_promoted(section):
    claim = _claim("If customer demand strengthens, reinvestment could support future cash generation.")
    result = review_claim(claim, {}, section=section)
    assert result["category"] == "Unverified hypothesis"
    assert {"MISSING_EVIDENCE", "SCENARIO_IS_CONDITIONAL"} <= _codes(result)


def test_real_but_irrelevant_quote_does_not_establish_cash_flow_cause(genuine):
    original = genuine.output.executive_summary[0]
    claim = _claim("Operating cash flow increased due to higher cash collections from customers.",
                   citations=original.financial_citations, passages=genuine.output.risks[0].passage_citations)
    result = review_claim(claim, genuine.evidence)
    assert result["category"] == "Unverified hypothesis"
    assert "CAUSAL_SUPPORT_REQUIRES_REVIEW" in _codes(result)


def test_wrong_financial_period_and_wrong_figure_fail_reused_mechanical_checks(genuine):
    original = genuine.output.performance[1]
    for change in ({"fiscal_year": 2000}, {"value": 123.0}, {"unit": "shares"}):
        data = original.model_dump()
        data["financial_citations"][0].update(change)
        result = review_claim(data, genuine.evidence)
        assert result["category"] == "Unsupported claim"
        assert "MECHANICAL_EVIDENCE_FAILURE" in _codes(result)


def test_comparison_reversal_is_rejected_even_when_each_citation_is_real(genuine):
    original = genuine.output.performance[1]
    claim = original.model_copy(update={"text": "Revenue declined materially."})
    result = review_claim(claim, genuine.evidence)
    assert result["category"] == "Unsupported claim"
    assert any("Comparative direction" in f["message"] for f in result["flags"])


def test_shared_compound_direction_is_checked_and_complex_compounds_are_not_certified(genuine):
    original = genuine.output.performance[1]
    reversed_claim = original.model_copy(update={"text": "Revenue and operating income declined materially."})
    result = review_claim(reversed_claim, genuine.evidence)
    assert result["category"] == "Unsupported claim"
    assert any("Bounded comparative direction" in flag["message"] for flag in result["flags"])
    ambiguous = original.model_copy(update={"text": "Revenue increased and operating income declined."})
    assert review_claim(ambiguous, genuine.evidence)["category"] != "Verified observation"


def test_wrong_year_causal_passage_is_not_current_period_support(genuine):
    claim = genuine.output.executive_summary[0]
    evidence = deepcopy(genuine.evidence)
    evidence[claim.passage_citations[0].source_id]["report_date"] = "2025-06-30"
    result = review_claim(claim, evidence)
    assert result["category"] == "Unverified hypothesis"
    assert "CAUSAL_PERIOD_SCOPE" in _codes(result)


def test_unknown_citation_misquotation_and_malformed_source_fail_safely(genuine):
    original = genuine.output.executive_summary[0]
    for change in ({"source_id": "invented:source"}, {"quote": "This invented quotation was not present in the filing."}):
        data = original.model_dump()
        data["passage_citations"][0].update(change)
        assert review_claim(data, genuine.evidence)["category"] == "Unsupported claim"
    evidence = deepcopy(genuine.evidence)
    evidence[original.passage_citations[0].source_id].pop("text")
    assert review_claim(original, evidence)["category"] == "Unsupported claim"
    evidence = deepcopy(genuine.evidence)
    evidence[original.financial_citations[0].source_id]["value"] = None
    assert review_claim(original, evidence)["category"] == "Unsupported claim"
    evidence[original.financial_citations[0].source_id] = ["malformed source"]
    assert review_claim(original, evidence)["category"] == "Unsupported claim"
    invalid = original.model_dump()
    invalid["financial_citations"][0]["fiscal_year"] = "invalid-year"
    assert review_claim(invalid, genuine.evidence)["flags"][0]["code"] == "STRUCTURAL_INVALID"


def test_bounded_financial_observation_and_calculation_categories_are_not_semantic_scores(genuine):
    observation = review_claim(genuine.output.performance[1], genuine.evidence)
    calculation = review_claim(genuine.output.performance[0], genuine.evidence)
    assert observation["category"] == "Verified observation"
    assert calculation["category"] == "Deterministic calculation"
    assert observation["requires_analyst_review"] is calculation["requires_analyst_review"] is True
    assert "materiality" in observation["support_basis"]
