"""Explicit research acceptance cases using synthetic, non-company SEC facts.

These small examples are not Microsoft figures or demonstrations of AI quality.
They exercise annual extraction, sign handling and auditable cash-flow signals.
"""
from dataclasses import asdict

import pytest

from alphalens.analytics import analytics_evidence, build_analytics
from alphalens.evidence import build_evidence_book
from alphalens.financials import extract_annuals
from alphalens.models import ResearchResult


def _synthetic_cash_result(prior_capex=40, current_capex=70):
    """Keep the user-provided illustrative amounts separate from real fixtures."""
    tags = {}
    concepts = {
        "RevenueFromContractWithCustomerExcludingAssessedTax": (200, 240),
        "NetCashProvidedByUsedInOperatingActivities": (100, 120),
        "PaymentsToAcquirePropertyPlantAndEquipment": (prior_capex, current_capex),
    }
    accessions = ["0000000001-25-000001", "0000000001-26-000001"]
    for concept, values in concepts.items():
        tags[concept] = {"units": {"USD": [
            {"val": value, "start": f"{year}-01-01", "end": f"{year}-12-31",
             "filed": f"{year + 1}-02-01", "accn": accession,
             "form": "10-K", "fy": year, "fp": "FY"}
            for year, accession, value in zip((2024, 2025), accessions, values)
        ]}}
    facts = {"cik": 1, "entityName": "SYNTHETIC ACCEPTANCE TEST ONLY",
             "facts": {"us-gaap": tags}}
    submissions = {"filings": {"recent": {
        "reportDate": ["2024-12-31", "2025-12-31"],
        "accessionNumber": accessions, "form": ["10-K", "10-K"],
    }}}
    return ResearchResult("TEST", "SYNTHETIC ACCEPTANCE TEST ONLY", "0000000001",
                          extract_annuals(facts, submissions, years=2), "offline",
                          "2026-10-20T00:00:00+00:00")


def test_scenario_a_cash_increases_but_fcf_falls_with_exact_source_reconciliation():
    result = _synthetic_cash_result()
    analysis = build_analytics(result)
    current = {row["metric"]: row for row in analysis["metrics"]
               if row["fiscal_year"] == 2025}
    assert [period.metrics["free_cash_flow"].value for period in result.periods] == [60, 50]
    assert current["operating_cash_flow_growth"]["value"] == pytest.approx(0.20)
    assert current["capital_expenditure_growth"]["value"] == pytest.approx(0.75)
    assert current["free_cash_flow_change"]["value"] == -10
    assert current["free_cash_flow_growth"]["value"] == pytest.approx(-10 / 60)
    assert current["capex_to_operating_cash_flow"]["value"] == pytest.approx(70 / 120)

    signals = {item["type"]: item for item in analysis["tensions"]}
    assert {"cash_flow_divergence", "cash_investment_tension", "investment_intensity"} <= signals.keys()
    divergence = signals["cash_flow_divergence"]
    comparisons = {item["metric"]: item for item in divergence["comparisons"]}
    assert [(comparisons[key]["prior"]["value"], comparisons[key]["current"]["value"])
            for key in ("operating_cash_flow", "capital_expenditure", "free_cash_flow")] == [
                (100, 120), (40, 70), (60, 50)]
    assert (120 - 100) - (70 - 40) == current["free_cash_flow_change"]["value"]
    assert divergence["id"] == "2025:cash_flow_divergence"
    assert divergence["current_period"] == {
        "fiscal_year": 2025, "period_start": "2025-01-01", "period_end": "2025-12-31"}
    assert divergence["prior_period"]["fiscal_year"] == 2024
    assert set(divergence["source_ids"]) == {
        "2024:operating_cash_flow", "2025:operating_cash_flow",
        "2024:capital_expenditure", "2025:capital_expenditure"}
    book = build_evidence_book(result)
    for source_id in divergence["source_ids"]:
        source = book[source_id]
        assert source["sources"][0]["value"] == source["value"]
        assert source["sources"][0]["end"] == source["period_end"]
        assert source["sources"][0]["form"] == "10-K"
    assert all(change["formula"] and change["dependencies"] for change in divergence["changes"])
    assert divergence["comparability_warnings"]
    assert "not proof of AI spending or poor future returns" in divergence["explanation"]


@pytest.mark.parametrize("defect", ["missing_capex", "noncontiguous_annual_period", "changed_concept"])
def test_scenario_b_unavailable_or_incompatible_inputs_cannot_create_a_cash_signal(defect):
    result = _synthetic_cash_result()
    current_period = result.periods[-1]
    if defect == "missing_capex":
        del current_period.metrics["capital_expenditure"]
    elif defect == "noncontiguous_annual_period":
        current_period.start = "2025-01-02"
        for metric in current_period.metrics.values():
            for source in metric.sources:
                if source.start is not None:
                    source.start = current_period.start
    else:
        current_period.metrics["capital_expenditure"].sources[0].concept = "us-gaap:DifferentScopeCapex"
    analysis = build_analytics(result)
    current = {row["metric"]: row for row in analysis["metrics"]
               if row["fiscal_year"] == 2025}
    for metric in ("capital_expenditure_growth", "free_cash_flow_change"):
        assert current[metric]["value"] is None
        assert current[metric]["reason"]
        assert current[metric]["source_id"] not in analytics_evidence(result)
    assert not {"cash_flow_divergence", "cash_investment_tension"} & {
        item["type"] for item in analysis["tensions"]}


@pytest.mark.parametrize("prior_capex,current_capex,invalid_index", [(-40, 70, 0), (40, -70, 1)])
def test_scenario_e_mixed_capex_signs_abstain_without_erasing_or_double_subtracting(prior_capex, current_capex, invalid_index):
    result = _synthetic_cash_result(prior_capex, current_capex)
    original = asdict(result)
    invalid = result.periods[invalid_index]
    assert invalid.metrics["capital_expenditure"].value is None
    assert invalid.metrics["capital_expenditure"].sources[0].value == (prior_capex, current_capex)[invalid_index]
    assert "positive cash-payment convention" in invalid.metrics["capital_expenditure"].reason
    assert invalid.metrics["free_cash_flow"].value is None
    valid = result.periods[1 - invalid_index]
    assert valid.metrics["free_cash_flow"].value == (50, 60)[invalid_index]

    analysis = build_analytics(result)
    current = {row["metric"]: row for row in analysis["metrics"]
               if row["fiscal_year"] == 2025}
    assert current["free_cash_flow_change"]["value"] is None
    assert current["capital_expenditure_growth"]["value"] is None
    assert not {"cash_flow_divergence", "cash_investment_tension"} & {
        item["type"] for item in analysis["tensions"]}
    assert f"{invalid.fiscal_year}:analytics.free_cash_flow" not in analytics_evidence(result)
    assert asdict(result) == original
