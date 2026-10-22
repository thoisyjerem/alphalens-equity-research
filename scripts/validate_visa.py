"""Reproducible, SEC-only second-company validation; never calls a model.

Run with ``--live`` for explicitly requested SEC access or ``--replay`` to
revalidate the saved genuine responses without network access. This driver does
not broaden the Streamlit supported-company list or alter extraction policy.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alphalens.analytics import build_analytics
from alphalens.evidence import build_evidence_book
from alphalens.financials import extract_annuals
from alphalens.models import ResearchResult
from alphalens.sec import SecClient, SecError

DEFAULT_OUTPUT = ROOT / "outputs/v1_1_2026-10-21/visa"
PAYLOAD_FILES = ("company_tickers.json", "visa_submissions.json", "visa_companyfacts.json")


def _write(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")


def resolve_visa(mapping: dict) -> dict:
    rows = [row for row in mapping.values() if isinstance(row, dict) and row.get("ticker") == "V"]
    if len(rows) != 1 or "VISA" not in str(rows[0].get("title", "")).upper():
        raise ValueError("The official mapping must identify exactly one V / Visa issuer; no substitute is allowed.")
    return {"ticker": "V", "name": rows[0]["title"], "cik": SecClient.padded_cik(rows[0]["cik_str"])}


def _source_matches(source: dict, facts: dict) -> bool:
    namespace, concept = source["concept"].split(":", 1)
    candidates = facts.get("facts", {}).get(namespace, {}).get(concept, {}).get("units", {}).get(source["unit"], [])
    return any(all(row.get(raw) == source[key] for raw, key in
        (("val", "value"), ("start", "start"), ("end", "end"),
         ("accn", "accession"), ("form", "form"), ("filed", "filed"))) for row in candidates)


def validate_payloads(mapping: dict, submissions: dict, facts: dict, records: list[dict]) -> tuple[ResearchResult, dict]:
    """Use the unchanged production financial pipeline and verify every raw citation."""
    from alphalens.service import _all_filings
    company = resolve_visa(mapping)
    if any(SecClient.padded_cik(payload.get("cik", "")) != company["cik"] for payload in (submissions, facts)):
        raise ValueError("Ticker mapping, submissions and companyfacts identify different issuers.")
    if "VISA" not in str(submissions.get("name", "")).upper():
        raise ValueError("Submissions do not identify Visa; analysis stopped.")
    expected_urls = {"https://www.sec.gov/files/company_tickers.json",
        f"https://data.sec.gov/submissions/CIK{company['cik']}.json",
        f"https://data.sec.gov/api/xbrl/companyfacts/CIK{company['cik']}.json"}
    if (not records or not expected_urls.issubset({row.get("url") for row in records})
            or any(not row.get("fetched_at") or not isinstance(row.get("cached"), bool) for row in records)):
        raise ValueError("SEC response provenance is required.")
    periods = extract_annuals(facts, submissions, years=3)
    if not periods:
        raise ValueError("No completed annual Visa periods were verified; no substitute data is permitted.")
    result = ResearchResult(**company, periods=periods, mode="live", retrieved_at=min(r["fetched_at"] for r in records),
        warnings=["Genuine official SEC response capture, replayable locally; not live market prices.",
                  "Visa validation uses the unchanged US-GAAP extraction policy; unavailable metrics remain N/A.",
                  "No AI generation was performed for Visa. Any separately retained reviewer-selected filing passages remain distinct from the numerical pipeline."], filings=_all_filings(submissions))
    analysis = build_analytics(result)
    evidence = build_evidence_book(result)
    matched, unique = 0, set()
    reconciliations = []
    for period in result.periods:
        if any(metric.value is not None and not metric.sources for metric in period.metrics.values()):
            raise ValueError("An available financial metric lacks raw source facts.")
        for metric in period.metrics.values():
            for source in metric.sources:
                raw = asdict(source)
                if not _source_matches(raw, facts):
                    raise ValueError("A selected citation does not match the captured SEC concept/value/period/filing.")
                matched += 1
                unique.add(json.dumps(raw, sort_keys=True))
        metrics = period.metrics
        values = [metrics[key].value for key in ("operating_cash_flow", "capital_expenditure", "free_cash_flow")]
        if all(value is not None for value in values):
            ocf, capex, fcf = map(lambda value: Decimal(str(value)), values)
            if capex < 0 or ocf - capex != fcf:
                raise ValueError("Cash PP&E sign or deterministic free-cash-flow reconciliation failed.")
            reconciliations.append({"fiscal_year": period.fiscal_year, "period_start": period.start,
                "period_end": period.end, "unit": "USD", "operating_cash_flow": str(ocf),
                "cash_ppe": str(capex), "free_cash_flow": str(fcf),
                "formula": "operating_cash_flow - cash_PPE_purchases", "status": "passed",
                "source_ids": [f"{period.fiscal_year}:{key}" for key in ("operating_cash_flow", "capital_expenditure", "free_cash_flow")]})
        else:
            reconciliations.append({"fiscal_year": period.fiscal_year, "status": "unavailable", "reason": "An input is N/A; no value was inferred."})
    if any(source_id not in evidence for signal in analysis["tensions"] for source_id in signal["source_ids"]):
        raise ValueError("A deterministic observation refers to an unavailable source ID.")
    coverage_notes = []
    tags = facts.get("facts", {}).get("us-gaap", {})
    if "PaymentsToAcquirePropertyPlantAndEquipment" not in tags and "PaymentsToAcquireProductiveAssets" in tags:
        definition = tags["PaymentsToAcquireProductiveAssets"]
        coverage_notes.append({"concept": "us-gaap:PaymentsToAcquireProductiveAssets",
            "description": definition.get("description", ""),
            "treatment": "Not substituted for cash PP&E: this broader concept includes software and other intangible assets; PP&E-only FCF stays N/A."})
    return result, {"status": "passed", "issuer": company, "source_occurrences_checked": matched,
        "unique_source_facts_checked": len(unique), "free_cash_flow_reconciliations": reconciliations,
        "annual_analysis": analysis, "evidence": evidence, "coverage_notes": coverage_notes,
        "missing_metrics": [{"fiscal_year": period.fiscal_year, "metric": key, "reason": metric.reason}
            for period in periods for key, metric in period.metrics.items() if metric.value is None],
        "limitations": ["Deterministic financial validation, not a complete investment analysis or semantic claim verification.",
            "Payment volumes, transaction growth, take rates, segment disclosures and share-repurchase analysis were not extracted.",
            "Cash PP&E is consolidated cash spending, not an AI-specific or lease-inclusive investment measure.",
            "Latest completed years depend on annual 10-K availability; a fiscal year-end alone is not a published annual report."]}


def _report(result: ResearchResult, audit: dict, comparison: dict) -> str:
    lines = ["# Visa — deterministic second-company evidence validation", "",
        "Genuine saved official SEC responses. No Gemini request, synthetic Visa figures or investment recommendation.", "",
        f"Issuer: {result.name}; ticker {result.ticker}; CIK {result.cik}. Original response capture: {result.retrieved_at}.", "",
        "The application still supports its existing dashboard companies; this standalone driver tests whether the same financial pipeline generalises.", "",
        "## Annual reported comparison", "", "USD billions, except EPS and margins. FCF = operating cash flow − cash PP&E.", "",
        "| Metric | " + " | ".join(f"FY{p.fiscal_year} ({p.start} to {p.end})" for p in result.periods) + " |",
        "| --- | " + " | ".join("---:" for _ in result.periods) + " |"]
    for key in result.periods[0].metrics:
        cells = []
        for p in result.periods:
            m = p.metrics[key]
            value = "N/A" if m.value is None else f"{m.value:.2%}" if m.unit == "ratio" else f"{m.value:.2f}" if m.unit == "USD/shares" else f"{m.value / 1e9:,.3f}"
            cells.append(f"{value} [{p.fiscal_year}:{key}]" if m.value is not None else value)
        lines.append(f"| {key.replace('_', ' ')} | " + " | ".join(cells) + " |")
    latest = max(result.periods, key=lambda p: p.end)
    rows = {row["metric"]: row for row in audit["annual_analysis"]["metrics"] if row["fiscal_year"] == latest.fiscal_year}
    lines += ["", "## Latest annual changes — Python calculations", "",
        "| Calculation | Result | Formula | Raw evidence IDs |", "| --- | ---: | --- | --- |"]
    for metric in ("revenue_growth", "operating_income_growth", "operating_margin_change_pp", "operating_cash_flow_growth", "net_income_growth"):
        row = rows.get(metric)
        if row is not None:
            number = "N/A" if row["value"] is None else f"{row['value']:+.3f} pp" if row["unit"] == "percentage_points" else f"{row['value']:+.2%}"
            lines.append(f"| {metric.replace('_', ' ')} | {number} | {row['calculation']} | {', '.join(row['dependencies'])} |")
    lines += ["", "## Screening observations — require economic interpretation", ""]
    for signal in audit["annual_analysis"]["tensions"]:
        lines += [f"- **{signal['id']}: {signal['title']}** — {signal['explanation']}",
                  "  Sources: " + ", ".join(signal["source_ids"]) + "."]
    if not audit["annual_analysis"]["tensions"]:
        lines.append("No existing materiality rule triggered. Absence of a screening signal does not establish an absence of investment risks.")
    lines += ["", "## Reviewer research questions — not model output or proven causes", "",
        "The latest comparison separates growth in reported sales from operating-profit conversion. If the margin-contraction screen is present, "
        "an analyst should reconcile the operating-expense bridge before deciding whether the change reflects recurring cost pressure, mix or a separately disclosed charge. "
        "Companyfacts totals alone do not identify those mechanisms' causal contribution. The separately recorded filing passages below, where available, "
        "provide the company's reported explanations; recurrence and economic significance still require analyst judgment.", "",
        "Compare operating cash-flow growth with operating-income and net-income growth, then inspect cash taxes, non-cash charges and working-capital movements. "
        "Do not infer working-capital improvement merely because operating cash flow increased. A sustainable cash-generation assessment requires that reconciliation.", "",
        "Cash PP&E and the defined free-cash-flow measure are unavailable under the unchanged mapping. Consequently this report cannot rank Visa's reinvestment intensity "
        "against Microsoft's or conclude that a lighter investment requirement supports a valuation premium. The broader productive-asset spending concept requires a separate, explicitly defined measure."]
    if audit.get("review_passages"):
        lines += ["", "## Additional disclosed context — separately reviewed SEC passages", "",
            "These are exact excerpts of the one identified FY2025 annual filing, preserved with document hashes and text offsets. "
            "They are company disclosures, not generated Gemini analysis or independent proof of sustainable economics.", ""]
        for source_id, record in audit["review_passages"].items():
            lines += [f"**{source_id} — {record['topic']}** ([FY2025 10-K, filed {record['filing_date']}]({record['url']}))", "",
                f"> {record['text']}", ""]
        lines += ["Reviewer interpretation: the company expressly attributes GAAP operating-expense growth to litigation provision and personnel costs, "
            "while its non-GAAP cost-growth disclosure also points to personnel, general and administrative costs, and depreciation/amortisation. "
            "The margin decline should therefore be investigated through both the disclosed legal charge and the underlying cost base; removing the provision "
            "does not by itself prove that all margin pressure is temporary.", "",
            "The cash-flow disclosure expressly identifies income-tax payment timing and higher incentive payments alongside business growth. "
            "It supports a timing qualification, not a quantified recurring-earnings-to-cash bridge or a generic claim of improved working capital. "
            "The separate litigation-accrual and escrow-deposit disclosure also warns against equating an accounting charge with current cash paid.", "",
            "Further diligence: reconcile the legal provision to legal cash payments and escrow funding; compare recurring personnel and depreciation growth "
            "with revenue; quantify the income-tax timing contribution before treating the OCF increase as repeatable. These questions are distinct from Microsoft's "
            "cash PP&E/reinvestment question and remain unresolved by the totals alone."]
    if audit.get("investment_reasoning"):
        from alphalens.research_exports import investment_reasoning_markdown
        lines += ["", investment_reasoning_markdown(audit["investment_reasoning"])]
    lines += ["", "## Microsoft comparison", "",
        "Each company is analysed over its own latest verified annual comparison; fiscal year ends differ. These are screening patterns, not a relative valuation.", "",
        "| Company | Comparison | Latest-period signals |", "| --- | --- | --- |"]
    for ticker, row in comparison.items():
        lines.append(f"| {ticker} | {row['prior_end']} to {row['current_end']} | {', '.join(row['signals']) or 'No material rule triggered'} |")
    lines += ["", "## Missing data / limits", ""]
    for row in audit["missing_metrics"]:
        lines.append(f"- FY{row['fiscal_year']} {row['metric']}: N/A — {row['reason']}")
    for row in audit["coverage_notes"]:
        lines.append(f"- Captured concept `{row['concept']}`: {row['description']} {row['treatment']}")
    lines += [f"- {line}" for line in audit["limitations"]]
    lines += ["", "## Source register", "", "Complete exact concepts, values, periods, units, accessions, forms and filing dates are in VALIDATION.json and FINANCIAL_EVIDENCE.json.", ""]
    for source_id, record in audit["evidence"].items():
        lines.append(f"- `{source_id}`: {record['value']} {record['unit']}; {record['period_start'] or 'instant'} to {record['period_end']}; "
            + "; ".join(f"[{source['concept']} — {source['accession']}, {source['form']}, filed {source['filed']}]({source['url']})" for source in record["sources"]))
    return "\n".join(lines) + "\n"


def run(output: Path = DEFAULT_OUTPUT, *, live: bool = False) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    if live:
        from dotenv import load_dotenv
        from alphalens.service import _extend_history
        load_dotenv(ROOT / ".env")
        client = SecClient(os.getenv("SEC_USER_AGENT", ""), ROOT / ".cache/sec")
        mapping = client.company_tickers()
        company = resolve_visa(mapping)
        submissions = _extend_history(client, client.submissions(company["cik"]))
        facts = client.company_facts(company["cik"])
        for name, payload in zip(PAYLOAD_FILES, (mapping, submissions, facts)):
            _write(output / name, payload)
        manifest = {"captured_for": "AlphaLens V1.1 SEC-only Visa validation", "ticker": "V", "cik": company["cik"],
            "captured_at": datetime.now(timezone.utc).isoformat(), "records": client.records,
            "files": {name: {"sha256": hashlib.sha256((output / name).read_bytes()).hexdigest()} for name in PAYLOAD_FILES},
            "ai_requests": 0, "synthetic_data": False}
        _write(output / "PROVENANCE.json", manifest)
    else:
        manifest = json.loads((output / "PROVENANCE.json").read_text(encoding="utf-8"))
        if manifest.get("synthetic_data") is not False or manifest.get("ticker") != "V":
            raise ValueError("This replay requires genuine saved Visa payloads.")
        for name in PAYLOAD_FILES:
            if hashlib.sha256((output / name).read_bytes()).hexdigest() != manifest["files"][name]["sha256"]:
                raise ValueError(f"Saved SEC payload changed: {name}")
        mapping, submissions, facts = [json.loads((output / name).read_text(encoding="utf-8")) for name in PAYLOAD_FILES]
    result, audit = validate_payloads(mapping, submissions, facts, manifest["records"])
    from alphalens.service import load_research, snapshot_csv, snapshot_json
    microsoft = load_research("MSFT", "offline")
    comparison = {}
    for company_result in (microsoft, result):
        latest = max(company_result.periods, key=lambda p: p.end)
        prior = sorted(company_result.periods, key=lambda p: p.end)[-2]
        comparison[company_result.ticker] = {"prior_end": prior.end, "current_end": latest.end,
            "signals": [s["type"] for s in build_analytics(company_result)["tensions"] if s["current_period"]["period_end"] == latest.end]}
    audit["comparison"] = comparison
    audit["review_passages"] = review_recorded_filing(output, expected_report_date=max(p.end for p in result.periods))
    from alphalens.investment_reasoning import build_investment_reasoning
    audit["investment_reasoning"] = build_investment_reasoning(audit["evidence"], audit["annual_analysis"])
    audit["execution"] = {"network_enabled_for_this_run": live, "model_requests": 0,
        "payloads": manifest["files"], "transport_records": manifest["records"]}
    _write(output / "VALIDATION.json", audit)
    _write(output / "FINANCIAL_EVIDENCE.json", audit["evidence"])
    (output / "FINANCIALS.csv").write_text(snapshot_csv(result), encoding="utf-8")
    (output / "FINANCIAL_SNAPSHOT.json").write_text(snapshot_json(result), encoding="utf-8")
    (output / "VISA_EVIDENCE_REPORT.md").write_text(_report(result, audit, comparison), encoding="utf-8")
    return {"status": audit["status"], "ticker": result.ticker, "cik": result.cik,
        "annual_periods": [p.fiscal_year for p in result.periods], "source_facts_checked": audit["unique_source_facts_checked"],
        "transport": [{"url": r["url"], "cached": r["cached"], "fetched_at": r["fetched_at"]} for r in manifest["records"]],
        "comparison": comparison, "model_requests": 0}


def review_recorded_filing(output: Path, *, expected_report_date: str | None = None) -> dict:
    """Extract bounded, exact diagnostic passages from the optional saved 10-K.

    This is a reviewer evidence aid for this evaluation, not a new companyfacts
    mapping or a semantic verification engine. No network access occurs here.
    """
    metadata_path = output / "FILING_PROVENANCE.json"
    if not metadata_path.exists():
        return {}
    from alphalens.filings import _visible_document
    from alphalens.service import _all_filings
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    raw = (output / "visa_latest_10k.html").read_bytes()
    if hashlib.sha256(raw).hexdigest() != metadata["sha256"]:
        raise ValueError("Recorded Visa filing fingerprint changed.")
    if metadata.get("ticker") != "V" or metadata.get("cik") != "0001403161" or metadata.get("report_date") != "2025-09-30":
        raise ValueError("Recorded Visa reviewer context has a different issuer or reporting period.")
    if expected_report_date is not None and metadata["report_date"] != expected_report_date:
        raise ValueError("Recorded Visa reviewer context is not for the current annual comparison.")
    capture_manifest = json.loads((output / "PROVENANCE.json").read_text(encoding="utf-8"))
    submissions_bytes = (output / "visa_submissions.json").read_bytes()
    if hashlib.sha256(submissions_bytes).hexdigest() != capture_manifest["files"]["visa_submissions.json"]["sha256"]:
        raise ValueError("Recorded Visa submissions fingerprint changed.")
    if not any(all(row.get(key) == metadata.get(key) for key in ("form", "filing_date", "report_date", "accession", "url"))
               for row in _all_filings(json.loads(submissions_bytes))):
        raise ValueError("Recorded Visa reviewer context differs from the captured annual filing library.")
    text = _visible_document(raw)[0]
    specs = (
        ("GAAP operating-cost drivers", "GAAP operating expenses increased 30% over the prior year", "expenses."),
        ("Non-GAAP operating-cost drivers (company-defined measure)", "Non-GAAP operating expenses increased 11% over the prior year", "expenses."),
        ("Litigation accruals versus escrow funding", "Interchange multidistrict litigation. During fiscal 2025", "deposits made into the U.S. litigation escrow account."),
        ("Operating-cash-flow drivers and timing", "Operating activities. Cash provided by operating activities increased in fiscal 2025", "payments."),
    )
    passages = {}
    for topic, start_text, end_text in specs:
        start = text.find(start_text)
        end = text.find(end_text, start + len(start_text)) if start >= 0 else -1
        if start < 0 or end < start or end + len(end_text) - start > 1800:
            raise ValueError(f"The expected bounded reviewer disclosure is absent: {topic}")
        end += len(end_text)
        record = {key: metadata[key] for key in ("ticker", "cik", "accession", "url", "report_date", "filing_date")}
        record.update(kind="passage", topic=topic, text=text[start:end], document_sha256=metadata["sha256"],
            offset_start=start, offset_end=end, offset_basis="existing parser's normalized complete visible SEC document",
            retrieved_at=metadata["transport"]["fetched_at"], classification="SEC company disclosure; reviewer-selected, not AI output")
        source_id = "visa-review:" + hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()[:24]
        passages[source_id] = record
    _write(output / "REVIEW_PASSAGES.json", passages)
    return passages


def fetch_recorded_filing(output: Path) -> dict:
    """Explicitly retrieve one 10-K already identified by the saved SEC library."""
    from dotenv import load_dotenv
    from alphalens.service import _all_filings
    manifest = json.loads((output / "PROVENANCE.json").read_text(encoding="utf-8"))
    for name in PAYLOAD_FILES:
        if hashlib.sha256((output / name).read_bytes()).hexdigest() != manifest["files"][name]["sha256"]:
            raise ValueError(f"Saved SEC payload changed: {name}")
    submissions = json.loads((output / "visa_submissions.json").read_text(encoding="utf-8"))
    filing = _all_filings(submissions)[0]
    load_dotenv(ROOT / ".env")
    client = SecClient(os.getenv("SEC_USER_AGENT", ""), ROOT / ".cache/sec")
    html = client.get_text(filing["url"])
    raw = html.encode("utf-8")
    (output / "visa_latest_10k.html").write_bytes(raw)
    provenance = {**filing, "cik": manifest["cik"], "ticker": "V", "sha256": hashlib.sha256(raw).hexdigest(),
        "transport": client.records[-1], "model_requests": 0}
    _write(output / "FILING_PROVENANCE.json", provenance)
    return provenance


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--live", action="store_true", help="Use identified official SEC access; no model requests.")
    mode.add_argument("--replay", action="store_true", help="Verify saved SEC responses without network access.")
    mode.add_argument("--fetch-filing", action="store_true", help="Retrieve the one latest 10-K already identified in saved responses.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        print(json.dumps(fetch_recorded_filing(args.output) if args.fetch_filing else run(args.output, live=args.live), indent=2))
    except (SecError, ValueError, OSError, KeyError) as exc:
        args.output.mkdir(parents=True, exist_ok=True)
        error = {"status": "blocked", "error_type": type(exc).__name__, "message": str(exc),
            "model_requests": 0, "synthetic_data_substituted": False}
        _write(args.output / "BLOCKER.json", error)
        print(json.dumps(error, indent=2))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
