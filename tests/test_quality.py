"""Actual saved-report replay and focused semantic-boundary regressions."""
from copy import deepcopy
import json
from pathlib import Path
import pytest

from alphalens.quality import (QUALITY_RUBRIC, evaluate_output, evaluate_saved_report,
    load_source_catalog, render_evaluation)
from scripts.evaluate_research_quality import main


ROOT = Path(__file__).resolve().parents[1]
RESPONSE = ROOT / "fixtures/gemini_schema_failure/brief.complete_response.json"
REQUEST = ROOT / "fixtures/gemini_http400/brief.request.json"


def book():
    return load_source_catalog(REQUEST)


def financial(source_id):
    source = book()[source_id]
    return {"source_id": source_id, **{field: source[field] for field in
        ("value", "unit", "fiscal_year", "period_start", "period_end")}}


def output(text, citations):
    return {"performance": [{"text": text, "kind": "fact", "financial_citations": citations,
            "passage_citations": []}], "business_developments": [], "investment_considerations": [], "risks": [],
        "missing_information": [{"text": "What additional evidence would change the interpretation?", "kind": "question",
            "financial_citations": [], "passage_citations": []}]}


def first(report):
    return report["claims"][0]


def test_actual_saved_report_still_fails_schema_and_new_comparison_checks_offline():
    report = evaluate_saved_report(RESPONSE, REQUEST)
    assert report["parsing_passed"] and not report["schema_passed"]
    assert not report["complete_local_validation_passed"] and report["diagnostic_only"]
    assert {"path": "missing_information[0].kind", "type": "missing"} in report["schema_issues"]
    growth = next(claim for claim in report["claims"] if claim["path"] == "performance[1]")
    assert growth["status"] == "unsupported"
    assert any("Comparative completeness" in issue for issue in growth["issues"])
    assert report["mechanical_counts"] == {"financial_citations_checked": 5, "financial_citations_matched": 5,
        "passage_quotes_checked": 5, "passage_quotes_matched": 5}
    assert all(row["citation_relevance"] == "requires_analyst_review" for row in report["passage_citations"])


def test_growth_requires_comparable_prior_period_not_just_latest_level():
    latest = financial("2026:operating_cash_flow")
    prior = financial("2025:operating_cash_flow")
    text = "Operating cash flow expanded during the latest annual period."
    assert first(evaluate_output(output(text, [latest]), book()))["status"] == "unsupported"
    both = evaluate_output(output(text, [prior, latest]), book())
    assert first(both)["status"] == "evidence_checked" and both["complete_local_validation_passed"]


def test_acceleration_requires_consecutive_growth_intervals_not_only_two_levels():
    text = "Revenue growth accelerated during the latest annual period."
    two = [financial("2025:revenue"), financial("2026:revenue")]
    assert first(evaluate_output(output(text, two), book()))["status"] == "unsupported"
    three = [financial("2024:revenue"), *two]
    report = evaluate_output(output(text, three), book())
    assert first(report)["status"] == "evidence_checked"
    # This is evidence completeness, not a proof that the acceleration assertion is true.
    assert first(report)["semantic_review"] == "requires_analyst_review"


def test_corporate_capex_cannot_be_declared_entirely_ai_spending():
    citation = financial("2026:capital_expenditure")
    report = evaluate_output(output("All corporate capital expenditure is exclusively investment in AI infrastructure.", [citation]), book())
    assert first(report)["status"] == "unsupported"
    assert any("Capital attribution" in issue for issue in first(report)["issues"])
    qualified = evaluate_output(output("Corporate capital expenditure cannot establish the AI-specific allocation of investment.", [citation]), book())
    assert first(qualified)["status"] == "evidence_checked"
    assert any("Capital attribution review" in flag for flag in first(qualified)["review_flags"])


