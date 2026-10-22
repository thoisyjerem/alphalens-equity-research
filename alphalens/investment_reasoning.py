"""Evidence-bound research questions, not generated causes or investment advice.

Existing analytics owns all figures and materiality thresholds. These small,
issuer-neutral templates organise its observations into competing, testable
economic mechanisms. No mechanism becomes a disclosed fact by matching a rule.
"""
from __future__ import annotations

from copy import deepcopy
import math

from .research_integrity import validate_observation_integrity


# Text is a reviewer-authored research framework. Each pair identifies evidence
# which would distinguish the hypotheses; no forecast or KPI is manufactured.
_FRAMEWORKS = {
    "cash_flow_divergence": (
        "Cash retained after cash PP&E fell despite higher operating cash generation. Persistent investment needs could reduce cash available for distributions or other uses unless operating cash generation catches up.",
        "Investment could build productive assets whose cash returns follow the cash outlay.",
        "Investment could remain persistently cash intensive, or current OCF could include cash-tax or collection timing effects that do not recur.",
        "Disclosed assets placed in service generate subsequent incremental cash after cash-tax/working-capital normalisation, with a reconciled PP&E and lease investment bridge.",
        "Repeated outlays lack corresponding incremental cash generation, or cash-tax/collection timing benefits reverse. Neither outcome is established by this packet.",
        "Can cash generation from deployed assets compensate for continuing reinvestment, after separating cash-tax and customer/supplier timing effects from operating progress?",
        "Cash-tax and receivables/payables bridges; expansion versus replacement spending; leases and commitments; asset deployment, utilisation and monetisation. Corporate cash PP&E is not AI-only spending or an incremental-return measure.",
    ),
    "revenue_profit_growth": (
        "Revenue and operating profit growth can expand the resources available for reinvestment. Their value depends on persistence, cash conversion and the investment needed to sustain growth.",
        "Recurring demand, pricing or favourable mix could support operating earnings and cash generation.",
        "Currency translation, segment mix, cost timing or accounting scope changes could explain part of the reported improvement without equivalent underlying demand growth.",
        "A disclosed constant-currency/segment bridge shows recurring operating progress with cash conversion after required reinvestment.",
        "A disclosed bridge is dominated by currency, temporary costs or scope changes, or reinvestment absorbs the operating cash gains. Aggregate growth does not establish these causes.",
        "Which disclosed demand, pricing, currency, segment-mix and cost changes explain operating growth, and does that growth convert into cash after required reinvestment?",
        "A comparable segment/constant-currency bridge, recurring cost analysis and cash conversion. Net-income investment gains do not explain operating-income growth.",
    ),
    "growth_margin_tension": (
        "Growing revenue with a lower operating margin raises the question of how much incremental sales contribute to profit and cash available to shareholders.",
        "Upfront spending to support future activity could precede operating returns.",
        "Pricing pressure, less profitable mix or persistent cost growth could reduce the economics of incremental activity.",
        "Disclosed temporary deployment costs are followed by better contribution margins and cash conversion.",
        "Like-for-like margin pressure persists after deployment, particularly if cash conversion also weakens.",
        "Does a disclosed segment, pricing and cost bridge distinguish temporary growth investment from persistent deterioration in incremental profitability?",
        "Segment revenues and operating costs; pricing/mix evidence; temporary versus recurring costs; investment deployment and cash conversion.",
    ),
    "earnings_conversion_tension": (
        "Higher net income with lower FCF relative to net income makes the cash available after reinvestment a separate question from reported earnings growth.",
        "Investment or temporary cash-tax/collection timing could delay conversion of earnings into retained cash.",
        "Non-operating earnings effects or persistent reinvestment requirements could make reported net-income growth a weak proxy for distributable cash growth.",
        "A net-income-to-OCF bridge and subsequent PP&E/lease reconciliation show conversion recovering after identifiable temporary effects.",
        "Conversion remains weak after separating non-operating items and timing. Low conversion alone does not establish poor earnings quality.",
        "How much of weaker earnings-to-FCF conversion comes from non-operating earnings, cash-tax/working-capital timing and reinvestment respectively?",
        "A net-income/OCF reconciliation and cash investment scope. Do not treat investment gains in net income as operating-profit drivers.",
    ),
    "investment_intensity": (
        "A larger share of revenue or OCF absorbed by cash PP&E increases the importance of future cash returns and the investment needed to sustain growth.",
        "A front-loaded asset deployment programme could earn cash returns after spending peaks.",
        "Recurring replacement, technology change or capacity needs could keep investment intensity elevated.",
        "Disclosure separates front-loaded growth assets from replacement and lease spending, and shows subsequent cash contribution.",
        "Replacement requirements remain elevated or deployed capacity lacks cash monetisation. Aggregate spending does not establish either.",
        "What investment must recur to sustain current cash generation, and what incremental cash contribution would justify the additional assets?",
        "Replacement versus expansion cash PP&E, leases, asset lives, deployment, utilisation and incremental cash contribution; no attributable ROIC is established.",
    ),
    "debt_cash_tension": (
        "Borrowings growing faster than operating cash generation can increase the importance of liquidity, maturities and financing uses, without establishing a solvency problem.",
        "Borrowing could bridge temporary funding needs or finance assets with later cash returns.",
        "Borrowing could finance distributions or recurring cash needs without comparable future operating cash generation.",
        "Disclosed uses of proceeds and subsequent cash generation cover maturity obligations after reinvestment.",
        "Refinancing dependence or funding gaps persist. Debt growth by itself does not establish this outcome.",
        "What uses of debt and maturity obligations must operating cash generation cover after reinvestment and distributions?",
        "Uses of proceeds, maturities, interest costs, liquidity and lease obligations; year-end debt/annual OCF is not average leverage or EBITDA coverage.",
    ),
}
_FRAMEWORKS["cash_investment_tension"] = _FRAMEWORKS["investment_intensity"]
_FRAMEWORKS["earnings_cash_tension"] = _FRAMEWORKS["earnings_conversion_tension"]
_FAMILIES = {"cash_flow_divergence": "cash_investment", "cash_investment_tension": "cash_investment",
             "investment_intensity": "cash_investment", "growth_margin_tension": "operating_performance",
             "revenue_profit_growth": "operating_performance", "earnings_cash_tension": "earnings_conversion",
             "earnings_conversion_tension": "earnings_conversion"}
