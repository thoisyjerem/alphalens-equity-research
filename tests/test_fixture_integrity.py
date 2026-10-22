"""Verify authentic fixture integrity and independently reconcile issuer tables.

These tests do not need internet access or an OpenAI API key. They deliberately
cross-check raw SEC facts against retained official Microsoft report HTML rather
than manufacturing fixture facts using the extraction implementation under test.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
FY25_ACCESSION = "0000950170-25-100235"
FY24_ACCESSION = "0000950170-24-087843"


@pytest.fixture(scope="module")
def companyfacts():
    return json.loads((FIXTURES / "msft_companyfacts.json").read_text(encoding="utf-8"))


def test_recorded_file_hashes_and_source_capture_metadata():
    manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["mode"] == "offline_fixture"
    assert "snapshot" in manifest["label"].lower()
    assert "unmodified" in manifest["transformation"].lower()
    assert {s["local_path"] for s in manifest["sources"]} >= {
        "msft_companyfacts.json", "msft_submissions.json", "company_tickers.json",
    }
    for source in manifest["sources"]:
        assert source["url"].startswith(("https://data.sec.gov/", "https://www.sec.gov/", "https://www.microsoft.com/"))
        assert datetime.fromisoformat(source["captured_at"]).tzinfo is not None
        assert source["local_path"] in manifest["files"]
    for relative, recorded in manifest["files"].items():
        data = (FIXTURES / relative).read_bytes()
        assert len(data) == recorded["bytes"], relative
        assert hashlib.sha256(data).hexdigest() == recorded["sha256"], relative


def test_genuine_sec_company_identity_and_supported_tickers(companyfacts):
    assert companyfacts["cik"] == 789019
    assert companyfacts["entityName"] == "MICROSOFT CORPORATION"
    assert set(companyfacts) == {"cik", "entityName", "facts"}
    mapping = json.loads((FIXTURES / "company_tickers.json").read_text(encoding="utf-8"))
    by_ticker = {x["ticker"]: x["cik_str"] for x in mapping.values()}
    assert len(mapping) > 1000  # complete response, not an invented tiny mapping
    assert {ticker: by_ticker[ticker] for ticker in ("MSFT", "AAPL", "AMZN")} == {
        "MSFT": 789019, "AAPL": 320193, "AMZN": 1018724,
    }


def test_latest_snapshot_filings_have_verified_annual_periods():
    submissions = json.loads((FIXTURES / "msft_submissions.json").read_text(encoding="utf-8"))
    recent = submissions["filings"]["recent"]
    annual = [
        (recent["reportDate"][i], recent["accessionNumber"][i], recent["filingDate"][i])
        for i, form in enumerate(recent["form"]) if form == "10-K"
    ]
    assert annual[:3] == [
        ("2026-06-30", "0001193125-26-323660", "2026-07-29"),
        ("2025-06-30", FY25_ACCESSION, "2025-07-30"),
        ("2024-06-30", FY24_ACCESSION, "2024-07-30"),
    ]


def _issuer_table_rows(filename):
    soup = BeautifulSoup((FIXTURES / "sources" / filename).read_text(encoding="utf-8"), "html.parser")
    result = []
    for row in soup.find_all("tr"):
        cells = row.find_all(["td", "th"], recursive=False)
        if not cells:
            continue
        first = re.sub(r"\s+", " ", cells[0].get_text(" ", strip=True)).strip()
        text = " ".join(cell.get_text(" ", strip=True) for cell in cells[1:])
        numbers = []
        for token in re.findall(r"\(?-?\d[\d,]*(?:\.\d+)?\)?", text):
            negative = token.startswith("(") or token.startswith("-")
            number = float(token.strip("()-").replace(",", ""))
            numbers.append(-number if negative else number)
        result.append((first, numbers))
    return result


# Values are read from the retained official issuer rows. The matching facts are
# restricted to the exact 10-K accession and exact annual interval/balance date.
@pytest.mark.parametrize("concept,label,unit,source,years,accession,outflow", [
    ("RevenueFromContractWithCustomerExcludingAssessedTax", "Total revenue", "USD", "msft_ar25.html", [2025, 2024, 2023], FY25_ACCESSION, False),
    ("OperatingIncomeLoss", "Operating income", "USD", "msft_ar25.html", [2025, 2024, 2023], FY25_ACCESSION, False),
    ("NetIncomeLoss", "Net income", "USD", "msft_ar25.html", [2025, 2024, 2023], FY25_ACCESSION, False),
    ("EarningsPerShareDiluted", "Diluted", "USD/shares", "msft_ar25.html", [2025, 2024, 2023], FY25_ACCESSION, False),
    ("NetCashProvidedByUsedInOperatingActivities", "Net cash from operations", "USD", "msft_ar25.html", [2025, 2024, 2023], FY25_ACCESSION, False),
    ("PaymentsToAcquirePropertyPlantAndEquipment", "Additions to property and equipment", "USD", "msft_ar25.html", [2025, 2024, 2023], FY25_ACCESSION, True),
    ("CashAndCashEquivalentsAtCarryingValue", "Cash and cash equivalents", "USD", "msft_ar25.html", [2025, 2024], FY25_ACCESSION, False),
    ("CommercialPaper", "Short-term debt", "USD", "msft_ar25.html", [2025, 2024], FY25_ACCESSION, False),
    ("LongTermDebtCurrent", "Current portion of long-term debt", "USD", "msft_ar25.html", [2025, 2024], FY25_ACCESSION, False),
    ("LongTermDebtNoncurrent", "Long-term debt", "USD", "msft_ar25.html", [2025, 2024], FY25_ACCESSION, False),
    ("CashAndCashEquivalentsAtCarryingValue", "Cash and cash equivalents", "USD", "msft_ar24.html", [2024, 2023], FY24_ACCESSION, False),
    ("CommercialPaper", "Short-term debt", "USD", "msft_ar24.html", [2024, 2023], FY24_ACCESSION, False),
    ("LongTermDebtCurrent", "Current portion of long-term debt", "USD", "msft_ar24.html", [2024, 2023], FY24_ACCESSION, False),
    ("LongTermDebtNoncurrent", "Long-term debt", "USD", "msft_ar24.html", [2024, 2023], FY24_ACCESSION, False),
])
def test_sec_facts_reconcile_to_independent_issuer_statement_rows(
    companyfacts, concept, label, unit, source, years, accession, outflow,
):
    fact_rows = companyfacts["facts"]["us-gaap"][concept]["units"][unit]
    expected = []
    for year in years:
        matching = [
            row for row in fact_rows
            if row.get("accn") == accession and row.get("form") == "10-K"
            and row["end"] == f"{year}-06-30"
            and ("start" not in row or row["start"] == f"{year - 1}-07-01")
        ]
        assert len({row["val"] for row in matching}) == 1, (concept, year)
        value = matching[0]["val"] / (1 if unit == "USD/shares" else 1_000_000)
        expected.append(-value if outflow else value)
    issuer_candidates = [values for row_label, values in _issuer_table_rows(source) if row_label == label]
    assert expected in issuer_candidates, (source, label, expected, issuer_candidates)
