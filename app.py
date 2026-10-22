"""AlphaLens: annual SEC research with explicit provenance and offline mode."""

from __future__ import annotations

import hashlib
import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

from alphalens.service import (
    SecError,
    build_observations,
    load_research,
    load_filing_excerpts,
    snapshot_csv,
    snapshot_json,
)


load_dotenv()
st.set_page_config(
    page_title="AlphaLens — AI Investment Research",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)

METRICS = [
    ("revenue", "Revenue", "USD m"),
    ("operating_income", "Operating income", "USD m"),
    ("operating_margin", "Operating margin", "%"),
    ("net_income", "Net income", "USD m"),
    ("diluted_eps", "Diluted EPS", "USD/share"),
    ("operating_cash_flow", "Operating cash flow", "USD m"),
    ("capital_expenditure", "Capital expenditure", "USD m"),
    ("free_cash_flow", "Free cash flow", "USD m"),
    ("cash_and_equivalents", "Cash and cash equivalents", "USD m"),
    ("total_debt", "Total debt", "USD m"),
    ("net_debt", "Net debt", "USD m"),
]
LABELS = {key: label for key, label, _ in METRICS}
COLORS = ["#147d78", "#263f5b", "#d39c4b"]


def metric_value(period, key):
    metric = period.metrics.get(key)
    return metric.value if metric is not None else None


def formatted_value(value, unit: str) -> str:
    if value is None:
        return "N/A"
    if unit == "%":
        return f"{value * 100:,.1f}%"
    if unit == "USD/share":
        return f"${value:,.2f}"
    return f"{value / 1_000_000:,.0f}"


def statement_frame(result) -> pd.DataFrame:
    rows = []
    for key, label, unit in METRICS:
        row = {"Metric": label, "Unit": unit}
        for period in result.periods:
            row[f"FY{period.fiscal_year} · {period.end}"] = formatted_value(
                metric_value(period, key), unit
            )
        rows.append(row)
    return pd.DataFrame(rows)


def provenance_frame(result) -> pd.DataFrame:
    rows = []
    for period in result.periods:
        for key, label, _ in METRICS:
            metric = period.metrics.get(key)
            sources = metric.sources if metric else []
            reason = metric.reason if metric else "Metric was not returned."
            if not sources:
                rows.append(
                    {
                        "Metric": label,
                        "Fiscal year": f"FY{period.fiscal_year}",
                        "Statement period": f"At {period.end}" if key in {"cash_and_equivalents", "total_debt", "net_debt"} else f"{period.start} to {period.end}",
                        "XBRL concept": "N/A",
                        "Source value": "N/A",
                        "Unit": "—",
                        "Fact period": "—",
                        "Accession": "—",
                        "Filed": "—",
                        "Form": "—",
                        "Source filing": None,
                        "Explanation": reason or "No supporting fact available.",
                    }
                )
            for source in sources:
                fact_period = (
                    f"{source.start} to {source.end}"
                    if source.start
                    else f"At {source.end}"
                )
                rows.append(
                    {
                        "Metric": label,
                        "Fiscal year": f"FY{period.fiscal_year}",
                        "Statement period": f"At {period.end}" if key in {"cash_and_equivalents", "total_debt", "net_debt"} else f"{period.start} to {period.end}",
                        "XBRL concept": source.concept,
                        "Source value": f"{source.value:,.4f}".rstrip("0").rstrip("."),
                        "Unit": source.unit,
                        "Fact period": fact_period,
                        "Accession": source.accession,
                        "Filed": source.filed,
                        "Form": source.form,
                        "Source filing": source.url,
                        "Explanation": reason or "Reported SEC XBRL fact.",
                    }
                )
    return pd.DataFrame(rows)


