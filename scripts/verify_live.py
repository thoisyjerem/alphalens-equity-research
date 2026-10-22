"""Explicit online integration check; not part of the offline pytest suite."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests
from dotenv import load_dotenv

from alphalens.financials import extract_annuals
from alphalens.sec import SecClient
from alphalens.service import resolve_company


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="Also verify Apple and Amazon")
    parser.add_argument("--output", type=Path, default=Path("outputs/live_verification.json"))
    args = parser.parse_args()
    load_dotenv()
    user_agent = os.getenv("SEC_USER_AGENT", "")

    class RecordingSession(requests.Session):
        verified_urls = []

        def send(self, request, **kwargs):
            # Inspect the actual prepared HTTP request, not a mocked method call.
            if request.headers.get("User-Agent") != user_agent:
                raise AssertionError("Prepared SEC request User-Agent does not match configuration")
            self.verified_urls.append(request.url)
            return super().send(request, **kwargs)

    session = RecordingSession()
    client = SecClient(user_agent, cache_dir="work/live_verification_cache", ttl_hours=0, session=session)
    report = {"checked_at": datetime.now(timezone.utc).isoformat(), "scope": "Actual SEC HTTPS requests; no mocks or fixtures", "companies": []}
    mapping = client.company_tickers()
    for ticker in (["MSFT", "AAPL", "AMZN"] if args.all else ["MSFT"]):
        company = resolve_company(ticker, mapping)
        submissions = client.submissions(company["cik"])
        facts = client.company_facts(company["cik"])
        assert int(facts["cik"]) == int(submissions["cik"]) == int(company["cik"])
        periods = extract_annuals(facts, submissions)
        assert len(periods) == 3
        assert all(period.metrics["revenue"].value is not None for period in periods)
        report["companies"].append({"ticker": ticker, "cik": company["cik"],
            "periods": [{"fiscal_year": p.fiscal_year, "start": p.start, "end": p.end,
                "available_metrics": sum(m.value is not None for m in p.metrics.values()),
                "unavailable": {k: m.reason for k, m in p.metrics.items() if m.value is None}} for p in periods]})
        print(f"PASS {ticker}: three annual periods, revenue present, CIK identity matches")
    report["prepared_user_agent_verified"] = True
    report["verified_request_urls"] = session.verified_urls
    report["pass"] = True
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"PASS User-Agent header verified on {len(session.verified_urls)} actual prepared requests")


if __name__ == "__main__":
    main()
