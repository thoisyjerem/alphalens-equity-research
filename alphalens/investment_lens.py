"""Company-linked macro scenarios; observed facts stay separate from hypotheses.

No retrieval or model calls. A macro proxy does not estimate issuer sensitivity,
establish historical causality, or supply a valuation/discount-rate assumption.
"""
from __future__ import annotations

from .analytics import build_analytics
from .evidence import build_evidence_book


FED_TRANSMISSION = "https://www.federalreserve.gov/monetarypolicy/monetary-policy-what-are-its-goals-how-does-it-work.htm"

_DEMAND = {
    "MSFT": {
        "mechanism": "If enterprise budgets tighten while infrastructure commitments remain fixed, slower cloud consumption or contract conversion could delay cash recovery from new capacity.",
        "alternative": "Migration to cloud services or spending that reduces customers' other costs could sustain demand despite weaker industrial activity. A services business need not track industrial output.",
        "monitor": "Compare disclosed cloud consumption, constant-currency growth, contract-to-revenue conversion and cash collections with cash PP&E, lease commitments and subsequent depreciation. Check what is actually disclosed before inferring utilisation.",
        "disconfirmer": "Sustained demand conversion and improving cash generation relative to investment would weaken the delayed-payback concern; backlog growth on its own would not settle it.",
        "missing": "Capacity utilisation, incremental cash margins, the timing of lease payments and AI-specific attributable returns are not established by these annual totals.",
    },
    "AMZN": {
        "mechanism": "If customer budgets weaken, retail demand and cloud consumption could slow while logistics and infrastructure cash commitments persist, delaying cash recovery.",
        "alternative": "Share gains, changes in product mix, cloud migration or operating efficiency could offset weaker aggregate activity.",
        "monitor": "Check disclosed retail demand, cloud growth, segment operating profit, working capital, cash PP&E and lease commitments together; separate retail from cloud economics.",
        "disconfirmer": "Improving segment cash generation and investment utilisation despite softer macro activity would weaken the demand-pressure scenario.",
        "missing": "Segment cash-flow attribution, utilisation and forward investment commitments are needed to estimate sensitivity.",
    },
    "AAPL": {
        "mechanism": "If household budgets tighten, device replacement could be deferred, affecting product mix and cash generation; industrial output is only a broad cycle proxy.",
        "alternative": "Replacement needs, product mix, services or regional differences could offset weaker aggregate activity.",
        "monitor": "Inspect disclosed product and regional revenue, channel inventory, margins, cash collections and currency-adjusted growth where available.",
        "disconfirmer": "Resilient replacement demand and cash conversion without inventory build-up would weaken the budget-pressure concern.",
        "missing": "Replacement cycles, regional spending exposure and product-level demand sensitivity are not established by company-wide annual totals.",
    },
}


