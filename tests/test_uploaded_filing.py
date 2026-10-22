"""Unverified manual fallback inspection; never SEC/AI evidence creation."""
import hashlib
import json
import re

import pytest

from alphalens.filings import _visible_document
from alphalens.uploaded_filing import (MAX_PASSAGES, MAX_UPLOAD_BYTES, PASSAGE_CHARS,
    inspect_uploaded_filing)


def test_text_results_have_exact_offsets_hash_and_no_invented_filing_identity(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Manual file inspection attempted network, credentials or inference")
    monkeypatch.setattr("requests.Session.request", forbidden)
    monkeypatch.setattr("httpx.Client.send", forbidden)
    monkeypatch.setattr("alphalens.providers.read_ai_config", forbidden)
    monkeypatch.setattr("openai.OpenAI", forbidden)
    content = ("Cash flow remains a research question.\r\n" + "filler " * 310
        + "Capital expenditure and liquidity risk require analysis.\t" + "detail " * 310).encode()
    visible = re.sub(r"\s+", " ", content.decode()).strip()
    result = inspect_uploaded_filing(content, r"C:\private\uploaded-report.TXT", "cash flow capital expenditure")
    assert result["file_name"] == "uploaded-report.TXT"
    assert result["sha256"] == hashlib.sha256(content).hexdigest()
    assert result["character_count"] == len(visible)
    assert result["origin"] == "user_supplied_unverified"
    assert "not authenticate" in result["verification_note"]
    assert {"issuer", "cik", "accession", "url", "report_date", "verified"}.isdisjoint(result)
    assert result["passages"] and len(result["passages"]) <= MAX_PASSAGES
    for passage in result["passages"]:
        assert passage["text"] == visible[passage["offset_start"]:passage["offset_end"]]
        assert len(passage["text"]) <= PASSAGE_CHARS
        assert passage["source_id"].startswith("uploaded:" + result["sha256"][:16] + ":")
        assert passage["score"] > 0
        assert {"cik", "accession", "url", "report_date", "verified"}.isdisjoint(passage)
    assert all(not row["text"] and row["reason"].startswith("N/A") for row in result["sections"])
    json.dumps(result, allow_nan=False)


def test_html_uses_visible_text_and_preserves_conservative_section_extraction():
    html = ("<html><head><style>hidden-secret{}</style><script>secret_cash_flow();</script></head><body>"
        "<p hidden>HIDDEN SECRET revenue</p><ix:header>HIDDEN METADATA</ix:header>"
        "<div style='display:none'>invisible liquidity</div><!-- hidden comment -->"
        "<h2>Item 1A. Risk Factors</h2><p>" + "Visible risk disclosure. " * 20 + "</p>"
        "<h2>Item 1B. Unresolved Staff Comments</h2>"
        "<h2>Item 7. Management's Discussion and Analysis</h2><p>" + "Cash flow and capital expenditure discussion. " * 20 + "</p>"
        "<h2>Item 7A. Quantitative and Qualitative Disclosures About Market Risk</h2></body></html>")
    result = inspect_uploaded_filing(html.encode(), "report.html", "cash flow risk")
    visible = _visible_document(html)[0]
    assert all(row["text"] and not row["reason"] for row in result["sections"])
    output = json.dumps(result)
    assert all(word not in output for word in ("secret_cash_flow", "HIDDEN SECRET", "HIDDEN METADATA", "invisible liquidity", "hidden comment"))
    for passage in result["passages"]:
        assert passage["text"] == visible[passage["offset_start"]:passage["offset_end"]]
    assert result["origin"] == "user_supplied_unverified"


def test_plain_text_markup_is_data_not_rendered_or_assigned_a_section():
    content = b"<script>displayed literal text</script> cash flow analysis"
    result = inspect_uploaded_filing(content, "notes.txt", "cash")
    assert "<script>" in result["passages"][0]["text"]
    assert all(section["reason"].startswith("N/A") for section in result["sections"])


def test_absent_html_headings_and_absent_search_terms_do_not_generate_examples():
    result = inspect_uploaded_filing(b"<p>Unverified customer discussion.</p>", "notes.htm", "liquidity")
    assert result["passages"] == []
    assert any("No query-word matches" in warning for warning in result["limitations"])
    assert all(section["text"] == "" and section["reason"].startswith("N/A") for section in result["sections"])


def test_search_ranks_overlap_limits_passages_and_uses_stable_source_offsets():
    content = (("cash filler " * 160 + " cash flow liquidity risk " + "detail " * 190) * 10).encode()
    result = inspect_uploaded_filing(content, "notes.txt", "cash flow liquidity risk")
    repeated = inspect_uploaded_filing(content, "different-name.txt", "cash flow liquidity risk")
    assert len(result["passages"]) == MAX_PASSAGES
    assert result["passages"] == repeated["passages"]
    ranks = [(-row["score"], row["offset_start"]) for row in result["passages"]]
    assert ranks == sorted(ranks)
    changed = inspect_uploaded_filing(content + b" changed", "notes.txt", "cash flow liquidity risk")
    assert changed["sha256"] != result["sha256"]
    assert changed["passages"][0]["source_id"] != result["passages"][0]["source_id"]


@pytest.mark.parametrize("content,filename", [
    (b"", "empty.txt"), (b" \n\t", "empty.txt"),
    (b"<html><script>cash flow</script><div hidden>risk</div></html>", "empty.html"),
    (b"\xff\xfe\x00\x00", "utf16.txt"), (b"valid text\x00binary", "binary.txt"),
    (b"%PDF-1.7 fake text", "renamed.txt"), (b"GIF89a", "renamed.txt"),
    (b"Cash flow", "report.pdf"), (b"Cash flow", "report"),
    (b"Cash flow", "bad\nname.txt"), ("Cash flow", "notes.txt"),
])
def test_empty_binary_bad_encoding_and_unsupported_uploads_fail_safely(content, filename):
    with pytest.raises(ValueError):
        inspect_uploaded_filing(content, filename)


def test_upload_size_is_rejected_before_parsing_or_search():
    with pytest.raises(ValueError, match="five MiB"):
        inspect_uploaded_filing(b"x" * (MAX_UPLOAD_BYTES + 1), "huge.txt")


def test_utf8_bom_and_unicode_text_are_accepted_without_inventing_identity():
    content = "\ufeffCash flow — dépenses d’investissement, résumé.".encode("utf-8")
    result = inspect_uploaded_filing(content, "résumé.txt", "dépenses")
    assert result["passages"][0]["text"].startswith("Cash flow")
    assert "dépenses" in result["passages"][0]["text"]
    assert result["sha256"] == hashlib.sha256(content).hexdigest()


@pytest.mark.parametrize("query", ["", "   ", "!!!", "x" * 151, None])
def test_invalid_queries_fail_before_search(query):
    with pytest.raises(ValueError):
        inspect_uploaded_filing(b"Cash flow and risk.", "notes.txt", query)
