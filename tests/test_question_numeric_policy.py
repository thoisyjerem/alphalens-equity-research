"""Nonquantitative research language cannot disable or bypass amount checks."""
import json
from pathlib import Path

import httpx
from openai import OpenAI
from streamlit.testing.v1 import AppTest

from alphalens.focused_briefing import _prose_issues
from alphalens.research import _numeric_prose


def test_limited_idiom_and_interrogative_exceptions_have_consistent_context():
    for text in (
        "Could one-off items explain the cash conversion pattern?",
        "Could one-time costs explain the cash conversion pattern?",
        "Could one\u2011off items explain the cash conversion pattern?",
    ):
        assert not _numeric_prose(text)
        assert not _prose_issues(text, question=True)
    for text in (
        "What percentage of cash outlays represents recurring maintenance?",
        "By which percent would the unknown cost base need to change?",
    ):
        assert not _numeric_prose(text, question=True)
        assert not _prose_issues(text, question=True)
        assert _numeric_prose(text)  # No blanket exemption for assertion fields.
        assert _numeric_prose(text.rstrip("?"), question=True)


def test_idiom_exception_cannot_hide_spelled_disguised_or_symbolic_amounts():
    for text in (
        "Could one-off gains of one billion explain performance?",
        "Could one-time costs equal forty percent of revenue?",
        "What percentage of the 2025 annual cash spending is maintenance?",
        "What percentage of revenue equals \uff14\uff10 percent?",
        "Could one-off costs amount to \u2153 of operating income?",
        "Could one-time costs amount to $cash spending?",
        "What percentage doubled after the operational change?",
        "Could one-time margins have improved by ten percentage points?",
    ):
        assert _numeric_prose(text, question=True)
        assert _prose_issues(text, question=True)


def test_streamlit_rejection_has_field_diagnostic_then_accepts_qualitative_question_without_retry(monkeypatch, tmp_path):
    """Two explicitly clicked mock attempts; no live HTTP or automatic repair."""
    from alphalens import commentary, observability
    from alphalens.providers import GEMINI_BASE_URL

    monkeypatch.setattr(observability, "ROOT", tmp_path)
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "authored-ui-question-key-never-real")
    payload = {
        "primary_interpretation": "Operating cash flow rose while free cash flow declined; the investment schedule may warrant closer scrutiny.",
        "additional_interpretation": "Revenue and operating income increased, which may provide resources for continued investment.",
        "questions": ["Could one billion dollars of non-recurring gains explain the improvement?"],
        "caveats": ["Historical financial comparisons do not establish future investment returns."],
    }
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={"id": "AUTHORED-QUESTION-UI", "object": "chat.completion",
            "created": 0, "model": "gemini-3.5-flash-lite", "choices": [{"index": 0,
            "finish_reason": "stop", "message": {"role": "assistant", "content": json.dumps(payload)}}]})

    original = commentary.request_structured
    with httpx.Client(transport=httpx.MockTransport(handle)) as http:
        with OpenAI(api_key="authored-never-real", base_url=GEMINI_BASE_URL, max_retries=0, http_client=http) as client:
            monkeypatch.setattr(commentary, "request_structured", lambda **kwargs: original(**{**kwargs, "client": client}))
            app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(timeout=30)
            consent = lambda: next(item for item in app.checkbox if item.key.startswith("ai_consent_"))
            consent().check().run(timeout=30)
            app.button(key="generate_ai").click().run(timeout=30)
            assert not app.exception and len(calls) == 1
            assert app.session_state["ai_brief"] is None
            assert any("questions[0]" in item.value for item in app.error)
            assert any(item.value == "questions[0]: numerical_prose" for item in app.text)
            assert len(app.metric) == 4 and len(app.get("download_button")) == 2
            app.run(timeout=30)
            assert len(calls) == 1 and not consent().value

            question = "What percentage of cash outlays represents recurring maintenance?"
            payload["questions"] = [question]
            consent().check().run(timeout=30)
            app.button(key="generate_ai").click().run(timeout=30)
            assert not app.exception and len(calls) == 2
            assert app.session_state["ai_brief"].questions == [question]
            assert not app.session_state["ai_error"]
            assert len(app.metric) == 4 and len(app.get("download_button")) == 2
            assert any(question in item.value for item in app.markdown)
            assert app.button(key="generate_ai").disabled and not consent().value
