"""Bounded financial overclaim guards; synthetic claims, no inference calls."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from alphalens.evidence import build_evidence_book
from alphalens.focused_briefing import (BriefingContext, FocusedBriefingInterpretation,
    _fingerprint, assemble_briefing)
from alphalens.research import Claim, ResearchAnalysis, validate_analysis
from alphalens.service import load_research


@pytest.fixture
def book():
    return build_evidence_book(load_research("MSFT", "offline"))


def check(text, book, *, kind="inference"):
    source = book["2026:capital_expenditure"]
    citation = {"source_id": "2026:capital_expenditure", **{key: source[key] for key in
        ("value", "unit", "fiscal_year", "period_start", "period_end")}}
    output = ResearchAnalysis(performance=[Claim(text=text, kind=kind, financial_citations=[citation])],
        business_developments=[], investment_considerations=[], risks=[], missing_information=[
            Claim(text="What additional evidence would establish incremental investment economics?", kind="question")])
    return validate_analysis(output, book).claims[0]


@pytest.mark.parametrize("text", [
    "AI ROIC is attractive, but future utilisation is unknown.",
    "AI ROIC is strong and future utilisation is unknown.",
    "Returns on invested capital are positive, although the monetisation timing is uncertain.",
    "Incremental returns remain robust while demand is uncertain.",
])
def test_unrelated_uncertainty_cannot_excuse_categorical_return_judgment(book, text):
    checked = check(text, book)
    assert checked.status == "unsupported"
    assert any("categorical ROIC or incremental-return" in issue for issue in checked.issues)


@pytest.mark.parametrize("text", [
    "All company cash PP&E purchases are exclusively AI investment.",
    "All property and equipment additions are exclusively AI investment.",
    "All cash purchases of property and equipment are AI investment.",
    "All spending on property and equipment is AI investment.",
])
def test_real_cash_ppe_wording_cannot_evade_all_ai_attribution_guard(book, text):
    checked = check(text, book)
    assert checked.status == "unsupported"
    assert any("Capital attribution" in issue for issue in checked.issues)


@pytest.mark.parametrize("text", [
    "Corporate cash PP&E does not isolate AI investment or establish incremental returns.",
    "Not all cash PP&E purchases are attributable to AI investment.",
    "Property and equipment additions are not entirely AI investment.",
    "ROIC is unknown and could be attractive if monetisation and utilisation develop favourably.",
    "Incremental returns depend on utilisation and monetisation that remain unestablished.",
    "Investment may support attractive returns on invested capital, but the outcome is uncertain.",
])
def test_cautious_qualifications_and_conditional_economics_remain_interpretations(book, text):
    checked = check(text, book)
    assert checked.status == "interpretation"
    assert checked.semantic_review == "requires_analyst_review"


@pytest.mark.parametrize("sentence", [
    " AI ROIC is attractive, but future utilisation is unknown.",
    " All company cash PP&E purchases are exclusively AI investment.",
])
def test_overclaims_appended_to_actual_accepted_response_cannot_pass_assembly(sentence):
    directory = Path(__file__).resolve().parents[1] / "outputs/msft_flat_live_2026-10-17"
    def read(name):
        return json.loads((directory / name).read_text(encoding="utf-8"))
    book, analysis, observations, packet = (read(name) for name in
        ("SOURCE_CATALOG.json", "FINANCIAL_ANALYSIS.json", "FINANCIAL_OBSERVATIONS.json", "FOCUSED_CONTEXT.json"))
    context = BriefingContext(book, analysis, observations, packet,
        _fingerprint(book, analysis, observations, packet))
    original = read("MODEL_INTERPRETATION.json")
    _, accepted = assemble_briefing(FocusedBriefingInterpretation.model_validate(original), context)
    assert accepted.unsupported_count == 0
    corrupted = deepcopy(original)
    corrupted["primary_finding"]["interpretation"] += sentence
    with pytest.raises(ValueError, match="Return attribution|Capital attribution"):
        assemble_briefing(FocusedBriefingInterpretation.model_validate(corrupted), context)
    assert read("MODEL_INTERPRETATION.json") == original


def check_comparison(text, book, metrics):
    citations = []
    for metric in metrics:
        for year in (2025, 2026):
            key = f"{year}:{metric}"
            citations.append({"source_id": key, **{field: book[key][field] for field in
                ("value", "unit", "fiscal_year", "period_start", "period_end")}})
    output = ResearchAnalysis(performance=[Claim(text=text, kind="inference", financial_citations=citations)],
        business_developments=[], investment_considerations=[], risks=[], missing_information=[
            Claim(text="What additional evidence would clarify the reported annual comparison?", kind="question")])
    return validate_analysis(output, book).claims[0]


@pytest.mark.parametrize("text, metric", [
    ("Operating cash flow did not increase.", "operating_cash_flow"),
    ("Operating cash flow didn't grow.", "operating_cash_flow"),
    ("Free cash flow did not decline.", "free_cash_flow"),
])
def test_simple_false_historical_negation_is_rejected(book, text, metric):
    checked = check_comparison(text, book, [metric])
    assert checked.status == "unsupported"
    assert any("negated" in issue and "contradicts" in issue for issue in checked.issues)


@pytest.mark.parametrize("text, metrics", [
    ("Operating cash flow did not decrease.", ["operating_cash_flow"]),
    ("Free cash flow didn't increase.", ["free_cash_flow"]),
    ("Operating cash flow may not increase.", ["operating_cash_flow"]),
    ("If operating cash flow did not increase, the investment outlook could weaken.", ["operating_cash_flow"]),
    ("Operating cash flow did not increase materially.", ["operating_cash_flow"]),
    ("Operating cash flow and free cash flow did not increase.", ["operating_cash_flow", "free_cash_flow"]),
])
def test_true_negation_or_ambiguous_conditional_grammar_is_not_inverted(book, text, metrics):
    checked = check_comparison(text, book, metrics)
    assert checked.status == "interpretation"
    assert checked.semantic_review == "requires_analyst_review"


@pytest.mark.parametrize("direction", ["increase", "decrease"])
def test_unchanged_level_does_not_contradict_either_simple_direction_denial(book, direction):
    # Synthetic equal-level control on a copy, not a claim about the SEC data.
    synthetic = deepcopy(book)
    synthetic["2026:operating_cash_flow"]["value"] = synthetic["2025:operating_cash_flow"]["value"]
    checked = check_comparison(f"Operating cash flow did not {direction}.", synthetic, ["operating_cash_flow"])
    assert checked.status == "interpretation"
