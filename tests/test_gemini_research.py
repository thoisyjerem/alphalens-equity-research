"""Real SDK parsing over a local HTTP transport, never a live Gemini request.

Run the existing clean/corrupt research scenarios through the added transport to
prove that changing providers does not bypass the financial/source verifier.
"""
import json

import httpx
from openai import OpenAI
import pytest

from alphalens.ai import AiError, challenge_thesis, generate_brief, generate_research_brief
from alphalens.providers import DEFAULT_GEMINI_MODEL, GEMINI_BASE_URL
from scripts.evaluate_ai import (
    HYPOTHESIS, build_case_response, build_clean_response, load_cases,
    load_evaluation_sources,
)


@pytest.fixture(scope="module")
def sources():
    return load_evaluation_sources()


def sdk_client(payload, requests):
    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={
            "id": "authored-gemini-mock", "object": "chat.completion", "created": 0,
            "model": DEFAULT_GEMINI_MODEL,
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": json.dumps({"result_json": json.dumps(payload)})}}],
            "usage": {"prompt_tokens": 500, "completion_tokens": 300, "total_tokens": 800},
        })

    return OpenAI(api_key="mock-key-never-a-real-credential", base_url=GEMINI_BASE_URL,
                  max_retries=0, http_client=httpx.Client(transport=httpx.MockTransport(respond)))


def generate(feature, result, contexts, client):
    kwargs = dict(api_key="mock-key-never-a-real-credential", model=DEFAULT_GEMINI_MODEL,
                  provider="gemini", filing_contexts=contexts, client=client)
    return (generate_research_brief(result, contract="legacy", **kwargs) if feature == "brief" else
            challenge_thesis(result, HYPOTHESIS, **kwargs))


@pytest.mark.parametrize("case", load_cases(), ids=lambda case: case["id"])
def test_gemini_reuses_every_existing_financial_and_source_safeguard(sources, case):
    result, contexts, book = sources
    payload = build_case_response(result, book, case)
    requests = []
    with sdk_client(payload, requests) as client:
        if case["expected"] == "schema_rejected":
            with pytest.raises(AiError):
                generate(case["feature"], result, contexts, client)
        else:
            output = generate(case["feature"], result, contexts, client)
            assert ("quarantined" if output.verification.unsupported_count else "accepted") == case["expected"]
            if case["expected"] == "quarantined":
                assert output.verification.unsupported_count == 1
                assert len(output.verification.claims) > 1
    assert len(requests) == 1
    assert requests[0].url.host == "generativelanguage.googleapis.com"
    assert requests[0].url.path.endswith("/chat/completions")


@pytest.mark.parametrize("feature", ["brief", "challenge"])
def test_gemini_packet_prompts_sources_and_usage_are_preserved(sources, feature):
    from alphalens.ai import _RESEARCH_SYSTEM

    result, contexts, book = sources
    requests = []
    with sdk_client(build_clean_response(result, book, feature), requests) as client:
        output = generate(feature, result, contexts, client)
    body = json.loads(requests[0].content)
    assert body["messages"][0]["role"] == "system"
    assert body["messages"][0]["content"].startswith(_RESEARCH_SYSTEM)
    assert "ORIGINAL OUTPUT SCHEMA:" in body["messages"][0]["content"]
    packet = json.loads(body["messages"][1]["content"])
    assert packet["source_catalog"] == book
    assert packet["company"]["ticker"] == "MSFT"
    assert packet["data_mode"] == "offline"
    assert packet["investment_hypothesis"] == (HYPOTHESIS if feature == "challenge" else None)
    assert "SEC_USER_AGENT" not in requests[0].content.decode()
    assert "mock-key-never-a-real-credential" not in requests[0].content.decode()
    assert body["max_tokens"] == 6000
    assert body["response_format"]["type"] == "json_schema"
    assert output.provider == "gemini"
    assert output.model == DEFAULT_GEMINI_MODEL
    assert output.usage == {"input_tokens": 500, "output_tokens": 300, "total_tokens": 800}
    assert output.latency_seconds >= 0
    assert output.verification.unsupported_count == 0
    assert any("Semantic entailment" in warning for warning in output.warnings)


@pytest.mark.parametrize("bad_citation", [False, True])
def test_gemini_legacy_commentary_remains_source_checked(sources, bad_citation):
    result, _, _ = sources
    payload = {
        "observations": [{"text": "Revenue expansion warrants further diligence on the durability of demand.",
                          "evidence_ids": ["invented:evidence" if bad_citation else "2026:revenue"]}],
        "questions": ["Which demand drivers are recurring?"],
        "caveats": ["Financial patterns alone do not establish causality."],
    }
    requests = []
    with sdk_client(payload, requests) as client:
        if bad_citation:
            with pytest.raises(AiError, match="unknown or unavailable"):
                generate_brief(result, "mock-key", DEFAULT_GEMINI_MODEL, provider="gemini", client=client)
        else:
            output = generate_brief(result, "mock-key", DEFAULT_GEMINI_MODEL, provider="gemini", client=client)
            assert output.observations[0].evidence_ids == ["2026:revenue"]
    assert len(requests) == 1
    assert json.loads(requests[0].content)["max_tokens"] == 2200


def test_gemini_real_citation_still_does_not_prove_claim_meaning(sources):
    result, contexts, book = sources
    payload = build_clean_response(result, book, "brief")
    payload["performance"][0]["text"] = (
        "Microsoft has permanently eliminated competitive risk and secured guaranteed future profitability."
    )
    requests = []
    with sdk_client(payload, requests) as client:
        output = generate("brief", result, contexts, client)
    # Deliberately measure the existing semantic limit; never call it verified.
    assert output.verification.claims[0].status == "evidence_checked"
    assert any("Semantic entailment" in warning for warning in output.warnings)


@pytest.mark.parametrize("feature", ["commentary", "brief", "challenge"])
def test_missing_gemini_key_cannot_attempt_a_request(sources, feature):
    from unittest.mock import Mock

    result, contexts, _ = sources
    client = Mock()
    with pytest.raises(AiError, match="GEMINI_API_KEY"):
        if feature == "commentary":
            generate_brief(result, "", DEFAULT_GEMINI_MODEL, provider="gemini", client=client)
        else:
            kwargs = dict(api_key="", model=DEFAULT_GEMINI_MODEL, provider="gemini",
                          filing_contexts=contexts, client=client)
            if feature == "brief":
                generate_research_brief(result, contract="legacy", **kwargs)
            else:
                challenge_thesis(result, HYPOTHESIS, **kwargs)
    assert not client.mock_calls
