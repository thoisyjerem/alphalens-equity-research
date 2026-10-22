"""Optional research tools for the existing dashboard.

Only an explicit, confirmed button press can request an LLM response. Model
prose is plain text; links, values and periods are rendered from local evidence.
"""
from __future__ import annotations

import hashlib
import json

import pandas as pd
import streamlit as st


SECTION_LABELS = {
    "executive_summary": "Executive investment research summary",
    "what_matters_most": "What matters most?",
    "capital_allocation": "Capital allocation and cash returns",
    "performance": "Financial performance",
    "business_developments": "Business developments",
    "investment_considerations": "Investment considerations",
    "assumptions": "Underlying assumptions",
    "supporting_evidence": "Supporting evidence",
    "contradictory_evidence": "Contradictory evidence",
    "risks": "Risks",
    "missing_information": "Missing information & diligence",
    "invalidation_conditions": "Observable invalidation conditions",
}

_FOCUSED_CONTRACTS = frozenset({"focused_v1", "focused_v2", "focused_v3"})


def _filing_contexts(result):
    """Use service-validated retrieved context, never model-created sources."""
    from .service import load_offline_filing_context, make_filing_context

    if result.mode == "offline":
        context = load_offline_filing_context(result)
        return [context] if context else []
    selection = st.session_state.get("research_context_selection")
    selected_accession = selection[2] if selection and selection[:2] == (result.ticker, result.cik) else None
    retrieved = st.session_state.get("research_filing_context")
    if (retrieved and retrieved.get("ticker") == result.ticker and retrieved.get("mode") == result.mode
            and (selected_accession is None or retrieved.get("accession") == selected_accession)):
        return [retrieved]
    stored = st.session_state.get("filing_excerpts")
    if stored and stored[0] == result.ticker and (selected_accession is None or stored[1] == selected_accession):
        try:
            return [make_filing_context(result, stored[1], stored[2])]
        except ValueError:
            # A stale accession must not become evidence for a different issuer.
            return []
    return []


def research_fingerprint(evidence: dict, model: str, hypothesis: str = "", *, filing_selection=None, provider: str = "openai") -> str:
    """Invalidate output when any source, period, number, model or thesis changes."""
    packet = {"evidence": evidence, "model": model, "hypothesis": hypothesis, "filing_selection": filing_selection, "provider": provider,
        "research_contract_revision": "focused_v3_reasoning_review_v1_1"}
    return hashlib.sha256(
        json.dumps(packet, sort_keys=True, ensure_ascii=False, allow_nan=False).encode("utf-8")
    ).hexdigest()


def _sync_filing_selection(result, accession: str):
    """A chosen filing cannot silently reuse another annual report's passages."""
    selection = (result.ticker, result.cik, accession)
    previous = st.session_state.get("research_context_selection")
    retrieved = st.session_state.get("research_filing_context")
    mismatched_retrieval = retrieved and retrieved.get("accession") != accession
    if (previous is not None and previous != selection) or mismatched_retrieval:
        st.session_state.research_filing_context = None
        for prefix in ("research_brief", "thesis"):
            st.session_state[f"{prefix}_result"] = None
            st.session_state[f"{prefix}_error"] = None
            st.session_state[f"{prefix}_fingerprint"] = None
            st.session_state[f"{prefix}_request_epoch"] = st.session_state.get(f"{prefix}_request_epoch", 0) + 1
    st.session_state.research_context_selection = selection


