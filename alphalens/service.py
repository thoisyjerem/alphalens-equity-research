"""Research orchestration and portable exports; no hidden offline fallbacks."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from alphalens.financials import extract_annuals, metric_definitions
from alphalens.models import ResearchResult
from alphalens.sec import SecClient, SecError

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
load_dotenv(ROOT / ".env")
SUPPORTED = {"MSFT", "AAPL", "AMZN"}


def resolve_company(ticker: str, mapping: dict) -> dict:
    ticker = ticker.strip().upper()
    if not re.fullmatch(r"[A-Z]{1,5}", ticker):
        raise ValueError("Enter a valid ticker: MSFT, AAPL or AMZN.")
    if ticker not in SUPPORTED:
        raise ValueError(f"{ticker} is not supported in this release. Choose MSFT, AAPL or AMZN.")
    for row in mapping.values():
        if isinstance(row, dict) and str(row.get("ticker", "")).upper() == ticker:
            return {"ticker": ticker, "name": row["title"], "cik": SecClient.padded_cik(row["cik_str"])}
    raise ValueError(f"{ticker} was not found in the SEC company ticker mapping. No company was substituted.")


def _read_fixture(name: str) -> dict:
    try:
        return json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SecError(f"Offline fixture {name} is missing or invalid. Restore the bundled fixtures.") from exc


def _validate_fixtures(manifest: dict):
    for name in ("company_tickers.json", "msft_companyfacts.json", "msft_submissions.json"):
        try:
            expected = manifest["files"][name]["sha256"]
            actual = hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest()
        except (OSError, KeyError, TypeError) as exc:
            raise SecError("Offline fixture provenance is incomplete. Restore the original fixtures and manifest.") from exc
        if actual != expected:
            raise SecError(f"Offline fixture integrity check failed for {name}. Restore the original snapshot; changed financial data was not displayed.")


def _all_filings(submissions: dict) -> list[dict]:
    rows = submissions.get("filings", {}).get("recent", {})
    result = []
    for i, form in enumerate(rows.get("form", [])):
        if form not in {"10-K", "10-K/A"}:
            continue
        def cell(key):
            values = rows.get(key, [])
            return values[i] if i < len(values) else ""
        accession = cell("accessionNumber")
        cik = str(int(submissions["cik"]))
        base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/"
        document = cell("primaryDocument")
        result.append({"form": form, "filing_date": cell("filingDate"), "report_date": cell("reportDate"),
                       "accession": accession, "url": base + (document or f"{accession}-index.html")})
    return sorted(result, key=lambda row: row["filing_date"], reverse=True)


def _extend_history(client: SecClient, submissions: dict) -> dict:
    # Some high-volume filers have fewer than three annual reports in recent filings.
    recent = submissions.get("filings", {}).get("recent", {})
    count = len({p["report_date"] for p in _all_filings(submissions) if p["form"] == "10-K"})
    for entry in sorted(submissions.get("filings", {}).get("files", []), key=lambda x: x.get("filingTo", ""), reverse=True):
        if count >= 3:
            break
        name = entry.get("name", "")
        if not re.fullmatch(r"CIK\d{10}-submissions-\d+\.json", name):
            continue
        older = client.get_json(f"https://data.sec.gov/submissions/{name}")
        for key in set(recent) | set(older):
            recent[key] = recent.get(key, []) + older.get(key, [""] * len(older.get("form", [])))
        count = len({p["report_date"] for p in _all_filings(submissions) if p["form"] == "10-K"})
    return submissions


def load_research(ticker: str, mode: str = "offline", user_agent: str = "") -> ResearchResult:
    ticker = ticker.strip().upper()
    # Validate before creating a network client or fetching data.
    if ticker not in SUPPORTED:
        raise ValueError("Choose MSFT, AAPL or AMZN. Other symbols are not supported in this release.")
    warnings = []
    if mode == "offline":
        if ticker != "MSFT":
            raise ValueError("Offline demonstration includes Microsoft only. Select MSFT or use live SEC mode for AAPL / AMZN.")
        manifest = _read_fixture("manifest.json")
        _validate_fixtures(manifest)
        mapping = _read_fixture("company_tickers.json")
        company = resolve_company(ticker, mapping)
        facts = _read_fixture("msft_companyfacts.json")
        submissions = _read_fixture("msft_submissions.json")
        stamp = manifest.get("captured_at", manifest.get("retrieved_at", "See fixture manifest"))
        warnings.append("OFFLINE DEMONSTRATION: checked-in SEC snapshot, not a fresh SEC download or live market data.")
    elif mode == "live":
        try:
            ttl = float(os.getenv("SEC_CACHE_TTL_HOURS", "24"))
        except ValueError as exc:
            raise ValueError("SEC_CACHE_TTL_HOURS must be a number.") from exc
        client = SecClient(user_agent or os.getenv("SEC_USER_AGENT", ""), ROOT / ".cache/sec", ttl)
        company = resolve_company(ticker, client.company_tickers())
        submissions = _extend_history(client, client.submissions(company["cik"]))
        facts = client.company_facts(company["cik"])
        stamp = min(row["fetched_at"] for row in client.records)
        if any(row["cached"] for row in client.records):
            warnings.append("One or more official SEC responses came from the local cache (maximum age set by SEC_CACHE_TTL_HOURS).")
        for row in client.records:
            warnings.append(f"SEC response {'cached' if row['cached'] else 'downloaded'}: {row['url']} | retrieved {row['fetched_at']}")
    else:
        raise ValueError("Data mode must be offline or live.")
    if str(int(facts.get("cik", 0))) != str(int(company["cik"])) or str(int(submissions.get("cik", 0))) != str(int(company["cik"])):
        raise SecError("SEC company identifiers disagree; analysis stopped to avoid showing another issuer's figures.")
    periods = extract_annuals(facts, submissions, years=3)
    if not periods:
        raise SecError("No completed annual 10-K periods could be verified in this company's SEC facts.")
    if len(periods) < 3:
        warnings.append(f"Only {len(periods)} verified annual periods were available; missing years were not estimated.")
    annual_ends = sorted({row["report_date"] for row in _all_filings(submissions)
                          if row["form"] == "10-K" and row["report_date"]}, reverse=True)[:3]
    represented_ends = {period.end for period in periods}
    absent = [end for end in annual_ends if end not in represented_ends]
    if absent:
        warnings.append("Recent annual filings have no verifiable supported annual duration: " + ", ".join(absent)
            + ". Displayed periods can therefore be older than the latest completed fiscal year; no start dates or values were inferred.")
    warnings.append("Annual reported US-GAAP facts only. Company-specific extensions, segment data and market prices are outside this release.")
    return ResearchResult(ticker=company["ticker"], name=submissions.get("name", company["name"]), cik=company["cik"],
        periods=periods, mode=mode, retrieved_at=stamp, warnings=warnings, filings=_all_filings(submissions))


def snapshot_json(result: ResearchResult) -> str:
    payload = asdict(result)
    payload["data_status"] = "OFFLINE DEMONSTRATION — SEC snapshot" if result.mode == "offline" else "SEC annual reported financials (may use cache)"
    payload["definitions"] = metric_definitions()
    from .analytics import build_analytics
    payload["annual_analysis"] = build_analytics(result)
    return json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False)


def load_filing_excerpts(result: ResearchResult, accession: str, user_agent: str = "") -> dict:
    """Fetch only an annual document already present in this issuer's SEC library."""
    if result.mode != "live":
        raise ValueError("The filing reader downloads SEC documents only in live mode. Offline mode keeps all analysis local.")
    matches = [row for row in result.filings if row["accession"] == accession]
    if not matches:
        raise ValueError("Choose an annual filing from the displayed SEC filing library.")
    from .filings import extract_filing_excerpts
    client = SecClient(user_agent or os.getenv("SEC_USER_AGENT", ""), ROOT / ".cache/sec")
    return extract_filing_excerpts(client.get_text(matches[0]["url"]))


