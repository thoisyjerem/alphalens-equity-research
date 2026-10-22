"""Quality-stage Streamlit interactions use authored mocks and local SEC fixtures."""
from copy import deepcopy
from pathlib import Path

from streamlit.testing.v1 import AppTest


APP = str(Path(__file__).resolve().parents[1] / "app.py")


def test_actual_recorded_briefing_loads_and_exports_without_api_key_or_inference(monkeypatch):
    import json
    from alphalens import research_exports, saved_research

    def forbidden(*args, **kwargs):
        raise AssertionError("Saved demonstration must not instantiate an API client or retrieve data")
    monkeypatch.setattr("openai.OpenAI", forbidden)
    monkeypatch.setattr("alphalens.providers.request_structured", forbidden)
    monkeypatch.setattr("httpx.Client.send", forbidden)
    monkeypatch.setattr("requests.Session.request", forbidden)
    bundle = Path(__file__).resolve().parents[1] / "outputs/msft_findings_live_2026-10-18"
    original = json.loads((bundle / "RESEARCH_BRIEFING.json").read_text(encoding="utf-8"))
    ledger = json.loads((bundle / "REQUEST_LEDGER.json").read_text(encoding="utf-8"))
    replay = saved_research.load_saved_briefing()
    assert replay.contract == "focused_v3"
    assert ledger["http_status"] == 200 and ledger["http_requests_attempted"] == 1
    assert replay.output.model_dump(mode="json") == original["assembled_report"]
    assert replay.verification.model_dump(mode="json") == original["verification"]
    assert replay.evidence == original["source_catalog"]
    for year, start, end, ocf, capex, fcf in (
        (2025, "2024-07-01", "2025-06-30", 136162000000, 64551000000, 71611000000),
        (2026, "2025-07-01", "2026-06-30", 182935000000, 115948000000, 66987000000),
    ):
        for metric, value in (("operating_cash_flow", ocf), ("capital_expenditure", capex), ("free_cash_flow", fcf)):
            source = replay.evidence[f"{year}:{metric}"]
            assert (source["value"], source["unit"], source["fiscal_year"], source["period_start"], source["period_end"]) == (
                value, "USD", year, start, end)
            assert source["sources"] and all(row["url"].startswith("https://www.sec.gov/") for row in source["sources"])
        assert ocf - capex == fcf

    exports = {}
    original_markdown = research_exports.export_research_markdown
    original_json = research_exports.export_research_json
    def markdown_export(validated):
        exports["markdown"] = original_markdown(validated)
        return exports["markdown"]
    def json_export(validated):
        exports["json"] = json.loads(original_json(validated))
        return json.dumps(exports["json"])
    monkeypatch.setattr(research_exports, "export_research_markdown", markdown_export)
    monkeypatch.setattr(research_exports, "export_research_json", json_export)
    app = AppTest.from_file(APP).run(timeout=30)
    app.button(key="load_saved_msft_briefing").click().run(timeout=30)
    assert not app.exception
    saved = app.session_state["saved_msft_briefing"]
    assert saved.verification.unsupported_count == 0
    assert saved.contract == "focused_v3"
    assert saved.usage == ledger["normalized_usage"] == {"input_tokens": 5381, "output_tokens": 560, "total_tokens": 5941}
    assert len(saved.transport_output) == 13
    assert not any(key.startswith("executive_") for key in saved.transport_output)
    assert saved.output.executive_summary == saved.output.what_matters_most
    assert saved.transport_output["primary_interpretation"].startswith("Operating cash flow expanded")
    assert any("SAVED LIVE DEMONSTRATION" in message.value for message in app.info)
    assert not any("tax receipts" in message.value for message in app.info)
    assert any(item.label == "Inspect Python financial observations" for item in app.expander)
    for key in ("generate_ai", "generate_research_brief", "generate_thesis"):
        assert app.button(key=key).disabled
    app.toggle(key="saved_msft_export_toggle").set_value(True).run(timeout=30)
    assert not app.exception and len(app.get("download_button")) == 4
    assert len(app.metric) == 4  # Financial dashboard remains intact.
    assert exports["json"]["assembled_report"] == original["assembled_report"]
    assert exports["json"]["verification"] == original["verification"]
    assert exports["json"]["raw_model_output"] == original["raw_model_output"]
    assert exports["json"]["source_catalog"] == original["source_catalog"]
    assert "SAVED LIVE DEMONSTRATION" in exports["markdown"]


def test_recorded_briefing_failure_keeps_dashboard_usable_and_hides_raw_error(monkeypatch):
    from alphalens import saved_research
    def rejected():
        raise ValueError("private-example-error-must-not-display")
    monkeypatch.setattr(saved_research, "load_saved_briefing", rejected)
    app = AppTest.from_file(APP).run(timeout=30)
    app.button(key="load_saved_msft_briefing").click().run(timeout=30)
    assert not app.exception and app.session_state["saved_msft_briefing"] is None
    assert any("failed its integrity or validation checks" in message.value for message in app.error)
    assert all("private-example-error" not in message.value for message in app.error)
    assert len(app.metric) == 4 and len(app.get("download_button")) == 2


