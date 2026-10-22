"""Annual analytical calculations: actual SEC fixtures plus labelled test cases."""
from copy import deepcopy
from dataclasses import asdict
import json

import pytest

from alphalens.analytics import analytics_evidence, build_analytics
from alphalens.evidence import build_evidence_book
from alphalens.models import AnnualPeriod, MetricValue, ResearchResult, SourceFact
from alphalens.service import load_research


_CONCEPTS = {
    "revenue": "RevenueFromContractWithCustomerExcludingAssessedTax",
    "operating_income": "OperatingIncomeLoss", "net_income": "NetIncomeLoss",
    "operating_cash_flow": "NetCashProvidedByUsedInOperatingActivities",
    "capital_expenditure": "PaymentsToAcquirePropertyPlantAndEquipment",
    "total_debt": "LongTermDebt", "cash_and_equivalents": "CashAndCashEquivalentsAtCarryingValue",
}


def synthetic_result(*years):
    """Synthetic test data; never represented as live or Microsoft statements."""
    periods = []
    for fiscal_year, values in years:
        start, end = f"{fiscal_year}-01-01", f"{fiscal_year}-12-31"
        metrics = {}
        for key, value in {"revenue": 100, "operating_income": 25, "net_income": 20,
                           "operating_cash_flow": 40, "capital_expenditure": 10,
                           "total_debt": 30, "cash_and_equivalents": 50, **values}.items():
            instant = key in {"total_debt", "cash_and_equivalents"}
            source = SourceFact(f"us-gaap:{_CONCEPTS[key]}", "USD", value, None if instant else start,
                                end, f"0000000001-{str(fiscal_year)[2:]}-000001", f"{fiscal_year + 1}-02-01", "10-K",
                                f"https://www.sec.gov/Archives/edgar/data/1/0000000001{str(fiscal_year)[2:]}000001/index.html")
            metrics[key] = MetricValue(value, "USD", [source] if value is not None else [], "Synthetic unavailable input" if value is None else "")
        periods.append(AnnualPeriod(fiscal_year, start, end, metrics))
    return ResearchResult("TEST", "SYNTHETIC UNIT TEST", "0000000001", periods, "offline", "2026-10-17T00:00:00+00:00")


def row(result, year, metric):
    return next(r for r in build_analytics(result)["metrics"] if r["fiscal_year"] == year and r["metric"] == metric)


def test_real_msft_cash_generation_tension_and_exact_raw_values():
    result = load_research("MSFT", "offline")
    research = build_analytics(result)
    metrics = {r["metric"]: r for r in research["metrics"] if r["fiscal_year"] == 2026}
    assert metrics["free_cash_flow"]["value"] == 66_987_000_000
    assert metrics["operating_cash_flow_growth"]["value"] == pytest.approx((182_935 - 136_162) / 136_162)
    assert metrics["capital_expenditure_growth"]["value"] == pytest.approx((115_948 - 64_551) / 64_551)
    assert metrics["free_cash_flow_growth"]["value"] == pytest.approx((66_987 - 71_611) / 71_611)
    assert metrics["capex_to_operating_cash_flow"]["value"] == pytest.approx(115_948 / 182_935)
    assert {t["type"] for t in research["tensions"] if t["current_period"]["fiscal_year"] == 2026} >= {
        "cash_investment_tension", "earnings_cash_tension", "investment_intensity"}
    assert metrics["net_debt"]["value"] is None
    assert "CommercialPaper" in metrics["net_debt"]["reason"]


def test_reported_and_derived_values_remain_unchanged_and_traceable():
    result = synthetic_result((2024, {}), (2025, {"revenue": 120, "operating_income": 24}))
    original = deepcopy(asdict(result))
    computed = row(result, 2025, "operating_margin_change_pp")
    assert computed["value"] == pytest.approx(-5)
    assert computed["unit"] == "percentage_points"
    assert computed["dependency_periods"][0]["fiscal_year"] == 2024
    assert computed["comparison_periods"] == [
        {"fiscal_year": 2024, "period_start": "2024-01-01", "period_end": "2024-12-31"},
        {"fiscal_year": 2025, "period_start": "2025-01-01", "period_end": "2025-12-31"}]
    assert len(computed["sources"]) == 4
    assert asdict(result) == original


def test_free_cash_flow_recomputed_in_python_instead_of_trusting_an_attached_total():
    result = synthetic_result((2025, {}))
    result.periods[0].metrics["free_cash_flow"] = MetricValue(9999, "USD", [])
    assert row(result, 2025, "free_cash_flow")["value"] == 30


def test_growth_has_both_exact_period_dependencies():
    result = synthetic_result((2024, {}), (2025, {"revenue": 125}))
    computed = row(result, 2025, "revenue_growth")
    assert computed["value"] == 0.25
    assert computed["dependencies"] == ["2024:revenue", "2025:revenue"]
    assert {s["start"] for s in computed["sources"]} == {"2024-01-01", "2025-01-01"}
    assert computed["derived"] and computed["evidence_label"] == "derived_calculation"


