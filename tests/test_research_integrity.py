"""Prepared financial records are reconciled without model or network calls."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from alphalens.focused_briefing import _fingerprint, build_briefing_context
from alphalens.research_integrity import validate_observation_integrity
from alphalens.service import load_offline_filing_context, load_research


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def genuine_context():
    result = load_research("MSFT", "offline")
    return build_briefing_context(result, [load_offline_filing_context(result)])


def _validate_after_fingerprint_rebuilt(context):
    """Exercise independent reconciliation, not the pre-existing hash guard."""
    context.fingerprint = _fingerprint(context.evidence, context.analysis, context.observations, context.packet)
    validate_observation_integrity(context.evidence, context.analysis, context.observations)


def test_current_and_recorded_genuine_msft_observations_reconcile_without_mutation(genuine_context):
    before = deepcopy((genuine_context.evidence, genuine_context.analysis, genuine_context.observations))
    _validate_after_fingerprint_rebuilt(genuine_context)
    assert (genuine_context.evidence, genuine_context.analysis, genuine_context.observations) == before
    bundle = ROOT / "outputs/msft_findings_live_2026-10-18"
    records = [json.loads((bundle / name).read_text(encoding="utf-8")) for name in
               ("SOURCE_CATALOG.json", "FINANCIAL_ANALYSIS.json", "FINANCIAL_OBSERVATIONS.json")]
    validate_observation_integrity(*records)


def test_changed_comparison_value_period_or_source_fails_even_with_new_fingerprint(genuine_context):
    def amount(entry):
        entry["value"] += 1000
    def fiscal_year(entry):
        entry["fiscal_year"] -= 1
    def source(entry):
        entry["source_id"] = "2026:invented"
    for corrupt in (amount, fiscal_year, source):
        context = deepcopy(genuine_context)
        comparison = context.observations["2026:cash_flow_divergence"]["comparisons"][0]["current"]
        corrupt(comparison)
        with pytest.raises(ValueError, match="Financial observation integrity failed"):
            _validate_after_fingerprint_rebuilt(context)


def test_observation_changes_must_match_analytics_formula_direction_and_dependencies(genuine_context):
    changes = {"value": -1, "formula": "invented arithmetic", "direction": "decrease",
               "dependencies": ["2026:revenue"]}
    for key, wrong_value in changes.items():
        context = deepcopy(genuine_context)
        context.observations["2026:cash_flow_divergence"]["changes"][0][key] = wrong_value
        with pytest.raises(ValueError, match="Financial observation integrity failed"):
            _validate_after_fingerprint_rebuilt(context)


def test_consistently_corrupted_fcf_copy_still_fails_independent_cash_identity(genuine_context):
    context = genuine_context
    record = next(row for row in context.analysis["metrics"] if row["source_id"] == "2026:analytics.free_cash_flow")
    record["value"] += 1_000_000
    # Make every duplicated comparison agree, so membership/copy matching alone
    # would pass. The retained OCF and cash purchases must expose the false FCF.
    for observation in context.observations.values():
        for comparison in observation["comparisons"]:
            if comparison["metric"] == "free_cash_flow":
                comparison["current"]["value"] = record["value"]
    with pytest.raises(ValueError, match="free cash flow does not reconcile"):
        _validate_after_fingerprint_rebuilt(context)


def test_matching_comparison_and_source_cannot_hide_incompatible_periods(genuine_context):
    entry = genuine_context.observations["2026:cash_flow_divergence"]["comparisons"][0]["current"]
    entry["period_start"] = "2026-01-01"
    genuine_context.evidence[entry["source_id"]]["period_start"] = entry["period_start"]
    with pytest.raises(ValueError, match="comparison fiscal dates"):
        _validate_after_fingerprint_rebuilt(genuine_context)


def test_nonfinancial_raw_dependency_and_wrong_capex_sign_fail_safely(genuine_context):
    for source_id, replacement in (("2026:operating_cash_flow", {"kind": "passage", "text": "Not financial evidence"}),
                                   ("2026:capital_expenditure", {**genuine_context.evidence["2026:capital_expenditure"], "value": -115948000000})):
        context = deepcopy(genuine_context)
        context.evidence[source_id] = replacement
        if source_id.endswith("capital_expenditure"):
            for observation in context.observations.values():
                for comparison in observation["comparisons"]:
                    if comparison["metric"] == "capital_expenditure":
                        comparison["current"]["value"] = replacement["value"]
        with pytest.raises(ValueError, match="Financial observation integrity failed"):
            _validate_after_fingerprint_rebuilt(context)


def test_extracted_fcf_display_cannot_disagree_with_reconciled_analytics(genuine_context):
    genuine_context.evidence["2026:free_cash_flow"]["value"] += 1000
    with pytest.raises(ValueError, match="displayed free cash flow conflicts"):
        _validate_after_fingerprint_rebuilt(genuine_context)
