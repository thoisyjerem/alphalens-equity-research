"""Presentation-only comparisons for the fixed, revalidated Microsoft replay.

No model text is edited. The segment projection accepts one retained table
layout, cross-checks its consolidated amounts, and abstains if it changes.
This is not a general segment extractor or a new research-generation input.
"""
from __future__ import annotations

from decimal import Decimal
import re

from .research_integrity import validate_observation_integrity

SEGMENT_SOURCE_ID = "sec:3eb3eccc7d1065f444ebdf69"


def build_recorded_readout(validated) -> dict:
    """Reconcile the recorded cash bridge and reviewer margin comparison."""
    try:
        return _build(validated)
    except (KeyError, TypeError, AttributeError, StopIteration, ArithmeticError, ValueError):
        raise ValueError("Recorded comparison could not be reconciled with its annual sources.") from None


def _build(validated):
    book = validated.evidence
    validate_observation_integrity(book, validated.analysis, validated.financial_observations)
    cash = max((row for row in validated.financial_observations.values()
                if row["type"] == "cash_flow_divergence"),
               key=lambda row: row["current_period"]["fiscal_year"])
    prior, current = cash["prior_period"], cash["current_period"]
    years = prior["fiscal_year"], current["fiscal_year"]
    labels = {"operating_cash_flow": "Operating cash flow",
              "capital_expenditure": "Cash PP&E expenditure", "free_cash_flow": "Defined free cash flow"}
    cash_rows = []
    for metric, label in labels.items():
        sources = [book[f"{year}:{metric}"] for year in years]
        for source, period in zip(sources, (prior, current)):
            if (source["unit"] != "USD" or source["kind"] != "financial"
                    or any(source[key] != period[key] for key in period)):
                raise ValueError("Invalid annual cash comparison")
        values = [Decimal(str(source["value"])) for source in sources]
        if not all(value.is_finite() for value in values):
            raise ValueError("Unavailable cash value")
        cash_rows.append({"metric": metric, "label": label, "prior": values[0], "current": values[1],
                          "change": values[1] - values[0], "source_ids": [f"{year}:{metric}" for year in years]})
    for side in ("prior", "current", "change"):
        if cash_rows[0][side] - cash_rows[1][side] != cash_rows[2][side]:
            raise ValueError("Free cash flow bridge disagrees")

    table = book[SEGMENT_SOURCE_ID]
    reference = book[f"{years[1]}:operating_income"]
    if (table["kind"] != "passage" or table["ticker"] != "MSFT" or table["cik"] != "0000789019"
            or table["report_date"] != current["period_end"]
            or not any(fact["accession"] == table["accession"] and fact["end"] == table["report_date"]
                       and fact["form"] in {"10-K", "10-K/A"} for fact in reference["sources"])):
        raise ValueError("Segment provenance differs from annual facts")
    text = " ".join(table["text"].split())
    header = f"SEGMENT RESULTS OF OPERATIONS (In millions, except percentages) {years[1]} {years[0]} PercentageChange "
    if not text.startswith(header):
        raise ValueError("Unsupported segment units or periods")
    # Bound each match to a named row with all four amounts and percentages;
    # never scan other filing sections for apparently matching numbers.
    pattern = (r"Revenue \$ ([\d,]+) \$ ([\d,]+) \(?\d+\)?% "
               r"Cost of revenue ([\d,]+) ([\d,]+) \(?\d+\)?% "
               r"Operating expenses ([\d,]+) ([\d,]+) \(?\d+\)?% "
               r"Operating income \$ ([\d,]+) \$ ([\d,]+) \(?\d+\)?%")
    margins = []
    for name, label in (("Total", "Consolidated"), ("Intelligent Cloud", "Intelligent Cloud")):
        matches = list(re.finditer(re.escape(name) + " " + pattern, text))
        if len(matches) != 1:
            raise ValueError("Unsupported segment row layout")
        numbers = [Decimal(value.replace(",", "")) for value in matches[0].groups()]
        percentages = []
        for year, index in zip(years, (1, 0)):
            revenue, cost, opex, income = numbers[index::2]
            if revenue <= 0 or revenue - cost - opex != income:
                raise ValueError("Segment table identity disagrees")
            if name == "Total" and any(value * 1_000_000 != Decimal(str(book[f"{year}:{metric}"]["value"]))
                                       for value, metric in ((revenue, "revenue"), (income, "operating_income"))):
                raise ValueError("Consolidated table disagrees with SEC facts")
            percentages.append(income / revenue * 100)
        margins.append({"label": label, "prior_pct": percentages[0], "current_pct": percentages[1],
                        "change_pp": percentages[1] - percentages[0]})
    return {"prior_period": dict(prior), "current_period": dict(current), "cash_rows": cash_rows,
            "margins": margins, "segment_source_id": SEGMENT_SOURCE_ID}
