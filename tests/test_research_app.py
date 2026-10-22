"""Interaction tests of the new AI tools, using local parsed mock responses.

No test in this module calls OpenAI or the SEC. The financial and narrative
inputs remain the application's genuine, explicitly offline SEC fixtures.
"""
from copy import deepcopy
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


APP = str(Path(__file__).resolve().parents[1] / "app.py")


def _consent(app, prefix):
    return next(item for item in app.checkbox if item.key.startswith(f"{prefix}_consent_"))


def _mock_research(result, model, contexts, *, challenge=False, corrupt=False):
    from alphalens.ai import ValidatedResearch
    from alphalens.evidence import build_evidence_book
    from alphalens.research import (
        Claim, FinancialCitation, PassageCitation, ResearchAnalysis,
        ThesisChallenge, validate_analysis,
    )

    book = build_evidence_book(result, contexts)
    source_id = f"{result.periods[-1].fiscal_year}:revenue"
    source = book[source_id]
    citation = FinancialCitation(source_id=source_id, **{
        field: source[field] for field in ("value", "unit", "fiscal_year", "period_start", "period_end")
    })
    financial_claim = Claim(
        text="Reported annual revenue provides a reference for business scale.",
        kind="fact", financial_citations=[citation],
    )
    question = Claim(text="What evidence would establish the sustainability of cash generation?", kind="question")
    narrative = []
    passages = [(key, value) for key, value in book.items() if value["kind"] == "passage"]
    if passages:
        passage_id, passage = passages[0]
        narrative = [Claim(
            text="The retrieved filing contains disclosures requiring closer analyst review.",
            kind="inference", passage_citations=[PassageCitation(source_id=passage_id, quote=passage["text"][:160])],
        )]
    incorrect = []
    if corrupt:
        incorrect = [Claim(
            text="This model assertion deliberately cites an incorrect financial figure.",
            kind="fact", financial_citations=[citation.model_copy(update={"value": source["value"] + 1000})],
        )]
    if challenge:
        output = ThesisChallenge(
            assumptions=[Claim(text="Assumption: future cash generation remains sustainable.", kind="hypothesis")],
            supporting_evidence=[financial_claim], contradictory_evidence=[], risks=narrative,
            missing_information=[question],
            invalidation_conditions=[Claim(
                text="If cash conversion deteriorates persistently, revisit the investment hypothesis.",
                kind="hypothesis",
            )],
        )
    else:
        output = ResearchAnalysis(
            performance=[financial_claim] + incorrect,
            business_developments=narrative, investment_considerations=[], risks=[], missing_information=[question],
        )
    return ValidatedResearch(
        output=output, verification=validate_analysis(output, book),
        evidence=book, model=model, warnings=[],
    )


def test_new_research_tabs_remain_available_without_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    app = AppTest.from_file(APP).run(timeout=30)

    assert not app.exception
    assert {"AI Research Briefing", "Challenge the Thesis", "AI commentary"}.issubset({tab.label for tab in app.tabs})
    assert app.button(key="generate_research_brief").disabled
    assert app.button(key="generate_thesis").disabled
    assert _consent(app, "research_brief").disabled
    assert _consent(app, "thesis").disabled
    assert any("checked-in historical SEC fixtures" in item.value for item in app.caption)
    assert any("SEC filing context supplied to AI" in item.label for item in app.expander)
    assert len(app.metric) == 4
    assert len(app.get("download_button")) == 2


def test_briefing_needs_explicit_consent_and_quarantines_incorrect_figure(monkeypatch):
    from alphalens import ai

    monkeypatch.setenv("OPENAI_API_KEY", "mock-key-never-used-on-network")
    calls = []

    def local_generation(result, api_key, model, *, filing_contexts):
        calls.append((result.ticker, model, len(filing_contexts)))
        return _mock_research(result, model, filing_contexts, corrupt=True)

    monkeypatch.setattr(ai, "generate_research_brief", local_generation)
    app = AppTest.from_file(APP).run(timeout=30)
    assert not app.exception
    assert not calls
    assert app.button(key="generate_research_brief").disabled
    _consent(app, "research_brief").check().run(timeout=30)
    app.button(key="generate_research_brief").click().run(timeout=30)

    assert not app.exception
    assert len(calls) == 1
    assert calls[0][2] == 1
    assert app.session_state["research_brief_result"].verification.unsupported_count == 1
    assert any("unsupported claims were excluded" in item.value for item in app.error)
    assert any("meaning unverified; analyst review required" in item.value for item in app.caption)
    assert any("Financial figure mismatch" in item.value for item in app.text)
    assert any("Exact source quote checked" in item.value for item in app.caption)
    assert any("Python value" in item.value.columns for item in app.dataframe)
    assert not _consent(app, "research_brief").value
    assert app.button(key="generate_research_brief").disabled
    assert len(app.metric) == 4


