"""Revalidate a fixed saved live briefing without credentials or network calls.

The manifest detects accidental changes to the demonstration bundle. It is a
local integrity record, not a signature, new SEC retrieval or fresh AI request.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
from pathlib import Path
import re

from .ai import ValidatedResearch
from .focused_briefing import (
    BriefingContext, FocusedBriefingInterpretation, _fingerprint,
    assemble_briefing, assembly_fingerprint,
)
from .gemini_briefing import GeminiBriefingFields
from .research_exports import export_research_json

ROOT = Path(__file__).resolve().parents[1]
_BUNDLE = Path("outputs/msft_findings_live_2026-10-18")
_FILES = (
    "SOURCE_CATALOG.json", "FINANCIAL_ANALYSIS.json", "FINANCIAL_OBSERVATIONS.json",
    "FOCUSED_CONTEXT.json", "TRANSPORT_OUTPUT.json", "ASSEMBLED_REPORT.json",
    "VALIDATION.json", "REQUEST_LEDGER.json", "RESEARCH_BRIEFING.json",
)
_MAX_FILE_BYTES = 5 * 1024 * 1024
_SAVED_NOTICE = (
    "SAVED LIVE DEMONSTRATION — replay of the approved Microsoft Gemini response and SEC "
    "snapshot from October 2026. Local checks were rerun; no fresh SEC retrieval or AI "
    "request was made. Qualitative investment judgments still require analyst review."
)


def available_saved_briefing(directory=None) -> bool:
    """Whether the complete fixed bundle exists; loading performs validation."""
    directory = Path(directory) if directory is not None else ROOT / _BUNDLE
    return all((directory / name).is_file() for name in (*_FILES, "DEMO_MANIFEST.json"))


def saved_briefing_identity(directory=None) -> str | None:
    """Invalidate a displayed replay if its selected bundle or manifest changes.

    This identity is not acceptance: load_saved_briefing still checks every
    fixed-file hash and the complete research contract before any display.
    """
    try:
        directory = Path(directory) if directory is not None else ROOT / _BUNDLE
        return hashlib.sha256(str(directory.resolve()).encode("utf-8") + b"\0"
                              + _read(directory / "DEMO_MANIFEST.json")).hexdigest()
    except (OSError, ValueError):
        return None


def _read(path: Path) -> bytes:
    if path.stat().st_size > _MAX_FILE_BYTES:
        raise ValueError("Saved briefing contains an oversized file.")
    content = path.read_bytes()
    if len(content) > _MAX_FILE_BYTES:
        raise ValueError("Saved briefing contains an oversized file.")
    return content


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Saved briefing contains duplicate JSON fields.")
        result[key] = value
    return result


def _json(content: bytes) -> dict:
    def nonfinite(_):
        raise ValueError("Saved briefing contains a non-finite number.")
    value = json.loads(content.decode("utf-8"), object_pairs_hook=_object, parse_constant=nonfinite)
    if not isinstance(value, dict):
        raise ValueError("Saved briefing requires JSON objects.")
    return value


def _ledger(ledger: dict, metadata: dict) -> None:
    model = ledger.get("requested_model")
    if (ledger.get("provider") != "gemini" or metadata.get("provider") != "gemini"
            or not isinstance(model, str) or re.fullmatch(r"gemini-[A-Za-z0-9._-]{1,100}", model) is None
            or ledger.get("reported_model") != model or metadata.get("model") != model
            or type(ledger.get("http_status")) is not int or ledger["http_status"] != 200
            or any(type(ledger.get(key)) is not int or ledger[key] != 1 for key in
                   ("maximum_http_requests", "http_requests_attempted"))
            or any(ledger.get(key) is not False for key in
                   ("automatic_retries", "provider_fallback", "billing_changes"))
            or ledger.get("finish_reasons") != ["stop"]
            or type(ledger.get("unsupported_claims")) is not int or ledger["unsupported_claims"] != 0
            or ledger.get("status") not in {"mechanically_validated_awaiting_analyst_review", "analyst_review_complete"}):
        raise ValueError("Saved briefing request ledger does not describe an accepted single Gemini request.")
    usage = ledger.get("normalized_usage")
    if (not isinstance(usage, dict) or set(usage) != {"input_tokens", "output_tokens", "total_tokens"}
            or any(type(value) is not int or value < 0 for value in usage.values())
            or usage["total_tokens"] != usage["input_tokens"] + usage["output_tokens"]
            or metadata.get("usage") != usage
            or ledger.get("reported_usage") != {"prompt_tokens": usage["input_tokens"],
                "completion_tokens": usage["output_tokens"], "total_tokens": usage["total_tokens"]}):
        raise ValueError("Saved briefing token metadata is inconsistent.")
    latency = ledger.get("adapter_latency_seconds")
    if (isinstance(latency, bool) or not isinstance(latency, (int, float))
            or not math.isfinite(latency) or latency < 0 or metadata.get("latency_seconds") != latency):
        raise ValueError("Saved briefing latency metadata is inconsistent.")
    if metadata.get("contract") not in {"focused_v2", "focused_v3"} or metadata.get("response_transport") != "gemini_flat_json":
        raise ValueError("Saved briefing uses an unsupported research contract.")


def load_saved_briefing(directory=None) -> ValidatedResearch:
    """Load, reassemble and recheck the approved result; never repair a draft.

    Only fixed filenames are read. Errors expose neither file contents nor
    user paths. This function does not write audit records or make requests.
    """
    try:
        directory = Path(directory) if directory is not None else ROOT / _BUNDLE
        manifest = _json(_read(directory / "DEMO_MANIFEST.json"))
        hashes = manifest.get("files")
        if not isinstance(hashes, dict) or set(hashes) != set(_FILES):
            raise ValueError("Saved briefing manifest does not match the fixed demonstration files.")
        files = {}
        for name in _FILES:
            content = _read(directory / name)
            digest = hashes[name]
            if (not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                    or not hmac.compare_digest(digest, hashlib.sha256(content).hexdigest())):
                raise ValueError("Saved briefing integrity verification failed; no report was loaded.")
            files[name] = _json(content)
        book, analysis, observations, packet = (files[name] for name in
            ("SOURCE_CATALOG.json", "FINANCIAL_ANALYSIS.json", "FINANCIAL_OBSERVATIONS.json", "FOCUSED_CONTEXT.json"))
        exported, ledger = files["RESEARCH_BRIEFING.json"], files["REQUEST_LEDGER.json"]
        metadata = exported["metadata"]
        _ledger(ledger, metadata)
        if (packet["company"]["ticker"] != "MSFT" or packet["company"]["cik"] != "0000789019"
                or packet["mode"] != "live" or analysis["mode"] != "live"
                or analysis["ticker"] != "MSFT"):
            raise ValueError("Saved briefing is not the expected live Microsoft snapshot.")
        full_observations = {row["id"]: row for row in analysis["tensions"]}
        if any(full_observations.get(key) != value for key, value in observations.items()):
            raise ValueError("Saved briefing financial observations are inconsistent.")
        context = BriefingContext(book, analysis, observations, packet,
            _fingerprint(book, analysis, observations, packet))
        contract = metadata["contract"]
        if contract == "focused_v2":
            transport = GeminiBriefingFields.model_validate(files["TRANSPORT_OUTPUT.json"])
            interpretation = FocusedBriefingInterpretation.model_validate(transport.compact_payload())
        else:
            from .gemini_briefing import GeminiFindingFields
            from .focused_briefing import FindingInterpretations
            transport = GeminiFindingFields.model_validate(files["TRANSPORT_OUTPUT.json"])
            interpretation = FindingInterpretations.model_validate(transport.compact_payload())
        report, verification = assemble_briefing(interpretation, context)
        if (verification.unsupported_count or report.model_dump(mode="json") != files["ASSEMBLED_REPORT.json"]
                or verification.model_dump(mode="json") != files["VALIDATION.json"]):
            raise ValueError("Saved briefing no longer passes its original report and source checks.")
        warnings = exported["warnings"]
        if not isinstance(warnings, list) or any(not isinstance(value, str) for value in warnings):
            raise ValueError("Saved briefing warnings are invalid.")
        validated = ValidatedResearch(output=report, verification=verification, evidence=book,
            model=ledger["requested_model"], warnings=list(warnings), provider="gemini",
            usage=ledger["normalized_usage"], latency_seconds=ledger["adapter_latency_seconds"],
            analysis=analysis, diagnostics=metadata["diagnostics"],
            model_interpretation=interpretation.model_dump(mode="json"), financial_observations=observations,
            contract=contract, transport_output=transport.model_dump(mode="json"))
        validated.assembly_fingerprint = assembly_fingerprint(validated)
        # Re-export all fields, including metadata and sections: a changed saved
        # export must not inherit the new local validation of a different object.
        if json.loads(export_research_json(validated)) != exported:
            raise ValueError("Saved briefing export is inconsistent with its revalidated sources and report.")
        validated.warnings.append(_SAVED_NOTICE)
        return validated
    except Exception:
        # Pydantic errors can contain model text, while filesystem errors expose
        # user paths. Keep the UI error stable and preserve original files.
        raise ValueError("The saved Microsoft briefing could not be revalidated. Check the original demonstration bundle; no API request was made.") from None