def test_wrong_year_and_fabricated_source_fail_even_when_figure_is_real():
    citation = financial("2026:revenue")
    wrong_year = deepcopy(citation)
    wrong_year["fiscal_year"] = 2025
    report = evaluate_output(output("Revenue is reported for the cited annual period.", [wrong_year]), book())
    assert not report["financial_citations"][0]["matched"]
    assert any("fiscal_year mismatch" in issue for issue in first(report)["issues"])
    unknown = {**citation, "source_id": "2026:nonexistent_metric"}
    report = evaluate_output(output("Revenue is reported for the cited annual period.", [unknown]), book())
    assert first(report)["status"] == "unsupported" and not report["financial_citations"][0]["matched"]


def test_quality_rubric_has_observable_rules_and_no_fabricated_analyst_grades():
    report = evaluate_saved_report(RESPONSE, REQUEST)
    assert len(QUALITY_RUBRIC) == 8
    assert {row["dimension"] for row in report["qualitative_assessments"]} == {
        "financial_accuracy", "evidence_traceability", "citation_relevance", "comparative_analysis",
        "investment_insight", "analytical_balance", "schema_reliability", "practical_usefulness"}
    assert all(row["assessment"] == "not_assessed" and row["score"] is None and row["criteria"]
               for row in report["qualitative_assessments"])
    assert all(set(row["manual_levels"]) == {"not_assessed", "does_not_meet", "partial", "meets"}
               for row in report["qualitative_assessments"])
    rendered = render_evaluation(report)
    assert "not a new live model test" in rendered
    assert "not a citation-relevance verdict" in rendered
    assert "missing_information[0].kind" in rendered


def test_malformed_and_truncated_saved_outputs_are_never_repaired(tmp_path):
    malformed = tmp_path / "malformed.json"
    malformed.write_text('{"result_json":"not valid JSON"}', encoding="utf-8")
    report = evaluate_saved_report(malformed, REQUEST)
    assert not report["parsing_passed"] and not report["complete_local_validation_passed"]
    raw = json.loads(RESPONSE.read_text(encoding="utf-8"))
    raw["choices"][0]["finish_reason"] = "length"
    malformed.write_text(json.dumps(raw), encoding="utf-8")
    assert not evaluate_saved_report(malformed, REQUEST)["parsing_passed"]


def test_offline_cli_generates_reproducible_rejected_report_without_credentials(tmp_path, capsys):
    assert main(["--output-dir", str(tmp_path)]) == 0
    stdout = json.loads(capsys.readouterr().out)
    assert stdout["offline_replay_completed"] and not stdout["schema_passed"]
    saved = json.loads((tmp_path / "EVALUATION.json").read_text(encoding="utf-8"))
    assert saved["live_request_executed_by_evaluator"] is False
    assert saved["mechanical_counts"]["financial_citations_matched"] == 5
    assert (tmp_path / "EVALUATION.md").is_file()


def _citation(source_id, catalog):
    row = catalog[source_id]
    return {"source_id": source_id, **{field: row[field] for field in
        ("value", "unit", "fiscal_year", "period_start", "period_end")}}


def test_risk_is_not_misread_as_a_rising_metric_and_net_debt_is_not_gross_debt():
    report = evaluate_output(output("Revenue remains exposed to business risks requiring further diligence.",
        [financial("2026:revenue")]), book())
    assert first(report)["status"] == "evidence_checked"
    assert not any("Comparative" in issue for issue in first(report)["issues"])


@pytest.mark.parametrize("defect", ["overlap", "gap", "changed_concept"])
def test_annual_comparisons_need_contiguous_dates_and_comparable_concepts(defect):
    catalog = book()
    current = catalog["2026:revenue"]
    if defect == "overlap":
        current["period_start"] = "2025-06-30"
    elif defect == "gap":
        current["period_start"] = "2025-07-02"
    else:
        current["sources"][0]["concept"] = "us-gaap:DifferentAccountingScopeForTestOnly"
    citations = [_citation(f"{year}:revenue", catalog) for year in (2025, 2026)]
    report = evaluate_output(output("Revenue increased during the latest annual period.", citations), catalog)
    assert first(report)["status"] == "unsupported"
    assert any("Comparative comparability" in issue for issue in first(report)["issues"])


