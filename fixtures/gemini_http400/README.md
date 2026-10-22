# Gemini HTTP 400 replay fixtures

These four files are byte-for-byte copies of the two saved outbound request
bodies and complete error response bodies from
`outputs/live_gemini_2026-10-17/`. `manifest.json` records SHA-256 hashes.
The request bodies contain public Microsoft SEC evidence and the existing
research prompts/schema. They contain no HTTP headers or API credentials.

Both actual responses are an array containing a generic HTTP 400
`INVALID_ARGUMENT` error. Neither includes `details`, a field violation, an
argument path or an explanation of the rejected value. These fixtures do not
establish that JSON Schema, a model parameter, the model, account eligibility or
any other particular argument caused the rejection.

`tests/test_gemini_http400_replay.py` uses the real installed OpenAI SDK with an
in-memory HTTPX transport. It checks exact request-body serialization and safely
replays each actual error with one mocked request and no retry or fallback.
Separately, authored successful JSON responses verify that the same request
path retains Pydantic and financial/source-citation validation locally. These
authored responses are not outputs from Gemini. Their mock usage counts are
synthetic test metadata, not measured API usage.

The tests make no live API requests and do not prove that Google accepts either
request or identify a server-side correction.
