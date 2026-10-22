# Development history

This is a concise record of the technical and research decisions behind AlphaLens. Current installation instructions are in the [README](../README.md), verification results in [EVALUATION.md](../EVALUATION.md), and the current research assessment in [ALPHALENS_V1_1_EVALUATION.md](../ALPHALENS_V1_1_EVALUATION.md). Historical test totals are not evidence of current performance.

## Financial research before model interpretation

The initial application established official SEC ticker resolution, annual XBRL fact selection, financial calculations and a Streamlit dashboard. Duration facts and year-end balances retain different period metadata. Financial concepts, units, dates and filing references remain inspectable. Missing or inconsistent inputs produce N/A rather than guessed values.

The cash-flow definition is operating cash flow less cash purchases of property, plant and equipment. It does not include every lease, acquisition or investment commitment. Genuine historical SEC captures support offline financial analysis; fixture mode is labelled separately from live or cached retrieval.

## Gemini compatibility and real failure evidence

The first rich-schema requests returned HTTP400. A separately approved minimal smoke test succeeded. Controlled diagnostics then rejected the original rich response-format configuration with a short prompt, while accepting the original long research prompt with a simple response format. This implicated the rich response-format configuration, not prompt length alone. Google's error did not identify a particular rejected schema keyword.

The adapter initially used a simple outer JSON envelope and validated the inner research object locally. A subsequent genuine HTTP200 response was valid JSON but omitted `missing_information[0].kind`, so the application correctly rejected it. Other saved failures exposed malformed nested JSON, unsuitable field types and quotation constraints. HTTP acceptance and JSON parsing were not treated as successful investment research.

The research path was progressively reduced to flat qualitative fields. Python owns the verified financial observations, references, periods and final assembly; the model supplies interpretations, alternatives, risks and questions. This reduces avoidable formatting work without relaxing local financial and source checks. Legacy transport contracts and optional OpenAI support remain covered by regression tests.

Exact historical evidence is retained in the [HTTP400 fixtures](../fixtures/gemini_http400/), [controlled diagnostics](../fixtures/gemini_ab/) and [missing-field response fixture](../fixtures/gemini_schema_failure/). These are saved responses replayed offline, not newly executed requests or successful report examples.

## Accepted Microsoft recordings

An [earlier accepted flat-contract briefing](../outputs/msft_flat_live_2026-10-17/) on 17 October 2026 established a complete saved-response workflow. A later [rejected response](../outputs/msft_recovery_live_2026-10-18/) remains available for regression testing; it is not shown as accepted research.

The [current recorded Microsoft briefing](../outputs/msft_findings_live_2026-10-18/) was generated on 18 October 2026. Its thirteen-field qualitative output passed the local Pydantic, financial-period, source-ID and quotation checks. Python assembles the executive summary from the source-bound findings. The accepted record reported 5,381 input tokens and 560 output tokens, with 2.265 seconds HTTP latency. These describe one historical request, not a latency or reliability benchmark.

The recording contains two model findings. It identifies the cash-flow/capex divergence but remains shallow on future cash economics. Its working-capital question assumes a benefit that the cited evidence does not establish, and its non-recurring operating-profit alternative lacks suitable support. Mechanical acceptance did not amount to analyst approval.

The recorded workflow rechecks retained files and source references without credentials or network access. Hash manifests detect accidental changes; they are not independent signatures or fresh SEC verification. Original model text and canonical audit records remain separate from subsequent reviewer material.

## Research review and V1.1

Offline work added financial-observation reconciliation, clearer source inspection, a source-checked cash bridge and a limited retained-table comparison of consolidated and Intelligent Cloud margins. These are Python/reviewer additions, not newly generated Gemini analysis.

The 20 October 2026 attempt to test revised instructions returned HTTP503 because of model demand. No report was generated, and no retry or fallback was made. Later prompt quality therefore remains unverified through a successful live response.

V1.1 added issuer-neutral investment-question framing and a separate analytical-review layer. The framework identifies competing mechanisms and specific evidence that could distinguish them. Bounded checks flag selected working-capital, accounting-line, aggregate-capex and unsupported-return errors. They do not prove general semantic support or economic causality. The genuine Microsoft report remains unchanged and its limitations are visible alongside the framework.

Visa was validated separately using official SEC mapping, submissions, companyfacts and an identified annual filing. The generic engine detected revenue growth with operating-margin contraction rather than applying Microsoft's reinvestment story. Visa's broader productive-assets concept was not substituted for cash PP&E, so the existing PP&E-defined free-cash-flow result remains N/A. This validates part of the deterministic pipeline, not live Visa AI research or additional dashboard coverage.

The [V1.1 evaluation](../ALPHALENS_V1_1_EVALUATION.md) records actual tests, the Microsoft review rubric, Visa evidence, implementation changes and remaining weaknesses. The [two-minute demonstration](V1_1_DEMONSTRATION.md) shows how to explain the workflow honestly. No synthetic scenario count or passing-test total is an overall AI accuracy measure.

## Boundaries retained for publication

- Financial facts and calculations remain separate from model interpretations, reviewer observations and unverified hypotheses.
- The installed recorded demonstration works when Gemini is unavailable and requires no API key.
- There are no automatic AI retries or paid-provider fallbacks.
- The revised prompt, successful live thesis-challenge quality and optional OpenAI live integration remain unverified.
- AlphaLens does not establish AI-specific ROIC, valuation, price targets or investment recommendations.
- The project is an independent educational research prototype developed with AI coding assistance, not an investment service or externally approved research process.
