"""Exercise original-spec additions through the actual Streamlit application."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from streamlit.testing.v1 import AppTest

from alphalens.service import load_research


APP = str(Path(__file__).resolve().parents[1] / "app.py")


def offline_only(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Financial export and local filing inspection must not call HTTP or AI")
    monkeypatch.setattr("requests.Session.request", forbidden)
    monkeypatch.setattr("alphalens.providers.request_structured", forbidden)


def test_financial_note_download_keeps_original_exports_and_needs_no_key(monkeypatch):
    from alphalens import financial_report
    offline_only(monkeypatch)
    notes = []
    original = financial_report.financial_markdown
    def capture(result):
        text = original(result)
        notes.append(text)
        return text
    monkeypatch.setattr(financial_report, "financial_markdown", capture)
    app = AppTest.from_file(APP).run(timeout=30)
    assert not app.exception and len(app.get("download_button")) == 2
    app.toggle(key="financial_report_toggle").set_value(True).run(timeout=30)
    assert not app.exception and len(notes) == 1
    assert len(app.get("download_button")) == 3
    assert "OFFLINE DEMONSTRATION" in notes[0]
    assert "2026:operating_cash_flow" in notes[0] and "## Financial source appendix" in notes[0]
    assert app.button(key="generate_ai").disabled
    assert any("Latest annual filing:" in item.value and "filed 2026-" in item.value for item in app.caption)


def test_financial_export_failure_does_not_break_dashboard_or_csv_json(monkeypatch):
    offline_only(monkeypatch)
    def rejected(*args):
        raise ValueError("An authored corrupt-source case")
    monkeypatch.setattr("alphalens.financial_report.financial_markdown", rejected)
    app = AppTest.from_file(APP).run(timeout=30)
    app.toggle(key="financial_report_toggle").set_value(True).run(timeout=30)
    assert not app.exception and len(app.metric) == 4
    assert len(app.get("download_button")) == 2
    assert any("could not pass source or arithmetic checks" in item.value for item in app.error)


def test_overview_abstains_on_changed_concepts_and_charts_margins_as_percent(monkeypatch):
    import streamlit as st
    offline_only(monkeypatch)
    result = deepcopy(load_research("MSFT", "offline"))
    result.periods[-1].metrics["revenue"].sources[0].concept = "us-gaap:DifferentRevenueScope"
    monkeypatch.setattr("alphalens.service.load_research", lambda *args, **kwargs: result)
    charts = []
    original = st.plotly_chart
    def capture(figure, *args, **kwargs):
        if kwargs.get("key") == "annual_operating_margin":
            charts.append(figure.to_plotly_json())
        return original(figure, *args, **kwargs)
    monkeypatch.setattr(st, "plotly_chart", capture)
    app = AppTest.from_file(APP).run(timeout=30)
    assert not app.exception
    assert app.metric[0].delta == ""
    assert any("Revenue comparison is N/A" in item.value for item in app.markdown)
    trace = charts[0]["data"][0]
    assert trace["connectgaps"] is False
    for period, actual in zip(result.periods, trace["y"]):
        expected = 100 * period.metrics["operating_income"].value / period.metrics["revenue"].value
        assert actual == pytest.approx(expected)
    evidence = next(item.value for item in app.dataframe if "XBRL concept" in item.value.columns)
    for metric in ("Cash and cash equivalents", "Total debt", "Net debt"):
        assert all(value.startswith("At ") for value in evidence.loc[evidence["Metric"] == metric, "Statement period"])


def test_uploaded_filing_inspection_is_labelled_local_and_clears_stale_results(monkeypatch):
    offline_only(monkeypatch)
    import streamlit as st
    from alphalens.evidence import build_evidence_book
    upload = SimpleNamespace(name="copied_filing.txt", getvalue=lambda: b"Capital expenditure may affect future cash flow. USER-SUPPLIED TEST TEXT.")
    def bounded_upload(*args, **kwargs):
        assert kwargs["max_upload_size"] == 5
        return upload
    monkeypatch.setattr(st, "file_uploader", bounded_upload)
    app = AppTest.from_file(APP).run(timeout=30)
    before = build_evidence_book(app.session_state["research_result"])
    assert not app.button(key="inspect_uploaded_filing").disabled
    app.button(key="inspect_uploaded_filing").click().run(timeout=30)
    assert not app.exception
    assert any("USER-SUPPLIED, UNVERIFIED" in item.value for item in app.warning)
    assert any("USER-SUPPLIED TEST TEXT" in item.value for item in app.text)
    assert app.session_state["manual_filing_preview"][1]["origin"] == "user_supplied_unverified"
    assert build_evidence_book(app.session_state["research_result"]) == before
    assert app.session_state["research_filing_context"] is None
    app.text_input(key="manual_filing_query").set_value("different query").run(timeout=30)
    assert not app.exception and app.session_state["manual_filing_preview"] is None
    assert not any("USER-SUPPLIED TEST TEXT" in item.value for item in app.text)


def test_invalid_upload_is_safe_and_never_promoted_to_evidence(monkeypatch):
    offline_only(monkeypatch)
    import streamlit as st
    upload = SimpleNamespace(name="corrupt.txt", getvalue=lambda: b"%PDF-invalid upload")
    monkeypatch.setattr(st, "file_uploader", lambda *args, **kwargs: upload)
    app = AppTest.from_file(APP).run(timeout=30)
    app.button(key="inspect_uploaded_filing").click().run(timeout=30)
    assert not app.exception and len(app.metric) == 4
    assert any("Binary documents are unsupported" in item.value for item in app.error)
    assert app.session_state["manual_filing_preview"] is None
    assert app.session_state["research_filing_context"] is None
