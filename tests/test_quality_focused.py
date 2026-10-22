"""Evaluate real native-flat output, not a schema-shaped authored substitute."""
import json
from pathlib import Path
import shutil

import pytest

from alphalens.quality import evaluate_focused_bundle, render_evaluation
from scripts.evaluate_research_quality import main

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "outputs/msft_flat_live_2026-10-17"


def test_real_focused_scorecard_replays_all_stages_without_credentials_or_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Offline scorecard must not configure or contact a model")
    monkeypatch.setattr("alphalens.providers.read_ai_config", forbidden)
    monkeypatch.setattr("openai.OpenAI", forbidden)
    monkeypatch.setattr("requests.sessions.Session.request", forbidden)
    report = evaluate_focused_bundle(BUNDLE)
    assert report["bundle_integrity_and_replay_passed"]
    assert report["transport_schema_passed"] and report["compact_schema_passed"]
    assert report["deterministic_assembly_reproduced"] and report["complete_local_validation_passed"]
    assert report["mechanical_counts"] == {"financial_citations_checked": 44, "financial_citations_matched": 44,
        "passage_quotes_checked": 6, "passage_quotes_matched": 6}
    assert report["original_usage"] == {"input_tokens": 5486, "output_tokens": 555, "total_tokens": 6041}
    assert all(row["assessment"] == "not_assessed" and row["score"] is None
               for row in report["qualitative_assessments"])
    assert report["live_request_executed_by_evaluator"] is False
    assert "not this offline replay" in render_evaluation(report)


@pytest.mark.parametrize("filename", ["TRANSPORT_OUTPUT.json", "SOURCE_CATALOG.json"])
def test_changed_bundle_cannot_inherit_source_or_schema_passes(tmp_path, filename):
    directory = tmp_path / "bundle"
    shutil.copytree(BUNDLE, directory)
    (directory / filename).write_text('{"unapproved":"modified content"}', encoding="utf-8")
    report = evaluate_focused_bundle(directory)
    assert not report["complete_local_validation_passed"]
    assert not report["bundle_integrity_and_replay_passed"]
    assert report["schema_passed"] is None and report["parsing_passed"] is None
    assert report["schema_issues"] == [] and report["empty_sections"] == []
    assert report["source_fingerprint"] is None
    assert not report["claims"]
    assert "not established" in render_evaluation(report)


def test_cli_evaluates_current_bundle_without_misreporting_saved_usage_as_new(tmp_path, capsys):
    assert main(["--bundle", str(BUNDLE), "--output-dir", str(tmp_path)]) == 0
    stdout = json.loads(capsys.readouterr().out)
    assert stdout["schema_passed"] and stdout["complete_local_validation_passed"]
    saved = json.loads((tmp_path / "EVALUATION.json").read_text(encoding="utf-8"))
    assert saved["original_usage"]["total_tokens"] == 6041
    assert saved["live_request_executed_by_evaluator"] is False
    assert "not this offline replay" in (tmp_path / "EVALUATION.md").read_text(encoding="utf-8")