def make_filing_context(result: ResearchResult, accession: str, excerpts: dict) -> dict:
    """Bind retrieved excerpts to an actual filing in this issuer's library.

    The original reader did not return its retrieval time, so do not invent one.
    New retrievals should use load_research_filing_context for full metadata.
    """
    matches = [row for row in result.filings if row["accession"] == accession]
    if not matches:
        raise ValueError("Filing context must belong to this company's SEC filing library.")
    row = matches[0]
    return {"ticker": result.ticker, "cik": result.cik, "accession": accession,
            "url": row["url"], "report_date": row["report_date"], "filing_date": row["filing_date"],
            "retrieved_at": None, "retrieval_note": "Legacy session excerpt; document retrieval timestamp was not recorded.",
            "mode": result.mode, "excerpts": excerpts}


def load_research_filing_context(result: ResearchResult, accession: str, user_agent: str = "") -> dict:
    """Explicit SEC retrieval for optional AI; never called automatically."""
    if result.mode != "live":
        raise ValueError("Use the checked-in SEC passage snapshot in offline mode.")
    context = make_filing_context(result, accession, {})
    from .filings import extract_filing_excerpts
    from .retrieval import select_filing_passages
    client = SecClient(user_agent or os.getenv("SEC_USER_AGENT", ""), ROOT / ".cache/sec")
    html = client.get_text(context["url"])
    context.update(excerpts=extract_filing_excerpts(html), retrieved_at=client.records[-1]["fetched_at"],
                   retrieval_note="Official SEC document; may use the identified client's disk cache.",
                   document_sha256=hashlib.sha256(html.encode("utf-8")).hexdigest(),
                   focused_passages=select_filing_passages(html))
    return context


