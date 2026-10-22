"""Portable command-line smoke test and provenance-rich JSON export."""
import argparse
from pathlib import Path

from .service import load_research, snapshot_json


def main():
    parser = argparse.ArgumentParser(description="AlphaLens annual SEC research")
    parser.add_argument("--ticker", default="MSFT")
    parser.add_argument("--mode", choices=["offline", "live"], default="offline")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = load_research(args.ticker, args.mode)
    except (ValueError, RuntimeError) as exc:
        parser.exit(1, f"AlphaLens: {exc}\n")
    payload = snapshot_json(result)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
        print(f"Saved {result.mode} {result.ticker} snapshot: {args.output}")
    else:
        print(payload)


if __name__ == "__main__":
    main()