def test_direction_and_acceleration_cannot_contradict_the_cited_series():
    catalog = book()
    citations = [_citation(f"{year}:revenue", catalog) for year in (2024, 2025, 2026)]
    wrong_direction = evaluate_output(output("Revenue declined during the latest annual period.", citations[-2:]), catalog)
    assert any("Comparative direction" in issue for issue in first(wrong_direction)["issues"])
    # The real saved revenue sequence has faster latest annual growth. Claiming
    # deceleration must be rejected even with all required periods present.
    wrong_acceleration = evaluate_output(output("Revenue growth decelerated during the latest annual period.", citations), catalog)
    assert any("Comparative acceleration" in issue for issue in first(wrong_acceleration)["issues"])


@pytest.mark.parametrize("middle", [0, -10])
def test_acceleration_cannot_use_zero_or_negative_growth_bases(middle):
    # Explicit synthetic edge case, using real period metadata only. These are
    # not asserted Microsoft figures and are never exported as a live result.
    catalog = book()
    for year, value in zip((2024, 2025, 2026), (100, middle, 50)):
        row = catalog[f"{year}:revenue"]
        row["value"] = value
        for source in row["sources"]:
            source["value"] = value
    citations = [_citation(f"{year}:revenue", catalog) for year in (2024, 2025, 2026)]
    report = evaluate_output(output("Revenue growth accelerated during the latest annual period.", citations), catalog)
    assert any("positive growth bases" in issue for issue in first(report)["issues"])


def test_cited_management_expectation_is_reviewed_without_inventing_historical_comparisons():
    catalog = book()
    source_id = "sec:77e3b1b02ae6f58b92aa85af"
    quote = "The investments we are making in cloud and AI infrastructure and devices will continue to increase our operating costs and may decrease our operating margins."
    payload = output("Management expects operating margin may decrease as infrastructure investment raises costs.",
                     [financial("2026:operating_margin")])
    payload["performance"][0]["passage_citations"] = [{"source_id": source_id, "quote": quote}]
    report = evaluate_output(payload, catalog)
    assert first(report)["status"] == "evidence_checked"
    assert any("Forward-looking disclosure" in flag for flag in first(report)["review_flags"])


def test_unrelated_uncertainty_cannot_excuse_an_all_ai_capex_overclaim():
    payload = output("Demand is uncertain, but all corporate capital expenditure is exclusively AI investment.",
                     [financial("2026:capital_expenditure")])
    report = evaluate_output(payload, book())
    assert any("Capital attribution" in issue for issue in first(report)["issues"])


def test_fair_value_accounting_is_not_automatically_a_stock_valuation_recommendation():
    payload = output("Fair value accounting disclosures require attention when assessing reported financial assets.",
                     [financial("2026:revenue")])
    report = evaluate_output(payload, book())
    assert first(report)["status"] == "evidence_checked"
    # Deliberately unrelated real citation: mechanical acceptance still cannot
    # establish that the cited revenue supports this accounting assertion.
    assert first(report)["semantic_review"] == "requires_analyst_review"


def test_future_roic_certainty_cannot_be_excused_by_an_unrelated_real_passage():
    catalog = book()
    source_id = "sec:77e3b1b02ae6f58b92aa85af"
    quote = "The investments we are making in cloud and AI infrastructure and devices will continue to increase our operating costs and may decrease our operating margins."
    payload = output("AI infrastructure investment will generate attractive returns on invested capital.",
                     [financial("2026:capital_expenditure")])
    payload["performance"][0].update(kind="inference", passage_citations=[{"source_id": source_id, "quote": quote}])
    report = evaluate_output(payload, catalog)
    assert first(report)["status"] == "unsupported"
    assert any("Return attribution" in issue for issue in first(report)["issues"])
