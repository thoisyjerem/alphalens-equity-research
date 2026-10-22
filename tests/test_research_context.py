"""Provenance checks for the optional AI filing-context service boundary."""
from copy import deepcopy
import hashlib
import json
from unittest.mock import Mock

import pytest

from alphalens import service


def test_offline_context_uses_genuine_checked_snapshot_without_network(monkeypatch):
    result = service.load_research("MSFT")
    monkeypatch.setattr(service, "SecClient", Mock(side_effect=AssertionError("No network in offline mode")))
    context = service.load_offline_filing_context(result)
    assert context["mode"] == "offline"
    assert context["url"] == result.filings[0]["url"]
    assert context["report_date"] == result.periods[-1].end
    assert context["retrieved_at"]
    assert len(context["document_sha256"]) == 64
    assert all(excerpt.text and excerpt.truncated for excerpt in context["excerpts"].values())


def test_changed_passage_file_fails_hash_check(tmp_path, monkeypatch):
    result = service.load_research("MSFT")
    manifest = service._read_fixture("research_manifest.json")
    (tmp_path / "research_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "msft_research_passages.json").write_text('{}', encoding="utf-8")
    monkeypatch.setattr(service, "FIXTURES", tmp_path)
    with pytest.raises(service.SecError, match="integrity check failed"):
        service.load_offline_filing_context(result)


def test_metadata_cannot_bind_another_issuer_even_if_local_hash_matches(tmp_path, monkeypatch):
    result = service.load_research("MSFT")
    payload = service._read_fixture("msft_research_passages.json")
    payload["ticker"] = "AAPL"
    raw = json.dumps(payload).encode("utf-8")
    (tmp_path / "msft_research_passages.json").write_bytes(raw)
    (tmp_path / "research_manifest.json").write_text(json.dumps({"sha256": hashlib.sha256(raw).hexdigest()}), encoding="utf-8")
    monkeypatch.setattr(service, "FIXTURES", tmp_path)
    with pytest.raises(service.SecError, match="metadata disagrees"):
        service.load_offline_filing_context(result)


def test_live_context_captures_actual_client_timestamp_and_document_hash(monkeypatch):
    result = service.load_research("MSFT")
    result.mode = "live"
    client = Mock()
    html = "<html>Bounded Item headings are unavailable in this mocked transport response.</html>"
    client.get_text.return_value = html
    client.records = [{"fetched_at": "2026-10-16T16:00:00+00:00"}]
    monkeypatch.setattr(service, "SecClient", Mock(return_value=client))
    context = service.load_research_filing_context(result, result.filings[0]["accession"], "test identity")
    assert context["retrieved_at"] == client.records[0]["fetched_at"]
    assert context["document_sha256"] == hashlib.sha256(html.encode()).hexdigest()
    client.get_text.assert_called_once_with(result.filings[0]["url"])
    assert all(excerpt.reason and not excerpt.text for excerpt in context["excerpts"].values())


def test_research_retrieval_rejects_offline_or_unlisted_filing_before_http(monkeypatch):
    result = service.load_research("MSFT")
    factory = Mock()
    monkeypatch.setattr(service, "SecClient", factory)
    with pytest.raises(ValueError, match="offline mode"):
        service.load_research_filing_context(result, result.filings[0]["accession"])
    result.mode = "live"
    with pytest.raises(ValueError, match="filing library"):
        service.load_research_filing_context(result, "0000000000-00-000000")
    factory.assert_not_called()


def test_offline_passages_cannot_be_passed_off_as_live():
    result = service.load_research("MSFT")
    result.mode = "live"
    with pytest.raises(ValueError, match="offline mode only"):
        service.load_offline_filing_context(result)
