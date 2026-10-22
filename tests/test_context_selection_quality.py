"""Regress actual overlap and debt-pricing selection defects without retrieval."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from alphalens.focused_briefing import (_additional_development, _short_passages,
    BriefingContext, FocusedBriefingInterpretation, _fingerprint, assemble_briefing,
    build_briefing_context)
from alphalens.service import load_offline_filing_context, load_research

ROOT = Path(__file__).resolve().parents[1]


def test_actual_saved_full_evidence_selects_competition_not_debt_market_pricing():
    original = json.loads((ROOT / "outputs/msft_flat_live_2026-10-17/SOURCE_CATALOG.json").read_text())
    parents = {key: row for key, row in original.items() if "parent_source_id" not in row}
    selected = _short_passages(parents)
    assert any(row["item"] == "1A" and row.get("parent_source_id") == "sec:cee5d01d4c45f8900753535a"
               for row in selected.values())
    assert not any("favorable pricing and liquidity in debt markets" in row["text"].lower()
                   for row in selected.values())
    for row in selected.values():
        parent = parents[row["parent_source_id"]]
        offset = row["offset_start"] - parent["offset_start"]
        assert parent["text"][offset:offset+len(row["text"]) ] == row["text"]


def test_msft_secondary_development_is_supported_growth_not_duplicate_investment():
    result = load_research("MSFT", "offline")
    context = build_briefing_context(result, [load_offline_filing_context(result)])
    selected = context.packet["required_additional_observation_id"]
    assert selected == "2026:revenue_profit_growth"
    assert selected in context.observations
    assert context.observations[selected]["source_ids"]
    assert context.packet["primary_observation_id"] == "2026:cash_flow_divergence"


def test_historical_response_remains_valid_but_overlap_cannot_fill_new_required_development():
    directory = ROOT / "outputs/msft_flat_live_2026-10-17"
    def read(name):
        return json.loads((directory / name).read_text())
    book, analysis, observations, packet = (read(name) for name in
        ("SOURCE_CATALOG.json", "FINANCIAL_ANALYSIS.json", "FINANCIAL_OBSERVATIONS.json", "FOCUSED_CONTEXT.json"))
    payload = FocusedBriefingInterpretation.model_validate(read("MODEL_INTERPRETATION.json"))
    old = BriefingContext(book, analysis, observations, packet, _fingerprint(book, analysis, observations, packet))
    assert assemble_briefing(payload, old)[1].unsupported_count == 0
    packet = deepcopy(packet)
    packet["required_additional_observation_id"] = _additional_development(observations)
    new = BriefingContext(book, analysis, observations, packet, _fingerprint(book, analysis, observations, packet))
    with pytest.raises(ValueError, match="additional financial development was omitted"):
        assemble_briefing(payload, new)
    # Nothing in the real output is relabelled or filled in to satisfy this rule.
    assert read("MODEL_INTERPRETATION.json")["findings"][0]["observation_ids"] == ["2026:investment_intensity"]


def test_no_independent_observation_is_invented_when_only_cash_rules_exist():
    observations = {"cash": {"type": "cash_flow_divergence"}, "intensity": {"type": "investment_intensity"}}
    assert _additional_development(observations) is None