@pytest.mark.parametrize("prior,current,reason", [(0, 10, "positive prior"), (-10, 10, "positive prior"),
                                                    (-10, -5, "positive prior"), (10, -5, "sign transition")])
def test_misleading_growth_is_unavailable_but_absolute_change_remains(prior, current, reason):
    result = synthetic_result((2024, {"net_income": prior}), (2025, {"net_income": current}))
    computed = row(result, 2025, "net_income_growth")
    assert computed["value"] is None and reason in computed["reason"]
    assert row(result, 2025, "net_income_change")["value"] == current - prior
    assert computed["source_id"] not in analytics_evidence(result)


def test_positive_growth_base_to_zero_is_valid_and_not_a_division_by_zero():
    result = synthetic_result((2024, {}), (2025, {"net_income": 0}))
    assert row(result, 2025, "net_income_growth")["value"] == -1


@pytest.mark.parametrize("metric,value,derived", [("revenue", 0, "capex_to_revenue"),
    ("revenue", -1, "operating_margin"), ("operating_cash_flow", 0, "capex_to_operating_cash_flow"),
    ("operating_cash_flow", -1, "net_debt_to_operating_cash_flow"),
    ("net_income", -1, "free_cash_flow_conversion")])
def test_nonpositive_ratio_denominators_are_explained(metric, value, derived):
    computed = row(synthetic_result((2025, {metric: value})), 2025, derived)
    assert computed["value"] is None
    assert "positive denominator" in computed["reason"]


def test_missing_sec_input_is_not_zero_and_never_becomes_ai_evidence():
    result = synthetic_result((2025, {"capital_expenditure": None}))
    computed = row(result, 2025, "free_cash_flow")
    assert computed["value"] is None
    assert "Synthetic unavailable" in computed["reason"]
    assert "2025:analytics.free_cash_flow" not in analytics_evidence(result)


def test_nonfinite_input_is_unavailable_without_invalid_json_exports():
    result = synthetic_result((2025, {"operating_cash_flow": float("inf")}))
    computed = row(result, 2025, "free_cash_flow")
    assert computed["value"] is None and "finite" in computed["reason"]
    json.dumps(build_analytics(result), allow_nan=False)


def test_concept_switch_blocks_comparisons_without_blocking_unrelated_series():
    result = synthetic_result((2024, {}), (2025, {"revenue": 120}))
    result.periods[1].metrics["revenue"].sources[0].concept = "us-gaap:Revenues"
    assert row(result, 2025, "revenue_growth")["value"] is None
    assert "concept sets changed" in row(result, 2025, "revenue_growth")["reason"]
    assert row(result, 2025, "net_income_growth")["value"] == 0


@pytest.mark.parametrize("defect", ["gap", "overlap", "quarter", "source_period", "source_unit", "value_mismatch"])
def test_period_and_source_inconsistencies_are_never_calculated(defect):
    result = synthetic_result((2024, {}), (2025, {"revenue": 120}))
    current = result.periods[1]
    if defect == "gap":
        result.periods[1].fiscal_year = 2026
    elif defect == "overlap":
        current.start = "2024-12-30"
    elif defect == "quarter":
        current.start = "2025-10-01"
        with pytest.raises(ValueError, match="annual"):
            build_analytics(result)
        return
    elif defect == "source_period":
        current.metrics["revenue"].sources[0].start = "2025-04-01"
    elif defect == "source_unit":
        current.metrics["revenue"].sources[0].unit = "shares"
    elif defect == "value_mismatch":
        current.metrics["revenue"].sources[0].value = 999
    assert row(result, current.fiscal_year, "revenue_growth")["value"] is None


def test_three_year_acceleration_uses_two_verified_growth_rates():
    result = synthetic_result((2023, {"revenue": 100}), (2024, {"revenue": 110}), (2025, {"revenue": 132}))
    assert row(result, 2024, "revenue_growth_acceleration_pp")["value"] is None
    computed = row(result, 2025, "revenue_growth_acceleration_pp")
    assert computed["value"] == pytest.approx(10)
    assert [p["fiscal_year"] for p in computed["comparison_periods"]] == [2023, 2024, 2025]
    assert {s["start"] for s in computed["sources"]} == {"2023-01-01", "2024-01-01", "2025-01-01"}


def test_fifty_two_and_fifty_three_week_years_are_allowed_with_length_caveat():
    result = synthetic_result((2024, {}), (2025, {"revenue": 110}))
    for period, start, end in zip(result.periods, ["2023-12-31", "2024-12-29"], ["2024-12-28", "2026-01-03"]):
        period.start, period.end = start, end
        for metric in period.metrics.values():
            for source in metric.sources:
                source.start = None if source.start is None else start
                source.end = end
    assert row(result, 2025, "revenue_growth")["value"] == 0.1
    assert any("52/53-week" in text for text in build_analytics(result)["limitations"])


