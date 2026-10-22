import csv
import io
import json

import pytest

from alphalens import service
from alphalens.service import SecError, build_observations, load_research, resolve_company, snapshot_csv, snapshot_json


def test_ticker_mapping_uses_sec_cik():
    for ticker, cik in [("msft", "0000789019"), (" AAPL ", "0000320193"), ("AMZN", "0001018724")]:
        assert resolve_company(ticker, service._read_fixture("company_tickers.json"))["cik"] == cik


def test_unknown_ticker_does_not_network(monkeypatch):
    monkeypatch.setattr(service, "SecClient", lambda *a, **k: pytest.fail("unexpected network"))
    with pytest.raises(ValueError):
        load_research("ZZZZ", "live")


def test_offline_requires_no_key_or_network(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("SEC_USER_AGENT", "")
    result = load_research("MSFT", "offline")
    assert result.mode == "offline"
    assert [p.fiscal_year for p in result.periods] == [2024, 2025, 2026]
    assert any("OFFLINE DEMONSTRATION" in item for item in result.warnings)


def test_json_and_csv_export_nulls_provenance_and_mode():
    result = load_research("MSFT")
    payload = json.loads(snapshot_json(result))
    assert payload["data_status"].startswith("OFFLINE")
    assert payload["periods"][-1]["metrics"]["total_debt"]["value"] is None
    rows = list(csv.DictReader(io.StringIO(snapshot_csv(result))))
    assert len(rows) == 33
    assert all(row["data_status"] == "OFFLINE DEMONSTRATION" for row in rows)
    debt = next(row for row in rows if row["metric"] == "total_debt" and row["fiscal_year"] == "2026")
    assert debt["value"] == "N/A" and debt["missing_reason"]
    revenue = next(row for row in rows if row["metric"] == "revenue")
    assert json.loads(revenue["sources_json"])[0]["concept"].startswith("us-gaap:")


def test_fixture_tampering_fails_before_financial_output(tmp_path, monkeypatch):
    manifest = service._read_fixture("manifest.json")
    monkeypatch.setattr(service, "FIXTURES", tmp_path)
    for name in ("company_tickers.json", "msft_companyfacts.json", "msft_submissions.json"):
        (tmp_path / name).write_text('{}', encoding="utf-8")
    with pytest.raises(SecError, match="integrity check failed"):
        service._validate_fixtures(manifest)


def test_observations_do_not_invent_unavailable_debt():
    result = load_research("MSFT")
    observations = build_observations(result)
    assert any("2026-06-30" in row for row in observations)
    assert not any("Total debt" in row for row in observations)


def test_filing_reader_offline_never_downloads(monkeypatch):
    result = load_research("MSFT")
    with pytest.raises(ValueError, match="only in live mode"):
        service.load_filing_excerpts(result, result.filings[0]["accession"])


def test_filing_reader_rejects_unlisted_accession():
    result = load_research("MSFT")
    result.mode = "live"
    with pytest.raises(ValueError, match="displayed SEC filing library"):
        service.load_filing_excerpts(result, "not-a-filing")


def test_filing_reader_uses_selected_verified_document(monkeypatch):
    from unittest.mock import Mock
    result = load_research("MSFT")
    result.mode = "live"
    client = Mock()
    client.get_text.return_value = "<html>Missing expected Item headings.</html>"
    monkeypatch.setattr(service, "SecClient", Mock(return_value=client))
    excerpts = service.load_filing_excerpts(result, result.filings[0]["accession"], "test contact")
    client.get_text.assert_called_once_with(result.filings[0]["url"])
    assert not excerpts["1A"].text and excerpts["1A"].reason.startswith("N/A")
