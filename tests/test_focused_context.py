"""Focused retrieval service/evidence integration over a local fake SEC client."""
from copy import deepcopy
from dataclasses import replace
import hashlib
from unittest.mock import Mock

import pytest

from alphalens import service
from alphalens.evidence import EvidenceError, build_evidence_book
from alphalens.filings import extract_filing_excerpts


BACKGROUND = "Synthetic background disclosure supplies general context without specific research terms. " * 90
LATE_RISK = "Synthetic test: competition, pricing and energy supply constrain datacenter capacity. " * 3
LATE_MDNA = (
    "Synthetic test: capital expenditures support additions to property and equipment. "
    "Synthetic test: cash from operations and operating activities inform liquidity. "
    "Synthetic test: depreciation, finance leases and purchase commitments merit review. "
    "Synthetic test: Intelligent Cloud, Azure and OpenAI partnership inform segment analysis. "
) * 3
HTML = f"""<html><body><h2>ITEM 1A. RISK FACTORS</h2><p>{BACKGROUND}</p><p>{LATE_RISK}</p>
<h2>ITEM 1B. UNRESOLVED STAFF COMMENTS</h2>
<h2>ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS</h2><p>{BACKGROUND}</p><p>{LATE_MDNA}</p>
<h2>ITEM 7A. QUANTITATIVE AND QUALITATIVE DISCLOSURES ABOUT MARKET RISK</h2></body></html>"""


@pytest.fixture
def live_context(monkeypatch):
    result = deepcopy(service.load_research("MSFT", "offline"))
    result.mode = "live"
    client = Mock()
    client.get_text.return_value = HTML
    client.records = [{"fetched_at": "2026-10-17T12:00:00+00:00", "cached": True}]
    factory = Mock(return_value=client)
    monkeypatch.setattr(service, "SecClient", factory)
    context = service.load_research_filing_context(result, result.filings[0]["accession"], "test identity")
    return result, context, client


def test_service_keeps_original_reader_and_adds_focused_context_with_actual_hash(live_context):
    result, context, client = live_context
    assert context["excerpts"] == extract_filing_excerpts(HTML)
    assert context["focused_passages"]
    assert context["document_sha256"] == hashlib.sha256(HTML.encode("utf-8")).hexdigest()
    assert context["retrieved_at"] == client.records[0]["fetched_at"]
    assert context["accession"] == result.filings[0]["accession"]
    assert context["url"] == result.filings[0]["url"]
    client.get_text.assert_called_once_with(result.filings[0]["url"])
    assert "capital expenditures" not in context["excerpts"]["7"].text
    assert any("capital expenditures" in p.text for p in context["focused_passages"])


def test_evidence_uses_focused_passages_instead_of_duplicating_old_heads(live_context):
    result, context, _ = live_context
    book = build_evidence_book(result, [context])
    passages = [row for row in book.values() if row["kind"] == "passage"]
    full = extract_filing_excerpts(HTML, max_chars=2_000_000)
    assert len(passages) == len(context["focused_passages"])
    for row in passages:
        assert row["text"] == full[row["item"]].text[row["offset_start"]:row["offset_end"]]
        assert row["offset_start"] > 6000
        assert row["offset_basis"] == "normalized complete Item section"
        assert row["selection_method"] == "deterministic_topic_windows_v1"
        assert row["document_sha256"] == context["document_sha256"]
        for field in ("ticker", "cik", "accession", "url", "report_date", "filing_date", "retrieved_at", "mode"):
            assert row[field] == context[field]


def test_original_separate_filing_reader_retains_head_excerpt_contract(live_context):
    result, context, client = live_context
    original_reader = service.load_filing_excerpts(result, context["accession"], "test identity")
    assert original_reader == context["excerpts"]
    assert all(len(excerpt.text) == 6000 and excerpt.truncated for excerpt in original_reader.values())
    assert client.get_text.call_count == 2


@pytest.mark.parametrize("field,value", [
    ("ticker", "AAPL"), ("cik", "0000320193"), ("mode", "offline"),
    ("accession", "0000000000-00-000000"), ("report_date", "2000-01-01"),
])
def test_focused_passages_keep_existing_issuer_filing_and_period_guards(live_context, field, value):
    result, context, _ = live_context
    context[field] = value
    with pytest.raises(EvidenceError):
        build_evidence_book(result, [context])


@pytest.mark.parametrize("change", [
    {"section_start": -1}, {"section_end": 1}, {"original_chars": 1},
    {"text": "short"}, {"selection_method": "model_invented_source"},
])
def test_invalid_focused_offsets_or_retrieval_method_are_rejected(live_context, change):
    result, context, _ = live_context
    context["focused_passages"][0] = replace(context["focused_passages"][0], **change)
    with pytest.raises(EvidenceError, match="Focused passage"):
        build_evidence_book(result, [context])


def test_empty_focused_selection_preserves_legacy_excerpt_evidence(live_context):
    result, context, _ = live_context
    context["focused_passages"] = []
    book = build_evidence_book(result, [context])
    passages = [row for row in book.values() if row["kind"] == "passage"]
    for item in ("1A", "7"):
        assert "".join(row["text"] for row in passages if row["item"] == item) == context["excerpts"][item].text
