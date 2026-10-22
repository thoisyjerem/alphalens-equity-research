"""Offline research evaluation: mechanical checks and a separate human rubric.

No API client is created. Invalid whole reports can be inspected claim by claim,
but that diagnostic never repairs them or promotes them to accepted research.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

from pydantic import ValidationError

from .evidence import evidence_fingerprint
from .providers import GeminiJSONEnvelope, _schema_issue_details
from .research import (Claim, ResearchAnalysis, ResearchNote, ThesisChallenge, _check_claim,
    _financial_issues, _passage_issues, semantic_review_flags)


QUALITY_RUBRIC = [
    {"dimension": "financial_accuracy", "method": "deterministic plus analyst review",
     "criteria": "Every cited figure, unit and annual period matches its source; calculated metrics retain aligned input facts. Matching citations do not prove associated prose."},
    {"dimension": "evidence_traceability", "method": "deterministic",
     "criteria": "Every material fact or inference has a known issuer-bound source; quotations are contiguous source spans; all required citation fields are present."},
    {"dimension": "citation_relevance", "method": "analyst judgement",
     "criteria": "Read each selected quote and source context. It must support every factual clause, the business scope, timing and strength of the claim. Existing source IDs alone are insufficient."},
    {"dimension": "comparative_analysis", "method": "deterministic cues plus analyst judgement",
     "criteria": "Trend claims retain consecutive comparative observations; acceleration needs consecutive growth intervals. Review whether material Python-identified tensions are explained rather than omitted."},
    {"dimension": "investment_insight", "method": "analyst judgement",
     "criteria": "Connect sourced operating developments to cash economics, reinvestment and competitive mechanisms; distinguish corporate cash PP&E from AI attribution and identify what evidence would change the interpretation."},
    {"dimension": "analytical_balance", "method": "analyst judgement",
     "criteria": "State plausible competing explanations, missing evidence and uncertainty. Do not manufacture contradictory evidence or equate spending with attractive incremental ROIC."},
    {"dimension": "schema_reliability", "method": "deterministic",
     "criteria": "Complete response decodes without repair and satisfies its declared transport and local Pydantic contracts. Python-owned classifications must not be invented as model content."},
    {"dimension": "practical_usefulness", "method": "analyst judgement",
     "criteria": "A reviewer can trace the central financial tension, distinguish fact from interpretation and prioritise specific diligence questions. A disclosure summary alone is insufficient for an investment recommendation."},
]

_MANUAL_ANCHORS = {
    "financial_accuracy": ("A cited amount, unit, period or calculated relationship is materially wrong.",
        "Cited amounts match, but scope, annual comparability or calculation provenance remains unresolved.",
        "Cited amounts and calculation inputs match, periods align, and scope/definitions have been inspected."),
    "evidence_traceability": ("Material assertions have fabricated, missing or unusable references.",
        "Some assertions trace to evidence, but individual clauses or derived inputs remain untraceable.",
        "Each material factual assertion has an inspectable issuer-bound record with retained source provenance."),
    "citation_relevance": ("A quotation exists but contradicts or does not support a material associated assertion.",
        "Citations support some clauses, while scope, timing or omitted qualifications require clarification.",
        "The reviewer read the source context and confirmed support for each factual clause and its qualifications."),
    "comparative_analysis": ("Comparisons contradict annual figures, mix periods or omit the central material tension.",
        "Comparisons are mechanically sound but important drivers or competing explanations remain unexplored.",
        "Relevant annual changes and deterministic tensions are sourced and economically interpreted with limitations."),
    "investment_insight": ("The report restates disclosures or claims durable returns without an economic mechanism.",
        "Some mechanisms link operations to cash returns, but attribution or decision-relevant evidence is incomplete.",
        "Company-specific mechanisms, cash economics and critical unresolved evidence are tied to a testable interpretation."),
    "analytical_balance": ("Unsupported certainties, invented counterarguments or missing downside dominate the conclusion.",
        "Uncertainty is acknowledged, but competing explanations or invalidation conditions are generic.",
        "Plausible alternative explanations, genuine contrary evidence and observable uncertainty are explicitly distinguished."),
    "schema_reliability": ("A response is malformed, missing required fields or accepted after substantive repair.",
        "The schema passes, but optional analytical sections are incomplete or generation reliability remains untested.",
        "The complete response passes the intended strict contract without inferred substantive fields; live provenance is recorded."),
    "practical_usefulness": ("An analyst cannot trace claims or identify a useful next research decision.",
        "The output is an inspectable starting summary, but prioritisation or investment implications remain shallow.",
        "An analyst can inspect sources, understand the central tension and prioritise specific thesis-changing diligence."),
}
for _dimension in QUALITY_RUBRIC:
    _anchors = _MANUAL_ANCHORS[_dimension["dimension"]]
    _dimension["manual_levels"] = {"not_assessed": "No explicit reviewer assessment has been recorded.",
        "does_not_meet": _anchors[0], "partial": _anchors[1], "meets": _anchors[2]}


def load_source_catalog(path: str | Path) -> dict:
    """Accept a saved source catalog or recover the exact book from a request."""
    saved = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(saved, dict) and isinstance(saved.get("messages"), list):
        for message in saved["messages"]:
            if message.get("role") == "user":
                packet = json.loads(message["content"])
                if isinstance(packet, dict) and isinstance(packet.get("source_catalog"), dict):
                    return packet["source_catalog"]
        raise ValueError("Saved request does not contain a source catalog.")
    if not isinstance(saved, dict) or not saved or not all(isinstance(row, dict) for row in saved.values()):
        raise ValueError("Expected a nonempty saved source catalog.")
    return saved


def evaluate_output(payload, book: dict, *, feature: str = "brief") -> dict:
    """Evaluate an already decoded object without inferring absent fields."""
    if feature not in {"brief", "challenge"}:
        raise ValueError("Feature must be brief or challenge.")
    extended = isinstance(payload, dict) and any(key in payload for key in ("executive_summary", "what_matters_most", "capital_allocation"))
    schema = (ResearchNote if extended else ResearchAnalysis) if feature == "brief" else ThesisChallenge
    schema_errors = []
    try:
        schema.model_validate(payload)
    except ValidationError as exc:
        schema_errors, truncated = _schema_issue_details(exc, schema)
        schema_passed = False
    else:
        schema_passed, truncated = True, False
    claims, financial, passages = [], [], []
    for section in schema.model_fields:
        rows = payload.get(section, []) if isinstance(payload, dict) else []
        if not isinstance(rows, list):
            continue
        for index, value in enumerate(rows[:5]):
            path = f"{section}[{index}]"
            try:
                claim = Claim.model_validate(value)
            except ValidationError as exc:
                errors, _ = _schema_issue_details(exc, Claim)
                claims.append({"path": path, "status": "schema_invalid", "schema_issues": errors,
                               "issues": [], "review_flags": [], "semantic_review": "not_completed"})
                continue
            status, issues = _check_claim(section, claim, book)
            claims.append({"path": path, "status": status, "schema_issues": [], "issues": issues,
                "review_flags": semantic_review_flags(claim, book), "semantic_review": "requires_analyst_review"})
            for citation in claim.financial_citations:
                found = _financial_issues(citation, book)
                financial.append({"claim_path": path, "source_id": citation.source_id,
                                  "matched": not found, "issues": found})
            for citation in claim.passage_citations:
                found = _passage_issues(citation, book)
                passages.append({"claim_path": path, "source_id": citation.source_id,
                    "quote_membership_matched": not found, "issues": found,
                    "citation_relevance": "requires_analyst_review"})
    counts = dict(Counter(row["status"] for row in claims))
    whole_passed = schema_passed and not counts.get("unsupported")
    return {"feature": feature, "evaluation_type": "offline deterministic checks; qualitative dimensions unscored",
        "source_fingerprint": evidence_fingerprint(book), "schema_passed": schema_passed,
        "schema_issues": schema_errors, "schema_issues_truncated": truncated,
        "complete_local_validation_passed": bool(whole_passed),
        "live_request_executed_by_evaluator": False,
        "diagnostic_only": not schema_passed, "claims": claims, "claim_counts": counts,
        "financial_citations": financial, "passage_citations": passages,
        "mechanical_counts": {"financial_citations_checked": len(financial),
            "financial_citations_matched": sum(row["matched"] for row in financial),
            "passage_quotes_checked": len(passages),
            "passage_quotes_matched": sum(row["quote_membership_matched"] for row in passages)},
        "empty_sections": [section for section in schema.model_fields
                           if not isinstance(payload, dict) or not payload.get(section)],
        "qualitative_assessments": [{**dimension, "assessment": "not_assessed", "score": None}
                                     for dimension in QUALITY_RUBRIC],
        "limitations": ["Per-claim inspection of a rejected report is not whole-report acceptance.",
            "Exact value, period and quote matches do not establish semantic entailment, causal truth or investment merit.",
            "Lexical comparison and attribution checks are conservative cues, not comprehensive natural-language understanding.",
            "No model accuracy percentage, analyst-quality score, productivity saving or investment performance is inferred."]}


def evaluate_saved_report(response_path: str | Path, source_catalog_path: str | Path,
                          *, feature: str = "brief") -> dict:
    """Decode the saved Gemini wire envelope and run the unchanged strict checks."""
    if feature not in {"brief", "challenge"}:
        raise ValueError("Feature must be brief or challenge.")
    book = load_source_catalog(source_catalog_path)
    try:
        raw = json.loads(Path(response_path).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("Response is not an object.")
        if "choices" in raw:
            choices = raw["choices"]
            if not isinstance(choices, list) or len(choices) != 1 or choices[0].get("finish_reason") != "stop":
                raise ValueError("Incomplete provider response.")
            message = choices[0]["message"]
            if message.get("refusal"):
                raise ValueError("Provider refused.")
            envelope = GeminiJSONEnvelope.model_validate_json(message["content"])
            payload = json.loads(envelope.result_json)
        elif "result_json" in raw:
            payload = json.loads(GeminiJSONEnvelope.model_validate(raw).result_json)
        else:
            payload = raw
    except (ValueError, TypeError, KeyError, AttributeError, ValidationError):
        result = evaluate_output(None, book, feature=feature)
        result.update(parsing_passed=False, parsing_error="Saved response could not be decoded completely; no repair was attempted.")
        return result
    result = evaluate_output(payload, book, feature=feature)
    result["parsing_passed"] = True
    return result


def evaluate_focused_bundle(directory: str | Path) -> dict:
    """Replay the current native/compact/assembled workflow with no model call.

    The saved loader verifies the manifest, request ledger, strict flat fields,
    compact model, financial/source checks and exact original export. A failed
    bundle cannot supply diagnostic facts or inherit another report's pass.
    Qualitative assessment always remains a separate reviewer responsibility.
    """
    from .saved_research import load_saved_briefing
    try:
        validated = load_saved_briefing(directory)
    except ValueError:
        report = evaluate_output(None, {})
        report.update(parsing_passed=None, schema_passed=None,
            schema_issues=[], schema_issues_truncated=False, empty_sections=[],
            source_fingerprint=None,
            bundle_integrity_and_replay_passed=False, diagnostic_only=True,
            evaluation_type="offline focused bundle replay; no live or qualitative score",
            replay_error="Saved bundle integrity or complete validation failed; later checks were not promoted to passed.")
        return report
    report = evaluate_output(validated.output.model_dump(mode="json"), validated.evidence)
    # load_saved_briefing already strictly reproduces every assembly stage.
    report.update(parsing_passed=True, bundle_integrity_and_replay_passed=True,
        evaluation_type="offline focused bundle replay; no live or qualitative score",
        contract=validated.contract, transport="gemini_flat_json",
        transport_schema_passed=True, compact_schema_passed=True,
        deterministic_assembly_reproduced=True,
        original_model=validated.model, original_usage=dict(validated.usage),
        original_sdk_validation_latency_seconds=validated.latency_seconds,
        observed_financial_ids=list(validated.financial_observations),
        historical_run_notice="Model, tokens and latency describe the saved original request, not this offline replay.")
    return report


def render_evaluation(report: dict) -> str:
    """Readable findings that keep mechanical counts separate from judgement."""
    rows = ["# Offline research quality evaluation", "",
        "This is a replay of saved output, not a new live model test. Rejected content was not repaired.", "",
        f"- JSON parsing passed: {report.get('parsing_passed', 'already decoded input') if report.get('parsing_passed', True) is not None else 'not established'}",
        f"- Whole Pydantic schema passed: {report['schema_passed'] if report['schema_passed'] is not None else 'not established'}",
        f"- Complete local validation passed: {report['complete_local_validation_passed']}",
        f"- Source fingerprint: {report['source_fingerprint']}", "", "## Mechanical findings", ""]
    if "bundle_integrity_and_replay_passed" in report:
        rows.extend([f"- Bundle integrity and complete replay passed: {report['bundle_integrity_and_replay_passed']}.",
            f"- Native transport / compact schema / deterministic assembly: {report.get('transport_schema_passed', 'not established')} / {report.get('compact_schema_passed', 'not established')} / {report.get('deterministic_assembly_reproduced', 'not established')}."])
        if report.get("replay_error"):
            rows.append("- " + report["replay_error"])
        if report.get("historical_run_notice"):
            rows.append("- " + report["historical_run_notice"])
    for error in report["schema_issues"]:
        rows.append(f"- Schema: `{error['path']}` — `{error['type']}`.")
    counts = report["mechanical_counts"]
    rows.extend([f"- Financial citations matched: {counts['financial_citations_matched']}/{counts['financial_citations_checked']}.",
        f"- Verbatim quotations matched: {counts['passage_quotes_matched']}/{counts['passage_quotes_checked']}.",
        "- Matching quotations are not a citation-relevance verdict.", ""])
    for row in report["claims"]:
        rows.append(f"- `{row['path']}`: {row['status']}.")
        for issue in row["issues"]:
            rows.append(f"  - {issue}")
        for flag in row["review_flags"]:
            rows.append(f"  - Review: {flag}")
    rows.extend(["", "## Review rubric — no automatic qualitative score", ""])
    for dimension in report["qualitative_assessments"]:
        rows.extend([f"**{dimension['dimension'].replace('_', ' ').title()}** ({dimension['method']}; not assessed)",
                     "", dimension["criteria"], ""])
        for level, anchor in dimension["manual_levels"].items():
            rows.append(f"- {level}: {anchor}")
        rows.append("")
    rows.extend(["## Limits", "", *[f"- {text}" for text in report["limitations"]], ""])
    return "\n".join(rows)
