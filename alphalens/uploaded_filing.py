"""Inspect unverified uploaded text locally; never create SEC or AI evidence.

The small search is exact query-word overlap over bounded contiguous chunks.
It is neither TF-IDF nor model retrieval. Original bytes are identified by their
SHA-256; displayed offsets refer to normalized visible uploaded text.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

from .filings import _visible_document, extract_filing_excerpts


MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_QUERY_CHARS = 150
PASSAGE_CHARS = 1800
MAX_PASSAGES = 6
SEARCH_METHOD = "local_exact_query_word_overlap_v1"
_EXTENSIONS = {"txt", "html", "htm"}
_BINARY_SIGNATURES = (b"%PDF-", b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff",
    b"GIF87a", b"GIF89a", b"PK\x03\x04", b"\x1f\x8b")


def _words(value: str) -> set[str]:
    return set(re.findall(r"[^\W_]+", value.casefold(), flags=re.UNICODE))


def _chunks(text: str):
    start, index = 0, 0
    while start < len(text):
        end = min(start + PASSAGE_CHARS, len(text))
        if end < len(text):
            boundary = text.rfind(" ", start + PASSAGE_CHARS // 2, end)
            if boundary > start:
                end = boundary + 1
        yield index, start, end, text[start:end]
        index += 1
        start = end


def inspect_uploaded_filing(content: bytes, filename: str,
                            query: str = "cash flow capital expenditure liquidity risk") -> dict:
    """Return bounded, serializable inspection results without network access.

    No issuer, SEC URL, accession, reporting period or authenticated-source
    status is inferred from either the filename or the supplied content.
    Plain-text headings are not promoted to verified filing section boundaries.
    """
    if not isinstance(content, bytes):
        raise ValueError("Upload content must be bytes from a UTF-8 text or HTML file.")
    if not content or len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("Choose a nonempty file no larger than five MiB.")
    if not isinstance(filename, str):
        raise ValueError("Choose a named .txt, .html or .htm file.")
    name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    if not name or len(name) > 255 or any(unicodedata.category(char) == "Cc" for char in name):
        raise ValueError("Choose a valid filename without control characters.")
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if extension not in _EXTENSIONS:
        raise ValueError("Only UTF-8 .txt, .html and .htm uploads are supported.")
    if not isinstance(query, str) or not query.strip() or len(query) > MAX_QUERY_CHARS:
        raise ValueError("Enter a search query of one to one hundred and fifty characters.")
    terms = _words(query)
    if not terms:
        raise ValueError("The search query must contain at least one word or number.")
    if content.startswith(_BINARY_SIGNATURES):
        raise ValueError("Binary documents are unsupported; upload UTF-8 text or HTML.")
    try:
        decoded = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("The uploaded file must use UTF-8 encoding.") from None
    if any(unicodedata.category(char) == "Cc" and char not in "\r\n\t\f" for char in decoded):
        raise ValueError("The uploaded file contains binary or unsupported control characters.")

    if extension in {"html", "htm"}:
        visible = _visible_document(decoded)[0]
        excerpts = extract_filing_excerpts(decoded)
        sections = [{"item": row.item, "title": row.title, "text": row.text,
                     "reason": row.reason, "truncated": row.truncated} for row in excerpts.values()]
    else:
        visible = re.sub(r"\s+", " ", decoded).strip()
        sections = [{"item": item, "title": title, "text": "",
            "reason": "N/A — Item boundaries are not verified in uploaded plain text; use the local passage search.",
            "truncated": False} for item, title in
            (("1A", "Risk factors"), ("7", "Management's discussion and analysis"))]
    if not visible.strip():
        raise ValueError("The uploaded file contains no visible text after local extraction.")

    digest = hashlib.sha256(content).hexdigest()
    ranked = []
    for index, start, end, text in _chunks(visible):
        score = len(terms & _words(text))
        if score:
            ranked.append({"source_id": f"uploaded:{digest[:16]}:{index}", "text": text,
                "offset_start": start, "offset_end": end, "score": score})
    ranked.sort(key=lambda row: (-row["score"], row["offset_start"]))
    limitations = [
        "User-supplied unverified content: authenticity, issuer, filing period and SEC origin are not established.",
        "Local keyword-overlap search, not TF-IDF, semantic retrieval, investment analysis or source verification.",
        "Offsets refer to normalized visible uploaded text; SHA-256 identifies the original uploaded bytes.",
        "Passages are bounded chunks and may cut sentences or tables; they are not complete disclosures.",
    ]
    if any(row["reason"] for row in sections):
        limitations.append("Some Item section boundaries are unavailable; search passages remain unverified uploaded content.")
    if any(row["truncated"] for row in sections):
        limitations.append("Identified Item excerpts are truncated; inspect the complete original file for context.")
    if not ranked:
        limitations.append("No query-word matches were found. No replacement or example passages were generated.")
    return {"file_name": name, "sha256": digest, "origin": "user_supplied_unverified",
        "verification_note": "Local inspection only. This reader does not authenticate the document, establish SEC provenance, or send uploaded content to AI or a network service.",
        "character_count": len(visible), "sections": sections, "passages": ranked[:MAX_PASSAGES],
        "limitations": limitations, "search_method": SEARCH_METHOD}
