"""Legacy display observations reuse the annual accounting safeguards."""
from copy import deepcopy
import csv
import io
import json

import pytest

from alphalens.analytics import build_analytics
from alphalens.service import build_observations, load_research, snapshot_csv


def msft():
    return deepcopy(load_research("MSFT", "offline"))


def test_normal_observations_keep_checked_growth_values_and_exact_annual_ends():
    result = msft()
    rows = {row["metric"]: row for row in build_analytics(result)["metrics"] if row["fiscal_year"] == 2026}
    output = build_observations(result)
    for metric, label in (("revenue_growth", "Revenue"), ("operating_income_growth", "Operating income")):
        assert f"{label} changed {rows[metric]['value']:+.1%} between fiscal years ended 2025-06-30 and 2026-06-30 (Python calculation)." in output
    assert output[-1].startswith("Research question:")
    assert not any("Total debt" in text for text in output)


@pytest.mark.parametrize("metric,label", [("revenue", "Revenue"), ("operating_income", "Operating income")])
def test_changed_concepts_cannot_publish_legacy_growth(metric, label):
    result = msft()
    result.periods[-1].metrics[metric].sources[0].concept = "us-gaap:ChangedScopeTestConcept"
    output = build_observations(result)
    assert not any(text.startswith(label + " changed") for text in output)
    assert any(text.startswith(label + " comparison is N/A:") and "concept" in text for text in output)


def test_noncontiguous_periods_abstain_even_with_consecutive_fiscal_labels():
    result = msft()
    current = result.periods[-1]
    current.start = "2025-07-02"
    for metric in current.metrics.values():
        for source in metric.sources:
            if source.start is not None:
                source.start = current.start
    output = build_observations(result)
    assert not any(text.startswith(("Revenue changed", "Operating income changed")) for text in output)
    assert any("N/A" in text and "contiguous" in text for text in output)


@pytest.mark.parametrize("side,value,expected", [("prior", 0, "positive prior-period base"),
    ("prior", -1, "positive prior-period base"), ("current", -1, "Current value is negative")])
def test_zero_negative_bases_and_sign_transitions_do_not_receive_growth_rates(side, value, expected):
    result = msft()
    metric = result.periods[-2 if side == "prior" else -1].metrics["revenue"]
    metric.value = value
    for source in metric.sources:
        source.value = value
    output = build_observations(result)
    assert not any(text.startswith("Revenue changed") for text in output)
    assert any(text.startswith("Revenue comparison is N/A:") and expected in text for text in output)


def test_missing_input_stays_na_and_latest_derived_values_come_from_analytics():
    result = msft()
    result.periods[-1].metrics["free_cash_flow"].value = 9999
    result.periods[-1].metrics["operating_margin"].value = 0.999
    output = build_observations(result)
    assert any("Free cash flow for the fiscal year ended 2026-06-30: USD 66.99bn" in text for text in output)
    assert any("Operating margin for the fiscal year ended 2026-06-30: 46.8%" in text for text in output)
    result.periods[-1].metrics["operating_cash_flow"].value = None
    output = build_observations(result)
    assert any(text.startswith("Free cash flow is N/A:") for text in output)
    assert not any(text.startswith("Free cash flow for") for text in output)


def test_csv_instant_and_duration_dates_are_explicit_without_changing_values_or_sources():
    result = msft()
    output = list(csv.DictReader(io.StringIO(snapshot_csv(result))))
    assert len(output) == 33
    for row in output:
        period = next(period for period in result.periods if period.fiscal_year == int(row["fiscal_year"]))
        metric = period.metrics[row["metric"]]
        instant = row["metric"] in {"cash_and_equivalents", "total_debt", "net_debt"}
        assert row["period_type"] == ("instant" if instant else "duration")
        assert row["period_start"] == ("" if instant else period.start)
        assert row["period_end"] == period.end
        assert row["value"] == ("N/A" if metric.value is None else str(metric.value))
        assert row["data_status"] == "OFFLINE DEMONSTRATION" and row["ticker"] == "MSFT"
        assert len(json.loads(row["sources_json"])) == len(metric.sources)
        if instant:
            assert all(source["start"] is None for source in json.loads(row["sources_json"]))


def test_empty_result_has_no_invented_financial_observations():
    result = msft()
    result.periods = []
    output = build_observations(result)
    assert len(output) == 1 and output[0].startswith("Research question:")
