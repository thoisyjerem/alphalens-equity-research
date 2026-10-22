"""Small local audit records for optional AI attempts, without model text.

This deliberately records a fixed subset of metadata. It does not persist API
keys, request headers, prompts, hypotheses, provider responses or arbitrary error
messages. A failed audit write must never break the SEC dashboard or research.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from itertools import islice
import json
import math
from pathlib import Path
import re
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
_STATES = frozenset({"not_run", "passed", "failed", "partial"})
_STATUS = frozenset({"completed", "rejected", "request_error", "incomplete", "validation_failed"})
_OPERATIONS = frozenset({"structured_response", "ai_commentary", "research_briefing", "thesis_challenge"})
_STAGES = frozenset({"provider_response", "envelope", "inner_json", "output_schema", "financial_sources", "native_output", "native_json"})
_ERROR_TYPES = frozenset({"missing", "extra_forbidden", "literal_error", "json_invalid", "string_type",
    "string_too_short", "string_too_long", "list_type", "dict_type", "too_short", "too_long",
    "float_type", "int_type", "int_parsing", "float_parsing", "value_error", "model_type",
    "model_attributes_type", "finite_number", "none_required", "bool_type", "is_instance_of",
    "union_tag_invalid", "validation_error", "numerical_prose"})
_FIELDS = frozenset({"performance", "business_developments", "investment_considerations", "risks",
    "executive_summary", "what_matters_most", "capital_allocation",
    "missing_information", "assumptions", "supporting_evidence", "contradictory_evidence",
    "invalidation_conditions", "text", "kind", "financial_citations", "passage_citations",
    "source_id", "value", "unit", "fiscal_year", "period_start", "period_end", "quote",
    "observations", "evidence_ids", "questions", "caveats", "result_json",
    "executive_interpretation", "findings", "observation_ids", "interpretation",
    "supporting_passage_ids", "alternative_explanation", "limitations", "unanswered_questions", "primary_finding",
    "executive_observation_id", "executive_passage_ids", "primary_interpretation", "primary_passage_ids",
    "primary_alternative_explanation", "primary_limitations", "additional_observation_id", "additional_interpretation",
    "additional_passage_ids", "additional_alternative_explanation", "additional_limitations",
    "risk_interpretation", "risk_passage_ids", "risk_limitations"})
_WARNING_CODES = frozenset({"unsupported_claims_quarantined", "missing_evidence", "offline_snapshot",
    "semantic_review_required", "incomplete_sections", "audit_truncated"})
_SOURCE_ID = re.compile(r"(?:[0-9]{4}:(?:analytics\.)?[a-z_]{1,90}|sec:[a-f0-9]{24})\Z")


def _allowed(value, choices: frozenset, default: str) -> str:
    return value if isinstance(value, str) and value in choices else default


def _number(value, *, maximum: float = 10_000_000_000):
    if type(value) is int and 0 <= value <= maximum:
        return value
    if type(value) is float and math.isfinite(value) and 0 <= value <= maximum:
        return value
    return None


def _timestamp(value) -> str:
    if isinstance(value, str) and len(value) <= 40:
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is not None:
                return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            pass
    return datetime.now(timezone.utc).isoformat()


def _model(value, provider: str) -> str:
    """Keep known provider model namespaces, not arbitrary configured strings."""
    if not isinstance(value, str) or len(value) > 120 or "sk-" in value or "AIza" in value:
        return "[redacted model identifier]"
    pattern = (r"(?:models/)?gemini-[a-z0-9][a-z0-9._-]{0,100}" if provider == "gemini"
               else r"(?:gpt-[a-z0-9][a-z0-9._-]{0,100}|o[134](?:-[a-z0-9._-]{1,100})?|chatgpt-[a-z0-9._-]{1,100})")
    return value if re.fullmatch(pattern, value) else "[redacted model identifier]"


def _issue_path(value) -> str:
    if not isinstance(value, str) or len(value) > 700:
        return "$"
    if value == "$":
        return value
    parts = value.split(".")[:8]
    safe = []
    for part in parts:
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)(\[[0-9]{1,6}\])?", part)
        if match and match.group(1) in _FIELDS:
            safe.append(match.group(1) + (match.group(2) or ""))
        else:
            safe.append("[unrecognized_field]")
    return ".".join(safe) or "$"


def _audit_record(diagnostics: dict, evidence_ids: Iterable[str], source_fingerprint: str) -> dict:
    """Create a JSON-safe record from fixed whitelists; not a general logger."""
    data = diagnostics if isinstance(diagnostics, dict) else {}
    provider = _allowed(data.get("provider"), frozenset({"gemini", "openai"}), "unknown")
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    numeric_usage = {name: usage[name] for name in ("input_tokens", "output_tokens", "total_tokens")
                     if type(usage.get(name)) is int and _number(usage[name]) is not None}
    ids = []
    if not isinstance(evidence_ids, (str, bytes)):
        try:
            ids = sorted({value for value in islice(evidence_ids, 1000)
                          if isinstance(value, str) and _SOURCE_ID.fullmatch(value)})
        except (TypeError, ValueError):
            ids = []
    raw_issues = data.get("validation_issues")
    safe_issues = []
    if isinstance(raw_issues, list):
        for issue in raw_issues[:12]:
            if isinstance(issue, dict):
                safe_issues.append({"path": _issue_path(issue.get("path")),
                    "type": _allowed(issue.get("type"), _ERROR_TYPES, "validation_error")})
    warnings = data.get("warning_codes", [])
    safe_warnings = (sorted({value for value in warnings if isinstance(value, str) and value in _WARNING_CODES})
                     if isinstance(warnings, list) else [])
    record = {"audit_version": 1, "timestamp_utc": _timestamp(data.get("timestamp_utc")),
        "provider": provider, "model": _model(data.get("model"), provider),
        "operation": _allowed(data.get("operation"), _OPERATIONS, "structured_response"),
        "status": _allowed(data.get("status"), _STATUS, "incomplete"),
        "http_status": data["http_status"] if type(data.get("http_status")) is int and 100 <= data["http_status"] <= 599 else None,
        "latency_seconds": _number(data.get("latency_seconds"), maximum=86400), "usage": numeric_usage,
        "parsing_result": _allowed(data.get("parsing_result"), _STATES, "not_run"),
        "schema_validation_result": _allowed(data.get("schema_validation_result"), _STATES, "not_run"),
        "numerical_validation_result": _allowed(data.get("numerical_validation_result"), _STATES, "not_run"),
        "source_validation_result": _allowed(data.get("source_validation_result"), _STATES, "not_run"),
        "validation_stage": _allowed(data.get("validation_stage"), _STAGES, "provider_response"),
        "validation_issues": safe_issues,
        "issues_truncated": data.get("issues_truncated") is True or isinstance(raw_issues, list) and len(raw_issues) > 12,
        "input_evidence_ids": ids[:300], "evidence_ids_truncated": len(ids) > 300,
        "source_fingerprint": source_fingerprint if isinstance(source_fingerprint, str)
            and re.fullmatch(r"[a-f0-9]{64}", source_fingerprint) else None,
        "warning_codes": safe_warnings}
    # Only the single documented metadata repair can enter persisted audits.
    paths = data.get("local_repair_paths")
    if (isinstance(paths, list) and len(paths) == 1 and isinstance(paths[0], str)
            and re.fullmatch(r"missing_information\[[0-4]\]\.kind", paths[0])):
        record["local_repair_paths"] = list(paths)
    return record


def record_attempt(diagnostics: dict, evidence_ids: Iterable[str], source_fingerprint: str,
                   *, directory: str | Path | None = None) -> Path | None:
    """Write one bounded local record, returning its path or None on failure.

    Records contain metadata only. They do not claim that valid IDs establish
    semantic support or that schema validation establishes investment merit.
    Caller-owned financial and source checks must set their explicit states.
    """
    path = None
    created = False
    try:
        record = _audit_record(diagnostics, evidence_ids, source_fingerprint)
        target = Path(directory) if directory is not None else ROOT / ".cache" / "ai_runs"
        target.mkdir(parents=True, exist_ok=True)
        path = target / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}_{uuid4().hex}.json"
        with path.open("x", encoding="utf-8") as handle:
            created = True
            json.dump(record, handle, ensure_ascii=True, allow_nan=False, indent=2)
            handle.write("\n")
        return path
    except Exception:
        # Optional observability must not replace a successful report with an
        # IO error, or print an exception containing a private filesystem path.
        if created and path is not None:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        return None
