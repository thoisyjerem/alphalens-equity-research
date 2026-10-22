"""Compact investor synthesis uses existing comparisons, never invented figures."""
from copy import deepcopy
import json

import pytest

from alphalens.analytics import build_analytics
from alphalens.investment_lens import build_investor_readout
from alphalens.service import load_research


def test_actual_msft_readout_preserves_cash_identity_cards_units_and_periods():
    result = load_research("MSFT", "offline")
    output = build_investor_readout(result)
    rows = {row["metric"]: row for row in build_analytics(result)["metrics"] if row["fiscal_year"] == 2026}
    assert "Stronger operating performance" in output["headline"]
    assert len(output["financial_cards"]) == 6
    for card in output["financial_cards"]:
        record = rows[card["metric"]]
        assert card["value"] == record["value"] and card["unit"] == record["unit"]
        assert card["source_ids"][0] == record["source_id"]
        assert set(card["source_ids"]) <= output["source_registry"].keys()
        assert output["source_registry"][record["source_id"]]["comparison_periods"] == [
            {"fiscal_year": 2025, "period_start": "2024-07-01", "period_end": "2025-06-30"},
            {"fiscal_year": 2026, "period_start": "2025-07-01", "period_end": "2026-06-30"}]
    bridge = output["cash_bridge"]
    assert bridge["fcf_change"] == bridge["ocf_change"] - bridge["cash_ppe_change"] == -4_624_000_000
    intensity = output["capital_intensity"]
    assert intensity["prior"] == pytest.approx(64_551 / 136_162)
    assert intensity["current"] == pytest.approx(115_948 / 182_935)
    assert intensity["change_unit"] == "percentage_points" and intensity["unit"] == "ratio"
    assert output["annual_comparison"]["current"]["period_end"] == "2026-06-30"
    assert output["financial_data_mode"] == "offline"
    json.dumps(output, allow_nan=False)


def test_missing_input_abstains_and_does_not_fill_financial_card_or_intensity():
    result = deepcopy(load_research("MSFT", "offline"))
    result.periods[-1].metrics["capital_expenditure"].value = None
    output = build_investor_readout(result)
    cards = {row["metric"]: row for row in output["financial_cards"]}
    assert cards["capital_expenditure_growth"]["value"] is None
    assert cards["capital_expenditure_growth"]["reason"] and not cards["capital_expenditure_growth"]["source_ids"]
    assert output["capital_intensity"] is None and output["capital_intensity_reason"]
    assert output["cash_bridge"] is None
    assert "cash recovery must catch up" not in output["headline"]


def test_changed_accounting_concept_abstains_from_cross_period_cash_claims():
    result = deepcopy(load_research("MSFT", "offline"))
    result.periods[-1].metrics["capital_expenditure"].sources[0].concept = "us-gaap:DifferentScopeTestConcept"
    output = build_investor_readout(result)
    card = next(row for row in output["financial_cards"] if row["metric"] == "capital_expenditure_growth")
    assert card["value"] is None and "concept" in card["reason"].lower()
    assert output["capital_intensity"] is None and output["cash_bridge"] is None


def test_macro_dates_remain_external_context_and_scenarios_are_not_valuations():
    macro = {"series": [{"series_id": "DGS10", "status": "available", "observation_date": "2026-10-15",
        "value": 5.1, "change": 1.05, "source_id": "macro:DGS10:2026-10-15"}]}
    output = build_investor_readout(load_research("MSFT", "offline"), macro)
    assert "postdate" in output["macro_context_limits"][0]
    assert "priced in" in " ".join(output["macro_context_limits"])
    assert output["constructive_case"].startswith("Hypothesis:")
    assert output["cautionary_case"].startswith("Hypothesis:")
    assert all(not key.startswith("macro:") for key in output["source_registry"])
    assert not any(key in output for key in ("ai_capex", "ai_roic", "roic", "wacc", "price_target", "recommendation"))
    assert len(output["more_constructive_if"]) == len(output["more_cautious_if"]) == 2


def test_empty_periods_do_not_invent_comparisons_or_positive_operating_case():
    result = deepcopy(load_research("MSFT", "offline"))
    result.periods = []
    output = build_investor_readout(result)
    assert output["annual_comparison"] == {"prior": None, "current": None}
    assert all(card["value"] is None and card["reason"] for card in output["financial_cards"])
    assert not output["source_registry"] and output["capital_intensity"] is None
    assert "Stronger operating performance" not in output["headline"]
    json.dumps(output, allow_nan=False)
