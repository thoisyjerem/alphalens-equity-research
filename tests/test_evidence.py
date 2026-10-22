"""Source-packet tests use real financial fixtures and labelled synthetic prose."""
from copy import deepcopy
from dataclasses import replace

import pytest

from alphalens.evidence import EvidenceError, build_evidence_book, evidence_fingerprint, source_fingerprint
from alphalens.filings import FilingExcerpt
from alphalens.service import load_offline_filing_context, load_research, make_filing_context


@pytest.fixture
def result():
    return load_research("MSFT", "offline")


def synthetic_context(result, text=None):
    """Synthetic prose for contract testing; never financial or live evidence."""
    filing = result.filings[0]
    text = text or "Synthetic test passage: competition and operational disruption may affect the business. " * 70
    return {"ticker": result.ticker, "cik": result.cik, "mode": result.mode,
            "retrieved_at": "2026-10-16T16:00:00+00:00", **filing,
            "excerpts": {"1A": FilingExcerpt("1A", "Risk factors", text, original_chars=len(text))}}


def test_real_fixture_catalog_preserves_values_inputs_and_offline_provenance(result):
    book = build_evidence_book(result)
    assert len(book) == 31
    assert "2026:total_debt" not in book
    revenue = book["2026:revenue"]
    original = result.periods[-1].metrics["revenue"]
    assert revenue["value"] == original.value
    assert revenue["sources"][0]["concept"] == original.sources[0].concept
    assert revenue["mode"] == "offline"
    assert revenue["cik"] == "0000789019"
    assert revenue["retrieved_at"] == result.retrieved_at


def test_instant_financials_are_not_labelled_as_durations(result):
    book = build_evidence_book(result)
    assert book["2026:cash_and_equivalents"]["period_start"] is None
    assert book["2026:revenue"]["period_start"] == result.periods[-1].start
    assert book["2024:total_debt"]["period_start"] is None
    assert book["2024:net_debt"]["period_start"] is None


def test_passage_chunks_are_contiguous_exact_bounded_and_auditable(result):
    context = synthetic_context(result)
    book = build_evidence_book(result, [context])
    passages = [(key, entry) for key, entry in book.items() if entry["kind"] == "passage"]
    assert len(passages) > 1
    assert "".join(entry["text"] for _, entry in passages) == context["excerpts"]["1A"].text
    previous_end = 0
    for source_id, entry in passages:
        assert source_id.startswith("sec:")
        assert len(entry["text"]) <= 1800
        assert entry["offset_start"] == previous_end
        assert entry["text"] == context["excerpts"]["1A"].text[entry["offset_start"]:entry["offset_end"]]
        assert entry["accession"] == context["accession"]
        assert entry["url"] == context["url"]
        assert entry["mode"] == "offline"
        previous_end = entry["offset_end"]


@pytest.mark.parametrize("field,value", [
    ("ticker", "AAPL"), ("cik", "0000320193"), ("mode", "live"),
    ("accession", "0000000000-00-000000"), ("url", "https://example.com/fake.html"),
    ("report_date", "2020-01-01"), ("filing_date", "2020-01-01"), ("retrieved_at", ""),
])
def test_cross_issuer_or_fabricated_filing_metadata_rejected(result, field, value):
    context = synthetic_context(result)
    context[field] = value
    with pytest.raises(EvidenceError):
        build_evidence_book(result, [context])


def test_context_requires_all_retrieval_fields(result):
    context = synthetic_context(result)
    del context["retrieved_at"]
    with pytest.raises(EvidenceError, match="required"):
        build_evidence_book(result, [context])


def test_absent_excerpt_not_invented_and_truncation_disclosed(result):
    context = synthetic_context(result, "Synthetic visible risk passage with sufficient content for source checking.")
    context["excerpts"]["7"] = FilingExcerpt("7", "Management discussion", "", reason="N/A — section unavailable.")
    context["excerpts"]["1A"] = replace(context["excerpts"]["1A"], truncated=True, original_chars=6000)
    passages = [row for row in build_evidence_book(result, [context]).values() if row["kind"] == "passage"]
    assert len(passages) == 1
    assert passages[0]["excerpt_truncated"] is True
    assert passages[0]["original_chars"] == 6000


def test_fingerprint_stable_and_sensitive_to_values_periods_mode_and_passages(result):
    context = synthetic_context(result)
    book = build_evidence_book(result, [context])
    fingerprint = evidence_fingerprint(book)
    assert source_fingerprint(result, [context]) == fingerprint
    assert evidence_fingerprint(dict(reversed(list(book.items())))) == fingerprint
    for field, value in [("value", 0), ("period_end", "2000-06-30"), ("mode", "live"), ("retrieved_at", "changed")]:
        changed = deepcopy(book)
        changed["2026:revenue"][field] = value
        assert evidence_fingerprint(changed) != fingerprint
    changed = deepcopy(book)
    next(row for row in changed.values() if row["kind"] == "passage")["text"] += "Changed."
    assert evidence_fingerprint(changed) != fingerprint


def test_passage_identifier_changes_with_content(result):
    first = build_evidence_book(result, [synthetic_context(result)])
    second = build_evidence_book(result, [synthetic_context(result, "Synthetic changed prose " * 100)])
    assert {key for key in first if key.startswith("sec:")}.isdisjoint(key for key in second if key.startswith("sec:"))


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True])
def test_invalid_financial_values_never_enter_sourcebook(result, value):
    result.periods[-1].metrics["revenue"].value = value
    with pytest.raises(EvidenceError, match="non-finite or invalid"):
        build_evidence_book(result)


def test_quarterly_period_cannot_be_relabelled_annual(result):
    result.periods[-1].start = "2026-04-01"
    with pytest.raises(EvidenceError, match="annual"):
        build_evidence_book(result)


def test_financial_source_issuer_or_period_mismatch_rejected(result):
    result.periods[-1].metrics["revenue"].sources[0].end = "2025-06-30"
    with pytest.raises(EvidenceError, match="metadata disagrees"):
        build_evidence_book(result)


def test_duplicate_annual_source_ids_cannot_overwrite_evidence(result):
    result.periods.append(deepcopy(result.periods[-1]))
    with pytest.raises(EvidenceError, match="Duplicate annual"):
        build_evidence_book(result)


def test_genuine_sec_narrative_fixture_retains_hash_retrieval_and_exact_text(result):
    context = load_offline_filing_context(result)
    book = build_evidence_book(result, [context])
    passages = [entry for entry in book.values() if entry["kind"] == "passage"]
    assert len(passages) == 8
    assert all(entry["mode"] == "offline" and "OFFLINE DEMONSTRATION" in entry["retrieval_note"] for entry in passages)
    assert all(entry["document_sha256"] == context["document_sha256"] for entry in passages)
    assert all(entry["retrieved_at"] == context["retrieved_at"] for entry in passages)
    for item in ("1A", "7"):
        assert "".join(entry["text"] for entry in passages if entry["item"] == item) == context["excerpts"][item].text


def test_unknown_legacy_timestamp_is_disclosed_without_inventing_a_retrieval(result):
    context = synthetic_context(result)
    legacy = make_filing_context(result, context["accession"], context["excerpts"])
    passages = [entry for entry in build_evidence_book(result, [legacy]).values() if entry["kind"] == "passage"]
    assert all(entry["retrieved_at"] is None for entry in passages)
    assert all("not recorded" in entry["retrieval_note"] for entry in passages)
    del legacy["retrieval_note"]
    with pytest.raises(EvidenceError):
        build_evidence_book(result, [legacy])
