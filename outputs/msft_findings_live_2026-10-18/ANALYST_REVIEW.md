# Microsoft finding-only briefing — independent review

## Assessment

**The core workflow succeeded mechanically and is suitable for a supervised portfolio demonstration with the qualifications below. The output is not a finished professional investment conclusion.** This is an AI-assisted reviewer assessment, not human analyst approval. A positive source/figure check does not prove an interpretation, hypothesis or question premise is supported.

One authorised Gemini request returned HTTP **200** using `gemini-3.5-flash-lite`: **2.265s HTTP latency**, **3.094s SDK/local-validation latency**, **3.359s total evaluation duration**. Usage was **5,381 input + 560 output = 5,941 tokens**, with a normal stop under the 3,200-output-token limit. The ledger records one request, no retry, no provider fallback and no billing change. Expected cost is USD0 on the owner's confirmed Free Tier without billing; the API reports no monetary charge and AlphaLens cannot infer billing status from a key. This review made no API or SEC requests.

The flat wire contract, strict compact Pydantic contract and deterministic financial/source checks passed. The report classifies **3 Python factual claims, 7 AI interpretations and 3 questions**, with **0 mechanically unsupported claims**. Some entries repeat the same finding in the executive and detailed sections; these counts do not represent independent analytical insights. Mechanical acceptance is distinct from the material semantic concerns below.

## Financial and period checks

Separate Decimal checks matched **36 financial-citation occurrences across 8 unique financial IDs**, including exact values, units, fiscal years, start dates and end dates. **7 quotation occurrences across 3 unique passage IDs** match the saved source text after whitespace normalization. There were no mismatches. These checks use the saved source catalogue and constitute a separate internal reconciliation; they are not a fresh independent download of SEC filings.

The research uses the genuine SEC snapshot identified by the application, retrieved **2026-10-16T23:55:34.392903+00:00**. Comparisons are complete annual periods: FY2025 **2024-07-01–2025-06-30** and FY2026 **2025-07-01–2026-06-30**. No quarterly/YTD or calendar/fiscal mixing was found in the cited financial records.

| USD billions unless stated | FY2025 | FY2026 | Python/reviewer change |
|---|---:|---:|---:|
| Revenue | 281.724 | 331.839 | +17.79% |
| Operating income | 128.528 | 155.237 | +20.78% |
| Operating cash flow | 136.162 | 182.935 | +34.35% |
| Cash purchases of PP&E | 64.551 | 115.948 | +79.62% |
| Defined free cash flow | 71.611 | 66.987 | −6.46% |
| Cash PP&E / OCF | 47.41% | 63.38% | +15.97 percentage points |

Both identities reconcile exactly: **136.162 − 64.551 = 71.611** and **182.935 − 115.948 = 66.987**. Thus free cash flow fell USD4.624bn despite rising operating cash flow. The model correctly identifies the economic relationship. Revenue and operating-income growth supply a second, distinct development.

Source IDs are `2025:` and `2026:` followed by `operating_cash_flow`, `capital_expenditure`, `revenue` and `operating_income`. FCF is calculated from the OCF and cash-PP&E inputs; it is not independently reported GAAP cash flow. Corporate cash PP&E is neither AI-only spending nor a complete lease-inclusive investment measure. Finance-lease principal repayments require separate consideration; operating lease cash costs may already enter OCF. The model does not repeat the previous blanket lease-payment exclusion error.

## Claim meaning and source relevance

