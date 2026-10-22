"""Investment framework integrity: actual SEC fixture identities, no inferred betas."""
from copy import deepcopy
import json
from pathlib import Path
from datetime import date
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from alphalens.investment_lens import build_investment_lens
from alphalens.service import load_research


APP = str(Path(__file__).resolve().parents[1] / "app.py")


def test_msft_bridge_uses_existing_reported_cash_flows_not_ai_spending_estimate():
    result = load_research("MSFT", "offline")
    lens = build_investment_lens(result)
    bridge = lens["cash_bridge"]
    assert bridge["prior_period"]["fiscal_year"] == 2025
    assert bridge["current_period"]["fiscal_year"] == 2026
    assert bridge["ocf_change"] == 182935000000 - 136162000000
    assert bridge["cash_ppe_change"] == 115948000000 - 64551000000
    assert bridge["fcf_change"] == 66987000000 - 71611000000 == -4624000000
    assert bridge["cash_recovery_gap"] == 4624000000
    assert set(bridge["source_ids"]) <= lens["company_source_registry"].keys()
    assert lens["financial_data_mode"] == "offline"
    assert "not a forecast" in bridge["interpretation"]
    assert all(row["classification"] == "conditional_research_scenario" for row in lens["channels"])
    assert all(row["macro_source_id"] is None for row in lens["channels"])
    assert "not a measure of global enterprise IT budgets" in " ".join(lens["limitations"])
    assert "cannot determine what is already priced in" in " ".join(lens["limitations"])


def test_missing_cash_metric_abstains_from_cash_bridge_without_hiding_questions():
    result = deepcopy(load_research("MSFT", "offline"))
    result.periods[-1].metrics["capital_expenditure"].value = None
    lens = build_investment_lens(result)
    assert lens["cash_bridge"] is None
    assert len(lens["channels"]) == 3
    assert all(row["alternative_explanation"] and row["missing_evidence"] for row in lens["channels"])


def test_cash_bridge_abstains_when_reported_concepts_are_not_comparable():
    result = deepcopy(load_research("MSFT", "offline"))
    result.periods[-1].metrics["capital_expenditure"].sources[0].concept = "us-gaap:DifferentAccountingScope"
    assert build_investment_lens(result)["cash_bridge"] is None


def test_macro_and_company_dates_sources_and_judgment_remain_separate():
    result = load_research("MSFT", "offline")
    snapshot = {"series": [{"series_id": "DGS10", "source_id": "macro:DGS10:2026-10-15",
        "status": "available", "observation_date": "2026-10-15", "value": 5.1,
        "comparison_date": "2025-10-15", "comparison_value": 4.1, "change": 1.0,
        "change_unit": "percentage_points", "source_url": "https://fred.stlouisfed.org/series/DGS10"}]}
    lens = build_investment_lens(result, snapshot)
    rate = next(row for row in lens["channels"] if row["id"] == "rates")
    assert rate["macro_source_id"] == "macro:DGS10:2026-10-15"
    assert rate["macro_context"]["observation_date"] == "2026-10-15"
    assert all(not key.startswith("macro:") for key in rate["company_source_ids"])
    assert all(not key.startswith("macro:") for key in lens["company_source_registry"])
    assert "not WACC" in rate["missing_evidence"]
    assert "higher than its comparison" in rate["current_read_through"]
    assert rate["inference_status"].startswith("Analyst research framework")
    snapshot["series"][0]["status"] = "stale"
    stale = build_investment_lens(result, snapshot)
    assert next(row for row in stale["channels"] if row["id"] == "rates")["macro_source_id"] is None
    assert "No supported current annual macro comparison" in next(row for row in stale["channels"] if row["id"] == "rates")["current_read_through"]


@pytest.mark.parametrize("change,expected", [(2.0, "does not establish a year-on-year industrial contraction"),
    (-2.0, "does not measure this issuer's customer budgets"), (0.0, "unchanged year on year")])
