"""Realistic authored mock outputs; no live model or network requests."""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest

from alphalens.ai import AiError
from alphalens.evidence import build_evidence_book, evidence_fingerprint
from alphalens.research import ResearchAnalysis, ThesisChallenge, validate_analysis
from scripts.evaluate_ai import (
    HYPOTHESIS, build_case_response, build_clean_response, evaluate_case,
    load_cases, load_evaluation_sources, measure_semantic_boundary, run_evaluation,
)


@pytest.fixture(scope="module")
def sources():
    return load_evaluation_sources()


@pytest.mark.parametrize("case", load_cases(), ids=lambda case: case["id"])
def test_realistic_mock_corruption_cases(sources, case):
    result, _contexts, book = sources
    outcome = evaluate_case(result, book, case)
    assert outcome["passed"], outcome
    if case["expected"] == "quarantined":
        assert outcome["issues"]
        assert outcome["claim_counts"]["unsupported"] == 1


@pytest.mark.parametrize("feature", ["brief", "challenge"])
def test_realistic_mock_sdk_end_to_end(sources, feature):
    from alphalens.ai import challenge_thesis, generate_research_brief

    result, contexts, book = sources
    schema = ResearchAnalysis if feature == "brief" else ThesisChallenge
    output = schema.model_validate(build_clean_response(result, book, feature))
    client = Mock()
    client.responses.parse.return_value = SimpleNamespace(status="completed", output_parsed=output)
    if feature == "brief":
        validated = generate_research_brief(result, "mock-never-a-real-key", "mock-model", filing_contexts=contexts, client=client)
    else:
        validated = challenge_thesis(result, HYPOTHESIS, "mock-never-a-real-key", "mock-model", filing_contexts=contexts, client=client)
    assert isinstance(validated.output, schema)
    assert validated.verification.unsupported_count == 0
    assert validated.verification.source_fingerprint == evidence_fingerprint(book)
    request = client.responses.parse.call_args.kwargs
    assert request["store"] is False
    assert request["text_format"] is schema
    # A real model would see the actual inputs, not fixture expected answers.
    request_text = json.dumps(request["input"])
    assert str(result.periods[-1].metrics["revenue"].value) in request_text
    assert any(source_id in request_text for source_id, row in book.items() if row["kind"] == "passage")
    if feature == "challenge":
        assert HYPOTHESIS in request_text


def test_mock_sdk_quarantines_corrupted_claim_but_retains_valid_remainder(sources):
    from alphalens.ai import generate_research_brief

    result, contexts, book = sources
    case = next(case for case in load_cases() if case["id"] == "incorrect_financial_figure")
    corrupted = ResearchAnalysis.model_validate(build_case_response(result, book, case))
    client = Mock()
    client.responses.parse.return_value = SimpleNamespace(status="completed", output_parsed=corrupted)
    validated = generate_research_brief(result, "mock", "mock-model", filing_contexts=contexts, client=client)
    assert validated.verification.unsupported_count == 1
    assert validated.verification.evidence_checked_count >= 1
    assert any("figure mismatch" in issue for claim in validated.verification.claims for issue in claim.issues)


@pytest.mark.parametrize("case_id", ["uncontrolled_schema_field", "boolean_financial_value"])
def test_mock_sdk_rejects_malformed_structured_response(sources, case_id):
    from alphalens.ai import generate_research_brief

    result, contexts, book = sources
    case = next(case for case in load_cases() if case["id"] == case_id)
    client = Mock()
    client.responses.parse.return_value = SimpleNamespace(
        status="completed", output_parsed=build_case_response(result, book, case))
    with pytest.raises(AiError, match="schema"):
        generate_research_brief(result, "mock", "mock-model", filing_contexts=contexts, client=client)


@pytest.mark.parametrize("field,value", [("ticker", "AAPL"), ("cik", "0000320193"), ("mode", "live")])
def test_stale_or_cross_issuer_context_never_reaches_sdk(sources, field, value):
    from copy import deepcopy
    from alphalens.ai import generate_research_brief

    result, contexts, _book = sources
    mismatched = deepcopy(contexts)
    mismatched[0][field] = value
    client = Mock()
    with pytest.raises(AiError, match="source context"):
        generate_research_brief(result, "mock", "mock-model", filing_contexts=mismatched, client=client)
    client.responses.parse.assert_not_called()


@pytest.mark.parametrize("feature", ["brief", "challenge"])
@pytest.mark.parametrize("status,parsed", [("incomplete", None), ("completed", None)])
def test_mock_sdk_refusal_or_incomplete_output_fails_safely(sources, feature, status, parsed):
    from alphalens.ai import challenge_thesis, generate_research_brief

    result, contexts, _book = sources
    client = Mock()
    client.responses.parse.return_value = SimpleNamespace(status=status, output_parsed=parsed)
    with pytest.raises(AiError):
        if feature == "brief":
            generate_research_brief(result, "mock", "mock-model", filing_contexts=contexts, client=client)
        else:
            challenge_thesis(result, HYPOTHESIS, "mock", "mock-model", filing_contexts=contexts, client=client)


