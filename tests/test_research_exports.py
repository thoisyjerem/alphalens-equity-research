"""Offline report exports use genuine SEC fixtures and explicitly authored mocks."""
from copy import deepcopy
import json

import pytest

from alphalens.ai import ValidatedResearch
from alphalens.analytics import build_analytics
from alphalens.evidence import build_evidence_book
from alphalens.research import Claim, ResearchNote, ThesisChallenge, validate_analysis
from alphalens.research_exports import export_research_json, export_research_markdown
from alphalens.service import load_offline_filing_context, load_research


@pytest.fixture
def validated():
    result = load_research("MSFT", "offline")
    book = build_evidence_book(result, [load_offline_filing_context(result)])
    source_id = f"{result.periods[-1].fiscal_year}:revenue"
    source = book[source_id]
    citation = {"source_id": source_id, **{key: source[key] for key in
                ("value", "unit", "fiscal_year", "period_start", "period_end")}}
    performance = Claim(text="Reported annual revenue provides context for the scale of the business.",
                        kind="fact", financial_citations=[citation])
    bad = Claim(text="This unsupported claim intentionally cites an incorrect financial amount.", kind="fact",
                financial_citations=[{**citation, "value": source["value"] + 1000}])
    passage_id, passage = next((key, row) for key, row in book.items() if row["kind"] == "passage")
    narrative = Claim(text="The retrieved management disclosure warrants closer fundamental analysis.",
                      kind="inference", passage_citations=[{"source_id": passage_id, "quote": passage["text"][:160]}])
    output = ResearchNote(performance=[performance], business_developments=[narrative],
        investment_considerations=[bad], risks=[], executive_summary=[performance],
        what_matters_most=[narrative], capital_allocation=[], missing_information=[
            Claim(text="What additional evidence would establish sustainable investment returns?", kind="question")])
    saved = ValidatedResearch(output=output, verification=validate_analysis(output, book),
        evidence=book, model="authored-offline-mock", warnings=["Offline authored mock; no live model call."],
        provider="gemini", usage={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
        latency_seconds=0.5)
    saved.analysis = build_analytics(result)
    saved.diagnostics = {"operation": "research_briefing", "status": "completed",
                         "parsing_result": "passed", "schema_validation_result": "passed",
                         "numerical_validation_result": "passed_except_quarantined",
                         "source_validation_result": "requires_analyst_review"}
    return saved


def test_json_separates_checked_body_from_raw_and_quarantined_model_claims(validated):
    payload = json.loads(export_research_json(validated))
    assert payload["report_type"] == "AI Investment Research Briefing"
    assert len(payload["unsupported_claims"]) == 1
    assert payload["supported_sections"]["investment_considerations"] == []
    assert payload["raw_model_output"]["investment_considerations"][0]["text"].startswith("This unsupported")
    assert "audit only" in payload["raw_output_notice"]
    assert payload["verification"]["source_fingerprint"] == validated.verification.source_fingerprint
    assert payload["source_catalog"] == validated.evidence
    assert payload["python_analysis"] == validated.analysis


def test_markdown_body_withholds_unsupported_claim_but_appendix_keeps_failure(validated):
    markdown = export_research_markdown(validated)
    body, appendix = markdown.split("## Quarantined model output — excluded from research", 1)
    assert "This unsupported claim" not in body
    assert "This unsupported claim" in appendix
    assert "Financial figure mismatch" in appendix
    assert "AI interpretation; analyst review required" in body
    assert "pending analyst review" in body
    assert "OFFLINE DEMONSTRATION" in body
    assert "does not prove the claim" in body


def test_original_and_new_optional_research_sections_are_exported(validated):
    payload = json.loads(export_research_json(validated))
    assert list(payload["supported_sections"]) == [
        "executive_summary", "what_matters_most", "performance", "business_developments",
        "investment_considerations", "capital_allocation", "risks", "missing_information"]
    markdown = export_research_markdown(validated)
    assert "## Executive summary" in markdown
    assert "## What matters most" in markdown
    assert "## Capital allocation" in markdown
    assert "N/A — no source-supported claims" in markdown


def test_figures_units_periods_and_links_come_from_catalog(validated):
    markdown = export_research_markdown(validated)
    source = validated.evidence["2026:revenue"]
    assert str(source["value"]) in markdown
    assert "USD" in markdown
    assert "2025\\-07\\-01 to 2026\\-06\\-30" in markdown
    assert "[Open official SEC source](<https://www.sec.gov/Archives/" in markdown
    assert "## Annual financial inputs" in markdown
    assert "Python calculation / financial pipeline" in markdown


def test_source_appendix_preserves_actual_management_passage_context(validated):
    payload = json.loads(export_research_json(validated))
    cited = validated.output.business_developments[0].passage_citations[0].source_id
    assert payload["source_catalog"][cited]["text"] == validated.evidence[cited]["text"]
    markdown = export_research_markdown(validated)
    assert "Management disclosure: Item" in markdown
    assert "Section offsets" in markdown
    assert "filing report dates do not establish" in markdown.lower()
    assert "Context is bounded or truncated" in markdown


def test_python_metric_rows_keep_unavailable_reasons_and_dependencies(validated):
    payload = json.loads(export_research_json(validated))
    assert any(row["value"] is None and row["reason"] for row in payload["python_analysis"]["metrics"])
    markdown = export_research_markdown(validated)
    assert "## Python-calculated financial analysis" in markdown
    assert "N/A" in markdown
    assert "dependencies" in markdown
    assert "Python screening observation" in markdown
    assert "not an AI spending estimate" in markdown


def test_model_markdown_html_and_urls_are_plain_data_never_exported_links(validated):
    malicious = "Inspect [this](https://untrusted.invalid) <script>alert('x')</script> before judging the cited disclosure."
    validated.output.performance[0].text = malicious
    validated.output.executive_summary = []
    validated.verification = validate_analysis(validated.output, validated.evidence)
    markdown = export_research_markdown(validated)
    assert "[this](https://untrusted.invalid)" not in markdown
    assert "<script>" not in markdown
    assert "\\[this\\]\\(https\\:\\/\\/untrusted\\.invalid\\)" in markdown
    assert "&lt;script&gt;" in markdown
    assert json.loads(export_research_json(validated))["raw_model_output"]["performance"][0]["text"] == malicious


def test_unknown_non_sec_link_in_catalog_never_becomes_clickable(validated):
    source = validated.evidence["2026:revenue"]
    source["sources"][0]["url"] = "https://untrusted.invalid/pretend-filing"
    validated.verification = validate_analysis(validated.output, validated.evidence)
    markdown = export_research_markdown(validated)
    assert "[Open official SEC source](<https://untrusted.invalid" not in markdown


def test_generation_metadata_is_saved_without_arbitrary_diagnostic_configuration(validated):
    validated.diagnostics["api_key"] = "opaque-test-value-that-must-not-be-exported"
    validated.diagnostics["audit_path"] = "internal-local-path"
    payload = json.loads(export_research_json(validated))
    assert payload["metadata"]["provider"] == "gemini"
    assert payload["metadata"]["usage"]["total_tokens"] == 150
    assert payload["metadata"]["latency_seconds"] == 0.5
    assert payload["metadata"]["diagnostics"]["schema_validation_result"] == "passed"
    assert "api_key" not in payload["metadata"]["diagnostics"]
    assert "opaque-test-value" not in export_research_json(validated)
    assert "opaque-test-value" not in export_research_markdown(validated)
    assert "internal-local-path" not in export_research_json(validated)


def test_invalid_usage_and_latency_do_not_masquerade_as_measured_values(validated):
    validated.usage = {"input_tokens": float("nan"), "output_tokens": -1, "total_tokens": 0,
                       "unrecognized_field": "not exported"}
    validated.latency_seconds = None
    payload = json.loads(export_research_json(validated))
    assert payload["metadata"]["usage"] == {"total_tokens": 0}
    assert payload["metadata"]["latency_seconds"] is None
    assert "Response latency: N/A seconds" in export_research_markdown(validated)


@pytest.mark.parametrize("export", [export_research_json, export_research_markdown])
def test_changed_financial_catalog_invalidates_export(validated, export):
    validated.evidence["2026:revenue"]["value"] += 1
    with pytest.raises(ValueError, match="evidence changed"):
        export(validated)


@pytest.mark.parametrize("export", [export_research_json, export_research_markdown])
def test_changed_model_claim_after_validation_invalidates_export(validated, export):
    validated.output.performance[0].text = "A different claim was inserted after the research checks completed."
    with pytest.raises(ValueError, match="claims changed"):
        export(validated)


def test_promoted_unsupported_claim_cannot_bypass_export_guard(validated):
    bad = next(claim for claim in validated.verification.claims if claim.status == "unsupported")
    bad.status = "evidence_checked"
    bad.issues = []
    with pytest.raises(ValueError, match="claims changed"):
        export_research_json(validated)


def test_legacy_saved_results_without_attached_python_analysis_remain_exportable(validated):
    validated.analysis = {}
    validated.diagnostics = {}
    validated.usage = {}
    markdown = export_research_markdown(validated)
    assert "N/A — no Python-calculated analysis" in markdown
    assert "Token usage: N/A" in markdown
    assert json.loads(export_research_json(validated))["metadata"]["diagnostics"] == {}


def test_thesis_challenge_exports_its_original_sections_and_unproven_conditions(validated):
    question = Claim(text="What additional evidence would establish the investment case?", kind="question")
    validated.output = ThesisChallenge(
        assumptions=[Claim(text="Assumption: infrastructure demand remains durable.", kind="hypothesis")],
        supporting_evidence=[], contradictory_evidence=[], risks=[], missing_information=[question],
        invalidation_conditions=[Claim(text="If persistent underutilisation emerges, revisit the thesis.", kind="hypothesis")])
    validated.verification = validate_analysis(validated.output, validated.evidence)
    payload = json.loads(export_research_json(validated))
    assert payload["report_type"] == "Challenge the Thesis"
    assert set(payload["supported_sections"]) == set(ThesisChallenge.model_fields)
    assert "Unproven hypothesis / assumption" in export_research_markdown(validated)


def test_exports_are_deterministic_and_do_not_mutate_saved_report(validated):
    before = deepcopy(validated)
    assert export_research_markdown(validated) == export_research_markdown(validated)
    assert export_research_json(validated) == export_research_json(validated)
    assert validated == before
