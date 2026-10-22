"""Realistic mocked claims, deliberate corruptions and schema guard checks.

Financial values are read from the genuine SEC snapshot. Narrative test prose
is explicitly synthetic; these tests do not imply a live OpenAI call passed.
"""
from copy import deepcopy

import pytest
from pydantic import ValidationError

from alphalens.evidence import build_evidence_book, evidence_fingerprint
from alphalens.filings import FilingExcerpt
from alphalens.research import Claim, FinancialCitation, PassageCitation, ResearchAnalysis, ThesisChallenge, validate_analysis
from alphalens.service import load_offline_filing_context, load_research


@pytest.fixture
def book():
    result = load_research("MSFT", "offline")
    text = "Synthetic test excerpt: competition and operational disruption may adversely affect the business and its operating results."
    context = {"ticker": result.ticker, "cik": result.cik, "mode": "offline",
               "retrieved_at": result.retrieved_at, **result.filings[0],
               "excerpts": {"1A": FilingExcerpt("1A", "Risk factors", text, original_chars=len(text))}}
    return build_evidence_book(result, [context])


def financial_ref(book, source_id="2026:revenue"):
    return {"source_id": source_id, **{key: book[source_id][key]
            for key in ("value", "unit", "fiscal_year", "period_start", "period_end")}}


def fact(book):
    return Claim(text="Revenue is reported for the cited annual fiscal period.", kind="fact",
                 financial_citations=[financial_ref(book)])


def analysis(book, claim=None):
    return ResearchAnalysis(performance=[claim or fact(book)], business_developments=[],
        investment_considerations=[], risks=[], missing_information=[
            Claim(text="Which additional disclosures would help assess the durability of customer demand?", kind="question")])


def test_correct_financial_claim_passes_with_exact_python_evidence(book):
    report = validate_analysis(analysis(book), book)
    assert report.evidence_checked_count == 1
    assert report.unsupported_count == 0
    assert report.claims[0].status == "evidence_checked"
    assert report.source_fingerprint == evidence_fingerprint(book)


@pytest.mark.parametrize("field,value,issue", [
    ("value", 1.0, "figure mismatch"), ("unit", "USD/shares", "unit mismatch"),
    ("fiscal_year", 2025, "fiscal_year mismatch"), ("period_start", "2026-04-01", "period_start mismatch"),
    ("period_end", "2026-03-31", "period_end mismatch"),
    ("source_id", "2026:invented_revenue", "Unknown or non-financial"),
])
def test_wrong_figures_units_fiscal_year_quarter_and_source_ids_quarantined(book, field, value, issue):
    reference = financial_ref(book)
    reference[field] = value
    claim = fact(book).model_copy(update={"financial_citations": [FinancialCitation(**reference)]})
    report = validate_analysis(analysis(book, claim), book)
    assert report.unsupported_count == 1
    assert any(issue in text for text in report.claims[0].issues)
    # The valid diligence question is retained alongside the quarantined claim.
    assert report.claims[-1].status == "question"


def test_rounding_is_not_a_tolerance_for_cited_values(book):
    reference = financial_ref(book, "2026:operating_margin")
    reference["value"] = round(reference["value"], 2)
    claim = Claim(text="Operating margin is provided in the cited annual financial evidence.", kind="fact",
                  financial_citations=[reference])
    assert validate_analysis(analysis(book, claim), book).unsupported_count == 1


def test_instant_cash_does_not_accept_fabricated_annual_start(book):
    reference = financial_ref(book, "2026:cash_and_equivalents")
    reference["period_start"] = "2025-07-01"
    claim = Claim(text="Cash and cash equivalents are reported at the fiscal year end.", kind="fact",
                  financial_citations=[reference])
    report = validate_analysis(analysis(book, claim), book)
    assert "period_start mismatch" in report.claims[0].issues[0]


def passage_ref(book):
    source_id = next(key for key in book if key.startswith("sec:"))
    return {"source_id": source_id, "quote": book[source_id]["text"][24:]}


def test_verbatim_passage_quote_with_whitespace_normalization_is_checked(book):
    citation = passage_ref(book)
    citation["quote"] = citation["quote"].replace(" ", " \n ")
    claim = Claim(text="The cited disclosure identifies competition as a business risk.", kind="fact",
                  passage_citations=[citation])
    output = analysis(book)
    output.risks = [claim]
    report = validate_analysis(output, book)
    assert report.unsupported_count == 0
    assert report.evidence_checked_count == 2


@pytest.mark.parametrize("field,value", [
    ("source_id", "sec:completely_fabricated"),
    ("quote", "Management guarantees uninterrupted demand and no business risks exist."),
    ("quote", "Competition and operational disruption will never adversely affect the business."),
])
def test_fake_citations_fabricated_quotes_and_altered_quotes_quarantined(book, field, value):
    citation = passage_ref(book)
    citation[field] = value
    claim = Claim(text="The disclosure describes the competitive business environment.", kind="fact", passage_citations=[citation])
    assert validate_analysis(analysis(book, claim), book).unsupported_count == 1