_PRIORITY = ("cash_flow_divergence", "growth_margin_tension", "revenue_profit_growth",
             "earnings_conversion_tension", "investment_intensity", "debt_cash_tension",
             "cash_investment_tension", "earnings_cash_tension")

_IMPLICATIONS = {
    "cash_flow_divergence": "Stronger OCF has not increased cash retained after PP&E. Distinguish a temporary deployment phase from recurring reinvestment before extrapolating operating growth into cash available for distributions; neither future returns nor a valuation change is established.",
    "revenue_profit_growth": "Reported operating growth may expand reinvestment capacity, but its persistence and required capital determine how much can become shareholder cash. Separate segment, currency and cost effects before treating aggregate growth as evidence of durable business quality.",
    "growth_margin_tension": "Additional revenue is accompanied by a lower operating-profit share. A business-quality assessment needs to distinguish temporary growth costs from recurring pricing, mix or cost pressure before assuming sales growth will restore profitability.",
    "earnings_conversion_tension": "Net-income growth is not translating proportionately into cash retained after PP&E. Separate non-operating earnings, operating cash timing and cash investment before using earnings growth as a proxy for distributable cash.",
    "investment_intensity": "More revenue or operating cash is absorbed by cash PP&E. A valuation process would need a defensible recurring reinvestment requirement and subsequent cash contribution; these ratios alone establish neither an adequate return nor excessive spending.",
    "debt_cash_tension": "Higher borrowings without comparable OCF growth make maturity coverage and uses of financing more consequential for financial flexibility after reinvestment. The comparison is a diligence trigger, not a solvency verdict.",
}
_IMPLICATIONS["cash_investment_tension"] = _IMPLICATIONS["investment_intensity"]
_IMPLICATIONS["earnings_cash_tension"] = _IMPLICATIONS["earnings_conversion_tension"]