def build_investment_lens(result, macro_snapshot=None):
    """Build an auditable research framework, never an automatic macro forecast."""
    analytics = build_analytics(result)
    latest = max((p.fiscal_year for p in result.periods), default=None)
    observations = {row["type"]: row for row in analytics["tensions"]
                    if row["current_period"]["fiscal_year"] == latest}
    cash = observations.get("cash_flow_divergence") or observations.get("cash_investment_tension")
    growth = observations.get("revenue_profit_growth") or observations.get("growth_margin_tension")
    intensity = observations.get("investment_intensity")
    demand = _DEMAND.get(result.ticker, {
        "mechanism": "Weaker demand could pressure revenue and cash generation while committed investment continues.",
        "alternative": "Issuer-specific demand, mix or efficiency may offset the broad cycle.",
        "monitor": "Inspect disclosed demand, cash conversion and investment commitments together.",
        "disconfirmer": "Resilient cash generation and investment utilisation would weaken the concern.",
        "missing": "Company-specific exposure and cash-flow sensitivity require further diligence.",
    })
    source_rows = {row["series_id"]: row for row in (macro_snapshot or {}).get("series", [])}

    def channel(key, title, series_id, anchor, mechanism, alternative, monitor, disconfirmer, missing):
        macro = source_rows.get(series_id)
        usable = macro is not None and macro.get("status") == "available"
        context = None
        if macro:
            context = {key: macro.get(key) for key in ("label", "observation_date", "value", "unit",
                "comparison_date", "comparison_value", "change", "change_unit", "source_url", "status")}
        change = macro.get("change") if usable else None
        read_through = "No supported current annual macro comparison is available. The mechanism below remains a conditional research question."
        if change is not None:
            if key == "demand":
                read_through = ("Industrial output is above its year-earlier level; this does not establish a year-on-year industrial contraction. A slowdown in this issuer's customers remains a separate question."
                    if change > 0 else "Industrial output is below its year-earlier level, which makes cyclical weakness worth investigating. It does not measure this issuer's customer budgets or establish a company slowdown."
                    if change < 0 else "Industrial output is unchanged year on year; it does not establish the direction of this issuer's customer demand.")
            elif key == "rates":
                read_through = ("The long Treasury yield is higher than its comparison observation. Revisit the opportunity cost of delayed cash returns; no company-specific discount-rate change is estimated."
                    if change > 0 else "The long Treasury yield is lower than its comparison observation. This does not guarantee lower company funding costs, better project returns or stronger customer demand."
                    if change < 0 else "The long Treasury yield is unchanged versus the comparison observation; company funding terms and required project returns still need separate analysis.")
            elif key == "fx":
                read_through = ("The broad dollar index is higher than its comparison observation. Check a disclosed constant-currency bridge before attributing reported growth changes to demand or competition."
                    if change > 0 else "The broad dollar index is lower than its comparison observation. A possible translation benefit must be checked against the issuer's actual currencies, costs and hedges."
                    if change < 0 else "The broad dollar index is unchanged versus the comparison observation; this does not rule out moves in the issuer's relevant currencies.")
        return {"id": key, "title": title, "classification": "conditional_research_scenario",
            "macro_series_id": series_id,
            "macro_source_id": macro.get("source_id") if usable else None,
            "macro_status": macro.get("status", "unavailable") if macro else "not_loaded",
            "macro_context": context,
            "current_read_through": read_through,
            "company_observation_id": anchor["id"] if anchor else None,
            "company_source_ids": anchor["source_ids"] if anchor else [],
            "observed_company_change": anchor["title"] if anchor else "No comparable material annual observation is available; exposure is unquantified.",
            "mechanism": mechanism, "alternative_explanation": alternative,
            "what_to_monitor": monitor, "what_would_weaken_concern": disconfirmer,
            "missing_evidence": missing, "mechanism_source_url": FED_TRANSMISSION,
            "inference_status": "Analyst research framework; not model-generated or mechanically proven"}

    channels = [
        channel("demand", "Demand resilience versus capacity payback", "INDPRO", cash or growth,
            **demand),
        channel("rates", "Required returns versus infrastructure payback", "DGS10", intensity or cash,
            "If long-term yields rise, the opportunity cost of long-lived investment and the discount rate investors require could rise. Slower cash payback could then become more consequential.",
            "Higher yields may accompany stronger demand; cash balances may earn more interest and fixed-rate debt may delay refinancing effects. Yield changes do not map one-for-one to company funding costs.",
            "Inspect debt maturities, cash income, investment commitments and incremental cash generation. For infrastructure, investigate energy and equipment costs, depreciation and utilisation; this panel contains no measured cost series.",
            "Improving investment cash payback and strong internal funding would weaken a funding-pressure concern even if Treasury yields remain elevated.",
            "Project cash flows, cost of equity, credit spreads, debt repricing and asset lives are needed for a defensible hurdle rate; the Treasury yield is not WACC."),
        channel("fx", "Reported growth versus underlying demand", "DTWEXBGS", growth,
            "If the dollar strengthens against relevant operating currencies, foreign-currency revenue may translate into fewer dollars. Reported growth could then understate local-currency demand.",
            "Foreign-currency costs, hedges, pricing and geographic mix may offset translation. A broad dollar index is not the company's revenue-weighted currency basket.",
            "Reconcile reported and disclosed constant-currency growth by segment or geography, alongside hedging disclosures and local-currency costs.",
            "Stable constant-currency demand with disclosed offsetting costs or hedges would weaken the inference that currency translation signals competitive deterioration.",
            "Currency-level revenue, costs, hedges and disclosure-based bridges are required before quantifying a company-specific earnings or cash-flow effect."),
    ]
    bridge = None
    if cash and cash["type"] == "cash_flow_divergence":
        values = {row["metric"]: row for row in cash["comparisons"]}
        ocf, capex = values["operating_cash_flow"], values["capital_expenditure"]
        ocf_delta = ocf["current"]["value"] - ocf["prior"]["value"]
        capex_delta = capex["current"]["value"] - capex["prior"]["value"]
        bridge = {"observation_id": cash["id"], "source_ids": cash["source_ids"],
            "prior_period": cash["prior_period"], "current_period": cash["current_period"],
            "ocf_change": ocf_delta, "cash_ppe_change": capex_delta,
            "fcf_change": ocf_delta - capex_delta,
            "cash_recovery_gap": capex_delta - ocf_delta, "unit": "USD",
            "formula": "change in FCF = change in OCF - change in cash PP&E",
            "interpretation": "At unchanged current cash PP&E, this is the extra annual OCF needed to restore the prior annual FCF level. It is an accounting bridge, not a forecast or an investment-return estimate.",
            "diligence": "Separate expansion from replacement spending, check leases and commitments, and examine utilisation, cash monetisation and asset lives. More investment can create value; these totals cannot establish whether it does."}
    book = build_evidence_book(result)
    refs = set(ref for row in channels for ref in row["company_source_ids"])
    if bridge:
        refs.update(bridge["source_ids"])
    return {"company": result.ticker, "financial_data_mode": result.mode,
        "latest_fiscal_year": latest, "cash_bridge": bridge, "channels": channels,
        "company_source_registry": {key: book[key] for key in sorted(refs)},
        "limitations": [
            "Macro observations have their own dates and frequencies; they are not company fiscal-year financial facts or explanations of historical results.",
            "Industrial production covers US manufacturing, mining and utilities; it is not a measure of global enterprise IT budgets, cloud demand or consumer device demand.",
            "No company exposure coefficient, price target, macro forecast, AI-specific capex or ROIC is estimated.",
            "The current data vintage may contain revisions and cannot be used as a historical point-in-time signal.",
            "No price or consensus evidence is available here, so the panel cannot determine what is already priced in.",
        ]}