def test_thesis_generation_and_hypothesis_change_reset_previous_output(monkeypatch):
    from alphalens import ai

    monkeypatch.setenv("OPENAI_API_KEY", "mock-key-never-used-on-network")
    calls = []

    def local_challenge(result, hypothesis, api_key, model, *, filing_contexts):
        calls.append(hypothesis)
        return _mock_research(result, model, filing_contexts, challenge=True)

    monkeypatch.setattr(ai, "challenge_thesis", local_challenge)
    app = AppTest.from_file(APP).run(timeout=30)
    app.text_area(key="thesis_input").set_value("Microsoft can sustain its cash generation.").run(timeout=30)
    _consent(app, "thesis").check().run(timeout=30)
    app.button(key="generate_thesis").click().run(timeout=30)

    assert not app.exception
    assert calls == ["Microsoft can sustain its cash generation."]
    assert app.session_state["thesis_result"] is not None
    assert any("Observable invalidation conditions" in item.value for item in app.markdown)
    assert any("Hypothesis / assumption" in item.value for item in app.caption)
    assert any("If cash conversion deteriorates" in item.value for item in app.text)
    app.text_area(key="thesis_input").set_value("Microsoft faces enduring competitive pressure.").run(timeout=30)
    assert not app.exception
    assert app.session_state["thesis_result"] is None
    assert not _consent(app, "thesis").value
    assert app.button(key="generate_thesis").disabled
    assert len(calls) == 1


def test_model_change_invalidates_generated_briefing(monkeypatch):
    from alphalens import ai

    monkeypatch.setenv("OPENAI_API_KEY", "mock-key-never-used-on-network")
    monkeypatch.setenv("OPENAI_MODEL", "model-before")
    monkeypatch.setattr(ai, "generate_research_brief", lambda result, api_key, model, *, filing_contexts:
                        _mock_research(result, model, filing_contexts))
    app = AppTest.from_file(APP).run(timeout=30)
    _consent(app, "research_brief").check().run(timeout=30)
    app.button(key="generate_research_brief").click().run(timeout=30)
    assert not app.exception
    assert app.session_state["research_brief_result"] is not None

    monkeypatch.setenv("OPENAI_MODEL", "model-after")
    app.run(timeout=30)
    assert not app.exception
    assert app.session_state["research_brief_result"] is None
    assert not _consent(app, "research_brief").value


def test_ai_failure_preserves_core_dashboard(monkeypatch):
    from alphalens import ai

    monkeypatch.setenv("OPENAI_API_KEY", "mock-key-never-used-on-network")

    def local_failure(*args, **kwargs):
        raise ai.AiError("A mocked optional AI request failed; core research is available.")

    monkeypatch.setattr(ai, "generate_research_brief", local_failure)
    app = AppTest.from_file(APP).run(timeout=30)
    _consent(app, "research_brief").check().run(timeout=30)
    app.button(key="generate_research_brief").click().run(timeout=30)

    assert not app.exception
    assert any("mocked optional AI request failed" in item.value for item in app.error)
    assert app.session_state["research_brief_result"] is None
    assert not _consent(app, "research_brief").value
    assert len(app.metric) == 4
    assert len(app.get("download_button")) == 2


@pytest.mark.parametrize("with_passages", [True, False])
def test_live_filing_selection_clears_cached_reports_context_and_consent(monkeypatch, with_passages):
    """Simulate live mode locally; selecting a year never triggers retrieval."""
    from alphalens import ai, service

    fixture_result = service.load_research("MSFT", mode="offline")
    fixture_context = service.load_offline_filing_context(fixture_result)
    simulated_live = deepcopy(fixture_result)
    simulated_live.mode = "live"
    context = deepcopy(fixture_context)
    context["mode"] = "live"
    selected = context["accession"]
    older = next(filing["accession"] for filing in simulated_live.filings if filing["accession"] != selected)
    retrievals, generations = [], []
    monkeypatch.setenv("OPENAI_API_KEY", "mock-key-never-used-on-network")
    monkeypatch.setattr(service, "load_research", lambda *args, **kwargs: deepcopy(simulated_live))

    def local_retrieval(result, accession, user_agent):
        retrievals.append(accession)
        assert accession == selected
        return deepcopy(context)

    def local_generation(result, api_key, model, *, filing_contexts):
        generations.append(deepcopy(filing_contexts))
        return _mock_research(result, model, filing_contexts)

    monkeypatch.setattr(service, "load_research_filing_context", local_retrieval)
    monkeypatch.setattr(ai, "generate_research_brief", local_generation)
    monkeypatch.setattr(ai, "challenge_thesis", lambda result, hypothesis, api_key, model, *, filing_contexts:
                        _mock_research(result, model, filing_contexts, challenge=True))
    app = AppTest.from_file(APP).run(timeout=30)
    assert not app.exception
    assert app.selectbox(key="research_context_choice").value == selected
    assert not retrievals
    if with_passages:
        app.button(key="research_load_context").click().run(timeout=30)
        # The legacy reader keeps its own filing; AI must exclude it after a selection change.
        app.session_state["filing_excerpts"] = (simulated_live.ticker, selected, context["excerpts"])
        app.run(timeout=30)
    _consent(app, "research_brief").check().run(timeout=30)
    app.button(key="generate_research_brief").click().run(timeout=30)
    app.text_area(key="thesis_input").set_value("Microsoft can sustain cash generation.").run(timeout=30)
    _consent(app, "thesis").check().run(timeout=30)
    app.button(key="generate_thesis").click().run(timeout=30)
    assert not app.exception
    assert app.session_state["research_brief_result"] is not None
    assert app.session_state["thesis_result"] is not None
    assert bool(generations[-1]) is with_passages
    _consent(app, "research_brief").check().run(timeout=30)
    _consent(app, "thesis").check().run(timeout=30)

    app.selectbox(key="research_context_choice").select(older).run(timeout=30)

    assert not app.exception
    assert app.session_state["research_filing_context"] is None
    if with_passages:
        assert app.session_state["filing_excerpts"][1] == selected
    else:
        assert app.session_state["filing_excerpts"] is None
    assert app.session_state["research_brief_result"] is None
    assert app.session_state["thesis_result"] is None
    assert not _consent(app, "research_brief").value
    assert not _consent(app, "thesis").value
    assert app.button(key="generate_research_brief").disabled
    assert app.button(key="generate_thesis").disabled
    assert any("Financial evidence only" in item.value for item in app.info)
    assert len(retrievals) == int(with_passages)

    # An explicitly reconfirmed request can use financials, without the old filing's passages.
    _consent(app, "research_brief").check().run(timeout=30)
    app.button(key="generate_research_brief").click().run(timeout=30)
    assert not app.exception
    assert generations[-1] == []
    assert all(source["kind"] == "financial" for source in app.session_state["research_brief_result"].evidence.values())
    assert len(retrievals) == int(with_passages)


