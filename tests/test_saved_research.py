"""Replay the actual accepted Microsoft response without inference or retrieval."""
import hashlib
import json
from pathlib import Path

import pytest

from alphalens import saved_research
from alphalens.research_exports import export_research_json, export_research_markdown


ACTUAL_BUNDLE = Path(__file__).resolve().parents[1] / "outputs/msft_flat_live_2026-10-17"


@pytest.fixture
def saved_bundle(tmp_path, monkeypatch):
    directory = tmp_path / "outputs/msft_flat_live_2026-10-17"
    directory.mkdir(parents=True)
    for name in saved_research._FILES:
        (directory / name).write_bytes((ACTUAL_BUNDLE / name).read_bytes())
    write_manifest(directory)
    monkeypatch.setattr(saved_research, "ROOT", tmp_path)
    monkeypatch.setattr(saved_research, "_BUNDLE", Path("outputs/msft_flat_live_2026-10-17"))
    return directory


def write_manifest(directory):
    manifest = {"files": {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                          for name in saved_research._FILES}}
    (directory / "DEMO_MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")


def replace_json(directory, name, update):
    value = json.loads((directory / name).read_text(encoding="utf-8"))
    update(value)
    (directory / name).write_text(json.dumps(value), encoding="utf-8")
    write_manifest(directory)


def snapshot(directory):
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in directory.iterdir()}