def test_macro_read_through_tracks_observed_direction_without_inventing_company_beta(change, expected):
    snapshot = {"series": [{"series_id": "INDPRO", "status": "available", "change": change}]}
    lens = build_investment_lens(load_research("MSFT", "offline"), snapshot)
    demand = next(row for row in lens["channels"] if row["id"] == "demand")
    assert expected in demand["current_read_through"]
    assert not any(key in demand for key in ("company_beta", "earnings_impact", "price_target", "wacc"))


def test_macro_ui_never_fetches_on_initial_render_and_does_not_call_a_model(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Initial research lens must work without network or AI")
    monkeypatch.setattr("requests.Session.request", forbidden)
    monkeypatch.setattr("alphalens.providers.request_structured", forbidden)
    app = AppTest.from_file(APP).run(timeout=30)
    assert not app.exception
    assert any(tab.label == "Macro & investment drivers" for tab in app.tabs)
    assert app.button(key="load_macro_snapshot")
    assert len(app.metric) == 4
    assert len(app.get("download_button")) == 2
    assert any("No saved macro observations are available yet" in item.value for item in app.info)
    assert any("$+46.77bn" in text.value and "$+51.40bn" in text.value for text in app.markdown)


def test_macro_ui_request_failure_keeps_financials_and_exports_usable(monkeypatch, tmp_path):
    from alphalens.macro import load_macro_snapshot
    def load(**kwargs):
        snapshot = load_macro_snapshot(cache_dir=tmp_path, refresh=False)
        snapshot["errors"] = ["Mocked FRED timeout: no current macro assessment available."]
        return snapshot
    monkeypatch.setattr("alphalens.macro_ui.load_macro_snapshot", load)
    app = AppTest.from_file(APP).run(timeout=30)
    app.button(key="load_macro_snapshot").click().run(timeout=30)
    assert not app.exception
    assert len(app.metric) == 4
    assert any("Mocked FRED timeout" in item.value for item in app.warning)
    assert len(app.get("download_button")) == 3
    assert app.session_state["research_result"].mode == "offline"
    assert json.dumps(build_investment_lens(app.session_state["research_result"]), allow_nan=False)


def test_saved_macro_dashboard_workflow_is_reproducible_without_network_or_ai(monkeypatch, tmp_path):
    from alphalens.macro import load_macro_snapshot
    session = Mock()
    def get(url, **kwargs):
        series = kwargs["params"]["id"]
        dates = ("2025-09-01", "2026-09-01") if series == "INDPRO" else ("2025-10-15", "2026-10-15")
        return Mock(status_code=200, text=f"observation_date,{series}\n{dates[0]},100\n{dates[1]},105\n")
    session.get.side_effect = get
    load_macro_snapshot(tmp_path, refresh=True, as_of=date(2026, 10, 18), session=session)
    def saved(**kwargs):
        assert kwargs["refresh"] is False
        return load_macro_snapshot(tmp_path, as_of=date(2026, 10, 18))
    monkeypatch.setattr("alphalens.macro_ui.load_macro_snapshot", saved)
    def forbidden(*args, **kwargs):
        raise AssertionError("Saved macro workflow must not retrieve data or call a model")
    monkeypatch.setattr("requests.Session.request", forbidden)
    monkeypatch.setattr("alphalens.providers.request_structured", forbidden)
    app = AppTest.from_file(APP).run(timeout=30)
    app.button(key="load_cached_macro_snapshot").click().run(timeout=30)
    assert not app.exception
    assert app.session_state["macro_snapshot"]["mode"] == "cached"
    macro_table = next(item.value for item in app.dataframe if "Indicator" in item.value.columns)
    assert list(macro_table["Latest level"]) == ["105.0000"] * 3
    assert macro_table.iloc[0]["Change"] == "+5.00 pp"
    assert macro_table.iloc[1]["Change"] == "+5.00 %"
    assert len(app.metric) == 4 and len(app.get("download_button")) == 3
    assert app.button(key="generate_ai").disabled


def test_cache_appears_automatically_and_revalidates_next_day_without_http(monkeypatch):
    from alphalens import macro_ui
    from alphalens.macro import load_macro_snapshot
    cache = macro_ui.MACRO_CACHE_DIR
    session = Mock()
    def get(url, **kwargs):
        series = kwargs["params"]["id"]
        dates = ("2025-09-01", "2026-09-01") if series == "INDPRO" else ("2025-10-15", "2026-10-15")
        return Mock(status_code=200, text=f"observation_date,{series}\n{dates[0]},100\n{dates[1]},105\n")
    session.get.side_effect = get
    load_macro_snapshot(cache, refresh=True, as_of=date(2026, 10, 18), session=session)
    current_day = [date(2026, 10, 18)]
    class Clock:
        @staticmethod
        def today():
            return current_day[0]
    monkeypatch.setattr(macro_ui, "date", Clock)
    def forbidden(*args, **kwargs):
        raise AssertionError("Automatic macro cache display must never request HTTP or AI")
    monkeypatch.setattr("requests.Session.request", forbidden)
    monkeypatch.setattr("alphalens.providers.request_structured", forbidden)
    app = AppTest.from_file(APP).run(timeout=30)
    assert not app.exception
    snapshot = app.session_state["macro_snapshot"]
    assert snapshot["mode"] == "cached"
    assert all(row["status"] == "available" for row in snapshot["series"])
    assert not any("not loaded" in item.value for item in app.info)
    assert len(app.get("download_button")) == 3
    table = next(item.value for item in app.dataframe if "Indicator" in item.value.columns)
    assert list(table["Latest level"]) == ["105.0000"] * 3
    current_day[0] = date(2026, 11, 18)
    app.run(timeout=30)
    assert not app.exception
    snapshot = app.session_state["macro_snapshot"]
    assert snapshot["as_of"] == "2026-11-18"
    assert all(row["status"] == "stale" for row in snapshot["series"])
    assert any("too old for a current macro assessment" in item.value for item in app.warning)


def test_corrupt_initial_macro_cache_is_explained_without_a_dashboard_crash(monkeypatch):
    from alphalens import macro_ui
    cache = macro_ui.MACRO_CACHE_DIR
    cache.mkdir(parents=True)
    (cache / "DGS10.json").write_text("not JSON", encoding="utf-8")
    def forbidden(*args, **kwargs):
        raise AssertionError("Corrupt cache must not trigger a hidden request")
    monkeypatch.setattr("requests.Session.request", forbidden)
    app = AppTest.from_file(APP).run(timeout=30)
    assert not app.exception
    assert app.session_state["macro_snapshot"]["mode"] == "unavailable"
    assert any("cached macro data is invalid" in item.value for item in app.warning)
    assert len(app.metric) == 4


def test_investor_page_displays_exact_company_comparison_and_cash_bridge_without_ai(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Investor page must not initiate HTTP or AI")
    monkeypatch.setattr("requests.Session.request", forbidden)
    monkeypatch.setattr("alphalens.providers.request_structured", forbidden)
    app = AppTest.from_file(APP)
    app.query_params["view"] = "macro"
    app.run(timeout=30)
    assert not app.exception
    visible = "\n".join(item.value for item in app.markdown)
    assert "Stronger operating performance" in visible
    for value in ("+17.8%", "+20.8%", "+1.16 pp", "+34.4%", "+79.6%", "-6.5%"):
        assert value in visible
    assert "The constructive case to test" in visible and "The risk case to test" in visible
    charts = [json.loads(item.proto.spec) for item in app.get("plotly_chart")]
    bridge = next(chart["data"][0] for chart in charts if chart["data"][0]["type"] == "waterfall")
    assert bridge["measure"] == ["relative", "relative", "total"]
    assert bridge["y"] == [46.773, -51.397, 0]
    assert bridge["text"][-1] == "-4.62"
    assert any("$+4.62bn" in item.value and "not a forecast" in item.value for item in app.caption)
    assert len(app.metric) == 4
    assert len(app.get("download_button")) == 2