def test_older_legacy_filing_reader_is_preserved_and_excluded_from_ai(monkeypatch):
    """Eager rendering of AI tabs must not discard the original filing reader."""
    from alphalens import ai, service

    fixture_result = service.load_research("MSFT", mode="offline")
    fixture_context = service.load_offline_filing_context(fixture_result)
    simulated_live = deepcopy(fixture_result)
    simulated_live.mode = "live"
    latest = simulated_live.filings[0]["accession"]
    older = simulated_live.filings[1]["accession"]
    # Mock the reader output only; it is deliberately excluded from AI evidence.
    excerpts = deepcopy(fixture_context["excerpts"])
    generations = []
    monkeypatch.setenv("OPENAI_API_KEY", "mock-key-never-used-on-network")
    monkeypatch.setattr(service, "load_research", lambda *args, **kwargs: deepcopy(simulated_live))
    monkeypatch.setattr(service, "load_filing_excerpts", lambda *args, **kwargs: excerpts)

    def local_generation(result, api_key, model, *, filing_contexts):
        generations.append(deepcopy(filing_contexts))
        return _mock_research(result, model, filing_contexts)

    monkeypatch.setattr(ai, "generate_research_brief", local_generation)
    app = AppTest.from_file(APP).run(timeout=30)
    app.selectbox(key="filing_choice").select(older).run(timeout=30)
    app.button(key="extract_filing").click().run(timeout=30)

    assert not app.exception
    assert app.selectbox(key="research_context_choice").value == latest
    assert app.session_state["filing_excerpts"] == (simulated_live.ticker, older, excerpts)
    assert any(excerpt.text in item.value for excerpt in excerpts.values() if excerpt.text for item in app.text)
    _consent(app, "research_brief").check().run(timeout=30)
    app.button(key="generate_research_brief").click().run(timeout=30)
    assert not app.exception
    assert generations == [[]]
    assert app.session_state["research_brief_result"] is not None
    epoch = app.session_state["research_brief_request_epoch"]
    app.run(timeout=30)
    assert not app.exception
    assert app.session_state["filing_excerpts"] == (simulated_live.ticker, older, excerpts)
    assert app.session_state["research_brief_result"] is not None
    assert app.session_state["research_brief_request_epoch"] == epoch


@pytest.mark.parametrize("field", ["value", "unit", "fiscal_year", "period_start", "period_end", "text", "url", "mode"])
def test_ui_fingerprint_invalidates_any_changed_source_field(field):
    from alphalens.research_ui import research_fingerprint

    book = {"source": {"value": 10, "unit": "USD", "fiscal_year": 2025,
                       "period_start": "2024-07-01", "period_end": "2025-06-30",
                       "text": "A genuine retrieved source passage.", "url": "https://www.sec.gov/source", "mode": "offline"}}
    changed = deepcopy(book)
    changed["source"][field] = "changed"
    before = research_fingerprint(book, "configured-model", "Research hypothesis")
    assert before != research_fingerprint(changed, "configured-model", "Research hypothesis")
    assert before != research_fingerprint(book, "another-model", "Research hypothesis")
    assert before != research_fingerprint(book, "configured-model", "A changed hypothesis")