def annual_chart(result, series: list[str], title: str):
    fig = go.Figure()
    for color, key in zip(COLORS, series):
        fig.add_bar(
            x=[f"FY{p.fiscal_year}" for p in result.periods],
            y=[
                metric_value(p, key) / 1_000_000_000
                if metric_value(p, key) is not None
                else None
                for p in result.periods
            ],
            customdata=[p.end for p in result.periods],
            name=LABELS[key],
            marker_color=color,
            marker_line_width=0,
            hovertemplate=(
                "%{x} · year ended %{customdata}<br>"
                + LABELS[key]
                + ": $%{y:,.2f}bn<extra></extra>"
            ),
        )
    fig.update_layout(
        title={"text": title, "font": {"size": 17, "color": "#20384c"}},
        template="plotly_white",
        barmode="group",
        bargap=0.32,
        height=350,
        margin={"l": 5, "r": 10, "t": 48, "b": 40},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"family": "Arial, sans-serif", "color": "#516274", "size": 12},
        legend={"orientation": "h", "yanchor": "top", "y": -0.15, "x": 0},
        yaxis={"title": "USD billions", "gridcolor": "#e6ebed", "zerolinecolor": "#d7e1e5"},
        xaxis={"showgrid": False, "fixedrange": True},
    )
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def show_status(result):
    if result.mode == "offline":
        st.warning(
            "OFFLINE DEMONSTRATION — checked-in historical SEC fixture. "
            "This is not a live SEC response or live market data. "
            "Company financial figures, charts and financial downloads use this fixture. Macro indicators are separately sourced and dated."
        )
    else:
        st.info(
            "SEC ANNUAL FILINGS — reported accounting data, subject to the local cache. "
            "This application does not provide live share prices or market data."
        )


