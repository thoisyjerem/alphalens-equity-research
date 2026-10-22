"""Professional reading export from the unchanged genuine saved model output."""
from copy import deepcopy
import json

import pytest

from alphalens.focused_briefing import assembly_fingerprint
from alphalens.research_exports import export_research_json, export_research_markdown
from alphalens.saved_research import load_saved_briefing


def test_recorded_microsoft_note_contains_priority_observations_competing_cases_and_review_qualifications():
    saved = load_saved_briefing()
    before = deepcopy(saved.model_interpretation)
    audit_before = export_research_json(saved)
    markdown = export_research_markdown(saved)
    assert all(title in markdown for title in (
        "Executive research summary", "Most important financial developments", "Key tensions and investment implications",
        "Bull case versus bear case", "Risks, uncertainties and missing evidence", "Questions requiring further analyst research",
        "Sources and validation"))
    assert "cash\\_flow\\_divergence" in markdown and "revenue\\_profit\\_growth" in markdown
    assert "182.935" in markdown and "66.987" in markdown and "-4.624" in markdown
    assert "not additional model findings" in markdown and "does not establish which case will prevail" in markdown
    assert "human investment review remains pending" in markdown
    assert "SAVED LIVE DEMONSTRATION" in markdown
    assert "working" in markdown and "unverified" in markdown
    assert "[Open official SEC source](<https://www.sec.gov/Archives/" in markdown
    # A global source appendix alone must not sever claim-to-passage links.
    for claim in [*saved.output.executive_summary, *saved.output.what_matters_most,
                  *saved.output.investment_considerations, *saved.output.risks]:
        from alphalens.research_exports import _text
        following = markdown.split(_text(claim.text), 1)[1].split("Evidence IDs: ", 1)[1].split(". Hypothesis", 1)[0]
        assert all(_text(c.source_id) in following for c in claim.financial_citations + claim.passage_citations)
    assert saved.model_interpretation == before and export_research_json(saved) == audit_before
    assert json.loads(audit_before)["raw_model_output"] == saved.transport_output


def test_export_reconciles_financial_observations_even_after_fingerprint_is_rebuilt():
    saved = load_saved_briefing()
    saved.financial_observations["2026:cash_flow_divergence"]["comparisons"][0]["current"]["value"] += 1234
    saved.assembly_fingerprint = assembly_fingerprint(saved)
    with pytest.raises(ValueError, match="integrity failed"):
        export_research_markdown(saved)
    with pytest.raises(ValueError, match="integrity failed"):
        export_research_json(saved)


def test_stale_model_type_export_failure_is_controlled_and_can_recover_without_ai(monkeypatch):
    """Reproduce the TypeError seen in an actual Streamlit hot-reload session."""
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    from alphalens import research_exports
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(timeout=30)
    app.button(key="load_saved_msft_briefing").click().run(timeout=30)
    original = research_exports.validate_analysis
    def stale_type(*args):
        raise TypeError("Expected a validated ResearchAnalysis or ThesisChallenge.")
    monkeypatch.setattr(research_exports, "validate_analysis", stale_type)
    app.toggle(key="saved_msft_export_toggle").set_value(True).run(timeout=30)
    assert not app.exception and len(app.metric) == 4 and len(app.get("download_button")) == 2
    assert any("Reload evidence" in item.value for item in app.error)
    assert not any("TypeError" in item.value for item in app.error)
    monkeypatch.setattr(research_exports, "validate_analysis", original)
    app.button(key="load_saved_msft_briefing").click().run(timeout=30)
    assert not app.exception and len(app.get("download_button")) == 4