@pytest.mark.parametrize("feature", ["brief", "challenge"])
def test_mock_sdk_error_hides_secret_and_model_output(sources, feature):
    from alphalens.ai import challenge_thesis, generate_research_brief

    result, contexts, _book = sources
    client = Mock()
    client.responses.parse.side_effect = RuntimeError("private-key-token-and-raw-model-content")
    with pytest.raises(AiError) as caught:
        if feature == "brief":
            generate_research_brief(result, "mock", "mock-model", filing_contexts=contexts, client=client)
        else:
            challenge_thesis(result, HYPOTHESIS, "mock", "mock-model", filing_contexts=contexts, client=client)
    assert "private-key-token" not in str(caught.value)
    assert "raw-model-content" not in str(caught.value)


@pytest.mark.parametrize("feature", ["brief", "challenge"])
def test_new_features_without_key_never_call_sdk(sources, feature):
    from alphalens.ai import challenge_thesis, generate_research_brief

    result, contexts, _book = sources
    client = Mock()
    with pytest.raises(AiError, match="OPENAI_API_KEY"):
        if feature == "brief":
            generate_research_brief(result, "", "mock-model", filing_contexts=contexts, client=client)
        else:
            challenge_thesis(result, HYPOTHESIS, "", "mock-model", filing_contexts=contexts, client=client)
    client.responses.parse.assert_not_called()


def test_evaluation_report_is_reproducible_and_explicitly_not_live(tmp_path, monkeypatch):
    import requests

    monkeypatch.setattr(requests.Session, "request", lambda *args, **kwargs: pytest.fail("Evaluation must stay offline"))
    report = run_evaluation(tmp_path)
    assert report["failed"] == 0
    assert report["passed"] == report["scenario_count"] == len(load_cases())
    assert report["live_ai_tested"] is False
    assert report["paid_api_requests"] == 0
    assert report["data_mode"] == "offline"
    assert report["passage_source_count"] > 0
    saved = json.loads((tmp_path / "AI_EVALUATION.json").read_text(encoding="utf-8"))
    assert saved == report
    markdown = (tmp_path / "AI_EVALUATION.md").read_text(encoding="utf-8")
    assert "not a model-accuracy benchmark" in markdown
    assert "Live OpenAI integration remains untested" in markdown
    boundary = report["semantic_boundary_demonstration"]
    assert boundary["expected_limitation"] == "semantic_entailment_not_established"
    assert boundary["included_in_scenario_pass_score"] is False
    assert boundary["meaning_verified"] is False
    assert "Observed semantic boundary (excluded from the pass score)" in markdown


def test_real_citation_with_misleading_prose_is_measured_as_unverified_meaning(sources, monkeypatch):
    from alphalens import research_ui

    result, _contexts, book = sources
    boundary = measure_semantic_boundary(result, book)
    assert boundary["observed_mechanical_status"] == "evidence_checked"
    assert boundary["exact_financial_fields_checked"] is True
    assert boundary["mechanical_issues"] == []
    assert boundary["meaning_verified"] is False
    assert boundary["analyst_review_required"] is True
    payload = build_clean_response(result, book, "brief")
    payload["performance"][0]["text"] = boundary["authored_adversarial_mock_claim"]
    output = ResearchAnalysis.model_validate(payload)
    validated = SimpleNamespace(output=output, verification=validate_analysis(output, book),
                                evidence=book, model="authored-mock-not-live", warnings=[])
    ui = MagicMock()
    monkeypatch.setattr(research_ui, "st", ui)
    research_ui.show_validated_research(validated)
    captions = [call.args[0] for call in ui.caption.call_args_list]
    assert boundary["display_policy"] in captions
    assert "do not prove the meaning" in ui.warning.call_args.args[0]


def test_missing_contradiction_stays_empty_and_is_disclosed(sources):
    from alphalens.ai import challenge_thesis

    result, contexts, book = sources
    case = next(case for case in load_cases() if case["mutation"] == "no_contradiction_available")
    payload = build_case_response(result, book, case)
    client = Mock()
    client.responses.parse.return_value = SimpleNamespace(status="completed", output_parsed=payload)
    validated = challenge_thesis(result, HYPOTHESIS, "mock", "mock-model", filing_contexts=contexts, client=client)
    assert validated.output.contradictory_evidence == []
    assert any("contradict" in claim.text for claim in validated.output.missing_information)
    assert any("contradictory evidence" in warning and "incomplete" in warning for warning in validated.warnings)
    assert validated.verification.unsupported_count == 0


def test_evidence_change_invalidates_reuse_of_previous_verification(sources):
    from copy import deepcopy

    result, contexts, book = sources
    output = ResearchAnalysis.model_validate(build_clean_response(result, book, "brief"))
    previous = validate_analysis(output, book)
    changed_result = deepcopy(result)
    changed_result.periods[-1].metrics["revenue"].value += 1
    changed_book = build_evidence_book(changed_result, contexts)
    current = validate_analysis(output, changed_book)
    assert previous.source_fingerprint != current.source_fingerprint
    assert current.unsupported_count == 1