def _source_context(evidence: dict, result, namespace: str):
    financials = [source for source in evidence.values() if source["kind"] == "financial"]
    passages = [(source_id, source) for source_id, source in evidence.items() if source["kind"] == "passage"]
    st.caption(
        f"Evidence available: {len(financials)} annual financial observations and "
        f"{len(passages)} bounded SEC filing passages. Figures and calculations come from Python."
    )
    if result.mode == "offline":
        st.caption("OFFLINE DEMONSTRATION — financials and filing passages are checked-in historical SEC fixtures.")
    if not passages:
        st.info(
            "Financial evidence only: business developments and narrative risks cannot be fully assessed. "
            "In live SEC mode, retrieve the selected annual filing passages in AI Research Briefing before generating research."
        )
        return
    with st.expander("Inspect the SEC filing context supplied to AI", expanded=False):
        seen = set()
        for source_id, source in passages:
            key = (source.get("accession"), source.get("item"))
            if key not in seen:
                st.caption(
                    f"Item {source.get('item', 'N/A')} · report date {source.get('report_date', 'N/A')} · "
                    f"accession {source.get('accession', 'N/A')}"
                )
                seen.add(key)
            st.caption(f"Source ID: {source_id}")
            if source.get("selection_method"):
                st.caption(f"Topic-selected source window · {', '.join(source.get('topics', []))} · section offsets {source['offset_start']}–{source['offset_end']}. This is not the complete filing.")
            elif source.get("excerpt_truncated"):
                st.caption("The retrieved section was truncated. These bounded passages do not represent the complete filing.")
            st.text(source["text"])
            if source.get("url"):
                st.link_button("Open the source SEC filing", source["url"], key=f"{namespace}_context_{source_id}")


def _show_financial_source(source_id: str, source: dict, namespace: str):
    st.caption(f"Financial source: {source_id}")
    st.dataframe(
        pd.DataFrame([{
            "Source ID": source_id,
            "Metric": source["metric"],
            "Python value": source["value"],
            "Unit": source["unit"],
            "Fiscal year": source["fiscal_year"],
            "Start": source.get("period_start") or "Instant balance",
            "End": source["period_end"],
            "Mode": source.get("mode", "N/A"),
        }]),
        hide_index=True,
        width="stretch",
    )
    for index, fact in enumerate(source.get("sources", [])):
        fact_period = f"{fact['start']} to {fact['end']}" if fact.get("start") else f"at {fact['end']}"
        st.caption(
            f"Concept {fact['concept']} · original value {fact['value']:,.8g} {fact['unit']} · "
            f"period {fact_period} · "
            f"accession {fact['accession']} · filed {fact['filed']}"
        )
        if fact.get("url"):
            st.link_button("Open SEC financial source", fact["url"], key=f"{namespace}_{source_id}_{index}")


def _show_claim_sources(claim, evidence: dict, namespace: str):
    for citation in claim.financial_citations:
        source = evidence[citation.source_id]
        _show_financial_source(citation.source_id, source, namespace)
    for citation in claim.passage_citations:
        source = evidence[citation.source_id]
        st.caption(
            f"Passage {citation.source_id} · Item {source.get('item', 'N/A')} · "
            f"report date {source.get('report_date', 'N/A')} · accession {source.get('accession', 'N/A')}"
        )
        st.caption("Exact source quote checked against the retrieved passage:")
        st.text(citation.quote)
        st.caption(
            f"Source mode: {source.get('mode', 'N/A')} · retrieved {source.get('retrieved_at') or 'not recorded (legacy session excerpt)'} · "
            f"passage offsets {source.get('offset_start', 'N/A')}–{source.get('offset_end', 'N/A')}"
        )
        if source.get("selection_method"):
            st.caption(f"Selection: {source['selection_method']} · offsets measured in the complete normalized Item section, not a stitched excerpt. Topics: {', '.join(source.get('topics', []))}.")
            if source.get("boundary_truncated"):
                st.caption("This source window cuts an oversized sentence/table block; inspect surrounding filing text before interpreting it.")
        elif source.get("excerpt_truncated"):
            st.caption("The original section excerpt was truncated; inspect the full filing for context.")
        st.caption("Complete retrieved passage:")
        st.text(source["text"])
        parent_id = source.get("parent_source_id")
        if parent_id:
            parent = evidence.get(parent_id)
            # Inspect retained context, never infer a source relationship from
            # an ID alone or promote extra disclosure into the model's claim.
            if (isinstance(parent, dict) and parent.get("kind") == "passage"
                    and all(parent.get(key) == source.get(key) for key in
                            ("ticker", "cik", "accession", "report_date", "document_sha256", "mode"))
                    and isinstance(parent.get("text"), str)
                    and type(source.get("offset_start")) is int and type(parent.get("offset_start")) is int
                    and source["offset_start"] >= parent["offset_start"]
                    and parent["text"][source["offset_start"] - parent["offset_start"]:
                        source["offset_start"] - parent["offset_start"] + len(source["text"])] == source["text"]):
                with st.expander("Surrounding recorded filing context", expanded=False):
                    st.caption("Reviewer context retained locally, not an additional model citation. The complete parent passage was not necessarily sent to Gemini. This remains a selected excerpt, not the entire filing.")
                    st.caption(f"Parent source {parent_id} · Item {parent.get('item', 'N/A')} · accession {parent['accession']}")
                    st.text(parent["text"])
            else:
                st.caption("The retained surrounding context could not be matched to this source window; inspect the audit JSON before relying on it.")
        if source.get("url"):
            st.link_button("Open cited SEC filing", source["url"], key=f"{namespace}_{citation.source_id}")


