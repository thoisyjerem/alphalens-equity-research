"""Build an auditable, issuer-bound source packet for optional AI research.

This module performs no retrieval and never turns model text into evidence.
Financial inputs come from the annual extraction pipeline; narrative inputs
must identify an annual filing already present in that issuer's filing library.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import date
import hashlib
import json
import math
import re
from urllib.parse import urlsplit

from .filings import FilingExcerpt
from .models import ResearchResult


class EvidenceError(ValueError):
    """The source packet cannot be safely bound to the selected research."""


_INSTANT_METRICS = {"cash_and_equivalents", "total_debt", "net_debt"}
_MAX_PASSAGE_CHARS = 1800


def _cik(value: object) -> str:
    if not re.fullmatch(r"\d{1,10}", str(value)):
        raise EvidenceError("Evidence has an invalid SEC company identifier.")
    return str(int(str(value))).zfill(10)


def _valid_date(value: object) -> bool:
    try:
        return date.fromisoformat(str(value)).isoformat() == value
    except (ValueError, TypeError):
        return False


def _sec_url(url: object, cik: str, accession: str) -> bool:
    if not isinstance(url, str):
        return False
    parsed = urlsplit(url)
    prefix = f"/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/"
    return (parsed.scheme == "https" and parsed.netloc == "www.sec.gov"
            and parsed.path.startswith(prefix) and len(parsed.path) > len(prefix)
            and not parsed.query and not parsed.fragment
            and "/../" not in parsed.path and "%" not in parsed.path)


def _financial_entry(result, period, key, metric):
    # A missing value, even with conflicting source rows, is never AI evidence.
    if metric.value is None or not metric.sources:
        return None
    if (isinstance(metric.value, bool) or not isinstance(metric.value, (int, float))
            or not math.isfinite(metric.value)):
        raise EvidenceError("Financial evidence contains a non-finite or invalid value.")
    instant = key in _INSTANT_METRICS
    for source in metric.sources:
        if (source.end != period.end or source.start != (None if instant else period.start)
                or source.form not in {"10-K", "10-K/A"}
                or not re.fullmatch(r"\d{10}-\d{2}-\d{6}", source.accession)
                or not _sec_url(source.url, _cik(result.cik), source.accession)
                or not _valid_date(source.filed)
                or isinstance(source.value, bool)
                or not isinstance(source.value, (int, float))
                or not math.isfinite(source.value)):
            raise EvidenceError("Financial source metadata disagrees with the selected annual period or issuer.")
    return {
        "kind": "financial", "value": metric.value, "unit": metric.unit,
        "fiscal_year": period.fiscal_year, "period_start": None if instant else period.start,
        "period_end": period.end, "metric": key,
        "sources": [asdict(source) for source in metric.sources],
        "ticker": result.ticker, "cik": _cik(result.cik), "mode": result.mode,
        "retrieved_at": result.retrieved_at,
    }


def _chunks(text: str):
    """Contiguous bounded chunks; offsets refer exactly to the retrieved excerpt."""
    start = 0
    while start < len(text):
        end = min(start + _MAX_PASSAGE_CHARS, len(text))
        # Prefer a whitespace boundary but do not discard or rewrite characters.
        if end < len(text):
            boundary = text.rfind(" ", start + _MAX_PASSAGE_CHARS // 2, end)
            if boundary > start:
                end = boundary + 1
        yield start, end, text[start:end]
        start = end


def _passage_entries(result: ResearchResult, context: dict):
    if not isinstance(context, dict):
        raise EvidenceError("A filing evidence context must be a mapping.")
    required = {"ticker", "cik", "accession", "url", "report_date", "filing_date", "retrieved_at", "mode", "excerpts"}
    if not required.issubset(context):
        raise EvidenceError("Filing evidence lacks required source or retrieval metadata.")
    cik = _cik(result.cik)
    if (context["ticker"] != result.ticker or _cik(context["cik"]) != cik
            or context["mode"] != result.mode):
        raise EvidenceError("Filing evidence issuer or live/offline mode disagrees with the selected research.")
    matches = [f for f in result.filings if f.get("accession") == context["accession"]]
    if not matches:
        raise EvidenceError("Filing evidence accession is absent from this issuer's annual filing library.")
    if not any(all(f.get(key) == context[key] for key in ("url", "report_date", "filing_date"))
               and f.get("form") in {"10-K", "10-K/A"} for f in matches):
        raise EvidenceError("Filing evidence metadata differs from the selected issuer's annual filing library.")
    timestamp_known = isinstance(context["retrieved_at"], str) and bool(context["retrieved_at"].strip())
    missing_timestamp_disclosed = (context["retrieved_at"] is None
                                   and isinstance(context.get("retrieval_note"), str)
                                   and bool(context["retrieval_note"].strip()))
    if (not re.fullmatch(r"\d{10}-\d{2}-\d{6}", str(context["accession"]))
            or not _sec_url(context["url"], cik, context["accession"])
            or not _valid_date(context["report_date"]) or not _valid_date(context["filing_date"])
            or not (timestamp_known or missing_timestamp_disclosed)):
        raise EvidenceError("Filing evidence has invalid SEC source or retrieval metadata.")
    if context.get("document_sha256") is not None and not re.fullmatch(r"[a-f0-9]{64}", str(context["document_sha256"])):
        raise EvidenceError("Filing document fingerprint is invalid.")
    excerpts = context["excerpts"]
    if not isinstance(excerpts, dict):
        raise EvidenceError("Filing excerpts must be a mapping of extracted sections.")
    focused = context.get("focused_passages")
    if focused is not None:
        from .retrieval import RetrievedPassage
        if not isinstance(focused, list) or len(focused) > 64:
            raise EvidenceError("Focused filing passages must be a bounded list of local retrieval records.")
        for passage in focused:
            if (not isinstance(passage, RetrievedPassage) or passage.item not in {"1A", "7"}
                    or not 24 <= len(passage.text) <= _MAX_PASSAGE_CHARS
                    or type(passage.section_start) is not int or type(passage.section_end) is not int
                    or type(passage.original_chars) is not int
                    or not 0 <= passage.section_start < passage.section_end <= passage.original_chars
                    or passage.section_end - passage.section_start != len(passage.text)
                    or passage.selection_method != "deterministic_topic_windows_v1"):
                raise EvidenceError("Focused passage text, section offsets or retrieval metadata is invalid.")
            entry = {"kind": "passage", "text": passage.text, "item": passage.item,
                "title": passage.title, "ticker": result.ticker, "cik": cik,
                "accession": context["accession"], "url": context["url"],
                "report_date": context["report_date"], "filing_date": context["filing_date"],
                "mode": context["mode"], "retrieved_at": context["retrieved_at"],
                "offset_start": passage.section_start, "offset_end": passage.section_end,
                "offset_basis": "normalized complete Item section",
                "excerpt_truncated": True, "section_truncated": passage.section_truncated,
                "boundary_truncated": passage.boundary_truncated,
                "original_chars": passage.original_chars,
                "selection_method": passage.selection_method, "topics": list(passage.topics)}
            for metadata_key in ("retrieval_note", "document_sha256"):
                if metadata_key in context:
                    entry[metadata_key] = context[metadata_key]
            digest = hashlib.sha256(json.dumps(entry, sort_keys=True, ensure_ascii=False,
                allow_nan=False).encode("utf-8")).hexdigest()
            yield f"sec:{digest[:24]}", entry
        if focused:
            return
    for item, excerpt in sorted(excerpts.items()):
        if not isinstance(excerpt, FilingExcerpt) or excerpt.item != item or item not in {"1A", "7"}:
            raise EvidenceError("Only retrieved, bounded Item 1A and Item 7 excerpts are accepted.")
        if not excerpt.text or excerpt.reason:
            continue
        if excerpt.original_chars < len(excerpt.text):
            raise EvidenceError("Filing excerpt length metadata is inconsistent.")
        for start, end, text in _chunks(excerpt.text):
            entry = {
                "kind": "passage", "text": text, "item": item, "title": excerpt.title,
                "ticker": result.ticker, "cik": cik, "accession": context["accession"],
                "url": context["url"], "report_date": context["report_date"],
                "filing_date": context["filing_date"], "mode": context["mode"],
                "retrieved_at": context["retrieved_at"], "offset_start": start, "offset_end": end,
                "excerpt_truncated": excerpt.truncated, "original_chars": excerpt.original_chars,
            }
            for metadata_key in ("retrieval_note", "document_sha256"):
                if metadata_key in context:
                    entry[metadata_key] = context[metadata_key]
            digest = hashlib.sha256(json.dumps(entry, sort_keys=True, ensure_ascii=False,
                                               allow_nan=False).encode("utf-8")).hexdigest()
            yield f"sec:{digest[:24]}", entry


def build_evidence_book(result: ResearchResult, filing_contexts: list[dict] | None = None) -> dict[str, dict]:
    """Return available annual facts and retrieved passages with source metadata.

    A context is trusted local retrieval output, never model-supplied data. This
    binding checks issuer/library/period metadata; it is not a cryptographic
    proof of the remote SEC document's authenticity.
    """
    book: dict[str, dict] = {}
    if result.mode not in {"live", "offline"}:
        raise EvidenceError("Evidence must retain the explicit live or offline research mode.")
    for period in result.periods:
        if (not _valid_date(period.start) or not _valid_date(period.end)
                or not 350 <= (date.fromisoformat(period.end) - date.fromisoformat(period.start)).days + 1 <= 380
                or isinstance(period.fiscal_year, bool) or not isinstance(period.fiscal_year, int)):
            raise EvidenceError("Financial evidence must describe a completed annual duration, with an explicit fiscal-year label.")
        for key, metric in period.metrics.items():
            entry = _financial_entry(result, period, key, metric)
            if entry is not None:
                source_id = f"{period.fiscal_year}:{key}"
                if source_id in book:
                    raise EvidenceError("Duplicate annual evidence identifier.")
                book[source_id] = entry
    for context in filing_contexts or []:
        for source_id, entry in _passage_entries(result, context):
            book[source_id] = entry
    return book


def evidence_fingerprint(book: dict[str, dict]) -> str:
    """Detect changes in values, periods, passages, issuer, mode or retrieval."""
    return hashlib.sha256(json.dumps(book, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False).encode("utf-8")).hexdigest()


def source_fingerprint(result: ResearchResult, filing_contexts: list[dict] | None = None) -> str:
    return evidence_fingerprint(build_evidence_book(result, filing_contexts))
