"""Synthetic *unit-test* data only; none of these numbers are company data.

The separately labelled checked-in offline demonstration fixtures are verified
reported figures. These deliberately artificial cases exercise selection logic.
"""

from copy import deepcopy

import pytest

from alphalens.financials import extract_annuals, metric_definitions


ACC = "0000000001-25-000001"
NEW = "0000000001-26-000001"
REVENUE = "RevenueFromContractWithCustomerExcludingAssessedTax"


def fact(value=100, start="2024-07-01", end="2025-06-30", filed="2025-08-01", accn=ACC,
         form="10-K", fy=2025, **extra):
    row = dict(val=value, end=end, filed=filed, accn=accn, form=form, fy=fy, fp="FY")
    if start is not None:
        row["start"] = start
    row.update(extra)
    return row


def facts(tags=None, cik=1):
    return {"cik": cik, "entityName": "SYNTHETIC UNIT TEST ONLY",
            "facts": {"us-gaap": tags or {}}}


def tag(*rows, unit="USD"):
    return {"units": {unit: list(rows)}}


def submissions(*rows):
    rows = rows or (("2025-06-30", ACC, "10-K"),)
    return {"filings": {"recent": {
        "reportDate": [r[0] for r in rows], "accessionNumber": [r[1] for r in rows],
        "form": [r[2] for r in rows],
    }}}


def metrics(data, sub=None):
    return extract_annuals(data, sub or submissions())[0].metrics


def full_data(cik=1):
    return facts({
        REVENUE: tag(fact(100)),
        "OperatingIncomeLoss": tag(fact(25)),
        "NetIncomeLoss": tag(fact(20)),
        "EarningsPerShareDiluted": tag(fact(2), unit="USD/shares"),
        "NetCashProvidedByUsedInOperatingActivities": tag(fact(35)),
        "PaymentsToAcquirePropertyPlantAndEquipment": tag(fact(12)),
        "CashAndCashEquivalentsAtCarryingValue": tag(fact(50, start=None)),
        "LongTermDebtCurrent": tag(fact(5, start=None)),
        "LongTermDebtNoncurrent": tag(fact(25, start=None)),
        "ShortTermBorrowings": tag(fact(4, start=None)),
    }, cik=cik)


def test_python_calculations_retain_input_provenance():
    result = metrics(full_data())
    assert result["operating_margin"].value == 0.25
    assert result["free_cash_flow"].value == 23
    assert result["total_debt"].value == 34
    assert result["net_debt"].value == -16
    assert len(result["free_cash_flow"].sources) == 2
    assert len(result["net_debt"].sources) == 4
    source = result["revenue"].sources[0]
    assert source.concept == f"us-gaap:{REVENUE}"
    assert source.start == "2024-07-01"
    assert source.url.endswith(f"/{ACC}-index.html")
    assert "/1/000000000125000001/" in source.url


def test_comparative_fy_is_not_period_year():
    data = facts({REVENUE: tag(
        fact(100),
        fact(90, start="2023-07-01", end="2024-06-30"),
        fact(80, start="2022-07-01", end="2023-06-30"),
        fact(70, start="2021-07-01", end="2022-06-30"),
    )})
    periods = extract_annuals(data, submissions())
    assert [p.fiscal_year for p in periods] == [2023, 2024, 2025]
    assert [p.metrics["revenue"].value for p in periods] == [80, 90, 100]


def test_missing_latest_report_not_silently_backfilled_with_old_year():
    data = facts({REVENUE: tag(
        fact(100),
        fact(90, start="2023-07-01", end="2024-06-30"),
        fact(80, start="2022-07-01", end="2023-06-30"),
    )})
    sub = submissions(("2026-06-30", NEW, "10-K"), ("2025-06-30", ACC, "10-K"))
    periods = extract_annuals(data, sub, years=3)
    assert [p.end for p in periods] == ["2024-06-30", "2025-06-30"]
    assert extract_annuals(data, sub, years=1) == []


def test_non_calendar_fiscal_label_from_own_filing_not_end_year():
    data = facts({REVENUE: tag(fact(100, start="2024-02-04", end="2025-02-01", fy=2024))})
    period = extract_annuals(data, submissions(("2025-02-01", ACC, "10-K")))[0]
    assert period.fiscal_year == 2024
    assert period.start == "2024-02-04"


def test_january_comparative_fiscal_year_label_uses_verified_current_label():
    data = facts({REVENUE: tag(
        fact(100, start="2024-02-04", end="2025-02-01", fy=2024),
        fact(90, start="2023-01-29", end="2024-02-03", fy=2024),
        fact(80, start="2022-01-30", end="2023-01-28", fy=2024),
    )})
    periods = extract_annuals(data, submissions(("2025-02-01", ACC, "10-K")))
    assert [p.fiscal_year for p in periods] == [2022, 2023, 2024]
    assert [p.end for p in periods] == ["2023-01-28", "2024-02-03", "2025-02-01"]


