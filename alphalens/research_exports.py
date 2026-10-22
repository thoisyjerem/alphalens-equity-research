"""Portable research exports with checked claims and an explicit audit appendix.

Model prose is escaped plain text. Links, figures and periods come from the
local evidence catalog; a valid citation never becomes a semantic approval.
There are no retrieval, configuration, provider or model calls in this module.
"""
from __future__ import annotations

import html
import json
import math
import re
from urllib.parse import urlsplit

from .evidence import evidence_fingerprint
from .research import ResearchAnalysis, validate_analysis


_LABELS = {
    "executive_summary": "Executive summary",
    "what_matters_most": "What matters most",
    "performance": "Financial performance",
    "business_developments": "Business developments",
    "investment_considerations": "Investment considerations",
    "capital_allocation": "Capital allocation",
    "assumptions": "Underlying assumptions",
    "supporting_evidence": "Supporting evidence",
    "contradictory_evidence": "Contradictory evidence",
    "risks": "Risks",
    "missing_information": "Missing information and diligence",
    "invalidation_conditions": "Observable invalidation conditions",
}
_STATUS_LABELS = {
    "evidence_checked": "Reported fact / management disclosure; references checked, meaning requires analyst review",
    "interpretation": "AI interpretation; analyst review required",
    "hypothesis": "Unproven hypothesis / assumption",
    "question": "Unanswered diligence question",
}
_DIAGNOSTIC_KEYS = {
    "timestamp_utc", "operation", "provider", "model", "status", "http_status",
    "latency_seconds", "usage", "parsing_result", "schema_validation_result",
    "validation_stage", "validation_issues", "issues_truncated",
    "numerical_validation_result", "source_validation_result", "warning_codes", "local_repair_paths",
}
_NOTICE = (
    "AI-generated research. Deterministic checks cover structure, source references, cited figures, "
    "reporting periods and quotation membership. They do not establish semantic support, causality, "
    "completeness or investment merit. Analyst review is required."
)


def _text(value) -> str:
    """Render data as Markdown text, including model-authored URLs and HTML."""
    value = " ".join(str(value).split())
    value = html.escape(value, quote=True)
    return re.sub(r"([\\`*_{}\[\]()#+.!|:/=\-])", r"\\\1", value)


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _value(value) -> str:
    return str(value) if _finite(value) else "N/A"


def _period(row: dict) -> str:
    start, end = row.get("period_start"), row.get("period_end")
    if not end:
        return "N/A — reporting period unavailable"
    return f"FY{row.get('fiscal_year', 'N/A')}; {start} to {end}" if start else f"FY{row.get('fiscal_year', 'N/A')}; as of {end}"


def _origin(source: dict) -> str:
    if source.get("derived") or source.get("metric") in {"operating_margin", "free_cash_flow", "total_debt", "net_debt"}:
        return "Python calculation / financial pipeline"
    return "Reported financial evidence"


def _link(url) -> str | None:
    """Only local-catalog, official SEC HTTPS links become clickable."""
    if not isinstance(url, str):
        return None
    parsed = urlsplit(url)
    if (parsed.scheme == "https" and parsed.netloc in {"www.sec.gov", "data.sec.gov"}
            and not parsed.query and not parsed.fragment and not any(c in url for c in "<>\\\r\n")):
        return f"[Open official SEC source](<{url}>)"
    return None


def _sections(output):
    fields = list(type(output).model_fields)
    if isinstance(output, ResearchAnalysis):
        preferred = ["executive_summary", "what_matters_most", "performance", "business_developments",
                     "investment_considerations", "capital_allocation", "risks", "missing_information"]
        return [name for name in preferred if name in fields] + [name for name in fields if name not in preferred]
    return fields


def _checked(validated):
    """Do not export an old positive check after any input/output was changed."""
    report = validated.verification
    if (getattr(validated, "contract", "legacy") in {"focused_v1", "focused_v2", "focused_v3"}
            or getattr(validated, "assembly_fingerprint", None) is not None
            or getattr(validated, "model_interpretation", None) is not None):
        from .focused_briefing import assembly_fingerprint
        if validated.assembly_fingerprint != assembly_fingerprint(validated):
            raise ValueError("Focused interpretation, observation or report changed after assembly.")
        from .research_integrity import validate_observation_integrity
        validate_observation_integrity(validated.evidence, validated.analysis, validated.financial_observations)
    if evidence_fingerprint(validated.evidence) != report.source_fingerprint:
        raise ValueError("Research evidence changed after validation; regenerate validation before exporting.")
    fresh = validate_analysis(validated.output, validated.evidence)
    if fresh.model_dump(mode="json") != report.model_dump(mode="json"):
        raise ValueError("Research claims changed after validation; regenerate validation before exporting.")
    return report