def _consent(app, prefix):
    return next(item for item in app.checkbox if item.key.startswith(f"{prefix}_consent_"))


def _mock_checked_research(result, model, contexts):
    from alphalens.ai import ValidatedResearch
    from alphalens.analytics import build_analytics
    from alphalens.evidence import build_evidence_book
    from alphalens.research import Claim, ResearchNote, validate_analysis

    book = build_evidence_book(result, contexts)
    source_id = f"{result.periods[-1].fiscal_year}:revenue"
    citation = {"source_id": source_id, **{key: book[source_id][key] for key in
                ("value", "unit", "fiscal_year", "period_start", "period_end")}}
    fact = Claim(text="Reported revenue is available for the cited annual period.", kind="fact", financial_citations=[citation])
    passage_id, passage = next((key, value) for key, value in book.items() if value["kind"] == "passage")
    narrative = Claim(text="The management disclosure provides context for further research.", kind="inference",
        passage_citations=[{"source_id": passage_id, "quote": passage["text"][:160]}])
    output = ResearchNote(performance=[fact], business_developments=[narrative],
        investment_considerations=[], risks=[], executive_summary=[fact], what_matters_most=[narrative],
        capital_allocation=[], missing_information=[Claim(text="What evidence would establish sustainable cash returns?", kind="question")])
    return ValidatedResearch(output=output, verification=validate_analysis(output, book), evidence=book,
        model=model, warnings=["Authored offline mock, not a live model evaluation."], analysis=build_analytics(result),
        diagnostics={"parsing_result": "passed", "schema_validation_result": "passed",
                     "numerical_validation_result": "passed", "source_validation_result": "requires_analyst_review"})


def test_no_credentials_disables_all_ai_but_keeps_calculations_tensions_and_na():
    app = AppTest.from_file(APP).run(timeout=30)
    assert not app.exception
    for key in ("generate_ai", "generate_research_brief", "generate_thesis"):
        assert app.button(key=key).disabled
    assert len(app.metric) == 4
    assert any(item.value == "Annual comparisons & capital allocation" for item in app.subheader)
    assert any("PYTHON CALCULATIONS" in item.value for item in app.caption)
    metrics = next(item.value for item in app.dataframe if "Why N/A" in item.value.columns and "Source IDs" in item.value.columns)
    assert "N/A" in set(metrics["Value"])
    assert metrics.loc[metrics["Value"] == "N/A", "Why N/A"].str.len().gt(0).all()
    assert any("Cash PP&E growth exceeds operating-cash-flow growth" in item.value for item in app.markdown)
    assert any("not an AI spending estimate" in item.value for item in app.text)
    assert any("2024-07-01 to 2025-06-30 versus 2025-07-01 to 2026-06-30" in item.value for item in app.caption)
    assert len(app.get("download_button")) == 2


def test_commentary_json_failure_exposes_safe_stage_and_preserves_core_dashboard(monkeypatch):
    from alphalens import commentary
    from alphalens.providers import ProviderError

    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "offline-ui-key")
    calls = []
    def malformed(*args, **kwargs):
        calls.append(1)
        assert kwargs["gemini_native"] is True
        raise ProviderError("Gemini returned malformed native JSON.", diagnostics={
            "parsing_result": "failed", "schema_validation_result": "not_run", "validation_stage": "native_json",
            "validation_issues": [{"path": "$", "type": "json_invalid"}]})

    monkeypatch.setattr(commentary, "request_structured", malformed)
    app = AppTest.from_file(APP).run(timeout=30)
    _consent(app, "ai").check().run(timeout=30)
    app.button(key="generate_ai").click().run(timeout=30)
    assert not app.exception and calls == [1]
    assert app.session_state["ai_brief"] is None
    assert any("Stage: native_json" in item.value and "Schema: not_run" in item.value for item in app.caption)
    assert any("$: json_invalid" == item.value for item in app.text)
    assert any(item.label == "Inspect AI commentary validation failure" for item in app.expander)
    assert len(app.metric) == 4 and len(app.get("download_button")) == 2
    assert app.button(key="generate_ai").disabled
    app.run(timeout=30)
    assert calls == [1]  # Rerendering a failure never generates another request.


