"""Read-only deterministic annual analysis, usable without any AI provider."""
import json

import pandas as pd
import streamlit as st

from .analytics import build_analytics


def show_investment_reasoning(reasoning):
    """Render auditable questions separately from model or company statements."""
    with st.expander("Investment reasoning — hypotheses and evidence", expanded=False):
        st.caption("PYTHON / REVIEWER FRAMEWORK — observations are calculated; economic mechanisms remain hypotheses. This is not new Gemini output.")
        if not reasoning["findings"]:
            st.info("No comparable material observation is available for this framework. No explanation was invented.")
        for finding in reasoning["findings"]:
            st.markdown("**" + finding["observation"] + "**")
            st.caption(f"Deterministic calculation · {finding['observation_id']} · FY{finding['prior_period']['fiscal_year']} to FY{finding['current_period']['fiscal_year']}")
            st.text("Economic significance: " + finding["economic_significance"])
            st.text("Investment implication: " + finding["investment_implication"])
            for case in finding["competing_explanations"]:
                st.text(case["case"] + " — " + case["mechanism"])
                st.caption("Unverified hypothesis. " + case["support_limit"])
                st.text("Evidence favouring this mechanism: " + case["strengthening_condition"])
                st.text("Evidence favouring the competing mechanism: " + case["weakening_condition"])
            st.text("Unresolved question: " + finding["unresolved_question"])
            st.text("Missing evidence: " + finding["missing_evidence"])
            st.caption("Financial basis (supports the observation, not its cause): " + ", ".join(finding["source_ids"]))
        st.caption(reasoning["limitation"])


def _display(value, unit, metric):
    if value is None:
        return "N/A"
    if unit == "percentage_points":
        return f"{value:+.2f} pp"
    if unit == "ratio":
        if "debt_to_operating_cash_flow" in metric:
            return f"{value:.2f}x"
        return f"{value * 100:.2f}%"
    return f"{value:,.0f} {unit}"


def show_financial_analysis(result, analysis=None):
    analysis = analysis if analysis is not None else build_analytics(result)
    st.subheader("Annual comparisons & capital allocation")
    st.caption("PYTHON CALCULATIONS — annual inputs, explicit comparisons and source-linked screening observations. These are not AI conclusions.")
    chosen = {"revenue_growth", "operating_income_growth", "operating_margin_change_pp", "net_income_growth",
        "operating_cash_flow_growth", "capital_expenditure_growth", "capex_to_revenue",
        "capex_to_operating_cash_flow", "free_cash_flow", "free_cash_flow_growth", "free_cash_flow_margin",
        "free_cash_flow_conversion", "net_debt", "net_debt_to_operating_cash_flow"}
    rows = []
    for record in analysis["metrics"]:
        if record["metric"] in chosen:
            rows.append({"Metric": record["label"], "Fiscal year": record["fiscal_year"],
                "Annual period": f"{record['period_start'] or 'Instant at'} to {record['period_end']}",
                "Value": _display(record["value"], record["unit"], record["metric"]),
                "Comparison": "; ".join(f"FY{p['fiscal_year']}: {p['period_start']} to {p['period_end']}" for p in record.get("comparison_periods", [])[:-1]),
                "Source IDs": ", ".join(record["dependencies"]), "Why N/A": record["reason"]})
    with st.expander("Inspect annual calculated metrics and comparison periods", expanded=False):
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        st.caption("Percentages are displayed from decimal ratios; margin changes are percentage points. Debt/OCF is a year-end balance divided by annual cash flow, not EBITDA leverage.")
    latest = max((p.fiscal_year for p in result.periods), default=None)
    tensions = [t for t in analysis["tensions"] if t["current_period"]["fiscal_year"] == latest]
    if not tensions:
        st.caption("No numerical relationship met the configured screening thresholds. This does not establish absence of investment risk.")
    for tension in tensions:
        with st.container(border=True):
            st.markdown("**" + tension["title"] + "**")
            st.text(tension["explanation"])
            st.caption(f"Annual comparison: {tension['prior_period']['period_start']} to {tension['prior_period']['period_end']} versus {tension['current_period']['period_start']} to {tension['current_period']['period_end']}")
            with st.expander("Inspect the numerical relationship and sources", expanded=False):
                st.dataframe(pd.DataFrame([{"Metric": c["metric"],
                    "Prior": _display(c["prior"]["value"], c["prior"]["unit"], c["metric"]),
                    "Current": _display(c["current"]["value"], c["current"]["unit"], c["metric"]),
                    "Prior sources": ", ".join(c["prior"]["raw_source_ids"]),
                    "Current sources": ", ".join(c["current"]["raw_source_ids"])} for c in tension["comparisons"]]),
                    hide_index=True, width="stretch")
                for change in tension["changes"]:
                    st.caption(f"{change['metric']}: {_display(change['value'], change['unit'], change['metric'])}")
    with st.expander("Analytical definitions, materiality and limitations", expanded=False):
        for text in analysis["limitations"]:
            st.text(text)
        st.caption("Screening thresholds (decimal growth rates; changes ending pp are percentage points):")
        st.code(json.dumps(analysis["thresholds"], indent=2), language="json")
        st.caption("Thresholds are configurable through build_analytics; they are screening choices, not economically universal significance tests. Full calculations and source facts are included in the snapshot JSON export.")
    from .evidence import build_evidence_book
    from .investment_reasoning import build_investment_reasoning
    try:
        reasoning = build_investment_reasoning(build_evidence_book(result), analysis)
    except ValueError:
        st.warning("Investment reasoning was withheld because its financial observations could not be reconciled. Annual financials remain available.")
    else:
        show_investment_reasoning(reasoning)
