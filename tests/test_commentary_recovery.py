"""Confirmed commentary citation-bound failure, reproduced without live calls.

The safe audit identifies a too_long error at observations[0].evidence_ids.
Authored responses below reproduce that mechanism using genuine local evidence
IDs; they are not represented as the unavailable original model response text.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import httpx
from openai import OpenAI
import pytest

from alphalens.ai import AiError, ResearchBrief, evidence_catalog, generate_brief
from alphalens.providers import GEMINI_BASE_URL
from alphalens.service import load_research


MODEL = "gemini-3.5-flash-lite"
FAKE_KEY = "authored-commentary-key-not-a-real-credential"


@pytest.fixture
def context(monkeypatch, tmp_path):
    from alphalens import observability
    monkeypatch.setattr(observability, "ROOT", tmp_path)
    result = load_research("MSFT", "offline")
    return result, list(evidence_catalog(result))


def authored(ids, *, text="Historical cash generation warrants diligence on investment timing."):
    return {
        "observations": [{"text": text, "evidence_ids": list(ids)}],
        "questions": ["Which investment commitments could affect future cash generation?"],
        "caveats": ["Annual financial patterns do not establish causal explanations."],
    }


def invoke(result, payload, calls):
    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={
            "id": "AUTHORED-COMMENTARY-BOUND-REPLAY", "object": "chat.completion", "created": 0,
            "model": MODEL,
            "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": json.dumps({"result_json": json.dumps(payload)})}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        })

    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        with OpenAI(api_key=FAKE_KEY, base_url=GEMINI_BASE_URL, max_retries=0, http_client=http) as client:
            return generate_brief(result, FAKE_KEY, MODEL, provider="gemini", client=client)


def test_confirmed_seven_id_failure_is_rejected_without_truncating_or_retrying(context):
    result, ids = context
    payload = authored(ids[:7])
    original, calls = deepcopy(payload), []
    with pytest.raises(AiError) as caught:
        invoke(result, payload, calls)
    assert payload == original and len(payload["observations"][0]["evidence_ids"]) == 7
    assert len(calls) == 1
    assert calls[0].url.host == "generativelanguage.googleapis.com"
    diagnostics = caught.value.diagnostics
    assert diagnostics["parsing_result"] == "passed"
    assert diagnostics["schema_validation_result"] == "failed"
    assert diagnostics["validation_stage"] == "output_schema"
    assert {"path": "observations[0].evidence_ids", "type": "too_long"} in diagnostics["validation_issues"]
    assert diagnostics["source_validation_result"] == "not_run"
    assert "more than six financial sources" in str(caught.value)
    assert "No citations were removed" in str(caught.value)
    assert "no automatic retry" in str(caught.value)
    assert FAKE_KEY not in str(caught.value)


def test_six_id_commentary_preserves_schema_source_checks_and_legacy_transport(context):
    result, ids = context
    payload, calls = authored(ids[:6]), []
    output = invoke(result, payload, calls)
    assert isinstance(output, ResearchBrief)
    assert output.model_dump() == payload
    assert len(calls) == 1
    body = json.loads(calls[0].content)
    assert body["model"] == MODEL and body["max_tokens"] == 2200
    assert set(body["response_format"]["json_schema"]["schema"]["properties"]) == {"result_json"}
    assert "ORIGINAL OUTPUT SCHEMA:" in body["messages"][0]["content"]
    instructions = body["messages"][0]["content"]
    assert "SOURCE BOUNDS: each observation must cite at most six distinct evidence_ids." in instructions
    assert "Never drop citations while keeping a claim that needs them." in instructions
    packet = json.loads(body["messages"][1]["content"])
    assert set(packet["evidence_ids"]) == set(evidence_catalog(result))
    assert FAKE_KEY not in json.dumps(body)


@pytest.mark.parametrize("failure", ["fabricated_id", "missing_fact", "numeric_prose", "duplicate_id"])
def test_commentary_recovery_does_not_weaken_existing_rejections(context, failure):
    result, ids = context
    payload = authored(ids[:1])
    if failure == "fabricated_id":
        payload["observations"][0]["evidence_ids"] = ["2026:fabricated_metric"]
    elif failure == "missing_fact":
        assert "2026:total_debt" not in ids
        payload["observations"][0]["evidence_ids"] = ["2026:total_debt"]
    elif failure == "numeric_prose":
        payload["observations"][0]["text"] = "Operating cash flow increased by 100 percent in 2026."
    else:
        payload["observations"][0]["evidence_ids"] *= 2
    original, calls = deepcopy(payload), []
    with pytest.raises(AiError):
        invoke(result, payload, calls)
    assert len(calls) == 1 and payload == original


def test_commentary_schema_failure_keeps_dashboard_usable_and_shows_safe_cause(context, monkeypatch):
    from streamlit.testing.v1 import AppTest
    from alphalens import ai

    result, ids = context
    captured = []
    with pytest.raises(AiError) as caught:
        invoke(result, authored(ids[:7]), captured)
    error = caught.value
    attempts = []
    def rejected(*args, **kwargs):
        attempts.append(1)
        raise error
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "ui-authored-key-not-real")
    monkeypatch.setattr(ai, "generate_brief", rejected)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(timeout=30)
    consent = next(item for item in app.checkbox if item.key.startswith("ai_consent_"))
    consent.check().run(timeout=30)
    app.button(key="generate_ai").click().run(timeout=30)
    assert not app.exception and attempts == [1] and len(captured) == 1
    assert app.session_state["ai_brief"] is None
    assert any(item.value == "observations[0].evidence_ids: too_long" for item in app.text)
    assert any("Parsing: passed" in item.value and "Schema: failed" in item.value for item in app.caption)
    assert any("more than six financial sources" in item.value and "No citations were removed" in item.value
               for item in app.error)
    assert len(app.metric) == 4 and len(app.get("download_button")) == 2
    assert app.button(key="generate_ai").disabled
    visible = " ".join(str(item.value) for group in (app.error, app.text, app.caption) for item in group)
    assert FAKE_KEY not in visible and "ui-authored-key-not-real" not in visible
    app.run(timeout=30)
    assert not app.exception and attempts == [1]


def test_actual_accepted_commentary_replays_exactly_through_sdk_and_original_validators(context, monkeypatch):
    """Real preserved output, not an authored replacement or semantic approval."""
    folder = Path(__file__).resolve().parents[1] / "fixtures/commentary_live_2026-10-18"
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    raw = (folder / "COMPLETE_RESPONSE.json").read_bytes()
    assert sha256(raw).hexdigest() == manifest["files"]["COMPLETE_RESPONSE.json"]
    complete = json.loads(raw)
    expected = json.loads(json.loads(complete["choices"][0]["message"]["content"])["result_json"])
    result, _ = context
    calls = []

    def forbidden(*args, **kwargs):
        pytest.fail("Saved commentary replay attempted real HTTP")
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", forbidden)

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json=complete)
    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        with OpenAI(api_key=FAKE_KEY, base_url=GEMINI_BASE_URL, max_retries=0, http_client=http) as client:
            output = generate_brief(result, FAKE_KEY, MODEL, provider="gemini", client=client)
    assert len(calls) == 1 and calls[0].url.host == "generativelanguage.googleapis.com"
    assert isinstance(output, ResearchBrief) and output.model_dump() == expected
    assert [len(observation.evidence_ids) for observation in output.observations] == [6, 6]
    catalog = evidence_catalog(result)
    assert all(source_id in catalog for observation in output.observations for source_id in observation.evidence_ids)
    # Preserve the original scope and imprecise wording. Neither is silently
    # upgraded to latest-year coverage or evidence of sound economic reasoning.
    assert {catalog[source_id]["fiscal_year"] for source_id in output.observations[0].evidence_ids} == {2024, 2025}
    assert output.observations[1].text.endswith("free cash flow experienced fluctuations.")
    assert manifest["usage"] == complete["usage"] == {
        "prompt_tokens": 11641, "completion_tokens": 295, "total_tokens": 11936}
    assert FAKE_KEY not in json.dumps(output.model_dump())