def test_financial_and_passage_source_types_cannot_be_swapped(book):
    reference = financial_ref(book)
    reference["source_id"] = passage_ref(book)["source_id"]
    claim = fact(book).model_copy(update={"financial_citations": [FinancialCitation(**reference)]})
    assert validate_analysis(analysis(book, claim), book).unsupported_count == 1
    citation = passage_ref(book)
    citation["source_id"] = "2026:revenue"
    claim = Claim(text="The disclosure describes the competitive business environment.", kind="fact", passage_citations=[citation])
    assert validate_analysis(analysis(book, claim), book).unsupported_count == 1


def test_duplicate_references_and_uncited_material_claims_are_quarantined(book):
    claim = fact(book)
    claim.financial_citations *= 2
    report = validate_analysis(analysis(book, claim), book)
    assert any("Duplicate" in issue for issue in report.claims[0].issues)
    claim.financial_citations = []
    assert validate_analysis(analysis(book, claim), book).unsupported_count == 1


@pytest.mark.parametrize("text", [
    "Revenue increased by 40 percent in the fiscal year.",
    "Revenue increased by ٤٠ percent in the fiscal year.",
    "Revenue increased by ４０％ in the fiscal year.",
    "Revenue was $300 billion in the fiscal year.",
    "Revenue doubled in the cited fiscal year.",
    "Revenue increased by forty percent in the fiscal year.",
    "Revenue in 2026 was higher than the prior fiscal period.",
    "Revenue increased by Ⅳ times in the cited fiscal period.",
])
def test_financial_numeric_prose_cannot_bypass_structured_figures(book, text):
    claim = fact(book).model_copy(update={"text": text})
    report = validate_analysis(analysis(book, claim), book)
    assert report.unsupported_count == 1
    assert any("Numerical prose" in issue for issue in report.claims[0].issues)


def test_checked_citations_do_not_promote_interpretation_to_verified_fact(book):
    claim = fact(book).model_copy(update={"kind": "inference", "text": "The reported cash generation may provide flexibility for future investment."})
    report = validate_analysis(analysis(book, claim), book)
    assert report.interpretation_count == 1
    assert report.evidence_checked_count == 0
    assert report.claims[0].status == "interpretation"


def test_business_development_requires_retrieved_narrative_evidence(book):
    output = analysis(book)
    output.business_developments = [fact(book)]
    report = validate_analysis(output, book)
    assert report.unsupported_count == 1
    assert "filing passage" in report.claims[1].issues[0]


def test_assumptions_questions_and_observable_invalidation_conditions_labelled(book):
    output = ThesisChallenge(
        assumptions=[Claim(text="Assumption: customer demand remains durable across the investment horizon.", kind="hypothesis")],
        supporting_evidence=[fact(book)], contradictory_evidence=[], risks=[],
        missing_information=[Claim(text="Which disclosures would clarify the durability of customer demand?", kind="question")],
        invalidation_conditions=[Claim(text="If reported annual cash generation persistently deteriorates, reconsider the durability assumption.", kind="hypothesis")])
    report = validate_analysis(output, book)
    assert report.unsupported_count == 0
    assert [row.status for row in report.claims] == ["hypothesis", "evidence_checked", "question", "hypothesis"]


def test_uncited_assertion_cannot_hide_under_question_or_hypothesis_kind(book):
    for kind in ("question", "hypothesis"):
        claim = Claim(text="The company has unassailable pricing power and faces no competitive threats.", kind=kind)
        report = validate_analysis(analysis(book, claim), book)
        assert report.unsupported_count == 1
    output = analysis(book)
    output.missing_information = [Claim(text="The business will certainly maintain its competitive advantage.", kind="question")]
    assert validate_analysis(output, book).unsupported_count == 1


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), True, "331839000000"])
def test_nonfinite_boolean_and_string_numeric_citations_fail_schema(book, value):
    reference = financial_ref(book)
    reference["value"] = value
    with pytest.raises(ValidationError):
        FinancialCitation(**reference)


def test_schema_rejects_uncontrolled_fields_and_excessive_output(book):
    payload = analysis(book).model_dump()
    payload["target_price"] = "unsupported field"
    with pytest.raises(ValidationError):
        ResearchAnalysis(**payload)
    payload = analysis(book).model_dump()
    payload["performance"] *= 6
    with pytest.raises(ValidationError):
        ResearchAnalysis(**payload)


def test_citation_period_and_year_fields_are_required(book):
    for field in ("period_start", "period_end", "fiscal_year", "unit"):
        reference = financial_ref(book)
        del reference[field]
        with pytest.raises(ValidationError):
            FinancialCitation(**reference)


def test_genuine_sec_risk_passage_quote_checks_against_actual_offline_snapshot():
    result = load_research("MSFT", "offline")
    book = build_evidence_book(result, [load_offline_filing_context(result)])
    source_id = next(key for key, value in book.items() if value["kind"] == "passage" and value["item"] == "1A")
    quote = "Our operations and financial results are subject to various risks and uncertainties"
    assert quote in book[source_id]["text"]
    output = analysis(book)
    output.risks = [Claim(text="The filing describes risks and uncertainties affecting operations and financial results.",
                         kind="fact", passage_citations=[{"source_id": source_id, "quote": quote}])]
    report = validate_analysis(output, book)
    assert report.unsupported_count == 0
    assert report.evidence_checked_count == 2


def test_modified_sdk_model_instance_is_revalidated_at_parse_boundary(book):
    output = analysis(book)
    output.performance[0].financial_citations[0].value = float("nan")
    with pytest.raises(ValidationError):
        ResearchAnalysis.model_validate(output)
