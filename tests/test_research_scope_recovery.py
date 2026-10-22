"""Actual rejected-response regressions; no model or retrieval requests."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from alphalens.research import Claim, ResearchNote, _comparative_issues, _overclaim_issues, validate_analysis


ROOT = Path(__file__).resolve().parents[1]
RECOVERY = ROOT / "outputs/msft_recovery_live_2026-10-18"


@pytest.fixture
def saved():
    book = json.loads((RECOVERY / "SOURCE_CATALOG.json").read_text(encoding="utf-8"))
    report = ResearchNote.model_validate(json.loads(
        (RECOVERY / "REJECTED_ASSEMBLED_REPORT.json").read_text(encoding="utf-8"))["output"])
    return book, report


def test_actual_executive_disclosed_gain_impact_is_not_a_net_income_or_eps_growth_assertion(saved):
    book, report = saved
    executive = report.executive_summary[0]
    assert "while net income and diluted EPS benefited" in executive.text
    assert not any("net_income" in citation.source_id or "diluted_eps" in citation.source_id
                   for citation in executive.financial_citations)
    # Only comparative grammar is checked. This does not approve its separate
    # observation scope or establish that the passage supports every assertion.
    assert _comparative_issues(executive, book) == []


@pytest.mark.parametrize("metric, subject", [("net_income", "Net income"), ("diluted_eps", "Diluted EPS")])
def test_actual_net_income_and_eps_comparisons_still_require_their_own_periods(saved, metric, subject):
    book, report = saved
    payload = report.executive_summary[0].model_dump(mode="json")
    payload["text"] = f"Operating income increased, while {subject} increased."
    assert any(f"{metric} requires 2 consecutive annual periods" in issue
               for issue in _comparative_issues(Claim.model_validate(payload), book))


@pytest.mark.parametrize("text", [
    "Free cash flow is an analyst-defined measure excluding lease payments.",
    "FCF excludes all lease payments.",
    "Free cash flow omits operating lease payments.",
    "Free cash flow does not include finance-lease payments.",
])
def test_blanket_lease_payment_exclusion_cannot_replace_finance_principal_definition(text):
    issues = _overclaim_issues(Claim(text=text, kind="inference"), {})
    assert any("Lease accounting" in issue for issue in issues)


@pytest.mark.parametrize("text", [
    "Free cash flow excludes finance-lease principal repayments.",
    "Free cash flow excludes finance lease principal payments.",
    "Free cash flow does not exclude operating lease payments.",
    "Free cash flow is not excluding all lease payments.",
    "Alternative free cash flow definitions may exclude lease payments.",
])
def test_precise_finance_lease_definition_and_qualified_controls_remain_reviewable(text):
    assert _overclaim_issues(Claim(text=text, kind="inference"), {}) == []


@pytest.mark.parametrize("text", [
    "Constant currency breakouts are limited.",
    "The company does not disclose infrastructure utilisation.",
    "The filing has not provided a relevant capital investment breakdown.",
])
def test_bounded_packet_does_not_establish_company_non_disclosure(text):
    assert any("Disclosure scope" in issue
               for issue in _overclaim_issues(Claim(text=text, kind="inference"), {}))


@pytest.mark.parametrize("text", [
    "Constant currency breakouts are not provided in the selected passages.",
    "The supplied context does not establish infrastructure utilisation.",
    "The company's disclosures are limited in this packet.",
    "Disclosures indicate potential power constraints without quantifying financial impact.",
])
def test_explicit_packet_limits_do_not_become_invented_company_disclosure_claims(text):
    assert _overclaim_issues(Claim(text=text, kind="inference"), {}) == []


def test_actual_saved_report_remains_rejected_for_specific_lease_and_disclosure_errors(saved):
    book, report = saved
    original = deepcopy(report.model_dump(mode="json"))
    verification = validate_analysis(report, book)
    issues = [issue for checked in verification.claims for issue in checked.issues]
    assert verification.unsupported_count > 0
    assert any("Lease accounting" in issue for issue in issues)
    assert any("Disclosure scope" in issue for issue in issues)
    assert not any("net_income requires" in issue or "diluted_eps requires" in issue for issue in issues)
    assert report.model_dump(mode="json") == original


def test_original_successful_bundle_keeps_its_full_verification_unchanged():
    accepted = ROOT / "outputs/msft_flat_live_2026-10-17"
    payload = json.loads((accepted / "RESEARCH_BRIEFING.json").read_text(encoding="utf-8"))
    report = ResearchNote.model_validate(payload["assembled_report"])
    verification = validate_analysis(report, payload["source_catalog"])
    assert verification.unsupported_count == 0
    assert verification.model_dump(mode="json") == payload["verification"]
