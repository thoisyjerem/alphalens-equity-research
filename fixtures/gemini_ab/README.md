# Recorded Gemini isolation diagnostics

These four files are byte-identical copies of the two approved diagnostic
request/response bodies in `outputs/gemini_ab_2026-10-17/`. The manifest records
their SHA-256 hashes. They contain no credentials or request headers.

- A retained the failed briefing's exact rich response format and generation
  settings, changing only the messages to a short fictional schema example.
  Google returned HTTP 400 `INVALID_ARGUMENT`, with no rejected-field details.
- B retained the exact original SEC messages and generation settings, changing
  only the response format to the successful smoke's single-string schema.
  Google returned HTTP 200 and `{"status":"success"}`. This satisfies the wire
  schema; it does not satisfy the smoke-only local `status == "ok"` check and is
  not an investment research output.

Tests replay these actual responses through HTTPX MockTransport. Responses for
the corrected single-string envelope are authored mocks, not new live results.
The evidence implicates the rich response format, not a particular schema
keyword. No research facts are generated from these diagnostic fixtures.
