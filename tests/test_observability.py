"""AI attempt audits persist safe metadata only; no network or credentials."""
from copy import deepcopy
import json
from pathlib import Path

from alphalens import observability


FINGERPRINT = "a" * 64


def complete_metadata():
    return {"timestamp_utc": "2026-10-17T12:00:00+00:00", "provider": "gemini",
        "model": "gemini-3.5-flash-lite", "operation": "research_briefing", "status": "completed",
        "http_status": None, "latency_seconds": 2.156,
        "usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
        "parsing_result": "passed", "schema_validation_result": "passed",
        "numerical_validation_result": "passed", "source_validation_result": "partial",
        "validation_stage": "financial_sources", "validation_issues": [], "issues_truncated": False,
        "warning_codes": ["semantic_review_required", "unsupported_claims_quarantined"]}


def read(path):
    assert isinstance(path, Path) and path.is_file()
    return json.loads(path.read_text(encoding="utf-8"))


def test_complete_attempt_is_recorded_with_source_ids_and_distinct_validation_states(tmp_path):
    metadata = complete_metadata()
    original = deepcopy(metadata)
    ids = ["2026:revenue", "sec:" + "b" * 24, "2026:analytics.free_cash_flow_growth", "2026:revenue"]
    record = read(observability.record_attempt(metadata, ids, FINGERPRINT, directory=tmp_path))
    assert record["timestamp_utc"] == metadata["timestamp_utc"]
    assert record["provider"] == "gemini" and record["model"] == "gemini-3.5-flash-lite"
    assert record["usage"] == metadata["usage"] and record["latency_seconds"] == 2.156
    assert record["schema_validation_result"] == record["numerical_validation_result"] == "passed"
    assert record["source_validation_result"] == "partial"
    assert record["input_evidence_ids"] == sorted(set(ids))
    assert record["source_fingerprint"] == FINGERPRINT
    assert "semantic_review_required" in record["warning_codes"]
    assert metadata == original


def test_failure_issue_is_preserved_but_raw_inputs_credentials_and_arbitrary_fields_are_dropped(tmp_path):
    secret = "AIza-fake-sensitive-key-not-a-real-credential"
    metadata = complete_metadata()
    metadata.update({"model": secret, "status": "rejected", "schema_validation_result": "failed",
        "parsing_result": "passed", "validation_stage": "output_schema", "raw_response": secret,
        "request": {"headers": {"Authorization": secret}}, "api_key": secret, "hypothesis": secret,
        "validation_issues": [{"path": "missing_information[0].kind", "type": "missing", "input": secret},
            {"path": secret, "type": secret, "message": secret}],
        "warning_codes": [secret]})
    path = observability.record_attempt(metadata, ["2026:revenue", secret], secret, directory=tmp_path)
    record = read(path)
    assert record["parsing_result"] == "passed" and record["schema_validation_result"] == "failed"
    assert record["validation_issues"][0] == {"path": "missing_information[0].kind", "type": "missing"}
    assert record["validation_issues"][1] == {"path": "[unrecognized_field]", "type": "validation_error"}
    assert record["model"] == "[redacted model identifier]" and record["source_fingerprint"] is None
    assert record["input_evidence_ids"] == ["2026:revenue"]
    assert secret not in path.read_text(encoding="utf-8")
    assert not {"api_key", "request", "raw_response", "hypothesis"} & record.keys()


def test_unavailable_audit_directory_never_raises_or_modifies_existing_file(tmp_path):
    blocking_file = tmp_path / "not-a-directory"
    blocking_file.write_text("preserve existing data", encoding="utf-8")
    assert observability.record_attempt(complete_metadata(), [], FINGERPRINT, directory=blocking_file) is None
    assert blocking_file.read_text(encoding="utf-8") == "preserve existing data"


def test_default_cache_location_and_unique_records_are_local(tmp_path, monkeypatch):
    monkeypatch.setattr(observability, "ROOT", tmp_path)
    first = observability.record_attempt(complete_metadata(), [], FINGERPRINT)
    second = observability.record_attempt(complete_metadata(), [], FINGERPRINT)
    assert first != second
    assert first.parent == second.parent == tmp_path / ".cache" / "ai_runs"
    assert read(first) == read(second)


def test_untrusted_metadata_is_bounded_and_cannot_invent_success_states(tmp_path):
    metadata = complete_metadata()
    metadata.update({"usage": {"input_tokens": True, "output_tokens": -1, "total_tokens": 10 ** 1000,
                               "arbitrary_provider_blob": "private-data"},
        "latency_seconds": float("nan"), "http_status": "200",
        "parsing_result": "private-data", "schema_validation_result": "probably-passed",
        "numerical_validation_result": "yes", "source_validation_result": True,
        "validation_issues": [{"path": "missing_information[0].kind", "type": "missing"}] * 20})
    # A large but well formed source catalog is capped without copying arbitrary inputs.
    ids = [f"2026:{'a' * (index // 26 + 1)}{chr(97 + index % 26)}" for index in range(400)]
    record = read(observability.record_attempt(metadata, ids, FINGERPRINT, directory=tmp_path))
    assert len(record["input_evidence_ids"]) == 300 and record["evidence_ids_truncated"]
    assert len(record["validation_issues"]) == 12 and record["issues_truncated"]
    assert record["usage"] == {} and record["latency_seconds"] is None and record["http_status"] is None
    for name in ("parsing_result", "schema_validation_result", "numerical_validation_result", "source_validation_result"):
        assert record[name] == "not_run"
    assert "private-data" not in json.dumps(record)


def test_optional_openai_model_is_retained_but_credential_shaped_model_is_redacted(tmp_path):
    metadata = complete_metadata()
    metadata.update(provider="openai", model="gpt-4.1-mini", operation="thesis_challenge")
    assert read(observability.record_attempt(metadata, [], FINGERPRINT, directory=tmp_path))["model"] == "gpt-4.1-mini"
    metadata["model"] = "gpt-sk-fake-secret"
    assert read(observability.record_attempt(metadata, [], FINGERPRINT, directory=tmp_path))["model"] == "[redacted model identifier]"


def test_bad_input_shapes_still_write_minimal_safe_record(tmp_path):
    record = read(observability.record_attempt(None, "private-string-instead-of-source-ids", None, directory=tmp_path))
    assert record["provider"] == "unknown" and record["status"] == "incomplete"
    assert record["input_evidence_ids"] == [] and record["source_fingerprint"] is None
    assert record["parsing_result"] == "not_run"
    assert "private-string" not in json.dumps(record)
