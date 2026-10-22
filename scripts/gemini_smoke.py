"""Prepare a tiny structured Gemini diagnostic; default operation is offline.

Live execution requires fresh explicit human approval and the opt-in CLI flag.
It permits one request, with no retries, model switch, or research evidence.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import httpx
from openai import OpenAI
from pydantic import BaseModel, ConfigDict, field_validator
from alphalens.providers import (
    DEFAULT_GEMINI_MODEL, GEMINI_BASE_URL, ProviderError, read_ai_config, request_structured,
)

MESSAGES = [
    {"role": "system", "content": "Return only the requested JSON object."},
    {"role": "user", "content": 'Return {"status":"ok"}.'},
]
TOKEN_CAP = 256


class SmokeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str

    @field_validator("status")
    @classmethod
    def expected_status(cls, value):
        if value != "ok":
            raise ValueError("The smoke response must contain status ok")
        return value


def _request(client, key: str, model: str):
    return request_structured(provider="gemini", api_key=key, model=model, messages=MESSAGES,
                              schema=SmokeOutput, max_output_tokens=TOKEN_CAP, timeout=45, client=client)


def prepare_offline(output_path: Path | None = None) -> dict[str, Any]:
    """Capture the real SDK's outgoing JSON using a local mock transport only."""
    captured = []

    def handle(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={
            "id": "authored-offline-smoke", "object": "chat.completion", "created": 0,
            "model": DEFAULT_GEMINI_MODEL,
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": json.dumps({"result_json": '{"status":"ok"}'})}}],
        })

    with OpenAI(api_key="offline-placeholder-never-a-credential", base_url=GEMINI_BASE_URL, max_retries=0,
                http_client=httpx.Client(transport=httpx.MockTransport(handle))) as client:
        result = _request(client, "offline-placeholder-never-a-credential", DEFAULT_GEMINI_MODEL)
    assert len(captured) == 1 and result.status == "completed" and result.output_parsed.status == "ok"
    plan = {
        "scope": "One tiny diagnostic, not a research evaluation or proof that the full schemas work",
        "approval": "Required before live execution; not yet granted",
        "provider": "gemini", "model": DEFAULT_GEMINI_MODEL,
        "url": GEMINI_BASE_URL + "chat/completions", "maximum_live_requests": 1,
        "automatic_retries": False, "provider_fallback": False,
        "project_requirement": "Owner-confirmed Free Tier with billing disabled",
        "request_body": captured[0], "expected_response": {"status": "ok"},
        "offline_mock_contract": "Passed; one local mocked HTTP response, zero live model requests",
        "interpretation": "Success would establish only basic model/endpoint/structured-output access. It would not identify the prior rejected field or validate the research schemas.",
    }
    if output_path is not None:
        output_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    return plan


def execute_approved_one(output_dir: Path) -> int:
    """Never invoke this until the owner explicitly approves this smoke test."""
    config = read_ai_config()
    if config.provider != "gemini" or config.model != DEFAULT_GEMINI_MODEL or not config.configured:
        raise ProviderError("The approved smoke requires the existing Gemini model and a local key. No request was made.")
    output_dir.mkdir(exist_ok=True)
    ledger_path = output_dir / "REQUEST_LEDGER.json"
    ledger = {"scope": "One explicitly approved harmless structured smoke test", "provider": "gemini",
              "model": config.model, "maximum_requests": 1, "requests_attempted": 0,
              "automatic_retries": False, "provider_fallback": False,
              "started_at": datetime.now(timezone.utc).isoformat(), "status": "prepared"}
    # Exclusive creation prevents accidentally repeating this approved test.
    with ledger_path.open("x", encoding="utf-8") as stream:
        json.dump(ledger, stream, indent=2)

    def save(path, data):
        text = json.dumps(data, indent=2, ensure_ascii=False)
        path.write_text(text.replace(config.api_key, "[REDACTED CREDENTIAL]"), encoding="utf-8")

    def before(request):
        assert str(request.url) == GEMINI_BASE_URL + "chat/completions" and request.method == "POST"
        assert ledger["requests_attempted"] == 0
        ledger["requests_attempted"] = 1
        ledger["status"] = "attempted"
        save(ledger_path, ledger)
        save(output_dir / "request.json", json.loads(request.content))

    def after(response):
        response.read()
        ledger["http_status"] = response.status_code
        try:
            body = response.json()
        except ValueError:
            body = {"non_json_response": response.text}
        save(output_dir / "complete_response.json", body)

    with httpx.Client(timeout=45, follow_redirects=False, transport=httpx.HTTPTransport(retries=0),
                      event_hooks={"request": [before], "response": [after]}) as http:
        with OpenAI(api_key=config.api_key, base_url=GEMINI_BASE_URL, max_retries=0,
                    timeout=45, http_client=http) as client:
            try:
                result = _request(client, config.api_key, config.model)
            except ProviderError as exc:
                ledger.update(status="failed", safe_error=str(exc))
            else:
                ledger.update(status="passed" if result.status == "completed" else "incomplete",
                              usage=result.usage, latency_seconds=result.latency_seconds)
                if result.output_parsed is not None:
                    save(output_dir / "output.json", result.output_parsed.model_dump())
    ledger["finished_at"] = datetime.now(timezone.utc).isoformat()
    save(ledger_path, ledger)
    print(f"Smoke status: {ledger['status']}; requests attempted: {ledger['requests_attempted']}/1. No retries or fallback.")
    return 0 if ledger["status"] == "passed" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-approved-one", action="store_true",
                        help="Use only after explicit approval for this one live request")
    args = parser.parse_args()
    if args.execute_approved_one:
        return execute_approved_one(ROOT / "outputs/gemini_smoke_2026-10-17")
    plan = prepare_offline(ROOT / "outputs/GEMINI_SMOKE_PLAN.json")
    print(f"OFFLINE mock preparation passed for {plan['model']}; live model requests: zero.")
    print("The live test remains unapproved and has not been executed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
