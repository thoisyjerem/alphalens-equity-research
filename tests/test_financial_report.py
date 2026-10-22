"""Financial Markdown exports preserve accounting and provenance, without AI.

All examples use the bundled, provenance-checked historical SEC fixture. Mutated
copies are deliberately invalid test inputs, never substitute financial data.
"""
from copy import deepcopy

import pytest

from alphalens.financial_report import financial_markdown
from alphalens.service import load_research


@pytest.fixture
def research(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("A deterministic financial export cannot make a request")

    monkeypatch.setattr("requests.sessions.Session.request", forbidden)
    monkeypatch.setattr("alphalens.providers.request_structured", forbidden)
    return deepcopy(load_research("MSFT", "offline"))


def section(report, source_id):
    return report.split(f"### `{source_id}`\n", 1)[1].split("\n### `", 1)[0]


def test_financial_note_has_source_bound_levels_and_checked_cash_flow_insight(research):
    report = financial_markdown(research)
    latest = research.periods[-1]
    year = latest.fiscal_year
    assert "OFFLINE DEMONSTRATION — historical genuine SEC fixture" in report
    assert "No AI output or market-price data is included" in report
    for key, label in (("revenue", "Revenue"), ("operating_cash_flow", "Operating cash flow"),
                       ("capital_expenditure", "Capital expenditure"), ("free_cash_flow", "Free cash flow")):
        metric = latest.metrics[key]
        assert f"{metric.value / 1_000_000:,.2f} (`{year}:{key}`)" in report
        assert f"Exact Python amount: {metric.value} USD; FY{year}; {latest.start} to {latest.end}." in section(report, f"{year}:{key}")
        assert f"| {label} |" in report
    assert "Operating cash flow increased while free cash flow declined" in report
    assert "not proof of AI spending or poor future returns" in report
    assert "## Checked annual calculations" in report
    assert "capital expenditure" in report.lower()
    assert "## Data warnings and limitations" in report


def test_source_appendix_retains_exact_units_accession_filing_dates_and_instant_period(research):
    report = financial_markdown(research)
    latest = research.periods[-1]
    for key in ("revenue", "diluted_eps", "cash_and_equivalents"):
        metric = latest.metrics[key]
        appendix = section(report, f"{latest.fiscal_year}:{key}")
        for source in metric.sources:
            dates = f"instant at {source.end}" if source.start is None else f"{source.start} to {source.end}"
            assert f"`{source.concept}`: {source.value} {source.unit}; {dates}; {source.form}; accession `{source.accession}`; filed {source.filed}; [SEC filing]({source.url})." in appendix
        assert f"Exact Python amount: {metric.value} {metric.unit};" in appendix
    cash = section(report, f"{latest.fiscal_year}:cash_and_equivalents")
    assert f"instant at {latest.end}" in cash
    assert latest.start not in cash
    margin = section(report, f"{latest.fiscal_year}:operating_margin")
    assert f"Exact Python amount: {latest.metrics['operating_margin'].value} ratio;" in margin
    assert "Exact Python amount: 46.78% ratio" not in margin
    assert f"{latest.metrics['operating_margin'].value * 100:.2f}% (`{latest.fiscal_year}:operating_margin`)" in report


def test_missing_debt_is_na_with_actual_missing_component_reason(research):
    latest = research.periods[-1]
    assert latest.metrics["total_debt"].value is None
    report = financial_markdown(research)
    assert f"FY{latest.fiscal_year} Total debt: N/A" in report
    assert f"FY{latest.fiscal_year} Net debt: N/A" in report
    assert "CommercialPaper" in report
    assert f"### `{latest.fiscal_year}:total_debt`" not in report
    assert f"### `{latest.fiscal_year}:net_debt`" not in report
    assert "missing, wrong-unit or incompatible-period facts are not substituted" in report


@pytest.mark.parametrize("key", ["free_cash_flow", "operating_margin", "net_debt"])
def test_mutated_calculated_amount_cannot_acquire_valid_looking_appendix(research, key):
    period = research.periods[-2]  # Debt is available for this source period.
    period.metrics[key].value += 1
    with pytest.raises(ValueError, match="calculated amount disagrees"):
        financial_markdown(research)


def test_mutated_total_debt_and_consistent_net_debt_are_rejected(research):
    period = research.periods[-2]
    period.metrics["total_debt"].value += 1_000_000_000
    period.metrics["net_debt"].value += 1_000_000_000
    with pytest.raises(ValueError, match="calculated debt amount disagrees"):
        financial_markdown(research)


@pytest.mark.parametrize("key", ["revenue", "operating_cash_flow", "diluted_eps"])
def test_mutated_reported_amount_is_rejected_without_touching_original_source(research, key):
    research.periods[-1].metrics[key].value += 1
    with pytest.raises(ValueError, match="reported amount disagrees"):
        financial_markdown(research)


@pytest.mark.parametrize("target,unit", [("metric", "EUR"), ("source", "EUR")])
def test_wrong_units_in_reported_financial_provenance_fail_closed(research, target, unit):
    metric = research.periods[-1].metrics["revenue"]
    if target == "metric":
        metric.unit = unit
    else:
        metric.sources[0].unit = unit
    with pytest.raises(ValueError, match="matching source units or provenance"):
        financial_markdown(research)


@pytest.mark.parametrize("key,field,value", [
    ("revenue", "start", "2025-10-01"),
    ("revenue", "end", "2026-03-31"),
    ("cash_and_equivalents", "start", "2025-07-01"),
])
def test_wrong_annual_or_instant_source_period_is_rejected(research, key, field, value):
    setattr(research.periods[-1].metrics[key].sources[0], field, value)
    with pytest.raises(ValueError, match="selected annual period or issuer"):
        financial_markdown(research)


def test_company_and_warning_text_cannot_inject_markdown_or_html(research):
    research.name = '<script>alert("unsafe")</script> [fake](https://example.test) | **heading**'
    research.warnings.append("<img src=x onerror=bad()>\n# forged | [link](unsafe)")
    report = financial_markdown(research)
    assert "<script>" not in report and "<img" not in report
    assert "&lt;script&gt;" in report and "&lt;img" in report
    assert r"\[fake\]\(https://example.test\) \| \*\*heading\*\*" in report
    assert r"\# forged \| \[link\]\(unsafe\)" in report


def test_empty_annual_data_is_explicit_failure_instead_of_empty_credible_report(research):
    research.periods = []
    with pytest.raises(ValueError, match="No verified annual periods"):
        financial_markdown(research)