def build_investor_readout(result, macro_snapshot=None, *, lens=None):
    """A compact research synthesis; figures remain Python-owned observations.

    Scenarios are prospective questions, never causal explanations or company
    disclosures. Comparison availability is inherited from the analytics engine.
    """
    analytics = build_analytics(result)
    lens = build_investment_lens(result, macro_snapshot) if lens is None else lens
    periods = sorted(result.periods, key=lambda item: item.end)
    current = periods[-1] if periods else None
    prior = periods[-2] if len(periods) > 1 else None
    annual = lambda period: ({"fiscal_year": period.fiscal_year, "period_start": period.start,
        "period_end": period.end} if period else None)
    latest = current.fiscal_year if current else None
    rows = {row["metric"]: row for row in analytics["metrics"] if row["fiscal_year"] == latest}
    book = build_evidence_book(result)
    book.update({row["source_id"]: row for row in analytics["metrics"] if row["value"] is not None})
    labels = {"revenue_growth": "Revenue growth", "operating_income_growth": "Operating income growth",
        "operating_margin_change_pp": "Operating margin change", "operating_cash_flow_growth": "Operating cash flow growth",
        "capital_expenditure_growth": "Cash PP&E growth", "free_cash_flow_growth": "Free cash flow growth"}
    cards, refs = [], set()
    for metric, label in labels.items():
        record = rows.get(metric)
        valid = record is not None and record["value"] is not None
        ids = [record["source_id"], *record["dependencies"]] if valid else []
        refs.update(ids)
        cards.append({"metric": metric, "label": label, "value": record["value"] if valid else None,
            "unit": record["unit"] if record else "percentage_points" if metric.endswith("_pp") else "ratio",
            "reason": record["reason"] if record else "No annual comparison is available.", "source_ids": ids})
    comparable = rows.get("capex_to_operating_cash_flow_change_pp")
    intensity = None
    if comparable and comparable["value"] is not None and prior:
        ids = [f"{period.fiscal_year}:analytics.capex_to_operating_cash_flow" for period in (prior, current)]
        if all(key in book for key in ids):
            dependencies = list(dict.fromkeys(ref for key in ids for ref in book[key]["dependencies"]))
            refs.update(ids + dependencies + [comparable["source_id"]])
            intensity = {"prior": book[ids[0]]["value"], "current": book[ids[1]]["value"], "unit": "ratio",
                "change": comparable["value"], "change_unit": "percentage_points",
                "formula": "cash PP&E purchases / operating cash flow", "source_ids": ids + dependencies,
                "prior_period": annual(prior), "current_period": annual(current)}
    growth = any(row["type"] == "revenue_profit_growth" and row["current_period"]["fiscal_year"] == latest
        for row in analytics["tensions"])
    cash = lens["cash_bridge"]
    if cash:
        refs.update(cash["source_ids"])
    headline = ("Stronger operating performance; cash recovery must catch up with reinvestment" if cash and growth else
        "Cash generation rose, but reinvestment absorbed the increase" if cash else
        "Stronger operating performance; test how growth converts into cash" if growth else
        "Separate observed financial change from the investment hypothesis")
    summary = ("Operating cash flow increased, but cash PP&E grew by more, reducing annual free cash flow. The distinction is between observed spending and its uncertain future cash returns."
        if cash else "Use the comparable financial observations below to identify what changed; the available evidence does not establish the cash-flow divergence pattern.")
    margin = rows.get("operating_margin_change_pp", {})
    constructive = ("Hypothesis: revenue and operating income growth could support future cash generation, provided reinvestment converts into sustained monetisation."
        if growth else "Hypothesis: resilient demand and effective use of investment could support future cash generation; the available annual data do not establish that outcome.")
    if growth and margin.get("value") is not None and margin["value"] > 0:
        constructive += " The observed operating margin also improved; this does not establish the cause or future returns."
    macro_dates = [row.get("observation_date") for row in (macro_snapshot or {}).get("series", []) if row.get("observation_date")]
    timing = ("Some macro observations postdate the company's latest fiscal year-end. They are forward research context, not explanations of that year's reported results."
        if current and any(day > current.end for day in macro_dates) else
        "Macro observation dates and company fiscal periods differ; alignment alone would not establish historical causality.")
    return {"company": result.ticker, "financial_data_mode": result.mode, "classification": "conditional_research_framework",
        "headline": headline, "summary": summary, "research_question": "Can demand and cash generation justify the pace of reinvestment?",
        "annual_comparison": {"prior": annual(prior), "current": annual(current)}, "financial_cards": cards,
        "capital_intensity": intensity, "capital_intensity_reason": "" if intensity else
            comparable["reason"] if comparable else "No comparable cash PP&E / operating cash flow series is available.",
        "cash_bridge": cash, "constructive_case": constructive,
        "cautionary_case": "Hypothesis: investment commitments and depreciation could keep rising before utilisation and monetisation deliver comparable cash generation. These totals cannot establish that this is happening or quantify investment returns.",
        "more_constructive_if": ["Operating cash generation catches up with cash PP&E while disclosed demand and monetisation remain resilient.",
            "Lease-inclusive commitments and utilisation evidence support better cash conversion; lower cash purchases alone would not establish lower total investment."],
        "more_cautious_if": ["Investment commitments and depreciation keep growing without comparable disclosed cash generation or demand conversion.",
            "The apparent improvement in operating cash flow depends on temporary working-capital releases rather than recurring cash generation; investigate rather than assume this."],
        "macro_context_limits": [timing, "No price or consensus evidence is supplied, so this framework cannot determine what is already priced in.",
            "Company-wide cash PP&E does not isolate AI investment. No issuer exposure coefficient, discount rate, price target or return estimate is calculated."],
        "source_registry": {key: book[key] for key in sorted(refs)}}