def show_validated_research(validated, namespace: str = "research"):
    """Only checked claims enter the main report; failed claims are quarantined."""
    report = validated.verification
    if report.unsupported_count:
        st.error("INCOMPLETE AI REPORT — claims failed mechanical checks and are withheld. Review the failures below; this is not a fully validated report.")
    st.warning(
        "AI-GENERATED RESEARCH — source, figure and period checks do not prove the meaning of a claim, "
        "causality or an investment conclusion. Analyst review is required."
    )
    st.caption(
        f"Source/figure checks passed for {report.evidence_checked_count} factual claims; "
        f"{report.interpretation_count} interpretations; {report.unsupported_count} unsupported claims withheld. "
        f"Model: {validated.model}."
    )
    from .analytical_review import review_research
    try:
        analytical = review_research(validated)
    except (ValueError, TypeError, KeyError, AttributeError):
        st.warning("The additional analytical review is unavailable. Original checks and text remain visible; do not infer analytical approval.")
        analytical = []
    with st.expander("Analytical evidence review — flags and limitations", expanded=False):
        st.caption("READ-ONLY REVIEW — original model text and historical mechanical results are unchanged. These bounded rules identify some errors, not general semantic correctness. Every category still requires analyst review.")
        for row in analytical:
            st.caption(f"{row['section']}[{row['index']}] · {row['category']}")
            st.text(row["claim_text"])
            st.text(row["support_basis"])
            st.caption("Cited evidence IDs: " + (", ".join(row["evidence_ids"]) or "None; a question is not evidence."))
            for flag in row["flags"]:
                st.text(flag["code"] + ": " + flag["message"])
    review_lookup = {(row["section"], row["index"]): row for row in analytical}
    for warning in validated.warnings:
        st.info(warning)
    if getattr(validated, "contract", "legacy") in _FOCUSED_CONTRACTS:
        st.caption("Focused workflow: Python assembles figures, periods, observation references and exact source windows. Gemini supplies only qualitative interpretations, alternatives, risks and questions.")
        with st.expander("Inspect Python financial observations", expanded=False):
            for observation_id, observation in validated.financial_observations.items():
                st.caption(f"Observation {observation_id} · {observation['title']}")
                st.json(observation)
        from .investment_reasoning import build_investment_reasoning
        from .analysis_ui import show_investment_reasoning
        try:
            reasoning = build_investment_reasoning(validated.evidence, validated.analysis, validated.financial_observations)
        except ValueError:
            st.warning("Economic question framing was withheld because its financial basis could not be reconciled.")
        else:
            show_investment_reasoning(reasoning)
    order = ["executive_summary", "performance", "business_developments", "what_matters_most", "capital_allocation",
             "investment_considerations", "risks", "missing_information"]
    sections = [s for s in order if s in type(validated.output).model_fields]
    sections += [s for s in type(validated.output).model_fields if s not in sections]
    if getattr(validated, "contract", "legacy") in _FOCUSED_CONTRACTS and not validated.output.business_developments:
        sections = [s for s in sections if s != "business_developments"]
    for section in sections:
        st.markdown(f"**{SECTION_LABELS.get(section, section.replace('_', ' ').title())}**")
        checked_claims = [claim for claim in report.claims if claim.section == section and claim.status != "unsupported"]
        if not checked_claims:
            st.caption("No source-supported claims were returned for this section. Review the missing information before drawing a conclusion.")
        for checked in checked_claims:
            with st.container(border=True):
                labels = {
                    "evidence_checked": "Source/figure checks passed — claim meaning unverified; analyst review required",
                    "interpretation": "Interpretation — requires analyst review",
                    "hypothesis": "Hypothesis / assumption — unproven",
                    "question": "Diligence question — unanswered",
                }
                st.caption(labels.get(checked.status, checked.status))
                review = review_lookup.get((checked.section, checked.index))
                if review:
                    st.caption("Additional evidence review: " + review["category"] + "; analyst judgment required.")
                    for flag in review["flags"]:
                        st.caption(flag["code"] + ": " + flag["message"])
                st.text(checked.claim.text)
                if checked.claim.financial_citations or checked.claim.passage_citations:
                    with st.expander("Inspect supporting sources", expanded=False):
                        _show_claim_sources(checked.claim, validated.evidence, f"{namespace}_{checked.section}_{checked.index}")
                with st.expander("Analyst review required", expanded=False):
                    for flag in checked.review_flags:
                        st.text(flag)
                    st.caption("Mechanical validation passed for the cited data; the claim has not been approved by a human analyst.")
    if report.unsupported_count:
        st.error(f"{report.unsupported_count} unsupported claims were excluded from the research above.")
        with st.expander("Review unsupported claims and validation failures", expanded=False):
            st.caption("UNSUPPORTED MODEL OUTPUT — do not treat this text or its references as verified evidence.")
            for checked in report.claims:
                if checked.status != "unsupported":
                    continue
                st.caption(SECTION_LABELS.get(checked.section, checked.section))
                st.text(checked.claim.text)
                for issue in checked.issues:
                    st.text(f"Validation issue: {issue}")
    st.caption(f"Evidence fingerprint: {report.source_fingerprint}")
    with st.expander("Source and validation appendix", expanded=False):
        st.json({key: value for key, value in getattr(validated, "diagnostics", {}).items() if key != "audit_path"})
        st.caption("Schema, number and source checks are separate from semantic relevance and research usefulness. Local audit records contain metadata without prompts, hypotheses, credentials or raw provider errors.")
    if st.toggle("Prepare downloadable AI research report", value=False, key=f"{namespace}_export_toggle") is True:
        from .research_exports import export_research_json, export_research_markdown
        try:
            markdown = export_research_markdown(validated)
            payload = export_research_json(validated)
        except (ValueError, TypeError):
            st.error("Report export failed source consistency checks. Reload evidence and review this report before exporting.")
        else:
            st.download_button("Research note Markdown", markdown, file_name=f"alphalens_{namespace}.md", mime="text/markdown", key=f"{namespace}_markdown")
            st.download_button("Research audit JSON", payload, file_name=f"alphalens_{namespace}.json", mime="application/json", key=f"{namespace}_json")


