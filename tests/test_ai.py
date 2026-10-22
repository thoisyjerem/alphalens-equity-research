"""Mocked AI contract tests: these do not claim a live model call passed."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from alphalens.ai import AiError, ResearchBrief, evidence_catalog, generate_brief, validate_brief
from alphalens.service import load_research


@pytest.fixture
def result():
    return load_research("MSFT", "offline")


def brief(evidence_id="2026:revenue", text="Revenue expansion warrants further diligence on the durability of demand."):
    return ResearchBrief(observations=[{"text": text, "evidence_ids": [evidence_id]}],
        questions=["Which demand drivers are recurring?"], caveats=["Financial patterns alone do not establish causality."])


def test_no_key_means_no_api_call(result):
    client = Mock()
    with pytest.raises(AiError, match="OPENAI_API_KEY"):
        generate_brief(result, "", "model-test", client=client)
    client.responses.parse.assert_not_called()


def test_mocked_structured_response_and_store_false(result):
    client = Mock()
    client.responses.parse.return_value = SimpleNamespace(status="completed", output_parsed=brief())
    output = generate_brief(result, "mock-test-key", "model-test", client=client)
    assert output.observations[0].evidence_ids == ["2026:revenue"]
    request = client.responses.parse.call_args.kwargs
    assert request["store"] is False
    assert request["text_format"] is ResearchBrief
    assert request["model"] == "model-test"


def test_unknown_or_missing_fact_citation_rejected(result):
    with pytest.raises(AiError, match="unknown or unavailable"):
        validate_brief(brief("2026:total_debt"), evidence_catalog(result))


@pytest.mark.parametrize("text", ["Revenue rose by 30 percent in the latest year.", "Revenue was $100 billion according to management.", "The margin is strong at 50% relative to peers."])
def test_numerical_llm_claims_rejected(result, text):
    with pytest.raises(AiError, match="numerical prose"):
        validate_brief(brief(text=text), evidence_catalog(result))


def test_duplicate_evidence_rejected(result):
    output = brief()
    output.observations[0].evidence_ids *= 2
    with pytest.raises(AiError, match="duplicated"):
        validate_brief(output, evidence_catalog(result))


def test_no_fabricated_zero_in_evidence(result):
    evidence = evidence_catalog(result)
    assert "2026:total_debt" not in evidence
    assert "2026:revenue" in evidence
    assert all(row["sources"] for row in evidence.values())


@pytest.mark.parametrize("status,parsed", [("incomplete", None), ("completed", None)])
def test_refused_or_incomplete_output_not_displayed(result, status, parsed):
    client = Mock()
    client.responses.parse.return_value = SimpleNamespace(status=status, output_parsed=parsed)
    with pytest.raises(AiError, match="complete structured brief"):
        generate_brief(result, "mock", "model-test", client=client)


def test_error_does_not_expose_key_or_raw_exception(result):
    client = Mock()
    client.responses.parse.side_effect = RuntimeError("leaked-private-key-token")
    with pytest.raises(AiError) as caught:
        generate_brief(result, "mock", "model-test", client=client)
    assert "leaked-private-key-token" not in str(caught.value)


def test_schema_forbids_extra_uncontrolled_fields():
    with pytest.raises(ValidationError):
        ResearchBrief.model_validate({**brief().model_dump(), "price_target": "invented"})
