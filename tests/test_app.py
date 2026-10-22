"""Browser-free interaction tests of the actual Streamlit application."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


APP = str(Path(__file__).resolve().parents[1] / "app.py")


def submit_research(app):
    return next(button for button in app.button if button.label == "Load annual research").click().run(timeout=30)


def test_offline_app_loads_with_evidence_and_exports(monkeypatch):
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "")
    app = AppTest.from_file(APP).run(timeout=30)

    assert not app.exception
    assert any("OFFLINE DEMONSTRATION" in item.value for item in app.warning)
    assert any("MICROSOFT" in item.value.upper() for item in app.subheader)
    assert len(app.metric) == 4
    assert app.metric[0].value != "N/A"
    assert len(app.dataframe) >= 3
    assert len(app.get("download_button")) == 2
    assert app.session_state["research_result"].mode == "offline"
    assert len(app.session_state["research_result"].periods) == 3
    assert app.button(key="generate_ai").disabled


def test_unknown_ticker_clears_previous_research():
    app = AppTest.from_file(APP).run(timeout=30)
    assert not app.exception
    app.text_input(key="ticker_input").set_value("ZZZZUNKNOWN")
    submit_research(app)

    assert not app.exception
    assert app.error
    assert app.session_state["research_result"] is None
    assert len(app.metric) == 0
    assert not any("MICROSOFT" in item.value.upper() for item in app.subheader)


def test_evidence_filter_changes_source_table():
    app = AppTest.from_file(APP).run(timeout=30)
    app.selectbox(key="evidence_filter").select("Revenue").run(timeout=30)

    assert not app.exception
    evidence_tables = [item.value for item in app.dataframe if "XBRL concept" in item.value.columns]
    assert len(evidence_tables) == 1
    assert set(evidence_tables[0]["Metric"]) == {"Revenue"}
    assert len(evidence_tables[0]) == 3


@pytest.mark.parametrize("ticker", ["AAPL", "AMZN"])
def test_offline_does_not_substitute_microsoft_for_other_tickers(ticker):
    app = AppTest.from_file(APP).run(timeout=30)
    app.text_input(key="ticker_input").set_value(ticker)
    submit_research(app)

    assert not app.exception
    assert any("Microsoft only" in item.value for item in app.error)
    assert app.session_state["research_result"] is None
    assert not app.metric


def test_invalid_live_identity_is_rejected_without_network(monkeypatch):
    import requests

    def unexpected_network(*args, **kwargs):
        raise AssertionError("Invalid live identity must be rejected before network access.")

    monkeypatch.setattr(requests.Session, "get", unexpected_network)
    app = AppTest.from_file(APP).run(timeout=30)
    app.selectbox(key="source_mode").select("Live SEC API")
    app.text_input(key="sec_user_agent_input").set_value("missing contact email")
    submit_research(app)

    assert not app.exception
    assert any("SEC_USER_AGENT" in item.value for item in app.error)
    assert app.session_state["research_result"] is None


def test_optional_ai_renders_python_evidence_and_clears_on_new_search(monkeypatch):
    from alphalens import ai

    monkeypatch.setenv("OPENAI_API_KEY", "test-only-no-network")

    def local_test_brief(result, api_key, model):
        latest = result.periods[-1]
        return ai.ResearchBrief(
            observations=[ai.Insight(
                text="Cash generation warrants closer investigation.",
                evidence_ids=[f"{latest.fiscal_year}:free_cash_flow"],
            )],
            questions=["How sustainable is cash generation?"],
            caveats=["Historical reporting does not establish future performance."],
        )

    monkeypatch.setattr(ai, "generate_brief", local_test_brief)
    app = AppTest.from_file(APP).run(timeout=30)
    assert not app.button(key="generate_ai").disabled
    app.button(key="generate_ai").click().run(timeout=30)

    assert not app.exception
    evidence_tables = [item.value for item in app.dataframe if "Evidence ID" in item.value.columns]
    assert len(evidence_tables) == 1
    latest = app.session_state["research_result"].periods[-1]
    expected_fcf = f"{latest.metrics['free_cash_flow'].value / 1_000_000:,.0f}"
    assert evidence_tables[0].iloc[0]["Value"] == expected_fcf
    assert evidence_tables[0].iloc[0]["Evidence ID"] == f"{latest.fiscal_year}:free_cash_flow"

    app.text_input(key="ticker_input").set_value("UNKNOWN")
    submit_research(app)
    assert not app.exception
    assert app.session_state["ai_brief"] is None
