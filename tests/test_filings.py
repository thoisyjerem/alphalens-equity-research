"""Synthetic narrative text tests; no financial information is invented."""

from pathlib import Path

import pytest

from alphalens.filings import FilingExcerpt, extract_filing_excerpts


RISK = "Competition and operational disruption may affect the business. " * 8
MDNA = "Management discusses operating results, liquidity and capital resources. " * 8


def document(risk=RISK, mdna=MDNA):
    return f"""<html><body>
      <table><tr><td>Item 1A.</td><td>Risk Factors</td><td>12</td></tr>
        <tr><td>Item 1B.</td><td>Unresolved Staff Comments</td><td>34</td></tr>
        <tr><td>Item 7.</td><td>Management’s Discussion and Analysis</td><td>44</td></tr>
        <tr><td>Item 7A.</td><td>Quantitative and Qualitative Disclosures About Market Risk</td><td>62</td></tr></table>
      <h2>ITEM 1A. RISK FACTORS</h2><p>{risk}</p>
      <h2>ITEM 1B. UNRESOLVED STAFF COMMENTS</h2><p>Not included in risks.</p>
      <h2>ITEM 7. MANAGEMENT’S DISCUSSION AND ANALYSIS OF FINANCIAL CONDITION AND RESULTS OF OPERATIONS</h2><p>{mdna}</p>
      <h2>ITEM 7A. QUANTITATIVE AND QUALITATIVE DISCLOSURES ABOUT MARKET RISK</h2><p>Not included in MD&amp;A.</p>
      </body></html>"""


def test_selects_substantial_body_sections_over_table_of_contents():
    result = extract_filing_excerpts(document())
    assert set(result) == {"1A", "7"}
    assert all(isinstance(section, FilingExcerpt) and not section.reason for section in result.values())
    assert RISK.strip() in result["1A"].text
    assert MDNA.strip() in result["7"].text
    assert "Not included" not in result["1A"].text + result["7"].text
    assert "ITEM 1B" not in result["1A"].text
    assert "ITEM 7A" not in result["7"].text


def test_splits_item_heading_across_spans_and_table_cells():
    markup = document().replace("<h2>ITEM 1A. RISK FACTORS</h2>",
        "<p><span>ITEM</span> <b>1A.</b> <span>RISK FACTORS</span></p>")
    markup = markup.replace("<h2>ITEM 7A. QUANTITATIVE AND QUALITATIVE DISCLOSURES ABOUT MARKET RISK</h2>",
        "<table><tr><td>ITEM 7A.</td><td>QUANTITATIVE AND QUALITATIVE DISCLOSURES ABOUT MARKET RISK</td></tr></table>")
    result = extract_filing_excerpts(markup)
    assert RISK.strip() in result["1A"].text
    assert MDNA.strip() in result["7"].text


def test_actual_sec_inline_word_splits_preserve_heading_and_body_words():
    # The official Microsoft FY2026 filing splits these words between spans.
    markup = document().replace("ITEM 1A. RISK FACTORS", "<span>ITEM 1A. RIS</span><span>K FACTORS</span>")
    markup = markup.replace("ITEM 1B. UNRESOLVED STAFF COMMENTS", "<span>ITEM 1B. UNRESOLVE</span><span>D STAFF COMMENTS</span>")
    markup = markup.replace("ITEM 7A. QUANTITATIVE AND QUALITATIVE DISCLOSURES ABOUT MARKET RISK",
        "<span>ITEM 7A. QUANTITATIVE AND QUALITAT</span><span>IVE DISCLOSURES ABOUT MARKET RISK</span>")
    markup = markup.replace(RISK, "<span>Competi</span><span>tion</span> " + RISK)
    result = extract_filing_excerpts(markup)
    assert "RISK FACTORS" in result["1A"].text
    assert "Competition" in result["1A"].text
    assert not result["1A"].reason and not result["7"].reason


def test_utf8_saved_document_ignores_stale_ascii_xml_declaration():
    markup = "<?xml version='1.0' encoding='ASCII'?>" + document()
    result = extract_filing_excerpts(markup.encode("utf-8"))
    assert "MANAGEMENT’S" in result["7"].text
    assert "�" not in result["7"].text


def test_hidden_metadata_and_executable_content_are_removed():
    secret = "HIDDEN_METADATA_MUST_NOT_SURVIVE"
    hidden = f"""<script>{secret}</script><style>{secret}</style><!-- {secret} -->
      <ix:hidden><p>{secret}</p></ix:hidden><ix:header>{secret}</ix:header>
      <p style='DISPLAY : none'>{secret}</p><p style='visibility: hidden'>{secret}</p>
      <div hidden>{secret}</div><p aria-hidden='true'>{secret}</p>"""
    result = extract_filing_excerpts(document(risk=RISK + hidden, mdna=MDNA + hidden))
    assert all(secret not in section.text for section in result.values())
    assert not result["1A"].reason and not result["7"].reason


def test_inline_cross_reference_does_not_close_actual_section():
    reference = "For context, see Item 7A. Quantitative and Qualitative Disclosures About Market Risk. "
    result = extract_filing_excerpts(document(mdna=MDNA + reference + "AFTER_REFERENCE"))
    assert "AFTER_REFERENCE" in result["7"].text


def test_orphan_table_of_contents_start_does_not_swallow_filing():
    markup = document().replace("<tr><td>Item 1B.</td><td>Unresolved Staff Comments</td><td>34</td></tr>", "")
    result = extract_filing_excerpts(markup)
    assert result["1A"].text.startswith("ITEM 1A.")
    assert "Management’s" not in result["1A"].text
    assert RISK.strip() in result["1A"].text


def test_missing_section_or_boundary_returns_explanation_not_document():
    missing = extract_filing_excerpts("<p>No recognizable filing sections.</p>")
    assert all(section.text == "" and section.reason.startswith("N/A") for section in missing.values())
    unclosed = extract_filing_excerpts(f"<h2>ITEM 1A. RISK FACTORS</h2><p>{RISK}</p>")["1A"]
    assert unclosed.text == ""
    assert "closing heading" in unclosed.reason


def test_toc_only_document_is_not_an_excerpt():
    html = "<h2>Item 1A. Risk Factors</h2><p>12</p><h2>Item 1B. Unresolved Staff Comments</h2>"
    result = extract_filing_excerpts(html)["1A"]
    assert result.text == ""
    assert "table-of-contents" in result.reason


def test_truncation_reports_original_length_and_respects_character_limit():
    result = extract_filing_excerpts(document(), max_chars=220)
    assert all(len(section.text) == 220 for section in result.values())
    assert all(section.truncated and section.original_chars > 220 for section in result.values())
    assert all(not section.reason for section in result.values())
    full = extract_filing_excerpts(document())
    assert all(not section.truncated and section.original_chars == len(section.text) for section in full.values())


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_invalid_limits(value):
    with pytest.raises(ValueError):
        extract_filing_excerpts(document(), max_chars=value)
    with pytest.raises(ValueError):
        extract_filing_excerpts(document(), min_section_chars=value)


def test_actual_issuer_ir_report_does_not_invent_missing_item_headings():
    source = Path(__file__).resolve().parents[1] / "fixtures/sources/msft_ar25.html"
    result = extract_filing_excerpts(source.read_bytes())
    # Investor-relations presentation lacks the SEC filing's explicit Item
    # headings. The parser must report missing, never relabel arbitrary prose.
    assert all(section.text == "" and section.reason.startswith("N/A") for section in result.values())