def _metadata(validated):
    diagnostics = getattr(validated, "diagnostics", {}) or {}
    return {
        "provider": validated.provider,
        "model": validated.model,
        "usage": {key: value for key, value in validated.usage.items()
                  if key in {"input_tokens", "output_tokens", "total_tokens"} and _finite(value) and value >= 0},
        "latency_seconds": validated.latency_seconds if _finite(validated.latency_seconds) and validated.latency_seconds >= 0 else None,
        "diagnostics": {key: value for key, value in diagnostics.items() if key in _DIAGNOSTIC_KEYS},
        "semantic_review": "requires_analyst_review",
        "contract": getattr(validated, "contract", "legacy"),
        "response_transport": "gemini_flat_json" if getattr(validated, "transport_output", None) is not None else "original_provider_format",
    }


def _payload(validated):
    report = _checked(validated)
    sections = {section: [claim.model_dump(mode="json") for claim in report.claims
                          if claim.section == section and claim.status != "unsupported"]
                for section in _sections(validated.output)
                if not (getattr(validated, "contract", "legacy") in {"focused_v1", "focused_v2", "focused_v3"}
                    and section == "business_developments" and not validated.output.business_developments)}
    return {
        "report_type": "AI Investment Research Briefing" if isinstance(validated.output, ResearchAnalysis) else "Challenge the Thesis",
        "notice": _NOTICE,
        "data_modes": sorted({source.get("mode", "unknown") for source in validated.evidence.values()}),
        "metadata": _metadata(validated),
        "supported_sections": sections,
        "unsupported_claims": [claim.model_dump(mode="json") for claim in report.claims if claim.status == "unsupported"],
        "python_analysis": getattr(validated, "analysis", {}) or {},
        "warnings": list(validated.warnings),
        "verification": report.model_dump(mode="json"),
        "source_catalog": validated.evidence,
        "financial_observations": getattr(validated, "financial_observations", {}),
        "raw_output_notice": (
            "Schema-normalized response, not original provider bytes: Python supplied only the omitted diligence-question classification recorded in metadata.diagnostics.local_repair_paths. Text, figures and citations were not repaired. Preserve the original provider capture separately; mechanical checks do not establish meaning."
            if getattr(validated, "diagnostics", {}).get("local_repair_paths") else
            "Original model interpretation retained for audit only, separately from Python's assembled report; mechanical checks do not establish meaning."),
        "raw_model_output": getattr(validated, "transport_output", None) or getattr(validated, "model_interpretation", None) or validated.output.model_dump(mode="json"),
        "compact_model_interpretation": getattr(validated, "model_interpretation", None),
        "assembled_report": validated.output.model_dump(mode="json"),
    }


def export_research_json(validated) -> str:
    """Export complete raw/check/source records without hiding failed claims."""
    return json.dumps(_payload(validated), indent=2, ensure_ascii=False, allow_nan=False)