def test_schema_failure_shows_exact_missing_field_without_partial_report_or_core_damage(monkeypatch):
    from alphalens import ai

    monkeypatch.setenv("OPENAI_API_KEY", "authored-mock-never-a-real-key")
    calls = []
    def fail_once(*args, **kwargs):
        calls.append(1)
        raise ai.AiError("AI response failed strict schema validation.", diagnostics={
            "parsing_result": "passed", "schema_validation_result": "failed", "validation_stage": "schema",
            "validation_issues": [{"path": "missing_information.0.kind", "type": "missing"}]})

    monkeypatch.setattr(ai, "generate_research_brief", fail_once)
    app = AppTest.from_file(APP).run(timeout=30)
    _consent(app, "research_brief").check().run(timeout=30)
    app.button(key="generate_research_brief").click().run(timeout=30)
    assert not app.exception
    assert calls == [1]
    assert app.session_state["research_brief_result"] is None
    assert any("missing_information.0.kind: missing" in item.value for item in app.text)
    assert any("Parsing: passed" in item.value and "Schema: failed" in item.value for item in app.caption)
    assert any("No automatic retry" in item.value for item in app.caption)
    assert len(app.metric) == 4
    assert any(item.value == "Annual comparisons & capital allocation" for item in app.subheader)
    assert len(app.get("download_button")) == 2
    assert app.button(key="generate_research_brief").disabled


def test_export_toggle_builds_two_actual_research_downloads_and_preserves_sources(monkeypatch):
    import json
    from alphalens import ai, research_exports

    monkeypatch.setenv("OPENAI_API_KEY", "authored-mock-never-a-real-key")
    calls, exports = [], []
    def generate(result, api_key, model, *, filing_contexts):
        calls.append(1)
        return _mock_checked_research(result, model, filing_contexts)
    original_markdown, original_json = research_exports.export_research_markdown, research_exports.export_research_json
    def markdown_export(saved):
        output = original_markdown(saved)
        exports.append(("markdown", output))
        return output
    def json_export(saved):
        output = original_json(saved)
        exports.append(("json", output))
        return output
    monkeypatch.setattr(ai, "generate_research_brief", generate)
    monkeypatch.setattr(research_exports, "export_research_markdown", markdown_export)
    monkeypatch.setattr(research_exports, "export_research_json", json_export)
    app = AppTest.from_file(APP).run(timeout=30)
    _consent(app, "research_brief").check().run(timeout=30)
    app.button(key="generate_research_brief").click().run(timeout=30)
    assert not app.exception
    assert calls == [1] and not exports
    assert any("Executive investment research summary" in item.value for item in app.markdown)
    assert any("Analyst review required" == item.label for item in app.expander)
    assert any("Financial source: 2026:revenue" in item.value for item in app.caption)
    assert len(app.get("download_button")) == 2
    app.toggle(key="research_brief_export_toggle").set_value(True).run(timeout=30)
    assert not app.exception
    assert calls == [1]
    assert len(app.get("download_button")) == 4
    assert [kind for kind, _ in exports] == ["markdown", "json"]
    markdown = exports[0][1]
    payload = json.loads(exports[1][1])
    assert "Open official SEC source" in markdown
    assert payload["metadata"]["semantic_review"] == "requires_analyst_review"
    assert payload["python_analysis"]["metrics"]
    assert payload["source_catalog"] == app.session_state["research_brief_result"].evidence


def test_focused_retrieval_ui_retains_independent_original_reader(monkeypatch):
    from alphalens import service
    from alphalens.filings import extract_filing_excerpts
    from alphalens.retrieval import select_filing_passages

    result = service.load_research("MSFT", "offline")
    result.mode = "live"
    text = "Synthetic business background without specific topic evidence. " * 120
    html = f"""<h2>ITEM 1A. RISK FACTORS</h2><p>{text}Competition and energy supply limit datacenter capacity.</p>
    <h2>ITEM 1B. UNRESOLVED STAFF COMMENTS</h2>
    <h2>ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS</h2><p>{text}Capital expenditures, depreciation, finance leases and cash from operations require review.</p>
    <h2>ITEM 7A. QUANTITATIVE AND QUALITATIVE DISCLOSURES ABOUT MARKET RISK</h2>"""
    excerpts = extract_filing_excerpts(html)
    context = service.make_filing_context(result, result.filings[0]["accession"], excerpts)
    context["focused_passages"] = select_filing_passages(html)
    retrievals = []
    monkeypatch.setattr(service, "load_research", lambda *args, **kwargs: deepcopy(result))
    monkeypatch.setattr(service, "load_filing_excerpts", lambda *args, **kwargs: excerpts)
    def retrieve(*args, **kwargs):
        retrievals.append(1)
        return deepcopy(context)
    monkeypatch.setattr(service, "load_research_filing_context", retrieve)
    app = AppTest.from_file(APP).run(timeout=30)
    assert not retrievals
    app.button(key="extract_filing").click().run(timeout=30)
    assert not app.exception
    assert app.session_state["filing_excerpts"][2] == excerpts
    app.button(key="research_load_context").click().run(timeout=30)
    assert not app.exception
    assert retrievals == [1]
    assert app.session_state["filing_excerpts"][2] == excerpts
    assert app.session_state["research_filing_context"]["focused_passages"] == context["focused_passages"]
    assert any("Capital expenditures, depreciation" in item.value for item in app.text)
    assert any(excerpt.text in item.value for excerpt in excerpts.values() for item in app.text)