def load_offline_filing_context(result: ResearchResult) -> dict:
    """Load hash-checked, genuine SEC narrative excerpts, labelled offline."""
    if result.mode != "offline" or result.ticker != "MSFT":
        raise ValueError("The offline SEC passage snapshot is available for Microsoft offline mode only.")
    manifest = _read_fixture("research_manifest.json")
    name = "msft_research_passages.json"
    try:
        raw = (FIXTURES / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != manifest["sha256"]:
            raise SecError("Offline SEC passage integrity check failed. Restore the original research fixtures.")
        payload = json.loads(raw)
    except (OSError, KeyError, ValueError) as exc:
        raise SecError("Offline SEC passage provenance is missing or invalid.") from exc
    from .filings import FilingExcerpt
    excerpts = {key: FilingExcerpt(**value) for key, value in payload["excerpts"].items()}
    context = make_filing_context(result, payload["accession"], excerpts)
    for key in ("ticker", "cik", "url", "report_date", "filing_date"):
        if str(payload[key]).lstrip("0") != str(context[key]).lstrip("0"):
            raise SecError("Offline SEC passage metadata disagrees with the selected issuer's filing.")
    context.update(mode="offline", retrieved_at=payload["retrieved_at"],
                   retrieval_note="OFFLINE DEMONSTRATION — checked-in genuine SEC passage snapshot, not a fresh retrieval.",
                   document_sha256=payload["document_sha256"])
    return context


def snapshot_csv(result: ResearchResult) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=["data_status", "ticker", "cik", "retrieved_at", "fiscal_year", "period_start", "period_end", "period_type",
        "metric", "value", "unit", "missing_reason", "sources_json"])
    writer.writeheader()
    for period in result.periods:
        for key, metric in period.metrics.items():
            instant = key in {"cash_and_equivalents", "total_debt", "net_debt"}
            writer.writerow({"data_status": "OFFLINE DEMONSTRATION" if result.mode == "offline" else "SEC reported (live/cache)",
                "ticker": result.ticker, "cik": result.cik, "retrieved_at": result.retrieved_at,
                "fiscal_year": period.fiscal_year, "period_start": None if instant else period.start,
                "period_end": period.end, "period_type": "instant" if instant else "duration", "metric": key,
                "value": metric.value if metric.value is not None else "N/A", "unit": metric.unit,
                "missing_reason": metric.reason, "sources_json": json.dumps([asdict(s) for s in metric.sources])})
    return output.getvalue()


def build_observations(result: ResearchResult) -> list[str]:
    """Render checked analytics; never create a second comparison policy."""
    from .analytics import build_analytics
    analysis = build_analytics(result)
    latest = max(result.periods, key=lambda period: period.end, default=None)
    rows = {row["metric"]: row for row in analysis["metrics"]
            if latest is not None and row["fiscal_year"] == latest.fiscal_year}
    observations = []
    for key, label in [("revenue_growth", "Revenue"), ("operating_income_growth", "Operating income")]:
        row = rows.get(key)
        if row is not None and row["value"] is not None:
            prior, current = row["comparison_periods"]
            observations.append(f"{label} changed {row['value']:+.1%} between fiscal years ended {prior['period_end']} and {current['period_end']} (Python calculation).")
        elif row is not None:
            observations.append(f"{label} comparison is N/A: {row['reason']}")
    for key, label in [("operating_margin", "Operating margin"), ("free_cash_flow", "Free cash flow")]:
        row = rows.get(key)
        if row is not None and row["value"] is not None:
            text = f"{row['value']:.1%}" if key == "operating_margin" else f"USD {row['value'] / 1e9:,.2f}bn"
            observations.append(f"{label} for the fiscal year ended {row['period_end']}: {text}; see inputs and source periods in the audit table.")
        elif row is not None:
            observations.append(f"{label} is N/A: {row['reason']}")
    observations.append("Research question: how sustainable are operating margins and cash generation? Financial statements alone do not establish a valuation or investment recommendation.")
    return observations