@pytest.mark.parametrize("start,end", [("2024-07-01", "2025-06-30"), ("2023-10-01", "2024-10-05")])
def test_52_and_53_week_years_eligible(start, end):
    data = facts({REVENUE: tag(fact(100, start=start, end=end))})
    assert extract_annuals(data, submissions((end, ACC, "10-K")))[0].metrics["revenue"].value == 100


@pytest.mark.parametrize("bad", [
    fact(999, start="2025-04-01"),  # quarter inside a 10-K
    fact(999, start="2025-01-01"),  # YTD inside a 10-K
    fact(999, form="10-Q"),         # annual-like duration from wrong form
    fact(999, start="2023-07-01"), # multi-year duration
    fact(999, start=None),          # balance sheet instant cannot be revenue
])
def test_reject_quarter_ytd_wrong_form_multiyear_and_instant(bad):
    data = facts({REVENUE: tag(fact(100), bad)})
    assert metrics(data)["revenue"].value == 100


def test_exact_start_required_and_not_calendar_year_substitution():
    data = full_data()
    data["facts"]["us-gaap"]["OperatingIncomeLoss"] = tag(fact(25, start="2024-07-02"))
    result = metrics(data)
    assert result["operating_income"].value is None
    assert result["operating_margin"].value is None
    assert "incompatible-period" in result["operating_income"].reason


def test_latest_comparative_wins_and_keeps_actual_reporting_dates():
    data = facts({REVENUE: tag(fact(100), fact(110, filed="2026-08-01", accn=NEW, fy=2026))})
    metric = metrics(data)["revenue"]
    assert metric.value == 110
    assert metric.sources[0].filed == "2026-08-01"
    assert metric.sources[0].start == "2024-07-01"


def test_later_amendment_wins_but_same_day_conflict_not_guessed():
    amended = fact(101, filed="2025-08-02", accn=NEW, form="10-K/A")
    data = facts({REVENUE: tag(fact(100), amended)})
    assert metrics(data)["revenue"].value == 101
    amended["filed"] = "2025-08-01"
    metric = metrics(data)["revenue"]
    assert metric.value is None
    assert "Conflicting" in metric.reason
    assert len(metric.sources) == 2


def test_duplicate_facts_deduplicated_and_conflicting_latest_values_na():
    row = fact(100)
    data = facts({REVENUE: tag(row, deepcopy(row))})
    assert len(metrics(data)["revenue"].sources) == 1
    data["facts"]["us-gaap"][REVENUE]["units"]["USD"].append(fact(101))
    assert metrics(data)["revenue"].value is None


def test_equivalent_revenue_tag_latest_filing_not_priority_order():
    data = facts({REVENUE: tag(fact(100)), "Revenues": tag(fact(111, filed="2025-09-01", accn=NEW))})
    metric = metrics(data)["revenue"]
    assert metric.value == 111
    assert metric.sources[0].concept == "us-gaap:Revenues"


def test_revenue_alternatives_conflict_becomes_na():
    data = facts({REVENUE: tag(fact(100)), "Revenues": tag(fact(111))})
    assert metrics(data)["revenue"].value is None


def test_accounting_scope_alternatives_not_assumed_equivalent():
    data = full_data()
    del data["facts"]["us-gaap"][REVENUE]
    del data["facts"]["us-gaap"]["NetIncomeLoss"]
    data["facts"]["us-gaap"]["SalesRevenueGoodsNet"] = tag(fact(500))
    data["facts"]["us-gaap"]["ProfitLoss"] = tag(fact(50))
    result = metrics(data)
    assert result["revenue"].value is None
    assert result["net_income"].value is None


def test_units_are_not_silently_converted_or_ignored():
    data = full_data()
    data["facts"]["us-gaap"][REVENUE] = tag(fact(100), unit="EUR")
    data["facts"]["us-gaap"]["EarningsPerShareDiluted"] = tag(fact(2), unit="USD")
    result = metrics(data)
    assert result["revenue"].value is None
    assert result["diluted_eps"].value is None
    assert "USD/shares" in result["diluted_eps"].reason


def test_instant_uses_exact_year_end_and_rejects_duration_cash():
    data = full_data()
    data["facts"]["us-gaap"]["CashAndCashEquivalentsAtCarryingValue"] = tag(
        fact(51, start=None, end="2025-06-29"), fact(99))
    assert metrics(data)["cash_and_equivalents"].value is None


def test_no_periods_from_balance_sheet_only_or_quarter_revenue():
    assert extract_annuals(facts({"CashAndCashEquivalentsAtCarryingValue": tag(fact(50, start=None))}), submissions()) == []
    assert extract_annuals(facts({REVENUE: tag(fact(50, start="2025-04-01"))}), submissions()) == []


def test_zero_revenue_margin_undefined_and_missing_capex_not_zero():
    data = full_data()
    data["facts"]["us-gaap"][REVENUE] = tag(fact(0))
    del data["facts"]["us-gaap"]["PaymentsToAcquirePropertyPlantAndEquipment"]
    result = metrics(data)
    assert result["operating_margin"].value is None
    assert "zero revenue" in result["operating_margin"].reason
    assert result["free_cash_flow"].value is None
    assert "Free cash flow unavailable" in result["free_cash_flow"].reason