All cited passages belong to the FY2026 filing, report date **2026-06-30**, accession **0001193125-26-323660**. The source catalogue retains original parent passages, selected windows and filing metadata. The underlying document is the [Microsoft FY2026 Form 10-K](https://www.sec.gov/Archives/edgar/data/789019/000119312526323660/msft-20260630.htm).

| Actual content | Source relevance | Reviewer judgment |
|---|---|---|
| OCF growth supported by higher customer collections and lower income-tax payments | `sec:838fe0caa8c807af7d81b902`, Item 7, explicitly names these drivers and higher supplier payments as a partial offset | Substantially supported. The report omits the supplier-payment offset, but does not reverse the disclosed drivers. Financial references separately establish the OCF/capex/FCF divergence. |
| Temporary working-capital timing as an alternative | Same OCF passage | Plausible hypothesis, clearly introduced with “could”; temporary timing or a working-capital release is not established. Customer collections can grow with business volume without a release of working capital. Cash-tax movements require their own explanation. |
| Revenue and operating income improved, with segment growth and favorable FX | `sec:2b952351bdb846469a21de3f`, Item 7, expressly attributes OI growth to Productivity and Business Processes/Intelligent Cloud and identifies favorable FX for revenue and OI | Growth and FX are supported. The single cited window does not independently establish every revenue-segment driver in the combined sentence. Broader available passages give more revenue detail, but source relevance should be assessed against the actual cited text. |
| Operating-profit growth may partly rely on non-recurring items or segment mix | Same segment/FX passage | **Unsupported operating-profit hypothesis.** The passage's OpenAI investment gains concern **net income and diluted EPS**, not operating income. Do not treat those gains as evidence of non-recurring operating-profit growth. Segment mix is plausible but not tested by a bridge or decomposition. |
| Power and utility constraints could limit future datacenter expansion | `sec:56d67b25b672d6b595978ea9`, Item 1A, describes conditional electricity/power-connection constraints | Directly relevant and appropriately conditional. It does not assert realised delays, quantify lost revenue or establish project impairment. |

No fabricated source ID, independently generated financial amount, AI-only capex assertion, ROIC estimate, stock rating or valuation conclusion was identified. This is narrower than proving absence of hallucination: unsupported explanations and presuppositions remain possible even with correct citations.

## Specific weaknesses requiring visible qualification

1. **The first diligence question contains an unsupported premise.** It asks how sustainable the “working capital benefits ... observed” are. The evidence establishes increased customer cash receipts and lower cash-tax payments, not a demonstrated working-capital release. Treat the question premise as unverified. An analyst should first determine how collections, receivables/payables and cash taxes explain the OCF movement, then assess what could reverse.
2. **Do not conflate net-income gains with operating-profit quality.** The non-recurring-operating-profit alternative has no identified operating-income evidence. Investigate an operating-profit/segment bridge before entertaining it as an explanation; analyse OpenAI gains separately in net income/EPS. A tentative word does not supply supporting evidence.
3. **Limitations are mostly copied generic warnings.** They accurately describe annual/restated data, corporate cash PP&E and bounded excerpts, but add little finding-specific judgment. Useful missing evidence would distinguish timing from recurring cash generation, or identify utilisation, deployment, monetisation and incremental-return evidence.
4. **Interpretation remains shallow.** There is no cash-tax normalization, quantified working-capital bridge, incremental-return estimate or falsifiable utilisation/monetisation threshold. The model does not determine whether higher capex will produce attractive or poor returns. Those uncertainties should remain explicit rather than being resolved by inference.
5. **One successful call does not establish repeatability.** The accepted output demonstrates a working recorded research path after real prior failures. It does not establish a success rate, general semantic reliability, or live Commentary/Challenge-the-Thesis quality.

## Demonstration suitability

The output is appropriate for demonstrating practical engineering and critical financial judgment to Janus Henderson: trace the annual SEC inputs, show Python detecting cash generation versus investment pressure, inspect the linked disclosures, then explain which model statements remain hypotheses. Show this review alongside the original report and distinguish structural/numerical/provenance checks from human economic review.

The two meaningful developments are present and correctly grounded at the financial-observation level. The datacenter constraint is company-specific and conditional. The original response should remain unchanged; the qualifications above are reviewer notes, not silent edits or a repaired model report. **Human analyst approval remains pending.** Do not describe the briefing as an investment recommendation, a fully verified economic argument, or evidence of AI-specific returns.

`INDEPENDENT_CHECKS.json` records the exact method, occurrence checks, annual Decimal reconciliations, source identities and the separate AI-assisted semantic judgments. This review changed only its own report and deterministic-check artifact; it made no new inference calls and did not modify raw outputs, assembled research, warnings or the demonstration manifest.
