"""The genuine recorded briefing remains demonstrable with all remote access denied.

This replays an actual saved Gemini response. No authored response replaces it.
"""
import builtins
import io
import json
import os
from pathlib import Path

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "outputs/msft_findings_live_2026-10-18"


def test_genuine_recorded_demo_sources_and_exports_need_neither_dotenv_nor_http(monkeypatch):
    from alphalens import providers, research_exports, service

    def forbidden(*args, **kwargs):
        raise AssertionError("Recorded demonstration attempted credentials or remote access")

    # The ordinary dashboard may inspect empty local configuration, but this
    # demonstration must not need to read the owner's actual configuration file.
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: False)
    monkeypatch.setattr(providers, "load_dotenv", lambda *args, **kwargs: False)
    monkeypatch.setattr(service, "load_dotenv", lambda *args, **kwargs: False)
    original_open, original_io_open = builtins.open, io.open

    def checked_open(original):
        def open_without_env(file, *args, **kwargs):
            if isinstance(file, (str, bytes, Path)) and Path(os.fsdecode(file)).name == ".env":
                forbidden()
            return original(file, *args, **kwargs)
        return open_without_env

    monkeypatch.setattr(builtins, "open", checked_open(original_open))
    monkeypatch.setattr(io, "open", checked_open(original_io_open))
    monkeypatch.setattr("openai.OpenAI", forbidden)
    monkeypatch.setattr(providers, "request_structured", forbidden)
    monkeypatch.setattr("httpx.Client.send", forbidden)
    monkeypatch.setattr("httpx.AsyncClient.send", forbidden)
    monkeypatch.setattr("requests.Session.request", forbidden)
    monkeypatch.setattr("urllib.request.urlopen", forbidden)
    monkeypatch.setattr("http.client.HTTPConnection.request", forbidden)

    original = json.loads((BUNDLE / "RESEARCH_BRIEFING.json").read_text(encoding="utf-8"))
    exported = {}
    actual_markdown = research_exports.export_research_markdown
    actual_json = research_exports.export_research_json

    def export_markdown(validated):
        exported["markdown"] = actual_markdown(validated)
        return exported["markdown"]

    def export_json(validated):
        payload = actual_json(validated)
        exported["json"] = json.loads(payload)
        return payload

    monkeypatch.setattr(research_exports, "export_research_markdown", export_markdown)
    monkeypatch.setattr(research_exports, "export_research_json", export_json)

    app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
    assert not app.exception
    assert app.selectbox(key="source_mode").value == "Offline SEC fixture"
    for key in ("generate_ai", "generate_research_brief", "generate_thesis"):
        assert app.button(key=key).disabled
    app.button(key="load_saved_msft_briefing").click().run(timeout=30)
    assert not app.exception
    recorded = app.session_state["saved_msft_briefing"]
    assert recorded.contract == "focused_v3"
    assert recorded.verification.unsupported_count == 0
    assert recorded.output.model_dump(mode="json") == original["assembled_report"]
    assert recorded.transport_output == original["raw_model_output"]
    assert recorded.evidence == original["source_catalog"]
    assert any("SAVED LIVE DEMONSTRATION" in row.value for row in app.info)
    assert any("not a new API result" in row.value for row in app.warning)
    assert any("Analyst review is required" in row.value for row in app.warning)

    # AppTest includes expander contents: inspect the actual bound financial
    # records and exact quotations, not merely the existence of source buttons.
    financial_ids, quotes = set(), set()
    for checked in recorded.verification.claims:
        financial_ids.update(citation.source_id for citation in checked.claim.financial_citations)
        for citation in checked.claim.passage_citations:
            assert citation.quote in recorded.evidence[citation.source_id]["text"]
            quotes.add(citation.quote)
    captions = [row.value for row in app.caption]
    text = [row.value for row in app.text]
    assert financial_ids and quotes
    assert all(f"Financial source: {source_id}" in captions for source_id in financial_ids)
    # Streamlit normalises display whitespace; saved quote membership above is
    # checked exactly before the presentation-only whitespace comparison.
    assert all(any(" ".join(quote.split()) in " ".join(value.split()) for value in text) for quote in quotes)
    assert any(row.label == "Inspect Python financial observations" for row in app.expander)
    assert any(row.label == "Surrounding recorded filing context" for row in app.expander)
    assert any("not an additional model citation" in value
               and "not necessarily sent to Gemini" in value for value in captions)
    cash_flow_parent = next(source["text"] for source in recorded.evidence.values()
                            if source["kind"] == "passage"
                            and "$22.2 billion increase in cash used in other investing" in source["text"])
    assert any(" ".join(cash_flow_parent.split()) == " ".join(value.split()) for value in text)
    assert "Cash from operations increased $46.8 billion" in cash_flow_parent
    assert "decrease in cash used to pay income taxes" in cash_flow_parent
    assert "primarily to facilitate the purchase of components" in cash_flow_parent

    app.toggle(key="saved_msft_export_toggle").set_value(True).run(timeout=30)
    assert not app.exception and len(app.get("download_button")) == 4
    assert len(app.metric) == 4
    assert exported["json"]["assembled_report"] == original["assembled_report"]
    assert exported["json"]["raw_model_output"] == original["raw_model_output"]
    assert exported["json"]["source_catalog"] == original["source_catalog"]
    assert exported["json"]["metadata"]["semantic_review"] == "requires_analyst_review"
    assert "SAVED LIVE DEMONSTRATION" in exported["markdown"]
    assert "not establish semantic support" in exported["markdown"]


def test_source_inspection_does_not_display_parent_from_another_accession():
    """An existing ID cannot legitimise mismatched surrounding disclosure."""
    from copy import deepcopy
    from alphalens.saved_research import load_saved_briefing

    recorded = load_saved_briefing()
    claim = next(checked.claim for checked in recorded.verification.claims
                 if any(recorded.evidence[citation.source_id].get("parent_source_id")
                        for citation in checked.claim.passage_citations))
    source = recorded.evidence[claim.passage_citations[0].source_id]
    parent_id = source["parent_source_id"]
    evidence = deepcopy(recorded.evidence)
    evidence[parent_id]["accession"] = "unrelated-accession"

    def source_view(claim_data, evidence_data):
        from alphalens.research import Claim
        from alphalens.research_ui import _show_claim_sources
        _show_claim_sources(Claim.model_validate(claim_data), evidence_data, "provenance_guard")

    app = AppTest.from_function(source_view, args=(claim.model_dump(mode="json"), evidence)).run(timeout=30)
    assert not app.exception
    assert any("could not be matched to this source window" in row.value for row in app.caption)
    assert not any(row.label == "Surrounding recorded filing context" for row in app.expander)
    assert any(" ".join(claim.passage_citations[0].quote.split()) == " ".join(row.value.split())
               for row in app.text)