def test_negative_capex_is_flagged_not_silently_reversed():
    data = full_data()
    data["facts"]["us-gaap"]["PaymentsToAcquirePropertyPlantAndEquipment"] = tag(fact(-12))
    result = metrics(data)
    assert result["capital_expenditure"].value is None
    assert result["free_cash_flow"].value is None
    assert result["capital_expenditure"].sources[0].value == -12


def test_current_aggregate_debt_may_include_leases_and_is_not_substituted():
    data = full_data()
    data["facts"]["us-gaap"]["DebtCurrent"] = tag(fact(99, start=None))
    data["facts"]["us-gaap"]["CommercialPaper"] = tag(fact(4, start=None))
    result = metrics(data)["total_debt"]
    assert result.value == 34
    assert {s.concept for s in result.sources} == {"us-gaap:LongTermDebtCurrent", "us-gaap:LongTermDebtNoncurrent", "us-gaap:ShortTermBorrowings"}
    del data["facts"]["us-gaap"]["ShortTermBorrowings"]
    assert metrics(data)["total_debt"].value is None


def test_long_term_aggregate_not_added_to_its_components_again():
    data = full_data()
    data["facts"]["us-gaap"]["LongTermDebt"] = tag(fact(30, start=None))
    assert metrics(data)["total_debt"].value == 34
    data["facts"]["us-gaap"]["LongTermDebt"] = tag(fact(31, start=None))
    result = metrics(data)["total_debt"]
    assert result.value is None
    assert "disagrees" in result.reason


@pytest.mark.parametrize("tag_name", ["LongTermDebtCurrent", "LongTermDebtNoncurrent"])
@pytest.mark.parametrize("invalid_value", [6, -1])
def test_debt_aggregate_cannot_hide_explicit_conflicting_or_negative_detail(tag_name, invalid_value):
    data = full_data()
    data["facts"]["us-gaap"]["LongTermDebt"] = tag(fact(30, start=None))
    row = fact(invalid_value, start=None)
    if invalid_value < 0:
        data["facts"]["us-gaap"][tag_name] = tag(row)
    else:
        data["facts"]["us-gaap"][tag_name]["units"]["USD"].append(row)
    result = metrics(data)["total_debt"]
    assert result.value is None
    assert "Conflicting" in result.reason if invalid_value > 0 else "Negative debt balance" in result.reason
    assert any(s.concept == f"us-gaap:{tag_name}" for s in result.sources)


def test_missing_debt_component_not_assumed_zero_and_leases_excluded():
    data = full_data()
    del data["facts"]["us-gaap"]["ShortTermBorrowings"]
    data["facts"]["us-gaap"]["OperatingLeaseLiabilityCurrent"] = tag(fact(4, start=None))
    data["facts"]["us-gaap"]["FinanceLeaseLiabilityCurrent"] = tag(fact(4, start=None))
    result = metrics(data)
    assert result["total_debt"].value is None
    assert result["net_debt"].value is None


def test_negative_debt_not_permitted_to_reduce_total():
    data = full_data()
    data["facts"]["us-gaap"]["ShortTermBorrowings"] = tag(fact(-4, start=None))
    result = metrics(data)["total_debt"]
    assert result.value is None
    assert "Negative debt balance" in result.reason


def test_commercial_paper_profile_is_explicit_and_never_added_twice():
    data = full_data(cik=789019)
    data["facts"]["us-gaap"]["CommercialPaper"] = tag(fact(4, start=None))
    assert metrics(data)["total_debt"].value == 34
    del data["facts"]["us-gaap"]["ShortTermBorrowings"]
    assert metrics(data)["total_debt"].value == 34
    data["cik"] = 1
    assert metrics(data)["total_debt"].value is None


def test_missing_values_have_specific_reason_and_valid_zero_retained():
    data = full_data()
    data["facts"]["us-gaap"]["NetIncomeLoss"] = tag(fact(0))
    del data["facts"]["us-gaap"]["OperatingIncomeLoss"]
    result = metrics(data)
    assert result["net_income"].value == 0
    assert result["operating_income"].value is None
    assert "2024-07-01 to 2025-06-30" in result["operating_income"].reason


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), True, "123"])
def test_malformed_non_numeric_facts_ignored(bad):
    data = full_data()
    data["facts"]["us-gaap"]["NetIncomeLoss"] = tag(fact(bad))
    assert metrics(data)["net_income"].value is None


def test_conflicting_near_annual_start_dates_are_not_merged():
    data = facts({REVENUE: tag(fact(100), fact(100, start="2024-07-02"))})
    assert extract_annuals(data, submissions()) == []


@pytest.mark.parametrize("years", [0, -1, True, 1.5])
def test_invalid_requested_years(years):
    with pytest.raises(ValueError):
        extract_annuals(full_data(), submissions(), years)


def test_definitions_copy_and_every_metric_documented():
    definitions = metric_definitions()
    assert set(metrics(full_data())) == set(definitions)
    assert all(d["label"] and d["unit"] and d["concepts"] and d["description"] for d in definitions.values())
    definitions["revenue"]["concepts"].clear()
    assert metric_definitions()["revenue"]["concepts"]