def test_cash_flow_ratios_and_net_cash_leverage_use_defensible_definitions():
    result = synthetic_result((2025, {}))
    assert row(result, 2025, "free_cash_flow_conversion")["value"] == 1.5
    assert row(result, 2025, "free_cash_flow_margin")["value"] == 0.3
    assert row(result, 2025, "net_debt")["value"] == -20
    assert row(result, 2025, "net_debt")["period_start"] is None
    assert row(result, 2025, "net_debt_to_operating_cash_flow")["value"] == -0.5
    limits = " ".join(build_analytics(result)["limitations"])
    assert all(term in limits for term in ("not EBITDA", "leases", "AI-specific", "ROIC"))


def test_leverage_changes_preserve_net_cash_signs_and_both_annual_denominators():
    result = synthetic_result((2024, {}), (2025, {"total_debt": 60, "operating_cash_flow": 50}))
    computed = row(result, 2025, "net_debt_to_operating_cash_flow_change")
    assert computed["value"] == pytest.approx(0.7)
    assert computed["unit"] == "ratio"
    assert set(computed["dependencies"]) == {"2024:total_debt", "2024:cash_and_equivalents", "2024:operating_cash_flow",
                                              "2025:total_debt", "2025:cash_and_equivalents", "2025:operating_cash_flow"}
    assert row(result, 2025, "net_debt_change")["value"] == 30


def test_tensions_retain_comparisons_magnitudes_and_sources_without_causality():
    result = synthetic_result((2024, {}), (2025, {"revenue": 120, "operating_income": 24, "net_income": 30,
                                                "operating_cash_flow": 44, "capital_expenditure": 30, "total_debt": 60}))
    analysis = build_analytics(result)
    book = build_evidence_book(result)
    expected = {"growth_margin_tension", "cash_investment_tension", "earnings_cash_tension", "investment_intensity",
                "cash_flow_divergence", "earnings_conversion_tension"}
    assert {t["type"] for t in analysis["tensions"]} == expected
    for tension in analysis["tensions"]:
        assert set(tension["source_ids"]) <= set(book)
        assert tension["prior_period"]["fiscal_year"] == 2024
        assert tension["current_period"]["fiscal_year"] == 2025
        assert tension["requires_analyst_interpretation"]
        assert tension["comparisons"] and tension["changes"]


def test_small_changes_do_not_trigger_exaggerated_materiality_observations():
    result = synthetic_result((2024, {}), (2025, {"revenue": 101, "operating_income": 25,
                                                 "capital_expenditure": 10.1, "total_debt": 30.2}))
    assert build_analytics(result)["tensions"] == []


def test_debt_growth_without_cash_generation_and_explicit_threshold_override():
    result = synthetic_result((2024, {}), (2025, {"total_debt": 36, "operating_cash_flow": 40.4}))
    assert "debt_cash_tension" in {t["type"] for t in build_analytics(result)["tensions"]}
    assert "debt_cash_tension" not in {t["type"] for t in build_analytics(result, {"debt_growth": 0.30})["tensions"]}


def test_negative_free_cash_flow_transition_is_detected_without_a_misleading_growth_rate():
    result = synthetic_result((2024, {}), (2025, {"net_income": 25, "capital_expenditure": 50}))
    assert row(result, 2025, "free_cash_flow_growth")["value"] is None
    assert "earnings_cash_tension" in {t["type"] for t in build_analytics(result)["tensions"]}


@pytest.mark.parametrize("thresholds", [{"invented": 1}, {"debt_growth": -1}, {"material_growth": True},
                                        {"margin_change_pp": float("nan")}])
def test_invalid_threshold_configuration_is_explicit(thresholds):
    with pytest.raises(ValueError, match="threshold"):
        build_analytics(synthetic_result((2025, {})), thresholds)


def test_analytics_are_json_serialisable_without_nonfinite_values_and_retain_offline_label():
    result = load_research("MSFT", "offline")
    payload = json.dumps(build_analytics(result), allow_nan=False)
    assert "offline" in payload
    assert all(entry["mode"] == "offline" for entry in analytics_evidence(result).values())
    assert all(entry["value"] is not None for entry in analytics_evidence(result).values())


def test_ambiguous_data_mode_duplicate_years_and_missing_periods_are_explicit():
    result = synthetic_result((2025, {}))
    result.mode = "unknown"
    with pytest.raises(ValueError, match="mode"):
        build_analytics(result)
    result.mode = "offline"
    result.periods.append(deepcopy(result.periods[0]))
    with pytest.raises(ValueError, match="Duplicate"):
        build_analytics(result)
    result.periods = []
    analysis = build_analytics(result)
    assert not analysis["metrics"] and not analysis["tensions"]
    assert "No annual periods" in analysis["limitations"][-1]
