# Microsoft briefing — first accepted live research workflow

## What was actually verified

One explicitly approved **native flat-format Gemini** request returned HTTP **200** using the existing `gemini-3.5-flash-lite` and owner-confirmed Free Tier. **2.219s HTTP latency**, **3.313s SDK/local validation latency**, **3.453s total harness duration**; **5,486 input + 555 output = 6,041 tokens**. The normal stop and output are not truncated. No retry, provider/model fallback, billing change, commentary request or thesis request occurred. This approval is exhausted.

The complete actual response, raw flat fields, compact mapping, assembled report and validation are preserved. Strict parsing, both Pydantic contracts, numerical/period checks, source IDs, exact quotations and financial-overclaim guards passed. The final report has **4 Python factual claims, 6 AI interpretations and 2 questions**, with **0 mechanically unsupported claims**. This classification is not a human investment endorsement.

An independent deterministic recheck matched **44 financial-citation occurrences across 8 unique financial IDs**, including values, units, fiscal years and dates. All **6 assembled quotation occurrences across 4 unique SEC passage IDs** match their prepared source windows exactly. Python copied these figures and quotations; Gemini did not generate independently certified numerical amounts. `INDEPENDENT_CHECKS.json` records the checks.

## Financial interpretation

FY2026 versus FY2025: OCF rose from **USD136.162bn to USD182.935bn**, while cash PP&E purchases rose from **USD64.551bn to USD115.948bn**. Python-defined FCF therefore fell from **USD71.611bn to USD66.987bn**. The model correctly identifies this divergence and higher cash-investment intensity. The underlying source periods are respectively 2024-07-01–2025-06-30 and 2025-07-01–2026-06-30. Independent Decimal checks confirm `FCF = OCF − cash PP&E` in both periods.

The comparison concerns incremental cash investment pressure: total cash PP&E still remains below OCF. Corporate cash PP&E is neither lease-inclusive infrastructure investment nor AI-only capex. No AI-specific ROIC, price target or rating is established.

## Source relevance and critical review

The executive statement about FX and Productivity and Business Processes/Intelligent Cloud is supported by its cited disclosure. The OCF passage supports management's cash-collections and income-tax-payment explanations; the financial citations separately establish the cash-flow divergence. Investment-intensity ratios come from Python's numerical sources. The planned-capex passage supplies business context and does not prove historical causation or eventual returns. The electricity passage accurately supports a conditional datacenter-capacity risk.

Useful strengths are the correct central relationship, company-specific sources, source-linked financial observations, cautious investment alternatives and explicit absence of AI-attributable return evidence. This is sufficient for a supervised portfolio demonstration of the research workflow.

Material weaknesses remain:

- “Tax receipts” in the alternative is imprecise. The passage describes lower cash payments for income taxes; timing remains an unverified hypothesis.
- “Property and equipment additions” is broader than the application's cash-purchases definition. Lease-financed additions are not captured by this cash measure.
- Both findings describe closely related investment pressure, so the report has limited breadth and shallow economic interpretation.
- Historical return thresholds are not specified; utilisation, monetisation and incremental returns remain unknown.
- The power-risk limitation largely repeats the risk. The evidence does not quantify realised project delays or impairment.
- Follow-up should include normalisation of cash taxes, the OpenAI investment gains/losses bridge, capacity deployment, utilisation and subsequent cash generation.

No fabricated numerical amount, citation ID, AI-only capex assertion, ROIC estimate or valuation conclusion was identified. That does not prove absence of hallucination or complete semantic support. Keep the original report unchanged and show `REVIEW_NOTES.md` alongside it. These are AI-assisted critical-review findings; **human analyst approval remains pending**.

## Failure history and minimal correction

The earlier approved request in `outputs/msft_reliable_briefing_2026-10-17/` returned HTTP200 but malformed JSON inside its string envelope (`{"string":"text"0}` and stray characters). It remained rejected; it was not repaired. The prospectively corrected Gemini briefing path uses a flat object of required strings/string lists, then deterministically maps those fields to the existing compact research model. No content or missing analysis is filled in.

Google documents [OpenAI-compatible structured output](https://ai.google.dev/gemini-api/docs/openai) and warns that [large/deep schemas may be rejected](https://ai.google.dev/gemini-api/docs/structured-output). The native adapter locally rejects complex schemas; the rich financial contract remains local. Existing envelope callers and OpenAI Responses remain supported without fallback.

Expected monetary cost is USD0 on the owner's confirmed Free Tier without billing. The API reports no charge amount; AlphaLens cannot independently determine account billing tier from a key.

## Demonstration

In the existing Streamlit **AI Research Briefing** tab, open **Recorded Microsoft briefing — no API request**, then **Load recorded Microsoft briefing**. The application verifies the fixed manifest, reparses original wire fields, reassembles the report, reruns financial/source validation and compares it with saved artifacts. It does not contact a model or SEC service. The recorded result and its review qualifications are explicitly labelled. Markdown/JSON exports use this revalidated result.

This establishes a functioning, auditable research prototype. It does not establish an investment-ready conclusion, repeated-run model reliability, live Commentary/Thesis reliability or a valuation methodology.