def _show_recorded_readout(saved):
    """Presentation of existing evidence, kept separate from recorded AI text."""
    from .recorded_readout import build_recorded_readout

    try:
        readout = build_recorded_readout(saved)
    except ValueError:
        st.warning("The presentation comparisons could not be reconciled and are withheld. The original recorded report and its source checks remain below.")
        return
    prior, current = readout["prior_period"], readout["current_period"]
    st.subheader("The investment question: when does reinvestment turn into cash?")
    st.caption(
        f"RECORDED SEC EVIDENCE · FY{current['fiscal_year']} ({current['period_start']} to {current['period_end']}) "
        f"versus FY{prior['fiscal_year']} ({prior['period_start']} to {prior['period_end']}). "
        "Python calculations below; no new Gemini output."
    )
    for col, row in zip(st.columns(3), readout["cash_rows"]):
        with col:
            st.markdown(f"**{row['label']} change**")
            st.markdown(f"**{row['change'] / 1_000_000_000:+,.3f} USD bn**")
    st.dataframe(pd.DataFrame([{
        "Annual measure (USD bn)": row["label"],
        f"FY{prior['fiscal_year']}": f"{row['prior'] / 1_000_000_000:,.3f}",
        f"FY{current['fiscal_year']}": f"{row['current'] / 1_000_000_000:,.3f}",
        "Change": f"{row['change'] / 1_000_000_000:+,.3f}",
        "Source IDs": ", ".join(row["source_ids"]),
    } for row in readout["cash_rows"]]), hide_index=True, width="stretch")
    st.caption("PYTHON CALCULATION · Defined FCF = operating cash flow − cash purchases of PP&E. Change in FCF = change in OCF − change in cash PP&E. Cash PP&E is shown as a positive cash outlay.")
    st.text("REVIEWER OBSERVATION — Investment requirements absorbed more than the additional operating cash generated. If elevated reinvestment persists, future free cash flow will depend on operating cash generation catching up or investment needs easing. These figures alone cannot determine whether investment creates or destroys value; company-wide cash PP&E is neither AI-only spending nor lease-inclusive investment.")
    st.markdown("**Margin improvement is not uniform across the business**")
    st.dataframe(pd.DataFrame([{
        "Operating margin": row["label"],
        f"FY{prior['fiscal_year']}": f"{row['prior_pct']:.2f}%",
        f"FY{current['fiscal_year']}": f"{row['current_pct']:.2f}%",
        "Change (percentage points)": f"{row['change_pp']:+.2f}",
    } for row in readout["margins"]]), hide_index=True, width="stretch")
    st.caption("REVIEWER CALCULATION · Operating income / revenue × 100, using the retained SEC segment table (USD millions). This context was not an additional citation in the recorded Gemini findings. It does not establish AI-specific profitability or returns.")
    from .investment_reasoning import segment_context_flags
    for flag in segment_context_flags(readout):
        st.warning(flag["message"] + " This is a calculated context warning, not a causal explanation.")
    with st.expander("Inspect cash bridge and segment sources", expanded=False):
        for row in readout["cash_rows"]:
            for source_id in row["source_ids"]:
                _show_financial_source(source_id, saved.evidence[source_id], "recorded_readout")
        source_id = readout["segment_source_id"]
        source = saved.evidence[source_id]
        st.caption(f"Reviewer table source: {source_id} · report date {source['report_date']} · accession {source['accession']}")
        st.text(source["text"])
        st.link_button("Open SEC segment table filing", source["url"], key="recorded_segment_source")
    with st.expander("What comes from SEC, Python, Gemini and the reviewer?", expanded=False):
        st.markdown(
            "- **SEC-reported facts:** annual amounts and retained filing passages, with fiscal periods and accessions.\n"
            "- **Python-calculated metrics:** growth, margins, defined FCF and the reconciled cash bridge.\n"
            "- **Gemini interpretations:** the genuine recorded response below, preserved unchanged.\n"
            "- **Independent reviewer observations:** this investment framing, the segment comparison and audit cautions.\n"
            "- **Unverified hypotheses / missing evidence:** explanations, future monetisation and investment returns that still require research."
        )
    with st.expander("Independent review — weaknesses in this recorded analysis", expanded=False):
        st.text("Working-capital premise: the question 'How sustainable are the working capital benefits and lower cash income-tax payments observed in operating cash flow?' assumes working-capital benefits that the cited passage does not establish. Higher customer receipts and lower cash-tax payments are disclosed; a working-capital attribution needs a separate reconciliation.")
        st.text("Operating versus net income: the proposed alternative about 'non-recurring items or specific segment mix shifts' is not established by the cited operating-profit evidence. Nearby OpenAI investment gains concern net income/EPS; they must not be used as evidence of operating-income growth.")
        st.text("Missing segment context: aggregate operating-margin improvement coexists with a decline in Intelligent Cloud operating margin. The reviewer calculation above supplies retained context; it is not a new Gemini finding or proof of its cause.")
        st.text("Unknown investment returns: consolidated cash PP&E cannot identify AI-only spending, lease-inclusive investment, utilisation, incremental cash returns or AI-specific ROIC. Neither the constructive nor cautionary interpretation is proven.")
        st.caption("Full independent assessment: outputs/offline_jhi_review_2026-10-20/INDEPENDENT_RESEARCH_REVIEW.md. The recorded response predates later prompt improvements; this replay does not validate the revised prompt.")
    st.markdown("**Genuine recorded Gemini interpretations — unchanged**")