def test_actual_saved_briefing_revalidates_and_exports_without_network_configuration_or_mutations(saved_bundle, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Saved demonstration attempted credentials, inference or network access")

    monkeypatch.setattr("openai.OpenAI", forbidden)
    monkeypatch.setattr("alphalens.providers.read_ai_config", forbidden)
    monkeypatch.setattr("alphalens.providers.request_structured", forbidden)
    monkeypatch.setattr("httpx.Client.send", forbidden)
    monkeypatch.setattr("requests.Session.request", forbidden)
    before = snapshot(saved_bundle)
    assert saved_research.available_saved_briefing()
    validated = saved_research.load_saved_briefing()
    assert validated.provider == "gemini"
    assert validated.model == "gemini-3.5-flash-lite"
    assert validated.contract == "focused_v2"
    assert validated.transport_output is not None
    assert validated.verification.unsupported_count == 0
    assert validated.usage == {"input_tokens": 5486, "output_tokens": 555, "total_tokens": 6041}
    assert validated.latency_seconds == 3.313
    assert "2026:cash_flow_divergence" in validated.financial_observations
    assert "SAVED LIVE DEMONSTRATION" in validated.warnings[-1]
    exported = json.loads(export_research_json(validated))
    original = json.loads((saved_bundle / "RESEARCH_BRIEFING.json").read_text(encoding="utf-8"))
    assert exported["assembled_report"] == original["assembled_report"]
    assert exported["verification"] == original["verification"]
    assert exported["source_catalog"] == original["source_catalog"]
    assert exported["raw_model_output"] == original["raw_model_output"]
    assert exported["warnings"][-1].startswith("SAVED LIVE DEMONSTRATION")
    assert "SAVED LIVE DEMONSTRATION" in export_research_markdown(validated)
    assert snapshot(saved_bundle) == before


def test_missing_bundle_is_unavailable_and_fails_with_safe_message(tmp_path, monkeypatch):
    private = tmp_path / "private-user-directory"
    monkeypatch.setattr(saved_research, "ROOT", private)
    assert not saved_research.available_saved_briefing()
    with pytest.raises(ValueError, match="could not be revalidated") as caught:
        saved_research.load_saved_briefing()
    assert "private-user-directory" not in str(caught.value)


@pytest.mark.parametrize("missing", ["DEMO_MANIFEST.json", "SOURCE_CATALOG.json", "TRANSPORT_OUTPUT.json"])
def test_incomplete_bundle_is_unavailable_and_never_partially_loaded(saved_bundle, missing):
    (saved_bundle / missing).unlink()
    assert not saved_research.available_saved_briefing()
    with pytest.raises(ValueError, match="no API request was made"):
        saved_research.load_saved_briefing(saved_bundle)


def test_changed_file_is_rejected_by_original_manifest(saved_bundle):
    with (saved_bundle / "TRANSPORT_OUTPUT.json").open("a", encoding="utf-8") as handle:
        handle.write(" ")
    with pytest.raises(ValueError, match="could not be revalidated"):
        saved_research.load_saved_briefing(saved_bundle)


def test_changed_hash_is_rejected(saved_bundle):
    manifest = json.loads((saved_bundle / "DEMO_MANIFEST.json").read_text(encoding="utf-8"))
    manifest["files"]["TRANSPORT_OUTPUT.json"] = "0" * 64
    (saved_bundle / "DEMO_MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        saved_research.load_saved_briefing(saved_bundle)


def test_manifest_cannot_supply_dynamic_paths(saved_bundle):
    manifest = json.loads((saved_bundle / "DEMO_MANIFEST.json").read_text(encoding="utf-8"))
    manifest["files"]["../../.env"] = "0" * 64
    (saved_bundle / "DEMO_MANIFEST.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        saved_research.load_saved_briefing(saved_bundle)


@pytest.mark.parametrize("changes", [
    {"http_status": 400}, {"http_requests_attempted": 2}, {"http_requests_attempted": True},
    {"maximum_http_requests": 2}, {"provider": "openai"}, {"reported_model": "another-model"},
    {"automatic_retries": True}, {"provider_fallback": True}, {"billing_changes": True},
    {"status": "rejected"}, {"unsupported_claims": 1}, {"finish_reasons": ["length"]},
    {"normalized_usage": {"input_tokens": 5486, "output_tokens": 556, "total_tokens": 6042}},
    {"adapter_latency_seconds": 99},
])
def test_rejected_or_inconsistent_ledger_cannot_be_promoted_by_updated_hashes(saved_bundle, changes):
    replace_json(saved_bundle, "REQUEST_LEDGER.json", lambda value: value.update(changes))
    with pytest.raises(ValueError, match="could not be revalidated"):
        saved_research.load_saved_briefing(saved_bundle)


@pytest.mark.parametrize("changes", [
    {"primary_passage_ids": ["sec:fabricated-source"]},
    {"primary_interpretation": "Microsoft free cash flow grew by 100 percent in 2026."},
    {"primary_limitations": []},
])
def test_changed_model_content_still_faces_original_schema_and_source_checks(saved_bundle, changes):
    replace_json(saved_bundle, "TRANSPORT_OUTPUT.json", lambda value: value.update(changes))
    with pytest.raises(ValueError):
        saved_research.load_saved_briefing(saved_bundle)


@pytest.mark.parametrize("name, update", [
    ("ASSEMBLED_REPORT.json", lambda value: value["what_matters_most"][0].update(text="Different unreviewed interpretation.")),
    ("VALIDATION.json", lambda value: value["claims"][0].update(status="unsupported")),
    ("RESEARCH_BRIEFING.json", lambda value: value["metadata"].update(semantic_review="approved")),
    ("FINANCIAL_OBSERVATIONS.json", lambda value: value["2026:cash_flow_divergence"].update(title="A changed observation.")),
])
def test_changed_report_verification_or_observation_never_inherits_original_acceptance(saved_bundle, name, update):
    replace_json(saved_bundle, name, update)
    with pytest.raises(ValueError):
        saved_research.load_saved_briefing(saved_bundle)


@pytest.mark.parametrize("content", [b'{"unfinished":', b'{"duplicate":1,"duplicate":2}', b'{"value":NaN}'])
def test_invalid_json_fails_safely_without_model_text_in_error(saved_bundle, content):
    (saved_bundle / "TRANSPORT_OUTPUT.json").write_bytes(content)
    write_manifest(saved_bundle)
    with pytest.raises(ValueError) as caught:
        saved_research.load_saved_briefing(saved_bundle)
    assert "unfinished" not in str(caught.value)
    assert "duplicate" not in str(caught.value)


def test_oversized_file_is_rejected_before_loading(saved_bundle):
    (saved_bundle / "TRANSPORT_OUTPUT.json").write_bytes(b" " * (saved_research._MAX_FILE_BYTES + 1))
    write_manifest(saved_bundle)
    with pytest.raises(ValueError):
        saved_research.load_saved_briefing(saved_bundle)


@pytest.fixture
def authored_v3_bundle(saved_bundle):
    """A declared mock v3 result over genuine historical evidence, not inference."""
    from alphalens.ai import ValidatedResearch
    from alphalens.focused_briefing import (
        BriefingContext, FindingInterpretations, _fingerprint, assemble_briefing, assembly_fingerprint,
    )
    from alphalens.gemini_briefing import GeminiFindingFields

    files = {name: json.loads((saved_bundle / name).read_text(encoding="utf-8"))
             for name in saved_research._FILES}
    old_wire = files["TRANSPORT_OUTPUT.json"]
    wire = GeminiFindingFields.model_validate({
        key: value for key, value in old_wire.items() if not key.startswith("executive_")})
    wire.additional_observation_id = "2026:revenue_profit_growth"
    wire.additional_interpretation = (
        "Revenue and operating income grew, which may indicate stronger operating earnings before investment outlays.")
    wire.additional_passage_ids = old_wire["executive_passage_ids"]
    wire.additional_alternative_explanation = (
        "Foreign currency effects or revenue mix could explain some reported growth.")
    wire.additional_limitations = ["Reported growth does not establish recurring demand or future monetisation."]
    packet = files["FOCUSED_CONTEXT.json"]
    packet["required_additional_observation_id"] = wire.additional_observation_id
    book, analysis, observations = (files[name] for name in
        ("SOURCE_CATALOG.json", "FINANCIAL_ANALYSIS.json", "FINANCIAL_OBSERVATIONS.json"))
    context = BriefingContext(book, analysis, observations, packet, _fingerprint(book, analysis, observations, packet))
    interpretation = FindingInterpretations.model_validate(wire.compact_payload())
    report, verification = assemble_briefing(interpretation, context)
    usage = {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}
    diagnostics = {**files["RESEARCH_BRIEFING.json"]["metadata"]["diagnostics"],
                   "usage": usage, "latency_seconds": 0.01}
    validated = ValidatedResearch(output=report, verification=verification, evidence=book,
        model="gemini-3.5-flash-lite", warnings=["AUTHORED OFFLINE MOCK — no new model request or live evaluation."],
        provider="gemini", usage=usage, latency_seconds=0.01, analysis=analysis, diagnostics=diagnostics,
        model_interpretation=interpretation.model_dump(mode="json"), financial_observations=observations,
        contract="focused_v3", transport_output=wire.model_dump(mode="json"))
    validated.assembly_fingerprint = assembly_fingerprint(validated)
    ledger = files["REQUEST_LEDGER.json"]
    ledger.update(approval="Authored offline test fixture; no live request made", normalized_usage=usage,
                  reported_usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
                  adapter_latency_seconds=0.01)
    files.update({"TRANSPORT_OUTPUT.json": wire.model_dump(mode="json"),
                  "ASSEMBLED_REPORT.json": report.model_dump(mode="json"),
                  "VALIDATION.json": verification.model_dump(mode="json"),
                  "RESEARCH_BRIEFING.json": json.loads(export_research_json(validated))})
    directory = saved_bundle.parent / "authored_focused_v3"
    directory.mkdir()
    for name, value in files.items():
        (directory / name).write_text(json.dumps(value), encoding="utf-8")
    write_manifest(directory)
    return directory


def test_v3_mock_replay_reassembles_python_executive_and_preserves_original_v2(saved_bundle, authored_v3_bundle, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Versioned replay attempted inference or retrieval")
    monkeypatch.setattr("openai.OpenAI", forbidden)
    monkeypatch.setattr("httpx.Client.send", forbidden)
    monkeypatch.setattr("requests.Session.request", forbidden)
    old = saved_research.load_saved_briefing(saved_bundle)
    new = saved_research.load_saved_briefing(authored_v3_bundle)
    assert old.contract == "focused_v2" and new.contract == "focused_v3"
    assert len(old.transport_output) == 16 and len(new.transport_output) == 13
    assert not any(key.startswith("executive_") for key in new.transport_output)
    assert new.output.executive_summary == new.output.what_matters_most
    assert new.output.executive_summary[0] is not new.output.what_matters_most[0]
    assert new.verification.unsupported_count == 0
    assert new.usage == {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150}
    assert "AUTHORED OFFLINE MOCK" in export_research_markdown(new)
    assert json.loads(export_research_json(new))["metadata"]["contract"] == "focused_v3"


def test_new_default_is_explicit_and_does_not_fall_back_to_existing_v2(saved_bundle, authored_v3_bundle, monkeypatch):
    monkeypatch.setattr(saved_research, "_BUNDLE", authored_v3_bundle.relative_to(saved_research.ROOT))
    assert saved_research.available_saved_briefing()
    assert saved_research.load_saved_briefing().contract == "focused_v3"
    (authored_v3_bundle / "TRANSPORT_OUTPUT.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        saved_research.load_saved_briefing()
    assert saved_research.load_saved_briefing(saved_bundle).contract == "focused_v2"


@pytest.mark.parametrize("changes", [
    {"executive_interpretation": "An undeclared model summary must be rejected."},
    {"primary_passage_ids": ["sec:invented"]},
    {"additional_observation_id": "2026:invented-observation"},
])
def test_v3_replay_cannot_bypass_contract_or_source_checks(authored_v3_bundle, changes):
    replace_json(authored_v3_bundle, "TRANSPORT_OUTPUT.json", lambda value: value.update(changes))
    with pytest.raises(ValueError):
        saved_research.load_saved_briefing(authored_v3_bundle)


def test_unknown_contract_is_rejected_instead_of_inferred_from_wire_shape(saved_bundle):
    replace_json(saved_bundle, "RESEARCH_BRIEFING.json", lambda value: value["metadata"].update(contract="focused_future"))
    with pytest.raises(ValueError):
        saved_research.load_saved_briefing(saved_bundle)


def test_bundle_identity_changes_with_selection_or_manifest_and_is_not_acceptance(saved_bundle, authored_v3_bundle):
    original = saved_research.saved_briefing_identity(saved_bundle)
    assert original and original != saved_research.saved_briefing_identity(authored_v3_bundle)
    with (saved_bundle / "DEMO_MANIFEST.json").open("a", encoding="utf-8") as handle:
        handle.write(" ")
    assert saved_research.saved_briefing_identity(saved_bundle) != original
    assert saved_research.saved_briefing_identity(saved_bundle / "missing") is None


def test_v3_recorded_ui_works_without_key_and_does_not_invent_old_review_flags(authored_v3_bundle, monkeypatch):
    from streamlit.testing.v1 import AppTest
    def forbidden(*args, **kwargs):
        pytest.fail("Recorded UI attempted inference")
    monkeypatch.setattr("openai.OpenAI", forbidden)
    monkeypatch.setattr(saved_research, "_BUNDLE", authored_v3_bundle.relative_to(saved_research.ROOT))
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(timeout=30)
    app.button(key="load_saved_msft_briefing").click().run(timeout=30)
    assert not app.exception
    assert app.session_state["saved_msft_briefing"].contract == "focused_v3"
    assert not any("tax receipts" in message.value for message in app.info)
    assert any(item.label == "Inspect Python financial observations" for item in app.expander)
    for key in ("generate_ai", "generate_research_brief", "generate_thesis"):
        assert app.button(key=key).disabled
    app.toggle(key="saved_msft_export_toggle").set_value(True).run(timeout=30)
    assert not app.exception and len(app.get("download_button")) == 4
    assert not any("Disclosed business developments" == item.value for item in app.markdown)


def test_recorded_ui_clears_stale_result_when_default_bundle_changes(saved_bundle, authored_v3_bundle, monkeypatch):
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(timeout=30)
    app.button(key="load_saved_msft_briefing").click().run(timeout=30)
    assert app.session_state["saved_msft_briefing"].contract == "focused_v2"
    previous = app.session_state["saved_msft_briefing_identity"]
    monkeypatch.setattr(saved_research, "_BUNDLE", authored_v3_bundle.relative_to(saved_research.ROOT))
    app.run(timeout=30)
    assert not app.exception
    assert app.session_state["saved_msft_briefing"] is None
    assert app.session_state["saved_msft_briefing_identity"] != previous
    app.button(key="load_saved_msft_briefing").click().run(timeout=30)
    assert not app.exception and app.session_state["saved_msft_briefing"].contract == "focused_v3"
