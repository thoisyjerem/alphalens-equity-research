# AlphaLens V1.1 — two-minute demonstration and interview wording

21 October 2026. Independent portfolio project; no JHI affiliation or endorsement. Development used AI coding assistance. Use alongside the final results in `../ALPHALENS_V1_1_EVALUATION.md`.

## Preparation and navigation

1. From the existing project folder, run `.\run.ps1`. Open `http://127.0.0.1:8501/`.
2. Enter **MSFT**, select **Offline SEC fixture**, and click **Load annual research**. Explain that the amounts are genuine historical SEC records, not a fresh download or live market data.
3. Open **AI Research Briefing** → **Recorded Microsoft briefing — no API request** → **Load recorded Microsoft briefing**. Leave live-generation consent unchecked.
4. Keep the cash bridge and segment-margin comparison ready. Open **Investment reasoning — hypotheses and evidence** and **Analytical evidence review — flags and limitations**. The reasoning framework is Python/reviewer material; the genuine 18 October Gemini response remains unchanged below it. Up to three distinct financial-framework findings are not three new model findings; the original recording contains two analytical findings.
5. Rehearse opening **Inspect cash bridge and segment sources**, the original finding's **Inspect supporting sources**, and **Surrounding recorded filing context**. This reveals the exact source records and the scope of the selected excerpt.
6. Under the recorded report, enable **Prepare downloadable AI research report** and keep the Markdown note and audit JSON available. The original audit preserves the model output and financial citations; V1.1 reviewer additions must remain visibly separate. Keep the exported note and the V1.1 evaluation open as a fallback.

The recorded demonstration needs no Gemini key or inference. Initial installation needs internet; the installed replay uses retained files. Source links can be inspected locally without opening the external SEC website.

## Two-minute narrative

**0:00–0:20 — overview and source mode**

I built AlphaLens to automate part of the evidence preparation behind equity research, while making the model's reasoning easier to challenge. This is a genuine recorded Microsoft example; it works offline and is clearly dated.

**0:20–0:45 — cash bridge**

Python selects comparable annual facts and calculates the changes. Operating cash flow increased by about 47 billion dollars, but cash PP&E increased by about 51 billion. Defined free cash flow fell by about 4.6 billion. The exact amounts and filing references are inspectable.

**0:45–1:10 — Investment reasoning — hypotheses and evidence; margin context**

The economic question is whether this spending creates productive capacity whose cash returns arrive later, or whether replacement needs and other costs keep reinvestment structurally high. Those are competing hypotheses, not reported facts. The framework identifies evidence that would distinguish them. Consolidated operating margin improved while Intelligent Cloud's margin declined, so aggregate growth alone is not the full story.

**1:10–1:35 — Analytical evidence review — flags and limitations; original model text**

Here is where a valid citation was insufficient. The recorded model assumed a working-capital benefit that its disclosure did not establish. Its alternative explanation for operating profit also lacked suitable support; nearby investment gains concerned net income. I preserve the original words and display the qualifications rather than silently repairing the history.

**1:35–2:00 — sources, exports and boundary**

The source passages and calculations are available here, and the note and audit trail can be exported when Gemini is unavailable. The application helps prioritize diligence; it does not establish AI-specific returns or produce a defensible valuation. Its value is a repeatable evidence workflow and clearer questions for an analyst.

Timing is approximate. Rehearse aloud; prioritize one cash bridge and one model-review example over opening every panel.

## CV entry

**AlphaLens — AI-assisted Equity Research | Independent Python project**

Built a source-linked research prototype combining annual SEC/XBRL data, deterministic financial analysis and critically reviewed AI interpretation.

- Built comparable annual SEC/XBRL extraction, cash-flow reconciliation and source-linked exports; validated Microsoft and Visa financial data while retaining explicit N/A values for unsupported metric definitions.
- Added evidence-aware review flags and competing investment hypotheses; audited a genuine Microsoft briefing for unsupported working-capital and operating-profit explanations while preserving the original model output.

**Technical skills:** Python, Pandas, Streamlit, Plotly, SEC EDGAR/XBRL, REST APIs, Pydantic, Pytest, JSON, local caching and Gemini integration through an OpenAI-compatible interface.

The second bullet describes implemented review rules and a documented audit, not complete automated semantic verification. Visa was tested through a standalone deterministic driver using the existing financial pipeline; it is not an additional validated dashboard company or live AI report. Cash PP&E and defined FCF remain N/A for Visa under the unchanged accounting-concept mapping. See `../outputs/v1_1_2026-10-21/visa/VISA_EVIDENCE_REPORT.md`. Do not add investment-performance, institutional-use or revised-prompt success claims. Explain AI coding assistance honestly if asked how the application was built.

## Investment questions the workflow helps investigate

| Question | What AlphaLens contributes | What still requires evidence or judgment |
|---|---|---|
| Why did cash retained after investment fall despite higher OCF? | Comparable OCF/PP&E/FCF amounts, bridge and investment-intensity screening | Tax/working-capital normalization and the persistence of spending |
| Is reinvestment front-loaded or structurally recurring? | Explicit alternative mechanisms and evidence discriminators | Maintenance/expansion split, leases, asset lives, deployment and recurring cash contribution |
| Does consolidated profit improvement extend across segments? | Checked retained Microsoft segment comparison and contrary-evidence flag | Segment demand, pricing, costs and cause of margin changes; no general segment extractor is claimed |
| Do earnings gains translate into cash available after investment? | Net-income/cash-conversion comparisons where periods and concepts permit | Non-cash/non-operating gains, cash taxes and investment scope |
| Is the model using evidence from the right accounting line? | Flags for identifiable operating-income/net-income attribution mismatches and missing support | Full accounting normalization and unmodeled items |
| What would strengthen or weaken a constructive investment case? | Mechanism, observation basis and observable evidence conditions | Magnitude, likelihood, competitive durability and a valuation/expectations framework |
| Does a cited passage actually justify the explanation? | Source identity, exact quotation access and narrowly scoped analytical-review warnings | Human assessment of relevance, causality and completeness |

The tool does not answer these questions conclusively merely by listing them. It makes the numerical starting point, uncertainty and next evidence requirement more explicit.

## Short responses to likely challenges

**Why not use a normal chatbot?** A chatbot can also assist with research. AlphaLens adds a repeatable pipeline for annual period/concept selection, calculations, source binding and saved-output replay. I can inspect why an interpretation passed mechanical checks and still required qualification.

**Does your validator know whether an economic explanation is true?** No. It catches identifiable accounting, numerical and attribution errors, and flags specified support gaps. A passed rule is not proof of causality; other claims remain subject to analyst review.

**What is the investment conclusion on Microsoft?** The demonstrated conclusion is a diligence priority: greater operating cash generation coexisted with more intensive reinvestment, and aggregate margin improvement did not extend to Intelligent Cloud. That raises questions about the duration and cash productivity of investment; it does not establish poor AI returns or a mispriced share.

**What did Gemini actually contribute?** The genuine recorded interpretations and questions are preserved. The newer mechanism framework, review flags, calculations and scoring are Python/reviewer additions. The revised prompt has not yet produced a successfully live-validated briefing.

**What would you do next as an analyst?** Reconcile recurring operating cash flow and all investment obligations, then connect segment/customer economics and asset deployment to incremental cash generation. Only then develop a valuation/expectations view. More persuasive prose would not substitute for that work.