def export_research_markdown(validated) -> str:
    """Export the checked report, Python tables and separately labelled audit."""
    payload = _payload(validated)
    if getattr(validated, "contract", "legacy") in {"focused_v1", "focused_v2", "focused_v3"}:
        return _focused_markdown(validated, payload)
    report = validated.verification
    metadata = payload["metadata"]
    lines = [f"# AlphaLens — {payload['report_type']}", "", _NOTICE, ""]
    modes = payload["data_modes"]
    if "offline" in modes:
        lines.extend(["**OFFLINE DEMONSTRATION — checked-in SEC snapshot; not a fresh retrieval.**", ""])
    lines.extend([
        f"Provider: {_text(metadata['provider'])}. Model: {_text(metadata['model'])}.",
        f"Response latency: {_value(metadata['latency_seconds'])} seconds. Token usage: {_text(json.dumps(metadata['usage'], ensure_ascii=False)) if metadata['usage'] else 'N/A'}.",
        f"Reference checks: {report.evidence_checked_count} factual claims; {report.interpretation_count} AI interpretations; {report.unsupported_count} unsupported claims quarantined.",
        "Semantic review: **pending analyst review**. Source membership alone does not prove the claim.",
        f"Evidence fingerprint: {_text(report.source_fingerprint)}", "",
    ])
    if payload["warnings"]:
        lines.extend(["## Warnings and limitations", ""])
        lines.extend(f"- {_text(warning)}" for warning in payload["warnings"])
        lines.append("")
    cited_ids = []
    for section, claims in payload["supported_sections"].items():
        lines.extend([f"## {_LABELS.get(section, section.replace('_', ' ').title())}", ""])
        if not claims:
            lines.extend(["N/A — no source-supported claims were returned for this section.", ""])
        for checked in claims:
            claim = checked["claim"]
            lines.extend([f"**{_STATUS_LABELS.get(checked['status'], checked['status'])}**", "", _text(claim["text"]), ""])
            for citation in claim["financial_citations"]:
                source_id = citation["source_id"]
                source = validated.evidence[source_id]
                cited_ids.append(source_id)
                origin = _origin(source)
                lines.extend([f"- {origin}: {_text(source_id)}; {_text(source.get('metric', 'N/A'))} = {_value(source.get('value'))} {_text(source.get('unit', 'N/A'))}; {_text(_period(source))}."])
            for citation in claim["passage_citations"]:
                source_id = citation["source_id"]
                source = validated.evidence[source_id]
                cited_ids.append(source_id)
                lines.append(f"- Management disclosure reference: {_text(source_id)}; Item {_text(source.get('item', 'N/A'))}; filing report date {_text(source.get('report_date', 'N/A'))}. See the source appendix for complete retrieved context.")
            for flag in checked.get("review_flags", []):
                lines.append(f"- Analyst review cue: {_text(flag)}")
            lines.append("")
    analysis = payload["python_analysis"]
    raw_financials = [(source_id, source) for source_id, source in validated.evidence.items()
                      if source.get("kind") == "financial" and not source.get("derived")]
    lines.extend(["## Annual financial inputs", "", "Values use the SEC financial pipeline's original units. Calculated margins, free cash flow and debt aggregates remain labelled Python calculations.", ""])
    if raw_financials:
        lines.extend(["| Source ID | Metric | Value | Unit | Reporting period | Origin |", "|---|---|---:|---|---|---|"])
        for source_id, source in raw_financials:
            lines.append(f"| {_text(source_id)} | {_text(source.get('metric', 'N/A'))} | {_value(source.get('value'))} | {_text(source.get('unit', 'N/A'))} | {_text(_period(source))} | {_origin(source)} |")
        lines.append("")
    else:
        lines.extend(["N/A — no reported annual financial inputs were attached.", ""])
    lines.extend(["## Python-calculated financial analysis", "", "Calculations are separate from AI interpretation. Raw values, units, annual periods and unavailable reasons are retained below.", ""])
    metrics = analysis.get("metrics", [])
    if metrics:
        lines.extend(["| Metric | Value | Unit | Annual period | Calculation / source references |", "|---|---:|---|---|---|"])
        for row in metrics:
            description = row.get("reason") if row.get("value") is None else row.get("calculation", "")
            refs = row.get("raw_dependencies", row.get("dependencies", []))
            detail = f"{description or 'N/A'}; source ID {row.get('source_id', 'N/A')}; dependencies {', '.join(refs) or 'N/A'}"
            lines.append(f"| {_text(row.get('label', row.get('metric', 'N/A')))} | {_value(row.get('value'))} | {_text(row.get('unit', 'N/A'))} | {_text(_period(row))} | {_text(detail)} |")
        lines.append("")
    else:
        lines.extend(["N/A — no Python-calculated analysis was attached to this saved research result.", ""])
    for tension in analysis.get("tensions", []):
        lines.extend([f"**Python screening observation: {_text(tension.get('title', 'N/A'))}**", "",
                      _text(tension.get("explanation", "N/A")), "",
                      "Source references: " + _text(", ".join(tension.get("source_ids", [])) or "N/A"), ""])
    if analysis.get("limitations"):
        lines.extend(f"- Python analysis limitation: {_text(reason)}" for reason in analysis["limitations"])
        lines.append("")
    lines.extend(["## Source appendix", "", "Source text, figures and links below come from the local SEC evidence catalog. Filing report dates do not establish the period of every number mentioned in narrative text.", ""])
    for source_id in dict.fromkeys(cited_ids):
        source = validated.evidence[source_id]
        lines.extend([f"### {_text(source_id)}", ""])
        if source["kind"] == "passage":
            lines.extend([f"Management disclosure: Item {_text(source.get('item', 'N/A'))}; report date {_text(source.get('report_date', 'N/A'))}; accession {_text(source.get('accession', 'N/A'))}.",
                          f"Retrieved: {_text(source.get('retrieved_at') or 'N/A — timestamp not recorded')}; mode {_text(source.get('mode', 'N/A'))}.",
                          f"Section offsets: {_text(source.get('section_offset_start', source.get('offset_start', 'N/A')))} to {_text(source.get('section_offset_end', source.get('offset_end', 'N/A')))}; original section characters: {_text(source.get('original_chars', 'N/A'))}.", "",
                          "> " + _text(source["text"]), ""])
            if source.get("excerpt_truncated") or source.get("boundary_truncated") or source.get("section_truncated"):
                lines.extend(["Context is bounded or truncated; inspect the complete SEC filing before relying on an interpretation.", ""])
            link = _link(source.get("url"))
            if link:
                lines.extend([link, ""])
        else:
            lines.extend([f"{_origin(source)}: {_text(source.get('metric', 'N/A'))} = {_value(source.get('value'))} {_text(source.get('unit', 'N/A'))}; {_text(_period(source))}.", ""])
            if source.get("calculation"):
                lines.extend(["Calculation: " + _text(source["calculation"]), ""])
            if source.get("dependencies"):
                lines.extend(["Dependencies: " + _text(", ".join(source["dependencies"])), ""])
            for fact in source.get("sources", []):
                lines.extend([f"- Reported input: {_text(fact.get('concept', 'N/A'))}; {_value(fact.get('value'))} {_text(fact.get('unit', 'N/A'))}; start {_text(fact.get('start') or 'N/A — instant')}; end {_text(fact.get('end', 'N/A'))}; filed {_text(fact.get('filed', 'N/A'))}; accession {_text(fact.get('accession', 'N/A'))}."])
                link = _link(fact.get("url"))
                if link:
                    lines.append("  " + link)
            lines.append("")
    if not cited_ids:
        lines.extend(["N/A — no checked claim cites a source.", ""])
    lines.extend(["## Quarantined model output — excluded from research", "",
                  "The claims below failed deterministic checks. Their wording and source references must not be treated as verified.", ""])
    if not payload["unsupported_claims"]:
        lines.extend(["None were quarantined. This does not establish semantic accuracy or completeness.", ""])
    for checked in payload["unsupported_claims"]:
        lines.extend([f"**UNSUPPORTED — {_LABELS.get(checked['section'], checked['section'])}**", "", _text(checked["claim"]["text"]), ""])
        lines.extend(f"- Validation issue: {_text(issue)}" for issue in checked["issues"])
        for citation in checked["claim"]["financial_citations"]:
            lines.append("- UNVERIFIED model financial citation: " + _text(json.dumps(citation, ensure_ascii=False, allow_nan=False)))
        for citation in checked["claim"]["passage_citations"]:
            lines.append("- UNVERIFIED model passage citation: " + _text(json.dumps(citation, ensure_ascii=False, allow_nan=False)))
        lines.append("")
    if metadata["diagnostics"]:
        lines.extend(["## Generation diagnostics", "", "Local diagnostic metadata does not establish live integration quality.", ""])
        for key, value in metadata["diagnostics"].items():
            lines.append(f"- {_text(key)}: {_text(json.dumps(value, ensure_ascii=False, allow_nan=False))}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def investment_reasoning_markdown(reasoning):
    """Reading section shared by existing financial and focused AI exports."""
    lines = ["## Economic implications and competing explanations", "",
        "PYTHON / REVIEWER FRAMEWORK — not additional Gemini findings. Financial references establish observations; the proposed mechanisms remain unverified hypotheses.", ""]
    if not reasoning["findings"]:
        lines.extend(["N/A — no comparable material development is available; no explanation was invented.", ""])
    for finding in reasoning["findings"]:
        lines.extend(["### " + _text(finding["observation"]), "",
            "Deterministic observation: " + _text(finding["observation_id"]) + ". "
            + _text(_period(finding["prior_period"])) + " → " + _text(_period(finding["current_period"])) + ".", "",
            "**Economic significance:** " + _text(finding["economic_significance"]), "",
            "**Investment implication:** " + _text(finding["investment_implication"]), "",
            "Financial evidence IDs: " + _text(", ".join(finding["source_ids"])) + ". These do not establish a cause.", ""])
        for case in finding["competing_explanations"]:
            lines.extend(["**" + case["case"] + " — unverified:** " + _text(case["mechanism"]), ""])
        constructive = finding["competing_explanations"][0]
        lines.extend(["Evidence favouring the constructive case / weakening the cautionary case: " + _text(constructive["strengthening_condition"]), "",
            "Evidence favouring the cautionary case / weakening the constructive case: " + _text(constructive["weakening_condition"]), ""])
        lines.extend(["**Unresolved question:** " + _text(finding["unresolved_question"]), "",
            "**Missing evidence:** " + _text(finding["missing_evidence"]), ""])
    return "\n".join(lines)


def _analytical_review_markdown(validated):
    from .analytical_review import review_research
    lines = ["## Analytical evidence review — separate from historical checks", "",
        "Bounded automated review, not semantic certification or a reviewer quality score. Original text is preserved. All categories require analyst judgment.", ""]
    unique = {}
    for row in review_research(validated):
        key = (row["claim_text"], row["category"], tuple(flag["code"] for flag in row["flags"]))
        if key not in unique:
            unique[key] = {**row, "locations": []}
        unique[key]["locations"].append(f"{row['section']}[{row['index']}]")
    lines.extend(["Repeated appearances of the same model finding are grouped; they are not independent analytical successes.", ""])
    for row in unique.values():
        # Keep each claim's first appearance in its original report section;
        # this compact appendix references its exact section/index instead.
        lines.extend([f"- {_text(', '.join(row['locations']))}: **{row['category']}**.",
            "  Cited evidence IDs: " + _text(", ".join(row["evidence_ids"]) or "None") + "."])
        if row["category"] == "Supported interpretation":
            lines.append("  " + _text(row["support_basis"]))
        lines.extend("  " + flag["code"] + ": " + _text(flag["message"]) for flag in row["flags"])
    lines.append("")
    return "\n".join(lines)


def _focused_markdown(validated, payload):
    """Reading edition; the unchanged JSON export retains the complete audit.

    Conditional cases come from the numerical observation types, not an
    invented bullish/bearish classification of the model's interpretation.
    """
    if validated.verification.unsupported_count:
        raise ValueError("A focused reading edition requires all findings to pass local checks.")
    observations = validated.financial_observations
    def references(claim):
        ids = [citation.source_id for citation in claim.financial_citations + claim.passage_citations]
        return "Evidence IDs: " + _text(", ".join(ids) or "No evidence supplied") + ". Hypothesis support and citation relevance require review."
    company = next((row.get("ticker") for row in validated.evidence.values() if row.get("ticker")), "Company")
    lines = [f"# AlphaLens — {company} investment research briefing", "", _NOTICE, "",
        "**Mechanical checks passed; human investment review remains pending.**", "",
        f"Provider: {_text(validated.provider)}. Model: {_text(validated.model)}. "
        f"Recorded generation latency: {_value(validated.latency_seconds)} seconds. "
        f"Tokens: {_text(json.dumps(payload['metadata']['usage']))}.", ""]
    if "offline" in payload["data_modes"]:
        lines.extend(["**OFFLINE DEMONSTRATION — historical SEC fixture, not a fresh retrieval.**", ""])
    lines.extend(["## Executive research summary", ""])
    for claim in validated.output.executive_summary:
        lines.extend([f"- INTERPRETATION — {_text(claim.text)}", "", references(claim), ""])
    lines.extend(["", "## Most important financial developments", "",
        "FACT: SEC-reported inputs. CALCULATION: Python comparisons. Cash PP&E is company-wide cash purchases, not AI-only or lease-inclusive investment. USD billions and percentages are rounded here by Python; exact amounts remain in the audit JSON.", ""])
    comparisons = {entry["metric"]: entry for row in observations.values() for entry in row["comparisons"]}
    lines.extend(["| Metric | Prior fiscal year | Current fiscal year | Units | Source IDs |", "|---|---:|---:|---|---|"])
    for metric, comparison in comparisons.items():
        prior, current = comparison["prior"], comparison["current"]
        divisor, unit = (1e9, "USD bn") if current["unit"] == "USD" else (0.01, "%") if current["unit"] == "ratio" else (1, current["unit"])
        lines.append(f"| {_text(metric)} | {prior['value'] / divisor:,.3f} | {current['value'] / divisor:,.3f} | {_text(unit)} | {_text(prior['source_id'])}; {_text(current['source_id'])} |")
    lines.append("")
    periods = {(json.dumps(row['prior_period'], sort_keys=True), json.dumps(row['current_period'], sort_keys=True)) for row in observations.values()}
    for prior, current in sorted(periods):
        lines.extend([f"Annual periods: {_text(_period(json.loads(prior)))} → {_text(_period(json.loads(current)))}.", ""])
    for observation_id, observation in observations.items():
        lines.append(f"- CALCULATION — {_text(observation_id)}: {_text(observation['title'])}. Formulas and input dependencies are retained under this observation ID in the audit JSON.")
    lines.append("")
    cash = next((row for row in observations.values() if row["type"] == "cash_flow_divergence"), None)
    if cash:
        changes = {row["metric"]: row["current"]["value"] - row["prior"]["value"] for row in cash["comparisons"]}
        lines.extend([f"Cash-flow bridge (USD bn): change in OCF {changes['operating_cash_flow'] / 1e9:+.3f} − change in cash PP&E {changes['capital_expenditure'] / 1e9:+.3f} = change in defined FCF {changes['free_cash_flow'] / 1e9:+.3f}. This reconciles cash retained, not investment returns.", ""])
    lines.extend(["## Key tensions and investment implications", ""])
    for finding, alternative in zip(validated.output.what_matters_most, validated.output.investment_considerations):
        lines.extend(["**INTERPRETATION — causal meaning requires review**", "", _text(finding.text), "",
            references(finding), "", "**Competing hypothesis and evidence gap**", "", _text(alternative.text), "",
            references(alternative), ""])
    lines.extend(["## Bull case versus bear case — hypotheses to investigate", "",
        "These conditional cases are Python's research framework, not additional model findings, forecasts or recommendations. The evidence does not establish which case will prevail.", ""])
    from .investment_reasoning import build_investment_reasoning
    reasoning = build_investment_reasoning(validated.evidence, validated.analysis, observations)
    lines.extend([investment_reasoning_markdown(reasoning), _analytical_review_markdown(validated)])
    lines.extend(["", "## Risks, uncertainties and missing evidence", ""])
    for risk in validated.output.risks:
        lines.extend([_text(risk.text), "", references(risk), ""])
    lines.extend(["## Questions requiring further analyst research", ""])
    lines.extend(f"- {_text(question.text)}" for question in validated.output.missing_information)
    lines.extend(["", "## Sources and validation", "",
        "FCF = operating cash flow − cash PP&E purchases. Ratios are decimal fractions; margin changes are percentage points. Neither company-wide PP&E nor this FCF bridge measures AI-specific ROIC.", "",
        f"Evidence fingerprint: {_text(validated.verification.source_fingerprint)}.", "",
        "Source membership, numerical reconciliation and quotation matches do not establish semantic support. Original model fields, full calculations, original SEC facts and validation details remain in the research audit JSON.", ""])
    used_ids = set(ref for row in observations.values() for ref in row["source_ids"])
    for checked in validated.verification.claims:
        used_ids.update(c.source_id for c in checked.claim.passage_citations)
    for source_id in sorted(used_ids):
        source = validated.evidence[source_id]
        label = _period(source) if source["kind"] == "financial" else "Management disclosure, Item " + str(source.get("item", "N/A"))
        lines.append(f"- {_text(source_id)}: {_text(label)}.")
        for url in dict.fromkeys([source.get("url"), *[fact.get("url") for fact in source.get("sources", [])]]):
            if _link(url):
                lines.append("  " + _link(url))
    lines.extend(["", "### Review qualifications and limitations", ""])
    # Omit only these already-stated boilerplate notices. Preserve unfamiliar
    # warnings by default, especially authored/mock labels and future failures.
    repeated = ("Python owns financial observations,", "Mechanical validation is not semantic approval.",
        "The focused contract intentionally omits", "Python assembles the executive")
    lines.extend(f"- {_text(warning)}" for warning in payload["warnings"] if not warning.startswith(repeated))
    lines.extend(["", "Full disclosure windows, source metadata, calculation formulas and all validation warnings remain inspectable in Streamlit and the research audit JSON."])
    lines.append("")
    return "\n".join(lines)
