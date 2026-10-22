"""Optional official macro data, plus explicitly conditional investor scenarios."""
from datetime import date
import json
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .investment_lens import build_investment_lens, build_investor_readout
from .macro import load_macro_snapshot


MACRO_CACHE_DIR = Path(__file__).resolve().parents[1] / ".cache" / "macro"


def _money(value):
    # Streamlit renders write() as Markdown: multiple bare dollar signs would
    # otherwise turn a sourced cash-flow comparison into a LaTeX expression.
    return f"\\${value / 1_000_000_000:+,.2f}bn"


def _card_value(record):
    value = record["value"]
    if value is None:
        return "N/A"
    if record["unit"] == "percentage_points":
        return f"{value:+.2f} pp"
    return f"{value * 100:+.1f}%" if record["unit"] == "ratio" else f"{value:,.2f}"


def _show_readout(readout, bridge):
    with st.container(border=True):
        st.caption("INVESTMENT READOUT · PYTHON FACTS + CONDITIONAL ANALYST FRAMEWORK")
        st.markdown("### " + readout["headline"])
        st.write(readout["summary"])
        st.markdown("**The question that matters:** " + readout["research_question"])
    with st.container(key="investor_financial_cards"):
        for start in (0, 3):
            columns = st.columns(3)
            for column, record in zip(columns, readout["financial_cards"][start:start + 3]):
                with column, st.container(border=True):
                    st.caption(record["label"])
                    st.markdown("### " + _card_value(record))
                    st.caption(record["reason"] or "Comparable annual SEC periods · Python calculation")
    periods = readout["annual_comparison"]
    if periods["prior"] and periods["current"]:
        st.caption(f"Company comparison: FY{periods['prior']['fiscal_year']} ({periods['prior']['period_end']}) → FY{periods['current']['fiscal_year']} ({periods['current']['period_end']}). Figures use the selected financial data mode.")
    else:
        st.caption("A comparable pair of annual periods is unavailable. Unsupported comparisons remain N/A.")
    if bridge:
        st.markdown("**Where the extra operating cash went**")
        chart = go.Figure(go.Waterfall(
            orientation="v", measure=["relative", "relative", "total"],
            x=["Extra operating cash", "Extra cash PP&E", "Change in free cash flow"],
            y=[bridge["ocf_change"] / 1e9, -bridge["cash_ppe_change"] / 1e9, 0],
            text=[f"+{bridge['ocf_change'] / 1e9:,.2f}", f"−{bridge['cash_ppe_change'] / 1e9:,.2f}", f"{bridge['fcf_change'] / 1e9:,.2f}"],
            textposition="outside", increasing={"marker": {"color": "#147d78"}},
            decreasing={"marker": {"color": "#b36c4c"}}, totals={"marker": {"color": "#263f5b"}}))
        chart.update_layout(height=320, margin={"t": 28, "r": 20, "b": 20, "l": 30},
            yaxis_title="Annual change · USD bn", paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)", showlegend=False)
        st.plotly_chart(chart, width="stretch", key="cash_return_bridge")
        st.write(f"FY{bridge['prior_period']['fiscal_year']} → FY{bridge['current_period']['fiscal_year']}: operating cash flow changed by {_money(bridge['ocf_change'])}; cash PP&E by {_money(bridge['cash_ppe_change'])}; free cash flow by {_money(bridge['fcf_change'])}.")
        intensity = readout["capital_intensity"]
        if intensity:
            st.write(f"Cash PP&E absorbed **{intensity['current'] * 100:.1f}% of operating cash flow**, versus **{intensity['prior'] * 100:.1f}%** in the comparative year.")
        st.caption(f"Holding current cash PP&E fixed, an additional {_money(bridge['cash_recovery_gap'])} of annual OCF would restore prior annual FCF. This is an accounting bridge, not a forecast or return estimate. Company cash PP&E does not isolate AI investment or include all lease commitments.")
    constructive, cautious = st.columns(2)
    with constructive, st.container(border=True):
        st.markdown("**The constructive case to test**")
        st.write(readout["constructive_case"])
        st.caption("Evidence that would strengthen it")
        for item in readout["more_constructive_if"]:
            st.markdown("- " + item)
    with cautious, st.container(border=True):
        st.markdown("**The risk case to test**")
        st.write(readout["cautionary_case"])
        st.caption("Evidence that would increase concern")
        for item in readout["more_cautious_if"]:
            st.markdown("- " + item)


