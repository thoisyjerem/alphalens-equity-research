"""Deterministic, source-linked annual comparisons; no retrieval or model calls.

Rates are decimal ratios; changes in margins/intensity are percentage points.
Non-positive growth bases and non-positive ratio denominators remain N/A.
Changes in XBRL concept sets are not automatically treated as comparable.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import date
import math

from .models import ResearchResult


DEFAULT_THRESHOLDS = {
    "material_growth": 0.05,
    "margin_change_pp": 1.0,
    "capex_growth_gap_pp": 10.0,
    "intensity_change_pp": 5.0,
    "debt_growth": 0.10,
    "cash_flow_growth_ceiling": 0.05,
}

_GROWTH_METRICS = ("revenue", "operating_income", "net_income", "operating_cash_flow",
                   "capital_expenditure", "free_cash_flow", "total_debt")
_INSTANTS = {"total_debt", "net_debt", "cash_and_equivalents"}
_LABELS = {
    "operating_margin": "Operating margin",
    "free_cash_flow": "Free cash flow (OCF less cash PP&E)",
    "net_debt": "Net debt (borrowings less cash equivalents)",
    "capex_to_revenue": "Cash PP&E / revenue",
    "capex_to_operating_cash_flow": "Cash PP&E / operating cash flow",
    "free_cash_flow_margin": "Free cash flow / revenue",
    "free_cash_flow_conversion": "Free cash flow / net income",
    "net_debt_to_operating_cash_flow": "Net debt / annual operating cash flow",
    "total_debt_to_operating_cash_flow": "Total debt / annual operating cash flow",
    "net_debt_to_operating_cash_flow_change": "Change in net debt / annual operating cash flow",
    "total_debt_to_operating_cash_flow_change": "Change in total debt / annual operating cash flow",
}

_LIMITATIONS = [
    "Calculated metrics use annual reported figures and may include later-filed restatements; this is not point-in-time data.",
    "Cash capex is total company cash purchases of PP&E; it is not an AI-specific or lease-inclusive investment measure.",
    "Free cash flow is OCF less cash PP&E purchases, an analyst-defined measure excluding finance-lease principal repayments.",
    "Net debt excludes leases and short-term investments; debt/OCF uses year-end debt and annual OCF, not EBITDA or average debt.",
    "No ROIC, incremental AI ROIC or valuation is calculated: attributable returns, invested capital and valuation inputs are absent.",
    "Positive-base growth excludes negative current values; absolute changes remain available where comparable. Missing values are never zero-filled.",
    "Matching concept sets are a minimum comparability check, not proof of unchanged economic scope; acquisitions and accounting changes require analyst review.",
    "Tensions are numerical screening observations, not causal conclusions or investment recommendations.",
]


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _period(period):
    return {"fiscal_year": period.fiscal_year, "period_start": period.start, "period_end": period.end}


def _date(value):
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _valid_period(period):
    start, end = _date(period.start), _date(period.end)
    return (isinstance(period.fiscal_year, int) and not isinstance(period.fiscal_year, bool)
            and start is not None and end is not None and 350 <= (end - start).days + 1 <= 380)


def _pair_reason(prior, current):
    if not _valid_period(prior) or not _valid_period(current):
        return "The comparison does not contain two verified annual durations."
    if current.fiscal_year != prior.fiscal_year + 1 or (_date(current.start) - _date(prior.end)).days != 1:
        return "Annual periods are not consecutive and contiguous; no gap, overlap or omitted fiscal year is bridged."
    return ""


def _unique_sources(records):
    sources = {}
    for record in records:
        for source in record["sources"]:
            sources[tuple(source.items())] = source
    return list(sources.values())


def _input(result, period, key):
    metric = period.metrics.get(key)
    expected = "USD/shares" if key == "diluted_eps" else "USD"
    reason = ""
    sources = [asdict(s) for s in metric.sources] if metric else []
    if metric is None or metric.value is None:
        reason = (metric.reason if metric else "Metric is absent from the annual extraction.") or "Metric is unavailable."
    elif not _finite(metric.value):
        reason = "Metric is not a finite number."
    elif metric.unit != expected:
        reason = f"Metric unit is {metric.unit}; {expected} is required."
    elif not sources:
        reason = "No reported source facts are attached to the metric."
    elif any(s["end"] != period.end or s["start"] != (None if key in _INSTANTS else period.start)
             or s["form"] not in {"10-K", "10-K/A"} or s["unit"] != expected
             or not _finite(s["value"]) for s in sources):
        reason = "Input source periods, annual filing forms or units disagree with the selected metric."
    elif key not in {"total_debt", "net_debt", "free_cash_flow"} and any(s["value"] != metric.value for s in sources):
        reason = "Reported metric value disagrees with its attached source facts."
    elif key in {"capital_expenditure", "total_debt", "cash_and_equivalents"} and metric.value < 0:
        reason = "A negative balance/outflow contradicts this metric's definition."
    # An invalid source number is not evidence and must not leak NaN/Infinity
    # into JSON exports. The rejected input remains in the untouched result.
    sources = [source for source in sources if _finite(source["value"])]
    return {
        "source_id": f"{period.fiscal_year}:{key}", "metric": key,
        "raw_dependencies": [f"{period.fiscal_year}:{key}"],
        "value": None if reason else float(metric.value), "unit": expected,
        "fiscal_year": period.fiscal_year,
        "period_start": None if key in _INSTANTS else period.start,
        "period_end": period.end, "sources": sources, "reason": reason,
    }


def _calculated(result, period, key, unit, inputs, operation, calculation, *, reason="", comparison=None):
    reasons = ([reason] if reason else []) + [row["reason"] for row in inputs if row["value"] is None and row["reason"]]
    reason = "; ".join(dict.fromkeys(reasons))
    value = None
    if not reason:
        try:
            value = operation(*[row["value"] for row in inputs])
        except (ZeroDivisionError, OverflowError):
            reason = "Calculation has an invalid denominator or non-finite result."
        if not _finite(value):
            value = None
            reason = reason or "Calculation produced an unavailable or non-finite result."
    previous = comparison or []
    dependencies = list(dict.fromkeys(ref for row in inputs for ref in row["raw_dependencies"]))
    dependency_periods = {}
    for row in inputs:
        for metadata in row.get("dependency_periods", [{"source_id": row["source_id"], **{k: row[k] for k in ("fiscal_year", "period_start", "period_end")}}]):
            dependency_periods[metadata["source_id"]] = metadata
    return {
        "source_id": f"{period.fiscal_year}:analytics.{key}", "kind": "financial",
        "metric": key, "label": _LABELS.get(key, key.replace("_", " ").capitalize()),
        "value": value, "unit": unit, "fiscal_year": period.fiscal_year,
        "period_start": None if key == "net_debt" else period.start, "period_end": period.end,
        "sources": _unique_sources(inputs), "dependencies": dependencies, "raw_dependencies": dependencies,
        "input_ids": [row["source_id"] for row in inputs],
        "dependency_periods": list(dependency_periods.values()),
        "comparison": previous[-1] if previous else None,
        "comparison_periods": previous + ([_period(period)] if previous else []),
        "calculation": calculation, "derived": True,
        "evidence_label": "derived_calculation", "reason": reason,
        "status": "unavailable" if value is None else "available",
        "ticker": result.ticker, "cik": str(result.cik).zfill(10), "mode": result.mode,
        "retrieved_at": result.retrieved_at,
    }


def _ratio(result, period, key, numerator, denominator, calculation):
    reason = ""
    if denominator["value"] is not None and denominator["value"] <= 0:
        reason = "A positive denominator is required; zero or negative denominators make this ratio economically ambiguous."
    return _calculated(result, period, key, "ratio", [numerator, denominator],
                       lambda a, b: a / b, calculation, reason=reason)


def _comparable(prior, current, previous_row, row):
    reason = _pair_reason(prior, current)
    if not reason and {s["concept"] for s in previous_row["sources"]} != {s["concept"] for s in row["sources"]}:
        reason = "Underlying XBRL concept sets changed; equivalence is not assumed without a comparability bridge."
    return reason


def build_analytics(result: ResearchResult, thresholds: dict | None = None) -> dict:
    """Return serialisable calculated rows, source-linked tensions and limitations.

    A missing row stays visible with ``value=None`` and an explicit reason.
    ``analytics_evidence`` exposes only finite available rows to the model.
    All thresholds are inclusive; growth values are decimal rates and ``*_pp``
    thresholds are percentage points. Overrides may change known nonnegative
    finite thresholds only. The caller decides which observations to prioritise.
    """
    if result.mode not in {"live", "offline"}:
        raise ValueError("Analytics must retain the explicit live or offline data mode.")
    active = dict(DEFAULT_THRESHOLDS)
    for key, value in (thresholds or {}).items():
        if key not in active or not _finite(value) or value < 0:
            raise ValueError("Analytics thresholds must be known, finite, nonnegative numerical values.")
        active[key] = float(value)
    periods = sorted(result.periods, key=lambda p: p.end)
    if any(not _valid_period(p) for p in periods):
        raise ValueError("Analytics requires verified annual durations and explicit integer fiscal labels.")
    if len({p.fiscal_year for p in periods}) != len(periods) or len({p.end for p in periods}) != len(periods):
        raise ValueError("Duplicate fiscal-year labels or annual period ends are ambiguous.")
    records, by_period = [], []
    for index, period in enumerate(periods):
        base = {key: _input(result, period, key) for key in
                ("revenue", "operating_income", "net_income", "operating_cash_flow", "capital_expenditure", "total_debt", "cash_and_equivalents")}
        calculated = {}
        def add(record):
            calculated[record["metric"]] = record
            records.append(record)
            return record
        fcf = add(_calculated(result, period, "free_cash_flow", "USD", [base["operating_cash_flow"], base["capital_expenditure"]],
                              lambda a, b: a - b, "operating_cash_flow - cash_PP&E_purchases"))
        debt = add(_calculated(result, period, "net_debt", "USD", [base["total_debt"], base["cash_and_equivalents"]],
                               lambda a, b: a - b, "total_debt - cash_and_equivalents"))
        base["free_cash_flow"], base["net_debt"] = fcf, debt
        for key, numerator, denominator in (
            ("operating_margin", "operating_income", "revenue"),
            ("capex_to_revenue", "capital_expenditure", "revenue"),
            ("capex_to_operating_cash_flow", "capital_expenditure", "operating_cash_flow"),
            ("free_cash_flow_margin", "free_cash_flow", "revenue"),
            ("free_cash_flow_conversion", "free_cash_flow", "net_income"),
            ("net_debt_to_operating_cash_flow", "net_debt", "operating_cash_flow"),
            ("total_debt_to_operating_cash_flow", "total_debt", "operating_cash_flow"),
        ):
            add(_ratio(result, period, key, base[numerator], base[denominator], f"{numerator} / {denominator}"))
        prior = periods[index - 1] if index else None
        previous = by_period[index - 1] if index else None
        for key in _GROWTH_METRICS:
            row = base[key]
            inputs = [previous["base"][key], row] if previous else [row]
            reason = _comparable(prior, period, inputs[0], row) if prior else "No comparable preceding annual period is available."
            if not reason and all(v["value"] is not None for v in inputs):
                if inputs[0]["value"] <= 0:
                    reason = "Percentage growth requires a positive prior-period base; zero or negative bases are not economically comparable."
                elif row["value"] < 0:
                    reason = "Current value is negative; a percentage growth rate would obscure a sign transition. Use the absolute change."
            add(_calculated(result, period, f"{key}_growth", "ratio", inputs, lambda a, b: (b - a) / a,
                            f"(current {key} - prior {key}) / prior {key}", reason=reason,
                            comparison=[_period(prior)] if prior else None))
            add(_calculated(result, period, f"{key}_change", "USD", inputs, lambda a, b: b - a,
                            f"current {key} - prior {key}",
                            reason=_comparable(prior, period, inputs[0], row) if prior else "No comparable preceding annual period is available.",
                            comparison=[_period(prior)] if prior else None))
        for key in ("operating_margin", "capex_to_revenue", "capex_to_operating_cash_flow", "free_cash_flow_margin", "free_cash_flow_conversion"):
            row = calculated[key]
            inputs = [previous["calculated"][key], row] if previous else [row]
            reason = _comparable(prior, period, inputs[0], row) if prior else "No comparable preceding annual period is available."
            add(_calculated(result, period, f"{key}_change_pp", "percentage_points", inputs,
                            lambda a, b: (b - a) * 100, f"(current {key} - prior {key}) * 100", reason=reason,
                            comparison=[_period(prior)] if prior else None))
        for key in ("net_debt_to_operating_cash_flow", "total_debt_to_operating_cash_flow", "net_debt"):
            row = calculated[key]
            inputs = [previous["calculated"][key], row] if previous else [row]
            reason = _comparable(prior, period, inputs[0], row) if prior else "No comparable preceding annual period is available."
            add(_calculated(result, period, f"{key}_change", "USD" if key == "net_debt" else "ratio", inputs,
                            lambda a, b: b - a, f"current {key} - prior {key}", reason=reason,
                            comparison=[_period(prior)] if prior else None))
        growth = calculated["revenue_growth"]
        inputs = [previous["calculated"]["revenue_growth"], growth] if previous else [growth]
        reason = "Acceleration requires three consecutive comparable annual periods." if index < 2 else _pair_reason(prior, period)
        add(_calculated(result, period, "revenue_growth_acceleration_pp", "percentage_points", inputs,
                        lambda a, b: (b - a) * 100, "(current annual revenue growth - prior annual revenue growth) * 100", reason=reason,
                        comparison=[_period(p) for p in periods[max(0, index - 2):index]]))
        by_period.append({"base": base, "calculated": calculated})
    tensions = _tensions(periods, by_period, active)
    limitations = list(_LIMITATIONS)
    for period in periods:
        if (_date(period.end) - _date(period.start)).days + 1 not in {365, 366}:
            limitations.append(f"FY{period.fiscal_year} contains {(_date(period.end) - _date(period.start)).days + 1} days; annual rates are not day-normalised for 52/53-week calendars.")
    if not periods:
        limitations.append("No annual periods are available; no metrics or tensions were inferred.")
    return {"metrics": records, "tensions": tensions, "limitations": limitations, "thresholds": active,
            "ticker": result.ticker, "mode": result.mode}


def _tensions(periods, rows, thresholds):
    output = []
    for i in range(1, len(periods)):
        current, prior = periods[i], periods[i - 1]
        c, p = rows[i]["calculated"], rows[i - 1]["calculated"]
        base, previous_base = rows[i]["base"], rows[i - 1]["base"]
        def value(key):
            return c[key]["value"]
        def available(*keys):
            return all(value(key) is not None for key in keys)
        def observation(code, title, keys, metrics, explanation):
            comparisons = []
            for metric in metrics:
                old = previous_base.get(metric, p.get(metric))
                new = base.get(metric, c.get(metric))
                comparisons.append({"metric": metric, "prior": {k: old[k] for k in ("source_id", "value", "unit", "fiscal_year", "period_start", "period_end")},
                                    "current": {k: new[k] for k in ("source_id", "value", "unit", "fiscal_year", "period_start", "period_end")}})
                comparisons[-1]["prior"]["raw_source_ids"] = old["raw_dependencies"]
                comparisons[-1]["current"]["raw_source_ids"] = new["raw_dependencies"]
            refs = list(dict.fromkeys([ref for key in keys for ref in c[key]["raw_dependencies"]] +
                       [ref for comparison in comparisons for side in ("prior", "current") for ref in comparison[side]["raw_source_ids"]]))
            changes = []
            for key in keys:
                change = {k: c[key][k] for k in ("source_id", "metric", "value", "unit", "dependencies")}
                change["direction"] = "increase" if change["value"] > 0 else "decrease" if change["value"] < 0 else "unchanged"
                change["formula"] = c[key]["calculation"]
                changes.append(change)
            output.append({"id": f"{current.fiscal_year}:{code}", "type": code, "title": title,
                           "current_period": _period(current), "prior_period": _period(prior),
                           "metrics": metrics, "comparisons": comparisons,
                           "changes": changes,
                           "source_ids": refs, "related_source_ids": refs, "explanation": explanation,
                           "classification": "deterministic_observation", "requires_analyst_interpretation": True})
            output[-1]["comparability_warnings"] = [
                "Matching annual periods and concept sets do not prove unchanged economic scope; acquisitions and restatements require review.",
                "Annual rates are not normalised for differing fiscal-year day counts."]
        if available("revenue_growth", "operating_margin_change_pp") and value("revenue_growth") >= thresholds["material_growth"] and value("operating_margin_change_pp") <= -thresholds["margin_change_pp"]:
            observation("growth_margin_tension", "Revenue growth with operating-margin contraction",
                        ["revenue_growth", "operating_margin_change_pp"], ["revenue", "operating_margin"],
                        "Revenue rose while operating margin declined materially; investigate mix, pricing and cost changes without assuming a cause.")
        if available("operating_cash_flow_growth", "capital_expenditure_growth") and value("operating_cash_flow_growth") >= thresholds["material_growth"] and (value("capital_expenditure_growth") - value("operating_cash_flow_growth")) * 100 >= thresholds["capex_growth_gap_pp"]:
            observation("cash_investment_tension", "Cash PP&E growth exceeds operating-cash-flow growth",
                        ["operating_cash_flow_growth", "capital_expenditure_growth"], ["operating_cash_flow", "capital_expenditure", "free_cash_flow"],
                        "Cash PP&E purchases grew faster than operating cash flow; investigate investment timing, cash-return conversion and financing needs. Company-wide cash capex is not an AI spending estimate.")
        if available("revenue_growth", "operating_income_growth") and min(value("revenue_growth"), value("operating_income_growth")) >= thresholds["material_growth"]:
            observation("revenue_profit_growth", "Revenue and operating income increased materially",
                        ["revenue_growth", "operating_income_growth", "operating_margin_change_pp"],
                        ["revenue", "operating_income", "operating_margin"],
                        "Reported revenue and operating income grew; assess the margin comparison alongside cash investment before inferring durable profitability.")
        prior_fcf = previous_base["free_cash_flow"]["value"]
        fcf_fell = (value("free_cash_flow_change") is not None and prior_fcf is not None and prior_fcf != 0
                    and value("free_cash_flow_change") < 0
                    and -value("free_cash_flow_change") / abs(prior_fcf) >= thresholds["material_growth"])
        if available("operating_cash_flow_growth") and value("operating_cash_flow_growth") >= thresholds["material_growth"] and fcf_fell:
            observation("cash_flow_divergence", "Operating cash flow increased while free cash flow declined",
                        ["operating_cash_flow_growth", "free_cash_flow_change"],
                        ["operating_cash_flow", "capital_expenditure", "free_cash_flow"],
                        "Operating cash flow increased but free cash flow declined as cash PP&E purchases absorbed more cash. This is a corporate cash-flow relationship, not proof of AI spending or poor future returns.")
        if available("net_income_growth") and value("net_income_growth") >= thresholds["material_growth"] and fcf_fell:
            observation("earnings_cash_tension", "Rising net income with declining free cash flow",
                        ["net_income_growth", "free_cash_flow_change"], ["net_income", "free_cash_flow"],
                        "Net income rose while free cash flow declined materially; investigate investment outlays and cash conversion before drawing conclusions about earnings quality.")
        if available("net_income_growth", "free_cash_flow_conversion_change_pp") and value("net_income_growth") >= thresholds["material_growth"] and value("free_cash_flow_conversion_change_pp") <= -thresholds["intensity_change_pp"]:
            observation("earnings_conversion_tension", "Net income improved while free-cash-flow conversion deteriorated",
                        ["net_income_growth", "free_cash_flow_conversion_change_pp"],
                        ["net_income", "free_cash_flow_conversion"],
                        "Reported net income increased while free cash flow relative to net income decreased materially; investigate non-operating earnings effects and cash investment. This alone is not proof of poor earnings quality.")
        if available("total_debt_growth", "operating_cash_flow_growth") and value("total_debt_growth") >= thresholds["debt_growth"] and value("operating_cash_flow_growth") <= thresholds["cash_flow_growth_ceiling"]:
            observation("debt_cash_tension", "Debt growth without comparable cash-generation growth",
                        ["total_debt_growth", "operating_cash_flow_growth"], ["total_debt", "operating_cash_flow"],
                        "Borrowings rose materially while operating cash flow grew slowly or declined; investigate uses of debt, maturities and liquidity. This is not a solvency conclusion.")
        changes = [key for key in ("capex_to_revenue_change_pp", "capex_to_operating_cash_flow_change_pp")
                   if value(key) is not None and value(key) >= thresholds["intensity_change_pp"]]
        if changes:
            observation("investment_intensity", "Increasing cash-investment intensity", changes,
                        [key.removesuffix("_change_pp") for key in changes],
                        "Cash PP&E consumes a materially greater share of revenue or operating cash flow; investigate capacity utilisation, monetisation and future cash requirements. A rising ratio does not establish investment returns.")
    return output


def analytics_evidence(result: ResearchResult) -> dict[str, dict]:
    """Financial evidence additions only; unavailable rows never become citations."""
    return {row["source_id"]: row for row in build_analytics(result)["metrics"] if row["value"] is not None}