def show_research_tool(result, *, challenge: bool = False):
    """Render one research feature without triggering requests during app loading."""
    from .ai import AiError, challenge_thesis, generate_research_brief
    from .evidence import EvidenceError, build_evidence_book
    from .providers import ProviderError, read_ai_config
    from .service import SecError, load_research_filing_context

    prefix = "thesis" if challenge else "research_brief"
    st.subheader("Challenge the Thesis" if challenge else "AI Investment Research Briefing")
    st.caption(
        "Test an investment hypothesis against the sourced financials and retrieved annual filing passages."
        if challenge else
        "A concise fundamental research briefing covering performance, developments, investment considerations and risks."
    )
    if not challenge and result.ticker == "MSFT":
        from .saved_research import available_saved_briefing, load_saved_briefing, saved_briefing_identity
        identity = saved_briefing_identity()
        if st.session_state.get("saved_msft_briefing_identity") != identity:
            st.session_state.saved_msft_briefing = None
            st.session_state.saved_msft_briefing_identity = identity
        if available_saved_briefing():
            with st.expander("Recorded Microsoft briefing — no API request", expanded=False):
                st.caption("Preserved actual Gemini output and its identified SEC snapshot. Loading rechecks the saved evidence and report locally; it does not generate fresh research.")
                if st.button("Load recorded Microsoft briefing", key="load_saved_msft_briefing"):
                    st.session_state.saved_msft_briefing = None
                    try:
                        st.session_state.saved_msft_briefing = load_saved_briefing()
                    except ValueError:
                        st.error("The saved briefing failed its integrity or validation checks. No recorded report was displayed.")
                saved = st.session_state.get("saved_msft_briefing")
                if saved is not None:
                    st.warning("Recorded SEC snapshot and AI response — not a new API result. Critical review flags remain; human analyst approval is pending.")
                    _show_recorded_readout(saved)
                    if saved.contract == "focused_v2":
                        st.info("Review flags for this historical report: 'tax receipts' should refer to cash-tax payments; cash PP&E excludes lease investment; the findings overlap and do not establish future investment returns.")
                    else:
                        st.info("Review this report's actual interpretations, alternatives, limitations and quoted passages. Corporate cash PP&E does not identify AI-only investment or establish future returns.")
                    show_validated_research(saved, "saved_msft")
    try:
        config = read_ai_config()
    except ProviderError as exc:
        st.error(str(exc))
        return
    api_key, model = config.api_key, config.model
    if not challenge and result.mode == "live" and result.filings:
        filings = {row["accession"]: row for row in result.filings}
        accession = st.selectbox(
            "SEC annual filing for AI context",
            list(filings),
            format_func=lambda value: f"{filings[value]['form']} · year ended {filings[value]['report_date']} · {value}",
            key="research_context_choice",
        )
        _sync_filing_selection(result, accession)
        if st.button("Retrieve selected SEC filing passages", key="research_load_context"):
            st.session_state.research_filing_context = None
            try:
                with st.spinner("Retrieving the selected official SEC filing…"):
                    st.session_state.research_filing_context = load_research_filing_context(
                        result, accession, st.session_state.get("sec_user_agent_input", "")
                    )
            except (ValueError, SecError) as exc:
                st.error(str(exc))
            else:
                st.rerun()
    try:
        contexts = _filing_contexts(result)
        evidence = build_evidence_book(result, contexts)
    except (ValueError, EvidenceError, SecError) as exc:
        st.error(f"AI source context could not be verified: {exc}")
        return
    if not challenge and config.provider == "gemini":
        from .focused_briefing import build_briefing_context
        try:
            focused = build_briefing_context(result, contexts)
        except ValueError:
            focused = None
        if focused is not None:
            # Inspect precisely the bounded narrative windows in the compact
            # request; complete parent records remain in Source evidence.
            context_evidence = {key: source for key, source in evidence.items() if source["kind"] == "financial"}
            context_evidence.update({key: focused.evidence[key] for key in focused.packet["passages"]})
            _source_context(context_evidence, result, prefix)
            with st.expander("Inspect the focused model context — no API request", expanded=False):
                st.json(focused.packet)
        else:
            _source_context(evidence, result, prefix)
    else:
        _source_context(evidence, result, prefix)
    hypothesis = ""
    if challenge:
        hypothesis = st.text_area(
            "Your investment hypothesis",
            placeholder="For example: Microsoft can sustain cash generation despite higher infrastructure investment.",
            max_chars=2500,
            key="thesis_input",
            help=f"This is an unverified research hypothesis. It will be sent to {config.label} only after you confirm a request.",
        ).strip()
    selection = st.session_state.get("research_context_selection") if result.mode == "live" else None
    fingerprint = research_fingerprint(evidence, model, hypothesis, filing_selection=selection, provider=config.provider)
    if st.session_state.get(f"{prefix}_fingerprint") != fingerprint:
        st.session_state[f"{prefix}_result"] = None
        st.session_state[f"{prefix}_error"] = None
        st.session_state[f"{prefix}_error_diagnostics"] = None
        st.session_state[f"{prefix}_fingerprint"] = fingerprint
    if not api_key:
        st.info(
            f"This optional AI tool is unavailable until {config.key_env} is configured in your local .env file and the app is restarted. "
            "No key is needed for the financial dashboard or source inspection."
        )
    st.caption(
        f"Configured provider: {config.label}. Model: {model}. A confirmed request sends public SEC financials, retrieved SEC passages"
        + (" and your typed hypothesis" if challenge else "")
        + f" to {config.label}. A configured key has not been authenticated until a request succeeds."
    )
    if config.provider == "gemini":
        st.caption(
            "Free-tier quotas apply. Check that this project shows Free tier in AI Studio with billing disabled; "
            "AlphaLens cannot determine account billing from a key. No request falls back to another provider."
        )
        consent_label = "I confirm this Gemini project uses Free tier with billing disabled, and authorise this request."
    else:
        consent_label = "I authorise this OpenAI request and any API usage charges."
    epoch = st.session_state.get(f"{prefix}_request_epoch", 0)
    consent = st.checkbox(
        consent_label,
        value=False,
        disabled=not api_key,
        key=f"{prefix}_consent_{fingerprint[:16]}_{epoch}",
    )
    if st.button(
        "Challenge my thesis" if challenge else "Generate investment research briefing",
        key=f"generate_{prefix}",
        disabled=not api_key or not consent or (challenge and len(hypothesis) < 12),
        type="primary",
    ):
        st.session_state[f"{prefix}_result"] = None
        st.session_state[f"{prefix}_error"] = None
        try:
            with st.spinner("Generating research and validating source IDs, figures and financial periods…"):
                provider_kwargs = {} if config.provider == "openai" else {"provider": config.provider}
                if challenge:
                    output = challenge_thesis(result, hypothesis, api_key=api_key, model=model, filing_contexts=contexts, **provider_kwargs)
                else:
                    output = generate_research_brief(result, api_key=api_key, model=model, filing_contexts=contexts,
                        **({"contract": "focused_v3"} if config.provider == "gemini" else {}), **provider_kwargs)
            st.session_state[f"{prefix}_result"] = output
        except AiError as exc:
            st.session_state[f"{prefix}_error"] = str(exc)
            st.session_state[f"{prefix}_error_diagnostics"] = exc.diagnostics
        st.session_state[f"{prefix}_request_epoch"] = epoch + 1
        st.rerun()
    if st.session_state.get(f"{prefix}_error"):
        st.error(st.session_state[f"{prefix}_error"])
        st.info("AI generation or validation failed. SEC financial tables and deterministic analysis remain available. No partial model report has been promoted to verified research.")
        details = st.session_state.get(f"{prefix}_error_diagnostics") or {}
        with st.expander("Inspect AI validation failure", expanded=False):
            st.caption(f"Parsing: {details.get('parsing_result', 'not_run')} · Schema: {details.get('schema_validation_result', 'not_run')} · Stage: {details.get('validation_stage', 'provider_response')}")
            for issue in details.get("validation_issues", []):
                st.text(f"{issue.get('path', '$')}: {issue.get('type', 'validation_error')}")
            st.caption("Missing classifications are not inferred. No automatic retry or alternative provider request was made.")
    output = st.session_state.get(f"{prefix}_result")
    if output is not None:
        show_validated_research(output, prefix)
