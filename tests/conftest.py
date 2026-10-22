"""Keep offline tests independent of a developer's private provider settings.

The original regression suite exercises the OpenAI contract. Gemini tests select
their provider explicitly. No real credentials from .env enter a request in tests.
"""
import pytest
import httpx


@pytest.fixture(autouse=True)
def isolated_macro_cache(monkeypatch, tmp_path):
    """Ordinary UI tests must not consume the owner's saved macro snapshot."""
    monkeypatch.setattr("alphalens.macro_ui.MACRO_CACHE_DIR", tmp_path / "macro-cache")


@pytest.fixture(autouse=True)
def isolated_ai_environment(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.5-flash-lite")


@pytest.fixture(autouse=True)
def block_live_model_http(monkeypatch):
    """Model tests must use injection/MockTransport, never the real network."""
    original = httpx.HTTPTransport.handle_request

    def guarded(transport, request):
        if request.url.host in {"api.openai.com", "generativelanguage.googleapis.com"}:
            raise AssertionError("Live AI HTTP is forbidden in the automated test suite")
        return original(transport, request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", guarded)