def build_investment_reasoning(evidence, analysis, observations=None, *, limit=3):
    """Select at most three distinct numerical developments; abstain if absent.

    Financial support establishes the observation only. The paired mechanisms
    remain unverified hypotheses until a reviewer examines further evidence.
    """
    if type(limit) is not int or not 1 <= limit <= 3:
        raise ValueError("Choose between one and three material developments.")
    observations = ({row["id"]: row for row in analysis["tensions"]}
                    if observations is None else observations)
    validate_observation_integrity(evidence, analysis, observations)
    latest = max((row["fiscal_year"] for row in analysis["metrics"]), default=None)
    eligible = [row for row in observations.values() if row["current_period"]["fiscal_year"] == latest
                and row["type"] in _FRAMEWORKS]
    eligible.sort(key=lambda row: _PRIORITY.index(row["type"]))
    selected, families = [], set()
    for row in eligible:
        family = _FAMILIES.get(row["type"], row["type"])
        if family in families:
            continue
        families.add(family)
        significance, constructive, cautionary, strengthen, weaken, question, gap = _FRAMEWORKS[row["type"]]
        selected.append({"observation_id": row["id"], "observation": row["title"],
            "category": "Deterministic calculation", "origin": "Python/reviewer research framework, not Gemini output",
            "prior_period": deepcopy(row["prior_period"]), "current_period": deepcopy(row["current_period"]),
            "comparisons": deepcopy(row["comparisons"]), "source_ids": list(row["source_ids"]),
            "economic_significance": significance,
            "competing_explanations": [
                {"case": "Constructive hypothesis", "mechanism": constructive, "category": "Unverified hypothesis",
                 "observation_basis_ids": [row["id"]], "supporting_financial_ids": list(row["source_ids"]),
                 "support_limit": "The financial pattern supports asking this question, not the proposed cause.",
                 "strengthening_condition": strengthen, "weakening_condition": weaken},
                {"case": "Cautionary hypothesis", "mechanism": cautionary, "category": "Unverified hypothesis",
                 "observation_basis_ids": [row["id"]], "supporting_financial_ids": list(row["source_ids"]),
                 "support_limit": "The financial pattern does not prove deterioration or the proposed cause.",
                 "strengthening_condition": weaken, "weakening_condition": strengthen}],
            "investment_implication": _IMPLICATIONS[row["type"]],
            "unresolved_question": question, "missing_evidence": gap,
            "warnings": list(row.get("comparability_warnings", [])), "requires_analyst_review": True})
        if len(selected) == limit:
            break
    return {"origin": "Evidence-bound Python/reviewer framework; no new model generation",
            "findings": selected, "requested_maximum": limit, "available_distinct_developments": len(selected),
            "limitation": "Causes, future cash returns and valuation are not mechanically proven. Fewer findings are shown when comparable evidence is insufficient."}


def segment_context_flags(readout):
    """Flag opposite signs in an already source-reconciled segment readout.

    Call only after build_recorded_readout; this helper verifies neither an
    arbitrary segment table nor a causal explanation of the divergence.
    """
    margins = readout.get("margins", [])
    consolidated = next((row for row in margins if row["label"] == "Consolidated"), None)
    if consolidated is None:
        return []
    flags = []
    for row in margins:
        if row is consolidated:
            continue
        overall, segment = float(consolidated["change_pp"]), float(row["change_pp"])
        if not all(math.isfinite(value) for value in (overall, segment)):
            raise ValueError("Segment margin changes must be finite.")
        if overall * segment < 0:
            flags.append({"code": "segment_consolidated_divergence", "category": "Deterministic calculation",
                "message": f"{row['label']} operating margin moved in the opposite direction to consolidated operating margin. Aggregate improvement does not establish segment-wide improvement.",
                "source_ids": [readout["segment_source_id"]], "requires_analyst_review": True})
    return flags
