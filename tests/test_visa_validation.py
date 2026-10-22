"""SIMULATED Visa-shaped examples test second-company mechanics, not Visa facts.

Actual SEC Visa results are documented separately in the captured evidence report.
No test sends network requests or represents these authored values as company data.
"""
from copy import deepcopy
import hashlib
import json

import pytest

from scripts import validate_visa as driver


def simulated_payloads():
    mapping = {"0": {"ticker": "V", "title": "VISA INC. — SIMULATED TEST ONLY", "cik_str": 1403161}}
    submissions = {"cik": "1403161", "name": "VISA INC. — SIMULATED TEST ONLY", "filings": {"recent": {
        "form": ["10-K"] * 3, "accessionNumber": [f"0001403161-{year % 100:02d}-000001" for year in (2023, 2024, 2025)],
        "filingDate": [f"{year}-11-15" for year in (2023, 2024, 2025)],
        "reportDate": [f"{year}-09-30" for year in (2023, 2024, 2025)], "primaryDocument": ["simulated.htm"] * 3}}}
    tags = {}
    amounts = {
        "RevenueFromContractWithCustomerExcludingAssessedTax": [100_000_000, 110_000_000, 125_000_000],
        "OperatingIncomeLoss": [65_000_000, 72_000_000, 70_000_000],
        "NetIncomeLoss": [50_000_000, 54_000_000, 55_000_000],
        "NetCashProvidedByUsedInOperatingActivities": [60_000_000, 65_000_000, 75_000_000],
        "PaymentsToAcquirePropertyPlantAndEquipment": [3_000_000, 3_000_000, 3_000_000],
    }
    for concept, values in amounts.items():
        tags[concept] = {"units": {"USD": [{"start": f"{year-1}-10-01", "end": f"{year}-09-30", "val": value,
            "accn": f"0001403161-{year % 100:02d}-000001", "form": "10-K", "filed": f"{year}-11-15", "fy": year, "fp": "FY"}
            for year, value in zip((2023, 2024, 2025), values)]}}
    facts = {"cik": 1403161, "entityName": "VISA INC. — SIMULATED TEST ONLY", "facts": {"us-gaap": tags}}
    records = [{"url": url, "fetched_at": "2026-10-21T00:00:00+00:00", "cached": False} for url in (
        "https://www.sec.gov/files/company_tickers.json",
        "https://data.sec.gov/submissions/CIK0001403161.json",
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0001403161.json")]
    return mapping, submissions, facts, records


def test_second_company_uses_generic_margin_signal_not_microsoft_capex_assumption():
    result, audit = driver.validate_payloads(*simulated_payloads())
    latest = [row for row in audit["annual_analysis"]["tensions"] if row["current_period"]["fiscal_year"] == 2025]
    assert result.ticker == "V" and result.cik == "0001403161"
    assert {row["type"] for row in latest} == {"growth_margin_tension"}
    assert result.periods[-1].metrics["free_cash_flow"].value == 72_000_000
    assert all(row["status"] == "passed" for row in audit["free_cash_flow_reconciliations"])
    assert all(row["current_period"]["period_end"] == "2025-09-30" for row in latest)


def test_wrong_issuer_or_missing_transport_evidence_is_rejected():
    mapping, submissions, facts, records = simulated_payloads()
    facts["cik"] = 789019
    with pytest.raises(ValueError, match="different issuers"):
        driver.validate_payloads(mapping, submissions, facts, records)
    facts["cik"] = 1403161
    with pytest.raises(ValueError, match="provenance"):
        driver.validate_payloads(mapping, submissions, facts, records[:1])


def test_broader_software_and_intangible_outlay_does_not_fill_missing_cash_ppe():
    mapping, submissions, facts, records = simulated_payloads()
    tags = facts["facts"]["us-gaap"]
    broader = tags.pop("PaymentsToAcquirePropertyPlantAndEquipment")
    broader["description"] = "Cash outflow for PP&E, software and other intangible assets."
    tags["PaymentsToAcquireProductiveAssets"] = broader
    result, audit = driver.validate_payloads(mapping, submissions, facts, records)
    assert all(p.metrics["capital_expenditure"].value is None and p.metrics["free_cash_flow"].value is None for p in result.periods)
    assert all(row["status"] == "unavailable" for row in audit["free_cash_flow_reconciliations"])
    assert "Not substituted" in audit["coverage_notes"][0]["treatment"]
    assert not any(row["type"] == "cash_flow_divergence" for row in audit["annual_analysis"]["tensions"])


def test_wrong_unit_capex_does_not_produce_false_fcf():
    mapping, submissions, facts, records = simulated_payloads()
    tags = facts["facts"]["us-gaap"]
    tags["PaymentsToAcquirePropertyPlantAndEquipment"]["units"] = {"shares": tags["PaymentsToAcquirePropertyPlantAndEquipment"]["units"]["USD"]}
    result, audit = driver.validate_payloads(mapping, submissions, facts, records)
    assert all(p.metrics["free_cash_flow"].value is None for p in result.periods)
    assert any(row["metric"] == "capital_expenditure" for row in audit["missing_metrics"])


def test_selected_citation_must_match_original_payload(monkeypatch):
    original = driver.extract_annuals

    def corrupt(*args, **kwargs):
        periods = original(*args, **kwargs)
        periods[-1].metrics["revenue"].sources[0].filed = "2025-11-16"
        return periods

    monkeypatch.setattr(driver, "extract_annuals", corrupt)
    with pytest.raises(ValueError, match="citation does not match"):
        driver.validate_payloads(*simulated_payloads())


def test_saved_replay_checks_hashes_and_requires_no_network(tmp_path, monkeypatch):
    mapping, submissions, facts, records = simulated_payloads()
    for name, value in zip(driver.PAYLOAD_FILES, (mapping, submissions, facts)):
        driver._write(tmp_path / name, value)
    manifest = {"synthetic_data": False, "ticker": "V", "records": records,
        "files": {name: {"sha256": hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()} for name in driver.PAYLOAD_FILES}}
    # The marker exercises provenance control only; authored payload names still
    # explicitly say SIMULATED TEST ONLY and are never shipped as genuine data.
    driver._write(tmp_path / "PROVENANCE.json", manifest)
    monkeypatch.setattr(driver.SecClient, "__init__", lambda *a, **k: pytest.fail("Replay must not create a network client"))
    assert driver.run(tmp_path, live=False)["model_requests"] == 0
    assert "SIMULATED TEST ONLY" in (tmp_path / "VISA_EVIDENCE_REPORT.md").read_text(encoding="utf-8")
    payload = json.loads((tmp_path / driver.PAYLOAD_FILES[-1]).read_text(encoding="utf-8"))
    payload["cik"] = 789019
    driver._write(tmp_path / driver.PAYLOAD_FILES[-1], payload)
    with pytest.raises(ValueError, match="payload changed"):
        driver.run(tmp_path, live=False)


def test_reviewer_passages_are_exact_and_bound_to_captured_filing(tmp_path):
    _, submissions, _, _ = simulated_payloads()
    driver._write(tmp_path / "visa_submissions.json", submissions)
    driver._write(tmp_path / "PROVENANCE.json", {"files": {"visa_submissions.json": {
        "sha256": hashlib.sha256((tmp_path / "visa_submissions.json").read_bytes()).hexdigest()}}})
    from alphalens.service import _all_filings
    filing = _all_filings(submissions)[0]
    html = """<html><body><h1>SIMULATED TEST ONLY</h1>
    <p>GAAP operating expenses increased 30% over the prior year, primarily driven by higher litigation provision and personnel expenses.</p>
    <p>Non-GAAP operating expenses increased 11% over the prior year, primarily driven by higher personnel, general and administrative, and depreciation and amortization expenses.</p>
    <p>Interchange multidistrict litigation. During fiscal 2025, we recorded accruals. Accruals could differ from deposits made into the U.S. litigation escrow account.</p>
    <p>Operating activities. Cash provided by operating activities increased in fiscal 2025 due to timing, partly offset by higher incentive payments.</p>
    </body></html>""".encode()
    (tmp_path / "visa_latest_10k.html").write_bytes(html)
    provenance = {**filing, "ticker": "V", "cik": "0001403161", "sha256": hashlib.sha256(html).hexdigest(),
        "transport": {"fetched_at": "2026-10-21T00:00:00+00:00"}}
    driver._write(tmp_path / "FILING_PROVENANCE.json", provenance)
    from alphalens.filings import _visible_document
    text = _visible_document(html)[0]
    passages = driver.review_recorded_filing(tmp_path)
    assert len(passages) == 4
    assert all(text[p["offset_start"]:p["offset_end"]] == p["text"] for p in passages.values())
    provenance["accession"] = "0001403161-25-999999"
    driver._write(tmp_path / "FILING_PROVENANCE.json", provenance)
    with pytest.raises(ValueError, match="annual filing library"):
        driver.review_recorded_filing(tmp_path)
    provenance["accession"] = filing["accession"]
    driver._write(tmp_path / "FILING_PROVENANCE.json", provenance)
    (tmp_path / "visa_latest_10k.html").write_bytes(html + b" altered")
    with pytest.raises(ValueError, match="filing fingerprint changed"):
        driver.review_recorded_filing(tmp_path)
