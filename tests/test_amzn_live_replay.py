"""Replay the actual approved Amazon response through SDK, validation and UI.

This is saved-output replay over a mock HTTP transport, never new inference.
"""
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import httpx
from openai import OpenAI
from streamlit.testing.v1 import AppTest

from alphalens.models import ResearchResult, AnnualPeriod, MetricValue, SourceFact
from alphalens.providers import GEMINI_BASE_URL


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures/amzn_commentary_live_2026-10-19"


def test_actual_amazon_response_replays_unmodified_through_production_sdk_and_dashboard(monkeypatch, tmp_path):
    from alphalens import commentary, observability, service
    from alphalens.evidence import evidence_fingerprint

    manifest = json.loads((FIXTURE / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["origin"] == "actual_single_approved_Gemini_request"
    for name, expected_hash in manifest["sha256"].items():
        assert hashlib.sha256((FIXTURE / name).read_bytes()).hexdigest() == expected_hash
    snapshot = json.loads((ROOT / manifest["source_fixture"]).read_text(encoding="utf-8"))
    snapshot["periods"] = [AnnualPeriod(**{**p, "metrics": {
        key: MetricValue(**{**m, "sources": [SourceFact(**s) for s in m["sources"]]})
        for key, m in p["metrics"].items()}}) for p in snapshot["periods"]]
    amazon = replace(ResearchResult(**snapshot), mode="live")
    context = commentary.build_commentary_context(amazon)
    assert evidence_fingerprint(context.evidence) == manifest["source_fingerprint"]
    response_body = json.loads((FIXTURE / "COMPLETE_RESPONSE.json").read_text(encoding="utf-8"))
    expected_request = json.loads((FIXTURE / "REQUEST_BODY.json").read_text(encoding="utf-8"))
    expected_brief = json.loads((FIXTURE / "VALIDATED_COMMENTARY.json").read_text(encoding="utf-8"))
    fields = json.loads(response_body["choices"][0]["message"]["content"])
    assert "What percentage" in fields["questions"][0] and "one-off" in fields["questions"][2]
    monkeypatch.setattr(observability, "ROOT", tmp_path)
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "replay-fake-key-never-real")
    monkeypatch.setenv("GEMINI_MODEL", manifest["model"])
    original_load, original_request = service.load_research, commentary.request_structured
    monkeypatch.setattr(service, "load_research", lambda ticker, *args, **kwargs:
        amazon if ticker == "AMZN" else original_load(ticker, *args, **kwargs))
    def no_network(*args, **kwargs):
        raise AssertionError("Saved Amazon response replay must never contact a network")
    monkeypatch.setattr("requests.Session.request", no_network)
    calls = []
    def replay(request):
        calls.append(request)
        assert json.loads(request.content) == expected_request
        return httpx.Response(200, json=response_body)
    with httpx.Client(transport=httpx.MockTransport(replay)) as http:
        with OpenAI(api_key="replay-fake-key-never-real", base_url=GEMINI_BASE_URL,
                    max_retries=0, http_client=http) as client:
            monkeypatch.setattr(commentary, "request_structured", lambda **kwargs:
                original_request(**{**kwargs, "client": client}))
            app = AppTest.from_file(str(ROOT / "app.py")).run(timeout=30)
            app.text_input(key="ticker_input").set_value("AMZN")
            app.selectbox(key="source_mode").select("Live SEC API")
            next(button for button in app.button if button.label == "Load annual research").click().run(timeout=30)
            assert not app.exception and not calls
            next(item for item in app.checkbox if item.key.startswith("ai_consent_")).check().run(timeout=30)
            app.button(key="generate_ai").click().run(timeout=30)
            assert not app.exception and len(calls) == 1
            assert app.session_state["ai_brief"].model_dump() == expected_brief
            assert not app.session_state["ai_error"]
            tables = [item.value for item in app.dataframe if "Evidence ID" in item.value.columns]
            assert len(tables) == 1
            assert set(tables[0]["Evidence ID"]) == set(expected_brief["observations"][0]["evidence_ids"])
            assert any(fields["questions"][0] in item.value for item in app.markdown)
            assert any(fields["questions"][2] in item.value for item in app.markdown)
            assert len(app.metric) == 4 and len(app.get("download_button")) == 2
            assert app.button(key="generate_ai").disabled
            app.run(timeout=30)
            assert not app.exception and len(calls) == 1
