"""The presentation readout must reconcile the genuine recorded evidence.

These are offline replay/corruption checks, not an evaluation of new model output.
"""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest

from alphalens.saved_research import load_saved_briefing


SEGMENT_ID = "sec:3eb3eccc7d1065f444ebdf69"


@pytest.fixture
def recorded():
    return load_saved_briefing()


def _readout(recorded):
    from alphalens.recorded_readout import build_recorded_readout
    return build_recorded_readout(recorded)


def test_genuine_recorded_cash_bridge_and_divergent_margins_are_recomputed_without_mutation(recorded, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("A recorded presentation must not retrieve data or call an AI provider")

    monkeypatch.setattr("alphalens.providers.request_structured", forbidden)
    monkeypatch.setattr("httpx.Client.send", forbidden)
    monkeypatch.setattr("requests.Session.request", forbidden)
    before = deepcopy((recorded.evidence, recorded.analysis, recorded.financial_observations,
                       recorded.output.model_dump(mode="json"), recorded.transport_output))
    readout = _readout(recorded)
    assert readout["prior_period"] == {"fiscal_year": 2025, "period_start": "2024-07-01", "period_end": "2025-06-30"}
    assert readout["current_period"] == {"fiscal_year": 2026, "period_start": "2025-07-01", "period_end": "2026-06-30"}
    cash = {row["metric"]: row for row in readout["cash_rows"]}
    expected = {
        "operating_cash_flow": (136162000000, 182935000000, 46773000000),
        "capital_expenditure": (64551000000, 115948000000, 51397000000),
        "free_cash_flow": (71611000000, 66987000000, -4624000000),
    }
    for metric, (prior, current, change) in expected.items():
        assert (cash[metric]["prior"], cash[metric]["current"], cash[metric]["change"]) == tuple(map(Decimal, (prior, current, change)))
        assert cash[metric]["source_ids"]
        assert set(cash[metric]["source_ids"]) <= recorded.evidence.keys()
    assert cash["operating_cash_flow"]["change"] - cash["capital_expenditure"]["change"] == cash["free_cash_flow"]["change"]
    consolidated = next(row for row in readout["margins"] if "consolidated" in row["label"].lower())
    cloud = next(row for row in readout["margins"] if "intelligent cloud" in row["label"].lower())
    for row, prior_income, prior_revenue, current_income, current_revenue in (
        (consolidated, 128528, 281724, 155237, 331839),
        (cloud, 44589, 106265, 56972, 137791),
    ):
        assert row["prior_pct"] == Decimal(prior_income) / Decimal(prior_revenue) * 100
        assert row["current_pct"] == Decimal(current_income) / Decimal(current_revenue) * 100
        assert row["change_pp"] == row["current_pct"] - row["prior_pct"]
    assert consolidated["change_pp"] > 0 > cloud["change_pp"]
    assert readout["segment_source_id"] == SEGMENT_ID
    assert (recorded.evidence, recorded.analysis, recorded.financial_observations,
            recorded.output.model_dump(mode="json"), recorded.transport_output) == before


@pytest.mark.parametrize("field,replacement", [
    ("value", 182936000000),
    ("unit", "USD/share"),
    ("period_start", "2026-01-01"),
    ("fiscal_year", 2025),
])
def test_cash_presentation_rejects_corrupt_amount_units_and_annual_periods(recorded, field, replacement):
    current = recorded.financial_observations["2026:cash_flow_divergence"]["comparisons"][0]["current"]
    current[field] = replacement
    with pytest.raises(ValueError):
        _readout(recorded)


@pytest.mark.parametrize("before,after", [
    ("In millions, except percentages", "In thousands, except percentages"),
    ("2026 2025 PercentageChange", "2026 2024 PercentageChange"),
    ("Operating income $ 56,972 $ 44,589", "Operating income $ 56,973 $ 44,589"),
    ("Total Revenue $ 331,839 $ 281,724", "Total Revenue $ 331,840 $ 281,724"),
])
def test_segment_readout_rejects_changed_scale_years_or_nonreconciling_table(recorded, before, after):
    source = recorded.evidence[SEGMENT_ID]
    assert before in source["text"]
    source["text"] = source["text"].replace(before, after, 1)
    with pytest.raises(ValueError):
        _readout(recorded)


@pytest.mark.parametrize("field,replacement", [
    ("accession", "0001193125-25-000001"),
    ("report_date", "2025-06-30"),
    ("ticker", "AAPL"),
    ("kind", "financial"),
])
def test_segment_presentation_does_not_attach_other_company_or_filing_context(recorded, field, replacement):
    recorded.evidence[SEGMENT_ID][field] = replacement
    with pytest.raises(ValueError):
        _readout(recorded)


def test_missing_recorded_segment_source_abstains_without_inventing_a_margin(recorded):
    del recorded.evidence[SEGMENT_ID]
    with pytest.raises(ValueError):
        _readout(recorded)


def test_actual_offline_streamlit_readout_separates_sources_judgment_and_model_with_safe_abstention(monkeypatch):
    from streamlit.testing.v1 import AppTest

    def forbidden(*args, **kwargs):
        raise AssertionError("The recorded readout must remain available without remote services")

    monkeypatch.setattr("alphalens.providers.request_structured", forbidden)
    monkeypatch.setattr("httpx.Client.send", forbidden)
    monkeypatch.setattr("requests.Session.request", forbidden)
    root = Path(__file__).resolve().parents[1]
    app = AppTest.from_file(str(root / "app.py")).run(timeout=30)
    app.button(key="load_saved_msft_briefing").click().run(timeout=30)
    assert not app.exception
    prose = "\n".join(row.value for row in app.markdown)
    for expected in ("+46.773 USD bn", "+51.397 USD bn", "-4.624 USD bn",
                     "SEC-reported facts", "Python-calculated metrics", "Gemini interpretations",
                     "Independent reviewer observations", "Unverified hypotheses / missing evidence",
                     "Genuine recorded Gemini interpretations — unchanged"):
        assert expected in prose
    captions = "\n".join(row.value for row in app.caption)
    assert "FY2026 (2025-07-01 to 2026-06-30)" in captions
    assert "FY2025 (2024-07-01 to 2025-06-30)" in captions
    assert "no new Gemini output" in captions and SEGMENT_ID in captions
    assert "replay does not validate the revised prompt" in captions
    table = next(row.value for row in app.dataframe if "Operating margin" in row.value.columns)
    assert table.to_dict("records") == [
        {"Operating margin": "Consolidated", "FY2025": "45.62%", "FY2026": "46.78%", "Change (percentage points)": "+1.16"},
        {"Operating margin": "Intelligent Cloud", "FY2025": "41.96%", "FY2026": "41.35%", "Change (percentage points)": "-0.61"},
    ]
    review = "\n".join(row.value for row in app.text)
    assert "working-capital benefits that the cited passage does not establish" in review
    assert "Nearby OpenAI investment gains concern net income/EPS" in review
    assert "company-wide cash PP&E is neither AI-only spending nor lease-inclusive investment" in review
    assert "cannot determine whether investment creates or destroys value" in review
    assert len(app.metric) == 4
    assert len(app.get("download_button")) == 2
    recorded = app.session_state["saved_msft_briefing"]
    assert recorded.transport_output["primary_interpretation"].startswith("Operating cash flow expanded")
    assert recorded.transport_output["unanswered_questions"][0].startswith("How sustainable are the working capital benefits")

    damaged = deepcopy(recorded)
    damaged.evidence[SEGMENT_ID]["report_date"] = "2025-06-30"

    def isolated_readout(saved):
        from alphalens.research_ui import _show_recorded_readout
        _show_recorded_readout(saved)

    withheld = AppTest.from_function(isolated_readout, args=(damaged,)).run(timeout=30)
    assert not withheld.exception
    assert any("could not be reconciled and are withheld" in row.value for row in withheld.warning)
    assert len(withheld.dataframe) == 0
    assert not any("USD bn" in row.value for row in withheld.markdown)
