"""A detached rehearsal artifact must not look like an actual model response."""
import json
import pytest
from types import SimpleNamespace

from scripts.prepare_msft_briefing import prepare


@pytest.mark.parametrize("contract", ["focused_v2", "focused_v3"])
def test_prepared_request_is_unapproved_and_json_declares_local_authored_response(tmp_path, monkeypatch, contract):
    def forbidden(*args, **kwargs):
        raise AssertionError("Request preparation must not connect to a remote service")
    monkeypatch.setattr("socket.create_connection", forbidden)
    monkeypatch.setattr("requests.sessions.Session.request", forbidden)
    monkeypatch.setattr("scripts.prepare_msft_briefing.read_ai_config", lambda: SimpleNamespace(
        provider="gemini", model="gemini-3.5-flash-lite", api_key="private-fixture-key", configured=True))
    plan = prepare(tmp_path, contract=contract)
    assert plan["authorised"] is False and plan["new_live_requests"] == 0
    assert plan["automatic_retries"] is False and plan["paid_fallback"] is False
    saved = json.loads((tmp_path / "AUTHORED_REPORT.json").read_text(encoding="utf-8"))
    assert saved["evaluation_mode"] == "authored_offline_rehearsal"
    assert saved["live_request_executed"] is False
    assert any("NOT A LIVE MODEL RESPONSE" in value for value in saved["warnings"])
    assert saved["metadata"]["contract"] == contract
    assert not saved["unsupported_claims"]
    assert all("private-fixture-key" not in p.read_text(encoding="utf-8") for p in tmp_path.iterdir())
