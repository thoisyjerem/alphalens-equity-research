# Verification and research limitations

Publication review completed on 22 October 2026; both full test runs below executed on 21 October 2026. This report separates software checks, genuine model history and reviewer judgments. Development and the qualitative review used AI assistance.

## Current execution

The complete existing suite passed **942 tests in 105.76 seconds**, with zero failures, errors or skips. This was a fresh run before the initial private publication, not a repetition of a historical claim. [JUnit result](outputs/publication_2026-10-21/TEST_RESULTS.xml).

The isolated publication copy also passed **942 tests in 146.56 seconds** (JUnit suite time 146.517 seconds), with zero failures, errors or skips. [Clean-copy JUnit result](outputs/publication_2026-10-21/CLEAN_COPY_TEST_RESULTS.xml). An initial direct invocation failed during temporary-directory setup because its parent directory had not been created. Repeating the documented `test.ps1` directory setup resolved those setup errors; no analytical code was changed. The clean copy contains no private `.env`.

The suite covers period/concept selection, duplicates, missing and wrong-unit facts, financial calculations, network failures, malformed responses, unsupported figures, invented citations, accounting-attribution errors, recorded replay and Streamlit interfaces/exports. Authored model fixtures are labelled simulated. Tests block real OpenAI/Gemini HTTP requests.

The publication tree is checked separately for links, excluded credentials, recorded Microsoft replay, Visa replay and complete test reproducibility. [Publication verification](outputs/publication_2026-10-21/VERIFICATION.json). Personal filesystem paths and machine hostnames are removed only from publication metadata copies; the [publication notes](docs/PUBLICATION_NOTES.md) explain the exact boundary.

Publication checks found no configured credentials, private contact details, personal absolute paths or broken relative Markdown links in the 239 selected files. Dependency consistency passed (`pip check`); the final source-package regression passed separately (one test, 5.40 seconds). No licence was selected.

## Financial evidence

- Microsoft FY2025/FY2026 OCF and cash PP&E retain annual dates, units, concepts and accession references. Both annual FCF identities and the change reconcile: `46.773 - 51.397 = -4.624`, in USD billions. Company-wide PP&E is not AI-only or lease-inclusive investment.
- The retained segment table supports a reviewer calculation of consolidated margin improvement alongside Intelligent Cloud margin decline. It does not establish the cause or project returns.
- Genuine Visa FY2023-FY2025 SEC responses support 21 unique source facts across 39 source occurrences. Latest revenue growth is 11.34%, operating-income growth 1.69%, and margin change -5.692 percentage points. Cash PP&E/defined FCF remain N/A because the broader productive-assets tag includes software/intangibles. EPS and complete debt are also unavailable under the current mapping.

See the [Visa report](outputs/v1_1_2026-10-21/visa/VISA_EVIDENCE_REPORT.md), [Microsoft source catalogue](outputs/msft_findings_live_2026-10-18/SOURCE_CATALOG.json) and [V1.1 assessment](ALPHALENS_V1_1_EVALUATION.md).

## Genuine AI results versus offline tests

The recorded Microsoft briefing was generated on 18 October 2026. It returned HTTP 200 on `gemini-3.5-flash-lite`, with 5,381 input and 560 output tokens. HTTP latency was 2.265 seconds; SDK/local handling was 3.094 seconds. It passed the original structural, financial and source checks. These are historical measurements, not a new generation or a repeated-run benchmark.

Subsequent review identified an unestablished working-capital premise, inadequate support for a non-recurring operating-profit explanation and missing segment context. Correct citations did not guarantee sound investment reasoning. The newer deterministic framework and review flags remain clearly separate from the original model response.

The latest revised-prompt request returned HTTP 503 and generated no report. The revised prompt remains **live-unverified**. No model request, credential/provider change, billing change, retry or fallback was made during publication preparation. Challenge the Thesis has no successful live research-quality evaluation; optional OpenAI live integration remains unverified.

## Qualitative reviewer assessment

These ordinal scores assess the original recorded model report, not later Python/reviewer additions. They are not automated semantic measurements, external approval or accuracy percentages. No composite score is calculated.

| Dimension | Reviewer score / 5 | Main reason |
|---|---:|---|
| Financial accuracy | 4 | Bound amounts and periods reconcile; broader cash/lease normalization remains incomplete. |
| Economic insight | 2 | Material relationship identified, but much of the prose describes rather than underwrites it. |
| Evidence quality | 2 | Relevant disclosures coexist with unestablished causal premises. |
| Competing explanations | 2 | Alternatives lack adequate reconciliations and evidence discrimination. |
| Usefulness to a fundamental analyst | 3 | Useful triage and diligence starting point, not a defensible investment conclusion. |

[Exact excerpts, rubric anchors and remedies](outputs/v1_1_2026-10-21/MICROSOFT_REVIEW.md).

## Readiness

Suitable for a supervised independent research-engineering demonstration. Not ready for autonomous investment decisions or circulation as an investment recommendation. Bounded language checks cannot prove causality; financial extraction remains annual and concept-limited; snapshots are dated; working capital, taxes, leases, competitive economics and valuation require further work.

Use the [two-minute guide](docs/V1_1_DEMONSTRATION.md) and [code explanation](EXPLAIN_THE_CODE.md). The demonstration deliberately preserves a real model weakness so the distinction between calculation checks and investment judgement can be examined.