def show_overview(result):
    from alphalens.analytics import build_analytics
    analysis = build_analytics(result)
    latest = result.periods[-1]
    previous = result.periods[-2] if len(result.periods) > 1 else None
    cards = [
        ("revenue", "Revenue", "USD m"),
        ("operating_margin", "Operating margin", "%"),
        ("free_cash_flow", "Free cash flow", "USD m"),
        ("net_debt", "Net debt", "USD m"),
    ]
    with st.container(key="overview_metrics"):
        for col, (key, label, unit) in zip(st.columns(4), cards):
            with col:
                with st.container(border=True):
                    value = metric_value(latest, key)
                    delta = None
                    if key == "revenue" and previous:
                        checked = next((row for row in analysis["metrics"] if row["fiscal_year"] == latest.fiscal_year and row["metric"] == "revenue_growth"), None)
                        if checked and checked["value"] is not None:
                            delta = f"{checked['value'] * 100:.1f}% vs FY{previous.fiscal_year}"
                    display = formatted_value(value, unit)
                    if value is not None and unit == "USD m":
                        display = f"${display}m"
                    st.metric(label, display, delta=delta)
                    st.caption(f"FY{latest.fiscal_year} · {'at' if key == 'net_debt' else 'year ended'} {latest.end}")
                    if value is None:
                        metric = latest.metrics.get(key)
                        with st.expander("Why N/A"):
                            st.caption(metric.reason if metric else "No supporting fact available.")

    with st.container(key="overview_charts"):
        left, right = st.columns(2)
        with left:
            annual_chart(result, ["revenue", "operating_income"], "Revenue & operating income")
        with right:
            annual_chart(
                result,
                ["operating_cash_flow", "capital_expenditure", "free_cash_flow"],
                "Cash generation & reinvestment",
            )
    st.caption(
        "Annual fiscal periods only. Missing observations remain empty. "
        "Capital expenditure is shown as a positive cash outlay."
    )
    margins = [row for row in analysis["metrics"] if row["metric"] == "operating_margin"]
    margin_chart = go.Figure(go.Scatter(
        x=[f"FY{row['fiscal_year']}" for row in margins],
        y=[row["value"] * 100 if row["value"] is not None else None for row in margins],
        customdata=[row["period_end"] for row in margins], mode="lines+markers", connectgaps=False,
        line={"color": "#147d78"}, name="Operating margin",
        hovertemplate="%{x} · year ended %{customdata}<br>Operating margin: %{y:.2f}%<extra></extra>"))
    margin_chart.update_layout(title="Operating margin · checked annual inputs", height=250,
        yaxis_title="Operating income / revenue (%)", template="plotly_white", margin={"l": 20, "r": 20, "t": 45, "b": 20},
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(margin_chart, width="stretch", key="annual_operating_margin")
    st.subheader("Research observations")
    st.caption("Calculated in Python from the displayed annual figures. These observations are not an investment recommendation.")
    observations = build_observations(result)
    if observations:
        for observation in observations:
            st.markdown(f"- {observation}")
    else:
        st.info("There are insufficient comparable annual figures to generate observations.")
    from alphalens.analysis_ui import show_financial_analysis
    show_financial_analysis(result, analysis)


def show_statements(result):
    st.subheader("Annual financial summary")
    st.caption(
        "Income and cash-flow metrics cover each complete fiscal year. Cash and debt are fiscal year-end balances. "
        "USD m means millions of US dollars; EPS is dollars per diluted share."
    )
    st.dataframe(statement_frame(result), hide_index=True, width="stretch", height=457)
    missing = []
    for period in result.periods:
        for key, label, _ in METRICS:
            metric = period.metrics.get(key)
            if metric is None or metric.value is None:
                missing.append(
                    {
                        "Fiscal year": f"FY{period.fiscal_year}",
                        "Metric": label,
                        "Why N/A": metric.reason if metric else "No supporting fact available.",
                    }
                )
    if missing:
        st.markdown("**Unavailable figures**")
        st.dataframe(pd.DataFrame(missing), hide_index=True, width="stretch")
    st.caption("Display values are rounded. Downloads retain the underlying calculation precision and source metadata.")


def show_provenance(result):
    st.subheader("Trace every figure to the filing")
    st.caption(
        "Reported figures retain their XBRL concept, unit, exact period and accession. "
        "Calculated metrics show every supporting input. Source values below use the original reported units, without millions scaling."
    )
    options = ["All metrics"] + [label for _, label, _ in METRICS]
    selected = st.selectbox("Filter source evidence", options, key="evidence_filter")
    frame = provenance_frame(result)
    if selected != "All metrics":
        frame = frame[frame["Metric"] == selected]
    st.dataframe(
        frame,
        hide_index=True,
        width="stretch",
        height=520,
        column_config={"Source filing": st.column_config.LinkColumn("Source filing", display_text="Open SEC filing")},
    )


def show_method(result):
    st.subheader("Filing library")
    if result.filings:
        rows = []
        for filing in result.filings:
            rows.append(
                {
                    "Form": filing.get("form", "10-K"),
                    "Filed": filing.get("filing_date", filing.get("filingDate", filing.get("filed", "—"))),
                    "Report date": filing.get("report_date", filing.get("reportDate", filing.get("end", "—"))),
                    "Accession": filing.get("accession", filing.get("accessionNumber", "—")),
                    "SEC filing": filing.get("url"),
                }
            )
        st.dataframe(
            pd.DataFrame(rows),
            hide_index=True,
            width="stretch",
            column_config={"SEC filing": st.column_config.LinkColumn("SEC filing", display_text="Open filing")},
        )
    else:
        st.info("No filing-library entries were available. Individual source facts remain available in Source evidence.")

    st.subheader("Read the annual filing")
    st.caption("Extract Item 1A risk factors and Item 7 management discussion from the selected SEC document. Excerpts preserve the filing's text and are not an AI summary.")
    if result.mode == "offline":
        st.info("Select live SEC mode to download filing text. Offline mode makes no network requests.")
    elif result.filings:
        by_accession = {row["accession"]: row for row in result.filings}
        accession = st.selectbox("Annual filing to read", list(by_accession),
            format_func=lambda value: f"{by_accession[value]['form']} · year ended {by_accession[value]['report_date']} · filed {by_accession[value]['filing_date']}", key="filing_choice")
        if st.button("Extract filing sections", key="extract_filing"):
            st.session_state.filing_excerpts = None
            st.session_state.research_filing_context = None
            try:
                with st.spinner("Downloading the official SEC document and locating section boundaries…"):
                    excerpts = load_filing_excerpts(result, accession, st.session_state.get("sec_user_agent_input", ""))
                st.session_state.filing_excerpts = (result.ticker, accession, excerpts)
            except (ValueError, SecError) as exc:
                st.error(str(exc))
        stored = st.session_state.get("filing_excerpts")
        if stored and stored[0] == result.ticker and stored[1] == accession:
            st.markdown(f"[Source SEC filing]({by_accession[accession]['url']}) · accession {accession}")
            for excerpt in stored[2].values():
                with st.expander(f"Item {excerpt.item} · {excerpt.title}"):
                    if excerpt.reason:
                        st.info(excerpt.reason)
                    else:
                        if excerpt.truncated:
                            st.caption(f"First {len(excerpt.text):,} of {excerpt.original_chars:,} section characters. Open the complete filing for context.")
                        st.text(excerpt.text)

    with st.expander("Manual filing text — local fallback", expanded=False):
        st.caption("If automated section extraction fails, upload a UTF-8 text or HTML copy to inspect it locally. Uploaded content is user-supplied and unverified; it is not added to the SEC evidence registry or sent to an AI provider.")
        uploaded = st.file_uploader("Filing text file (maximum 5 MB)", type=["txt", "html", "htm"], max_upload_size=5, key="manual_filing_upload")
        query = st.text_input("Search the uploaded text", value="cash flow capital expenditure liquidity risk", max_chars=150, key="manual_filing_query")
        content = uploaded.getvalue() if uploaded is not None else None
        signature = (hashlib.sha256(content).hexdigest(), query) if content is not None else None
        stored = st.session_state.get("manual_filing_preview")
        if stored and stored[0] != signature:
            st.session_state.manual_filing_preview = None
            stored = None
        if st.button("Inspect uploaded filing locally", disabled=uploaded is None, key="inspect_uploaded_filing"):
            from alphalens.uploaded_filing import inspect_uploaded_filing
            try:
                preview = inspect_uploaded_filing(content, uploaded.name, query)
                stored = (signature, preview)
                st.session_state.manual_filing_preview = stored
            except ValueError as exc:
                stored = None
                st.session_state.manual_filing_preview = None
                st.error(str(exc))
        if stored:
            preview = stored[1]
            st.warning("USER-SUPPLIED, UNVERIFIED FILING TEXT — this preview does not authenticate an SEC filing or the company's identity. Financial figures continue to come from the selected SEC dataset.")
            st.text(f"File: {preview['file_name']} · SHA-256: {preview['sha256']}")
            st.caption(preview["verification_note"])
            st.caption(preview["search_method"])
            for passage in preview["passages"]:
                st.caption(f"Local passage {passage['source_id']} · normalized text offsets {passage['offset_start']}–{passage['offset_end']}")
                st.text(passage["text"])
            for section in preview["sections"]:
                if section["reason"]:
                    st.caption(section["reason"])
            for limitation in preview["limitations"]:
                st.caption(limitation)

    st.subheader("Accounting & calculation policy")
    st.markdown(
        """
- **Annual periods:** completed fiscal years from annual SEC filings. Duration facts must match the fiscal-year start and end; balance-sheet facts must match the year-end date.
- **Operating margin:** operating income ÷ revenue. An unavailable input or zero revenue produces N/A.
- **Capital expenditure:** cash paid to acquire property, plant and equipment, shown as a positive outlay. It does not include all acquisition or investment spending.
- **Free cash flow:** operating cash flow − capital expenditure. This is a defined analytical measure, not a US-GAAP subtotal.
- **Total debt:** interest-bearing borrowings at carrying value, excluding lease liabilities. Source evidence lists the component concepts. Missing debt components are not assumed to be zero.
- **Net debt:** total debt − cash and cash equivalents. Short-term investments are not treated as cash. A negative result indicates net cash under this definition.
- **Diluted EPS:** the reported diluted earnings-per-share concept, in USD/share.
- **Missing facts:** N/A is preserved and its reason is shown. No financial figure is estimated by an LLM or substituted with sample data.
"""
    )
    st.caption(
        "The latest eligible filed facts are used, including subsequent comparatives and amendments; historical values may be restated and are not point-in-time backtest data. "
        "Review Source evidence for the exact concept and submission used for each year. "
        "Fiscal-year labels follow company reporting periods, which may differ from calendar years."
    )


def show_ai_research(result):
    """Optional commentary. Financial evidence is always rendered from Python."""
    from alphalens.ai import AiError, evidence_catalog, generate_brief
    from alphalens.providers import ProviderError, read_ai_config

    st.subheader("Optional AI research commentary")
    st.caption(
        "The core financial analysis works without an AI API key. "
        "When enabled, the model receives the sourced annual metric snapshot; "
        "it does not calculate financial figures or fetch additional data."
    )
    try:
        config = read_ai_config()
    except ProviderError as exc:
        st.error(str(exc))
        return
    api_key, model = config.api_key, config.model
    from alphalens.ai import COMMENTARY_REVISION
    fingerprint = hashlib.sha256(
        (COMMENTARY_REVISION + "\n" + config.provider + "\n" + model + "\n" + snapshot_json(result)).encode("utf-8")
    ).hexdigest()
    if st.session_state.get("ai_fingerprint") != fingerprint:
        st.session_state.ai_brief = None
        st.session_state.ai_error = None
        st.session_state.ai_error_diagnostics = None
        st.session_state.ai_fingerprint = fingerprint

    if not api_key:
        st.info(
            f"AI commentary is unavailable until {config.key_env} is set in your local .env file and the app is restarted. "
            "The annual metrics, source evidence and downloads remain available."
        )
    st.caption(f"Configured provider: {config.label}. Model: {model}. A configured key has not been authenticated until a request succeeds.")
    consent = True
    epoch = st.session_state.get("ai_request_epoch", 0)
    if config.provider == "gemini":
        st.caption("Gemini supplies qualitative commentary. AlphaLens selects the latest comparable financial observations and attaches their verified source references.")
        st.caption(
            "A confirmed request sends this public SEC research snapshot to Google. Free-tier quotas apply. "
            "Check that this project shows Free tier in AI Studio with billing disabled; AlphaLens cannot determine account billing from a key. "
            "No request falls back to another provider."
        )
        consent = st.checkbox(
            "I confirm this Gemini project uses Free tier with billing disabled, and authorise this request.",
            value=False, disabled=not api_key,
            key=f"ai_consent_{fingerprint[:16]}_{epoch}",
        )
    else:
        st.caption("Generating commentary sends this research snapshot to OpenAI and may incur API usage charges.")
    if st.button("Generate AI commentary", disabled=not api_key or not consent, key="generate_ai"):
        st.session_state.ai_brief = None
        st.session_state.ai_error = None
        st.session_state.ai_error_diagnostics = None
        try:
            with st.spinner("Generating and validating sourced commentary…"):
                provider_kwargs = {} if config.provider == "openai" else {"provider": config.provider}
                st.session_state.ai_brief = generate_brief(result, api_key=api_key, model=model,
                    **({"contract": "bound_v1"} if config.provider == "gemini" else {}), **provider_kwargs)
        except AiError as exc:
            st.session_state.ai_error = str(exc)
            st.session_state.ai_error_diagnostics = exc.diagnostics
        if config.provider == "gemini":
            st.session_state.ai_request_epoch = epoch + 1
            st.rerun()

    if st.session_state.get("ai_error"):
        st.error(st.session_state.ai_error)
        details = st.session_state.get("ai_error_diagnostics") or {}
        with st.expander("Inspect AI commentary validation failure", expanded=False):
            st.caption(f"Parsing: {details.get('parsing_result', 'not_run')} · Schema: {details.get('schema_validation_result', 'not_run')} · Stage: {details.get('validation_stage', 'provider_response')}")
            for issue in details.get("validation_issues", []):
                st.text(f"{issue.get('path', '$')}: {issue.get('type', 'validation_error')}")
            st.caption("Malformed output is rejected without repair. No automatic retry or alternative provider request was made.")
    brief = st.session_state.get("ai_brief")
    if brief is None:
        return

    st.warning(
        "AI-GENERATED INTERPRETATION — requires analyst review. Validation checks the output structure and evidence references "
        "and rejects numerical prose. It does not establish that the interpretation is correct or that an investment thesis is sound."
    )
    catalog = evidence_catalog(result)
    for insight in brief.observations:
        with st.container(border=True):
            st.markdown(insight.text)
            rows = []
            for evidence_id in insight.evidence_ids:
                evidence = catalog[evidence_id]
                key = evidence["metric"]
                display_unit = "%" if key == "operating_margin" else "USD/share" if key == "diluted_eps" else "USD m"
                rows.append(
                    {
                        "Evidence ID": evidence_id,
                        "Metric": LABELS.get(key, key),
                        "Value": formatted_value(evidence["value"], display_unit),
                        "Unit": display_unit,
                        "Fiscal year": f"FY{evidence['fiscal_year']}",
                        "Period": (
                            f"At {evidence['period_end']}"
                            if key in {"cash_and_equivalents", "total_debt", "net_debt"}
                            else f"{evidence['period_start']} to {evidence['period_end']}"
                        ),
                    }
                )
            st.caption("Supporting financial values below come from Python. Trace their original filings in Source evidence.")
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    if brief.questions:
        st.markdown("**Questions for the analyst**")
        for question in brief.questions:
            st.markdown(f"- {question}")
    if brief.caveats:
        st.markdown("**Model caveats**")
        for caveat in brief.caveats:
            st.markdown(f"- {caveat}")


st.markdown(
    """<style>
    .stApp { background: #f6f8fa; color: #23394d; }
    .block-container { padding: 2rem; max-width: 1500px; }
    [data-testid="stSidebar"] { background: #eaf0f2; border-right: 1px solid #dce4e8; }
    [data-testid="stMetricValue"] { color: #17394b; font-size: 1.85rem; }
    [data-testid="stMetricLabel"] { color: #5b6f7e; }
    [data-testid="stVerticalBlockBorderWrapper"] > div { background: #ffffff; }
    h1 { letter-spacing: -.035em; font-weight: 650 !important; }
    h2, h3 { color: #203d51; letter-spacing: -.02em; }
    button[data-baseweb="tab"] { font-weight: 600; }
    .al-brand { font-size: .8rem; font-weight: 750; letter-spacing: .17em; color: #147d78; margin-bottom: .55rem; }
    .al-kicker { color: #637887; font-size: .92rem; margin-bottom: 1rem; }
    @media (max-width: 1150px) {
      .st-key-overview_metrics [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
      .st-key-overview_metrics [data-testid="stColumn"] { flex: 1 1 calc(50% - 1rem); min-width: 0; }
      .st-key-overview_charts [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
      .st-key-overview_charts [data-testid="stColumn"] { flex: 1 1 100%; min-width: 0; }
      .st-key-investor_financial_cards [data-testid="stHorizontalBlock"],
      .st-key-investor_macro_cards [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
      .st-key-investor_financial_cards [data-testid="stColumn"],
      .st-key-investor_macro_cards [data-testid="stColumn"] { flex: 1 1 220px; min-width: 0; }
    }
    @media (max-width: 650px) {
      .block-container { padding: 1rem; }
      .st-key-overview_metrics [data-testid="stColumn"] { flex: 1 1 100%; }
      .st-key-investor_financial_cards [data-testid="stColumn"],
      .st-key-investor_macro_cards [data-testid="stColumn"] { flex: 1 1 100%; }
    }
    </style>""",
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("### ◈ ALPHALENS")
    st.caption("AI INVESTMENT RESEARCH")
    st.divider()
    with st.form("research_form"):
        st.markdown("**Research a company**")
        ticker = st.text_input("Ticker", "MSFT", key="ticker_input", max_chars=12).strip().upper()
        st.caption("Initial coverage: MSFT · AAPL · AMZN")
        source_mode = st.selectbox(
            "Data source", ["Offline SEC fixture", "Live SEC API"], key="source_mode"
        )
        user_agent = st.text_input(
            "SEC User-Agent",
            value=os.getenv("SEC_USER_AGENT", ""),
            key="sec_user_agent_input",
            placeholder="Your name your.real.email@domain.com",
            help="Live mode requires a descriptive User-Agent with your legitimate contact email. You can also set SEC_USER_AGENT in .env.",
        )
        submitted = st.form_submit_button("Load annual research", width="stretch", type="primary")
    st.caption("Offline mode needs no API key or internet. Live requests use the SEC's official APIs and a local response cache.")
    st.divider()
    st.markdown("**Evidence before interpretation**")
    st.caption("Python calculates the financial metrics. Every available figure links back to an SEC filing and reporting period.")

st.markdown('<div class="al-brand">ALPHALENS / RESEARCH WORKSPACE</div>', unsafe_allow_html=True)
st.title("AI Investment Research")
st.markdown('<div class="al-kicker">Fundamental analysis, grounded in reported financial statements.</div>', unsafe_allow_html=True)

if submitted or "research_result" not in st.session_state:
    # Clear the previous company before loading, so a failed search cannot leave a stale result visible.
    st.session_state.research_result = None
    st.session_state.filing_excerpts = None
    st.session_state.research_filing_context = None
    st.session_state.research_error = None
    st.session_state.ai_brief = None
    st.session_state.ai_error = None
    st.session_state.ai_error_diagnostics = None
    st.session_state.ai_fingerprint = None
    for tool_prefix in ("research_brief", "thesis"):
        st.session_state[f"{tool_prefix}_result"] = None
        st.session_state[f"{tool_prefix}_error"] = None
        st.session_state[f"{tool_prefix}_fingerprint"] = None
    selected_mode = "live" if source_mode == "Live SEC API" else "offline"
    try:
        with st.spinner(f"Loading {ticker or 'company'} annual SEC research…"):
            st.session_state.research_result = load_research(ticker, mode=selected_mode, user_agent=user_agent)
    except (ValueError, SecError) as exc:
        st.session_state.research_error = str(exc)

if st.session_state.get("research_error"):
    st.error(st.session_state.research_error)
    st.info("Check the ticker and data source, then load again. Live mode requires a legitimate SEC User-Agent. Offline coverage is limited to the checked-in fixtures.")
    st.stop()

result = st.session_state.get("research_result")
if result is None:
    st.info("Enter a ticker and load annual research to begin.")
    st.stop()
if not result.periods:
    st.error("No completed annual reporting periods were available for this company.")
    st.stop()

show_status(result)
latest_period = result.periods[-1]
st.subheader(f"{result.name} · {result.ticker}")
snapshot_label = "Fixture snapshot" if result.mode == "offline" else "SEC response snapshot"
st.caption(
    f"CIK {str(result.cik).zfill(10)}  ·  "
    f"FY{result.periods[0].fiscal_year}–FY{latest_period.fiscal_year}  ·  "
    f"Latest fiscal year ended {latest_period.end}  ·  {snapshot_label}: {result.retrieved_at}"
)
latest_filing = max(result.filings, key=lambda row: row.get("filing_date", ""), default=None)
if latest_filing:
    st.caption(f"Latest annual filing: {latest_filing['form']} · filed {latest_filing['filing_date']} · report date {latest_filing['report_date']} · accession {latest_filing['accession']}.")
else:
    st.caption("Latest annual filing date: N/A — no verified filing metadata is available.")
if result.warnings:
    with st.expander(f"Data notes ({len(result.warnings)})", expanded=False):
        for warning in result.warnings:
            st.markdown(f"- {warning}")

overview, statements, provenance, method, ai_research, briefing, thesis, macro = st.tabs(
    ["Overview", "Annual financials", "Source evidence", "Filings & methodology", "AI commentary", "AI Research Briefing", "Challenge the Thesis", "Macro & investment drivers"],
    default="Macro & investment drivers" if st.query_params.get("view") == "macro" else "Overview",
)
with overview:
    show_overview(result)
with statements:
    show_statements(result)
with provenance:
    show_provenance(result)
with method:
    show_method(result)
with ai_research:
    show_ai_research(result)
with briefing:
    from alphalens.research_ui import show_research_tool
    show_research_tool(result)
with thesis:
    show_research_tool(result, challenge=True)
with macro:
    from alphalens.macro_ui import show_macro_lens
    show_macro_lens(result)

st.divider()
export_left, export_csv, export_json = st.columns([2.6, 1, 1])
with export_left:
    st.markdown("**Export the research snapshot**")
    st.caption("Exports include source periods and mode labels. OFFLINE exports remain explicitly marked as fixture data." if result.mode == "offline" else "Exports include source periods, source evidence and the SEC response snapshot timestamp.")
    if st.toggle("Prepare financial research note (Markdown)", value=False, key="financial_report_toggle"):
        from alphalens.financial_report import financial_markdown
        try:
            financial_note = financial_markdown(result)
        except ValueError:
            st.error("The financial note could not pass source or arithmetic checks. Reload the financial data; CSV and source inspection remain available.")
        else:
            st.download_button("Financial research note Markdown", financial_note,
                file_name=f"alphalens_{result.ticker}_{result.mode}_financials.md", mime="text/markdown", key="financial_report_download")
prefix = f"alphalens_{result.ticker}_{result.mode}"
with export_csv:
    st.download_button("↓ Financials CSV", snapshot_csv(result), file_name=f"{prefix}.csv", mime="text/csv", width="stretch")
with export_json:
    st.download_button("↓ Full evidence JSON", snapshot_json(result), file_name=f"{prefix}.json", mime="application/json", width="stretch")
st.caption("AlphaLens · Annual fundamental research · Accounting data can be revised in subsequent filings. Inspect the source evidence before forming an investment view.")
