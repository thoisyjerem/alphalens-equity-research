"""Deterministic financial Markdown note; no provider, prompt or network access."""
from __future__ import annotations

import html
import re

from .analytics import build_analytics
from .evidence import build_evidence_book
from .financials import metric_definitions
from .service import build_observations


DERIVED = {"operating_margin", "free_cash_flow", "total_debt", "net_debt"}


def _text(value):
    value = html.escape(" ".join(str(value).split()), quote=True)
    return re.sub(r"([\\`*_{}\[\]()#+|])", r"\\\1", value)


def _value(value, unit, *, scaled=False):
    if value is None:
        return "N/A"
    if unit == "ratio":
        return f"{value * 100:,.2f}%"
    if unit == "percentage_points":
        return f"{value:+,.2f} pp"
    if scaled and unit == "USD":
        return f"{value / 1_000_000:,.2f}"
    return f"{value:,.4f}".rstrip("0").rstrip(".")


def financial_markdown(result):
    """Render annual levels, checked comparisons, N/A reasons and exact sources.

    The source packet must pass the existing issuer/period checks. Reported
    single-tag amounts and the principal formula outputs are also tied out;
    a mutated amount must not acquire a credible-looking source appendix.
    """
    if not result.periods:
        raise ValueError("No verified annual periods are available for a financial report.")
    book = build_evidence_book(result)
    analytics = build_analytics(result)
    periods = sorted(result.periods, key=lambda p: p.end)
    definitions = metric_definitions()
    for period in periods:
        for key, metric in period.metrics.items():
            if metric.value is None:
                continue
            source = book.get(f"{period.fiscal_year}:{key}")
            source_unit = "USD" if key in DERIVED else metric.unit
            if (source is None or metric.unit != definitions[key]["unit"]
                    or any(fact["unit"] != source_unit for fact in source["sources"])):
                raise ValueError("A financial amount lacks matching source units or provenance.")
            if key not in DERIVED and any(fact["value"] != metric.value for fact in source["sources"]):
                raise ValueError("A reported amount disagrees with its source facts.")
            # Extraction has already selected non-overlapping debt components.
            # Retie the aggregate as well as its net-debt derivative on export.
            if key == "total_debt" and metric.value != sum(fact["value"] for fact in source["sources"]):
                raise ValueError("A calculated debt amount disagrees with its source components.")
        for key, inputs, formula in (
            ("free_cash_flow", ("operating_cash_flow", "capital_expenditure"), lambda a, b: a - b),
            ("operating_margin", ("operating_income", "revenue"), lambda a, b: a / b if b else None),
            ("net_debt", ("total_debt", "cash_and_equivalents"), lambda a, b: a - b),
        ):
            metric = period.metrics.get(key)
            if metric is None or metric.value is None:
                continue
            values = [period.metrics.get(item) for item in inputs]
            expected = formula(*[item.value for item in values]) if all(item and item.value is not None for item in values) else None
            if expected is None or metric.value != expected:
                raise ValueError("A calculated amount disagrees with its financial inputs.")
    mode = "OFFLINE DEMONSTRATION — historical genuine SEC fixture" if result.mode == "offline" else "SEC annual reported financials — downloaded or cached as disclosed below"
    lines = [f"# AlphaLens financial research — {_text(result.name)} ({_text(result.ticker)})", "",
        f"**Data status:** {mode}", f"**CIK:** {_text(result.cik)}", f"**Source snapshot:** {_text(result.retrieved_at)}", "",
        "Python-generated financial note. No AI output or market-price data is included.", "", "## Reporting periods", ""]
    for period in periods:
        lines.append(f"- FY{period.fiscal_year}: {period.start} to {period.end}; balance-sheet figures are instants at {period.end}.")
    lines.extend(["", "## Annual financial summary", "", "USD millions except margins (%) and diluted EPS (USD/share). Rounded displays retain exact amounts in the source appendix.", "",
        "| Metric | " + " | ".join(f"FY{p.fiscal_year}" for p in periods) + " |",
        "| --- | " + " | ".join("---:" for _ in periods) + " |"])
    for key, definition in definitions.items():
        cells = []
        for period in periods:
            metric = period.metrics.get(key)
            if metric is None or metric.value is None:
                cells.append("N/A")
            else:
                cells.append(f"{_value(metric.value, metric.unit, scaled=True)} (`{period.fiscal_year}:{key}`)")
        lines.append(f"| {_text(definition['label'])} | " + " | ".join(cells) + " |")
    lines.extend(["", "## Deterministic financial briefing", ""])
    lines.extend("- " + _text(text) for text in build_observations(result))
    latest = periods[-1].fiscal_year
    preferred = ("cash_flow_divergence", "revenue_profit_growth", "investment_intensity")
    observations = {row["type"]: row for row in analytics["tensions"] if row["current_period"]["fiscal_year"] == latest}
    for kind in preferred:
        if kind in observations:
            row = observations[kind]
            lines.extend(["", f"**{_text(row['title'])}** (`{row['id']}`)", "", _text(row["explanation"]), "",
                "Financial source IDs: " + ", ".join(f"`{key}`" for key in row["source_ids"]) + "."])
    chosen = {"revenue_growth", "operating_income_growth", "operating_margin_change_pp", "operating_cash_flow_growth",
        "capital_expenditure_growth", "free_cash_flow_growth", "free_cash_flow_margin"}
    lines.extend(["", "## Checked annual calculations", "", "| Calculation | Value | Periods | Formula / source IDs |", "| --- | ---: | --- | --- |"])
    for row in analytics["metrics"]:
        if row["fiscal_year"] != latest or row["metric"] not in chosen:
            continue
        dates = row["comparison_periods"] or [{"period_start": row["period_start"], "period_end": row["period_end"]}]
        labels = "; ".join(f"{p['period_start']} to {p['period_end']}" for p in dates)
        detail = row["reason"] if row["value"] is None else row["calculation"] + "; inputs " + ", ".join(row["dependencies"])
        lines.append(f"| {_text(row['label'])} | {_value(row['value'], row['unit'])} | {labels} | {_text(detail)} |")
    from .investment_reasoning import build_investment_reasoning
    from .research_exports import investment_reasoning_markdown
    lines.extend(["", investment_reasoning_markdown(build_investment_reasoning(book, analytics)), ""])
    lines.extend(["", "## Missing information", ""])
    missing = False
    for period in periods:
        for key in definitions:
            metric = period.metrics.get(key)
            if metric is None or metric.value is None:
                missing = True
                lines.append(f"- FY{period.fiscal_year} {_text(definitions[key]['label'])}: N/A — {_text(metric.reason if metric else 'Metric is absent.')}.")
    if not missing:
        lines.append("All requested metrics are available; broader research inputs may still be absent.")
    lines.extend(["", "## Definitions and source selection", ""])
    for definition in definitions.values():
        lines.append(f"- **{_text(definition['label'])}:** {_text(definition['description'])}")
    lines.extend(["", "Only matching annual durations and year-end instants are used. Later comparative filings may restate history; this is not point-in-time backtest data. Concept changes are not assumed comparable.", "",
        "## Financial source appendix", ""])
    for source_id, source in book.items():
        if source["kind"] != "financial":
            continue
        period = f"instant at {source['period_end']}" if source["period_start"] is None else f"{source['period_start']} to {source['period_end']}"
        lines.extend([f"### `{source_id}`", "", f"Exact Python amount: {source['value']} {_text(source['unit'])}; FY{source['fiscal_year']}; {period}."])
        for fact in source["sources"]:
            dates = f"instant at {fact['end']}" if fact["start"] is None else f"{fact['start']} to {fact['end']}"
            lines.append(f"- `{fact['concept']}`: {fact['value']} {_text(fact['unit'])}; {dates}; {_text(fact['form'])}; accession `{fact['accession']}`; filed {fact['filed']}; [SEC filing]({fact['url']}).")
        lines.append("")
    lines.extend(["## Data warnings and limitations", ""])
    lines.extend("- " + _text(text) for text in [*result.warnings, *analytics["limitations"]])
    lines.extend(["", "Financial-source and arithmetic checks do not establish investment merit. No valuation, forecast, rating or AI-specific return is calculated.", ""])
    return "\n".join(lines)