def show_macro_lens(result):
    st.subheader("Macro & investment drivers")
    st.caption("A research framework linking company cash flows to macro scenarios. No AI request or API key is needed.")
    today = date.today()
    # Saved data should be useful in every browser session. Revalidate its age
    # when the calendar day changes; this path never initiates HTTP.
    if st.session_state.get("macro_snapshot_checked_on") != today.isoformat():
        saved = load_macro_snapshot(cache_dir=MACRO_CACHE_DIR, refresh=False, as_of=today)
        has_data = any(item.get("value") is not None for item in saved["series"])
        st.session_state["macro_snapshot"] = saved if has_data or saved.get("errors") else None
        st.session_state["macro_snapshot_checked_on"] = today.isoformat()
    snapshot = st.session_state.get("macro_snapshot")
    with st.expander("Manage macro data", expanded=snapshot is None):
        if st.button("Load / refresh macro indicators (free)", key="load_macro_snapshot"):
            with st.spinner("Retrieving public Federal Reserve data…"):
                snapshot = load_macro_snapshot(cache_dir=MACRO_CACHE_DIR, refresh=True, as_of=today)
                st.session_state["macro_snapshot"] = snapshot
        if st.button("Use saved macro snapshot (no network)", key="load_cached_macro_snapshot"):
            snapshot = load_macro_snapshot(cache_dir=MACRO_CACHE_DIR, refresh=False, as_of=today)
            st.session_state["macro_snapshot"] = snapshot
    lens = build_investment_lens(result, snapshot)
    readout = build_investor_readout(result, snapshot, lens=lens)
    bridge = lens["cash_bridge"]
    _show_readout(readout, bridge)
    st.markdown("### What macro changes in this debate")
    if snapshot is None:
        st.info("No saved macro observations are available yet. Click ‘Load / refresh macro indicators (free)’ to retrieve public Federal Reserve data. Saved data will appear automatically in future sessions. No Gemini request or API key is needed.")
    else:
        st.caption(f"Macro snapshot: {snapshot['mode'].upper()} · observation cutoff {snapshot['as_of']} · retrieved {snapshot.get('retrieved_at') or 'N/A'}. Individual observation dates differ.")
        with st.container(key="investor_macro_cards"):
            columns = st.columns(3)
            for column, item in zip(columns, snapshot["series"]):
                with column, st.container(border=True):
                    labels = {"DGS10": "US 10-year Treasury", "DTWEXBGS": "Broad US dollar", "INDPRO": "US industrial activity"}
                    st.caption(labels[item["series_id"]])
                    level = "N/A" if item["value"] is None else f"{item['value']:.2f}" + ("%" if item["series_id"] == "DGS10" else "")
                    st.markdown("### " + level)
                    change = item.get("change")
                    unit = "pp" if item["change_unit"] == "percentage_points" else "%"
                    st.write("Annual comparison: N/A" if change is None else f"{change:+.2f} {unit} versus {item['comparison_date']}")
                    st.caption(f"Observed {item.get('observation_date') or 'N/A'} · {item['status']}")
                    st.markdown(f"[Official source]({item['source_url']})")
        rows = []
        for item in snapshot["series"]:
            available = item.get("value") is not None
            change = item.get("change")
            rows.append({"Indicator": item["label"],
                "Latest level": f"{item['value']:,.4f}" if available else "N/A",
                "Units": item["unit"], "Observation date": item.get("observation_date") or "N/A",
                "Frequency": item["frequency"],
                "Comparison date": item.get("comparison_date") or "N/A",
                "Comparison level": f"{item['comparison_value']:,.4f}" if item.get("comparison_value") is not None else "N/A",
                "Change": f"{change:+.2f} {'pp' if item['change_unit'] == 'percentage_points' else '%'}" if change is not None else "N/A",
                "Status": item["status"], "Source": item["source_url"]})
        with st.expander("Inspect macro observations and annual comparisons", expanded=False):
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                column_config={"Source": st.column_config.LinkColumn("Official series")})
        st.caption("Changes compare available observations about one year apart; exact dates are shown. Treasury yield changes are percentage points; dollar and industrial-output changes are percentages. Monthly output is not an annualised growth rate.")
        for item in snapshot["series"]:
            if item["status"] != "available":
                st.warning(f"{item['label']}: {item.get('reason') or 'Current macro context unavailable.'} Historical levels do not establish current conditions.")
            for warning in item.get("warnings", []):
                st.caption(f"{item['label']}: {warning}")
        for error in snapshot.get("errors", []):
            st.warning(error)

    for text in readout["macro_context_limits"]:
        st.caption(text)
    st.markdown("**Read-through and next research steps**")
    for channel in lens["channels"]:
        st.markdown("**" + channel["title"] + "**")
        st.write(channel["current_read_through"])
        st.caption("Next: " + channel["what_to_monitor"])
    st.caption("Interpretations and scenarios require analyst review. A macro series does not prove issuer exposure or historical causation.")
    for channel in lens["channels"]:
        with st.expander("Evidence and counterarguments: " + channel["title"], expanded=False):
            st.caption("OBSERVED COMPANY ANCHOR")
            st.write(channel["observed_company_change"])
            st.caption(f"Financial observation: {channel['company_observation_id'] or 'N/A'} · macro series {channel['macro_series_id']} ({channel['macro_status']}).")
            context = channel["macro_context"]
            if context and context.get("value") is not None:
                st.write(f"Observed macro context: {context['value']:,.4f} {context['unit']} on {context['observation_date']}.")
                if context.get("change") is not None:
                    unit = "percentage points" if context["change_unit"] == "percentage_points" else "%"
                    st.caption(f"Change versus {context['comparison_date']}: {context['change']:+.2f} {unit}. This is a macro observation, not an estimated company impact.")
                if channel["macro_status"] != "available":
                    st.caption("Historical context only: no current-condition assessment is supported.")
            st.markdown("**Current read-through**")
            st.write(channel["current_read_through"])
            st.markdown("**Conditional mechanism**")
            st.write(channel["mechanism"])
            st.markdown("**Competing explanation**")
            st.write(channel["alternative_explanation"])
            st.markdown("**Evidence to watch**")
            st.write(channel["what_to_monitor"])
            st.markdown("**What would weaken the concern?**")
            st.write(channel["what_would_weaken_concern"])
            st.caption("Missing evidence: " + channel["missing_evidence"])
    with st.expander("Sources, definitions & research limits", expanded=False):
        for text in lens["limitations"]:
            st.write(text)
        st.markdown("General rates, demand and currency transmission: [Federal Reserve explanation](https://www.federalreserve.gov/monetarypolicy/monetary-policy-what-are-its-goals-how-does-it-work.htm). Company-specific transmission remains an analyst hypothesis.")
        source_rows = []
        for key, record in {**lens["company_source_registry"], **readout["source_registry"]}.items():
            for source in record.get("sources", []):
                source_rows.append({"Company source ID": key, "Value": record["value"],
                    "Unit": record["unit"], "Fiscal year": record["fiscal_year"],
                    "Period end": record["period_end"], "Underlying XBRL tag": source["concept"],
                    "Accession": source["accession"], "SEC filing": source["url"]})
        st.dataframe(pd.DataFrame(source_rows), hide_index=True, width="stretch",
            column_config={"SEC filing": st.column_config.LinkColumn("SEC filing")})
        if snapshot:
            for item in snapshot["series"]:
                st.markdown(f"[{item['series_id']} — official definition]({item['source_url']})")
                st.caption(item.get("change_formula") or "No supported comparison.")
            st.download_button("Download macro research framework JSON",
                json.dumps({"status": "Research framework; analyst review required", "macro": snapshot,
                    "investment_lens": lens, "investor_readout": readout}, ensure_ascii=False, indent=2, allow_nan=False),
                file_name=f"alphalens_{result.ticker}_{result.mode}_macro_framework.json", mime="application/json",
                key="download_macro_framework")
