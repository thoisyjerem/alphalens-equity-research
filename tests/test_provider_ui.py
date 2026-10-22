"""Provider-aware UI checks. Every generation here is mocked; no API calls."""
from pathlib import Path

from streamlit.testing.v1 import AppTest


APP = str(Path(__file__).resolve().parents[1] / "app.py")


def _consent(app, prefix):
    return next(item for item in app.checkbox if item.key.startswith(f"{prefix}_consent_"))


def _research_result(result, model, contexts, *, challenge=False):
    from alphalens.ai import ValidatedResearch
    from alphalens.evidence import build_evidence_book
    from alphalens.research import Claim, ResearchAnalysis, ThesisChallenge, validate_analysis

    evidence = build_evidence_book(result, contexts)
    question = Claim(text="What evidence would establish attractive future investment returns?", kind="question")
    if challenge:
        output = ThesisChallenge(
            assumptions=[Claim(text="Assumption: infrastructure investment supports durable customer demand.", kind="hypothesis")],
            supporting_evidence=[], contradictory_evidence=[], risks=[], missing_information=[question],
            invalidation_conditions=[Claim(text="If customer demand persistently weakens, reconsider the hypothesis.", kind="hypothesis")],
        )
    else:
        source_id = f"{result.periods[-1].fiscal_year}:revenue"
        source = evidence[source_id]
        from alphalens.research import FinancialCitation
        citation = FinancialCitation(source_id=source_id, **{
            field: source[field] for field in ("value", "unit", "fiscal_year", "period_start", "period_end")
        })
        output = ResearchAnalysis(
            performance=[Claim(text="Reported revenue establishes the scale of the business.", kind="fact", financial_citations=[citation])],
            business_developments=[], investment_considerations=[], risks=[], missing_information=[question],
        )
    return ValidatedResearch(output=output, verification=validate_analysis(output, evidence), evidence=evidence, model=model, warnings=[])


def test_gemini_without_key_disables_all_ai_and_never_uses_openai_key(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-used-for-gemini")
    app = AppTest.from_file(APP).run(timeout=30)

    assert not app.exception
    for key in ("generate_ai", "generate_research_brief", "generate_thesis"):
        assert app.button(key=key).disabled
    for prefix in ("ai", "research_brief", "thesis"):
        assert _consent(app, prefix).disabled
    assert sum("GEMINI_API_KEY" in item.value for item in app.info) == 3
    assert len(app.metric) == 4
    assert len(app.get("download_button")) == 2


def test_all_gemini_features_require_confirmation_and_route_only_to_gemini(monkeypatch):
    from alphalens import ai

    secret = "mock-gemini-secret-never-sent"
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", secret)
    monkeypatch.setenv("GEMINI_MODEL", "configured-gemini-model")
    calls = []

    def commentary(result, api_key, model, *, provider, contract):
        assert contract == "bound_v1"
        calls.append(("commentary", api_key, model, provider))
        return ai.ResearchBrief(
            observations=[ai.Insight(text="Infrastructure investment warrants further research.", evidence_ids=[f"{result.periods[-1].fiscal_year}:revenue"])],
            questions=["What evidence would establish sustainable returns?"],
            caveats=["Historical reporting does not establish future returns."],
        )

    def briefing(result, api_key, model, *, filing_contexts, provider, contract):
        assert contract == "focused_v3"
        calls.append(("briefing", api_key, model, provider))
        return _research_result(result, model, filing_contexts)

    def thesis(result, hypothesis, api_key, model, *, filing_contexts, provider):
        calls.append(("thesis", api_key, model, provider))
        assert "Microsoft" in hypothesis
        return _research_result(result, model, filing_contexts, challenge=True)

    monkeypatch.setattr(ai, "generate_brief", commentary)
    monkeypatch.setattr(ai, "generate_research_brief", briefing)
    monkeypatch.setattr(ai, "challenge_thesis", thesis)
    app = AppTest.from_file(APP).run(timeout=30)
    assert not app.exception
    assert not calls
    for key in ("generate_ai", "generate_research_brief", "generate_thesis"):
        assert app.button(key=key).disabled
    assert all("Free tier with billing disabled" in _consent(app, prefix).label
               for prefix in ("ai", "research_brief", "thesis"))
    for prefix, button in (("ai", "generate_ai"), ("research_brief", "generate_research_brief")):
        _consent(app, prefix).check().run(timeout=30)
        assert not app.button(key=button).disabled
        app.button(key=button).click().run(timeout=30)
        assert not app.exception
        assert not _consent(app, prefix).value
        assert app.button(key=button).disabled
    app.text_area(key="thesis_input").set_value("Microsoft AI investment will support attractive long-term returns.").run(timeout=30)
    _consent(app, "thesis").check().run(timeout=30)
    app.button(key="generate_thesis").click().run(timeout=30)

    assert not app.exception
    assert [call[0] for call in calls] == ["commentary", "briefing", "thesis"]
    assert all(call[1:] == (secret, "configured-gemini-model", "gemini") for call in calls)
    assert app.session_state["ai_brief"] is not None
    assert app.session_state["research_brief_result"] is not None
    assert app.session_state["thesis_result"] is not None
    assert not _consent(app, "thesis").value
    assert len(app.metric) == 4
    assert len(app.get("download_button")) == 2
    displayed = " ".join(str(item.value) for kind in (app.info, app.caption, app.text, app.markdown, app.error) for item in kind)
    assert secret not in displayed

    # No cached Gemini output may appear under a different provider, even when
    # model aliases match. Changing provider never triggers another request.
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "mock-openai-key")
    monkeypatch.setenv("OPENAI_MODEL", "configured-gemini-model")
    app.run(timeout=30)
    assert not app.exception
    assert app.session_state["ai_brief"] is None
    assert app.session_state["research_brief_result"] is None
    assert app.session_state["thesis_result"] is None
    assert len(calls) == 3
    assert not _consent(app, "research_brief").value
    assert not _consent(app, "thesis").value


def test_unsupported_provider_reports_safe_error_and_preserves_financials(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "unsupported-provider")
    app = AppTest.from_file(APP).run(timeout=30)
    assert not app.exception
    assert len(app.error) == 3
    assert all("AI_PROVIDER" in item.value for item in app.error)
    assert len(app.metric) == 4
    assert len(app.get("download_button")) == 2


def test_research_fingerprint_includes_provider():
    from alphalens.research_ui import research_fingerprint

    evidence = {"actual-source": {"value": 123, "unit": "USD"}}
    assert research_fingerprint(evidence, "shared-model", provider="gemini") != research_fingerprint(
        evidence, "shared-model", provider="openai"
    )
