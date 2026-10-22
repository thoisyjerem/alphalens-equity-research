"""Replay saved research with no network, credential loading or model calls."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alphalens.quality import evaluate_focused_bundle, evaluate_saved_report, render_evaluation


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--response", type=Path,
        default=ROOT / "fixtures/gemini_schema_failure/brief.complete_response.json")
    source.add_argument("--bundle", type=Path,
        help="Replay a complete accepted focused bundle, including native fields and Python assembly")
    parser.add_argument("--source-catalog", type=Path,
        default=ROOT / "fixtures/gemini_http400/brief.request.json")
    parser.add_argument("--feature", choices=("brief", "challenge"), default="brief")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs/research_quality_offline_2026-10-17")
    args = parser.parse_args(argv)
    if args.bundle is not None and args.feature != "brief":
        parser.error("--bundle supports the focused briefing only; thesis uses the original --response replay.")
    report = (evaluate_focused_bundle(args.bundle) if args.bundle is not None else
              evaluate_saved_report(args.response, args.source_catalog, feature=args.feature))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "EVALUATION.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (args.output_dir / "EVALUATION.md").write_text(render_evaluation(report), encoding="utf-8")
    print(json.dumps({"offline_replay_completed": True, "schema_passed": report["schema_passed"],
        "complete_local_validation_passed": report["complete_local_validation_passed"],
        "mechanical_counts": report["mechanical_counts"], "output_directory": str(args.output_dir)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
