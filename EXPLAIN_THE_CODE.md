# Explain the AlphaLens code

This guide follows the existing implementation. Use it with the source open and the recorded Microsoft demonstration running. The objective is to explain why each step exists, trace a number to its source, and recognise what the software cannot establish.

Development used AI-assisted coding. Do not claim unaided implementation or investment expertise that you cannot substantiate. Review the functions, tests and failed experiments yourself before describing the project in an interview.

## 1. Follow the data before reading the interface

There are three separate workflows:

```text
SEC API or labelled local fixtures
  -> service.load_research
  -> financials.extract_annuals
  -> ResearchResult
  -> analytics.build_analytics
  -> dashboard, source inspection and financial exports

Explicitly authorised NEW AI briefing
  -> filing context + existing ResearchResult
  -> focused_briefing.build_briefing_context
  -> providers.request_structured
  -> strict transport model -> strict interpretation model
  -> focused_briefing.assemble_briefing
  -> research.validate_analysis
  -> display and research exports

RECORDED real briefing, no API request
  -> saved_research.load_saved_briefing
  -> fixed-file hashes and request-ledger checks
  -> same interpretation, assembly and financial/source validation
  -> recorded display and exports
```

The first workflow works without an AI key. The recorded workflow also works without a key, internet, quota or new inference after dependencies are installed. Opening a dashboard tab does not authorise an AI request.

The original-scope check on 19 October added `financial_report.financial_markdown(result)`: a pure Python note with annual tables, checked comparisons and an exact fact appendix. It checks source units/periods and reties reported figures, FCF, margin, debt-component totals and net debt before rendering. `service.build_observations()` and the Overview growth card now reuse `analytics.build_analytics()` rather than a second, less strict growth calculation. For example, a changed revenue concept can keep both reported levels visible while making their growth comparison N/A.

The manual fallback is deliberately a separate path: `uploaded_filing.inspect_uploaded_filing(content, filename, query)` parses visible UTF-8 text, hashes the original bytes and ranks bounded passages by query-word overlap. It establishes neither company identity nor SEC provenance. `show_method()` displays the unverified result locally; it never adds those passages to `evidence.build_evidence_book()` or sends them to Gemini. Authenticating and binding arbitrary uploaded documents is outside this release.

## 2. The four small financial data models

Read [alphalens/models.py](alphalens/models.py).

| Model | What it holds |
|---|---|
| `SourceFact` | XBRL concept, raw value, unit, start/end dates, accession, filing date, form and SEC URL. |
| `MetricValue` | A financial value, its sources and an explanation when unavailable. `None` means unavailable; it does not mean zero. |
| `AnnualPeriod` | Fiscal label, actual annual dates and the metric dictionary. |
| `ResearchResult` | Company identity, annual periods, live/offline mode, retrieval information, warnings and filing library. |

These are Python dataclasses. They carry financial results through the application; they are separate from the Pydantic models that validate model-generated research.

For example, `result.periods[-1].metrics["operating_cash_flow"]` contains the latest displayed OCF value and its original reported facts. The UI formats billions for readability while preserving the full-unit values in exports.

## 3. Company identity, SEC access and caching

Read [alphalens/service.py](alphalens/service.py) and [alphalens/sec.py](alphalens/sec.py).

`load_research(ticker, mode, user_agent)` coordinates the financial workflow. It validates the supported ticker before contacting a service. `resolve_company()` looks up the issuer in the SEC ticker mapping; it does not guess the CIK from the company name.

In live mode, `SecClient.company_tickers()`, `submissions()` and `company_facts()` call official SEC endpoints. `padded_cik()` produces the required ten-digit identifier. `_extend_history()` can fetch older submissions when the recent filing list does not contain enough annual reports. The service checks that the selected issuer, companyfacts and submissions identify the same CIK.

`SecClient._get()` contains the shared HTTP/cache logic:

- Only official HTTPS SEC hosts are accepted, with redirects disabled.
- `validate_user_agent()` requires an identified contact string; the header is supplied on each actual request.
- `_throttle()` spaces network requests by approximately half a second across client instances in the same Python process. This is not a machine-wide rate limiter.
- Requests have connect/read timeouts. Transient connection, rate-limit and server failures have bounded retries/backoff. A 403 produces guidance, not an access-restriction workaround.
- A URL/type-derived filename identifies a local response. A valid cache entry within its TTL can be reused; TTL zero disables cache reads. Writes use a temporary sibling and replacement to avoid partial JSON files.
- Retrieval records say whether a response was cached and when it was fetched.

SEC retries and AI retries are different: the SEC client has bounded transient retries; the AI client is constructed with `max_retries=0` and has no provider fallback.

In offline mode, `load_research()` loads Microsoft fixtures only. `_validate_fixtures()` checks their manifest hashes. Failure in live mode never silently selects fixtures. The user must deliberately choose the labelled offline mode.

## 4. Why annual extraction is more than selecting an XBRL tag

Read [alphalens/financials.py](alphalens/financials.py), starting with `metric_definitions()` and `extract_annuals()`.

The public mapping states the concept and definition for each metric. For example, OCF uses `NetCashProvidedByUsedInOperatingActivities`; cash capex uses `PaymentsToAcquirePropertyPlantAndEquipment`. Revenue permits a small set of consolidated revenue alternatives. Goods-only or services-only sales are not substituted for total revenue. `ProfitLoss` is not treated as interchangeable with parent-attributable `NetIncomeLoss`.

The selection steps are:

1. `_eligible()` requires a finite number, a valid accession/date and form 10-K or 10-K/A. `_annual()` accepts duration facts spanning 350–380 days, including normal 52/53-week years. An annual filing can contain quarterly comparatives; form alone is insufficient.
2. `_periods()` finds annual start/end pairs using actual dates and the filing library. It uses the report's own accession for fiscal labels where available, rather than treating a later comparative fact's `fy` as its historical fiscal year. Verified labels can be carried to neighbouring annual dates. Its final calendar-year fallback is one reason this extractor should not be generalised to other fiscal calendars without review.
3. `_select()` requires the selected exact start/end and unit. Balance-sheet instants have no duration start and must end at the fiscal year-end.
4. Among eligible matching facts it selects the latest filing date. Identical duplicate sources are deduplicated. Equally recent contradictory values become unavailable; the code does not break a conflict by an arbitrary accession order.
5. `_combine()` performs arithmetic only when inputs are available and period-compatible, while retaining the input source records.

Later-filed comparatives can restate earlier numbers. Different metrics can originate from different latest eligible filings. This is an annual reported-data view, not a reconstruction of information available at a historical investment date.

`extract_annuals()` calculates operating margin, FCF and net debt in Python. Cash capex is a **positive cash outflow**. A negative reported payment value is rejected with a reason; the code does not silently apply `abs()`.

`_debt()` uses a reported long-term aggregate or compatible current/noncurrent components, then adds supported short-term borrowing. It never adds the aggregate to its own components. Its Microsoft/Apple commercial-paper fallback is issuer-specific. Missing required components, negative debt or contradictory totals can make debt and net debt N/A. No missing component is assumed to be zero.

**Rehearsal:** explain why a 10-K fact covering only three months is ineligible, why a year-end cash balance is an instant, and why an absent borrowing amount cannot automatically be zero.

## 5. Python identifies the financial relationship before the model sees it

Read [alphalens/analytics.py](alphalens/analytics.py).

`build_analytics()` produces calculated metric rows, numerical screening observations called `tensions`, thresholds and limitations. Every calculated row retains its formula, units, dates, input IDs and raw dependencies.

`_pair_reason()` requires consecutive fiscal years and contiguous annual dates. `_comparable()` also checks the underlying XBRL concept sets. A matching concept set is a necessary check, not proof that acquisitions or accounting scope have not changed.

Percentage growth requires a positive prior base and a nonnegative current value. Ratios require positive denominators. Zero/negative bases, unavailable inputs, gaps or concept changes produce an unavailable result and explanation. Absolute changes may still be useful where percentage growth is misleading. Annual rates are not day-normalised for 52/53-week differences.

`_tensions()` applies explicit thresholds from `DEFAULT_THRESHOLDS`; these are screening choices, not statistical discoveries. It can identify revenue/margin tension, capex/OCF divergence, rising investment intensity and deteriorating cash conversion. Each observation includes a stable ID, both periods, exact comparisons, calculated changes, source IDs and comparability warnings.

The saved Microsoft FY2025–FY2026 comparison illustrates the core arithmetic, in USD billions:

```text
OCF:          136.162 -> 182.935     increase 46.773, growth 34.35%
Cash PP&E:     64.551 -> 115.948     increase 51.397, growth 79.62%
Defined FCF:   71.611 ->  66.987     decrease  4.624, change -6.46%

FCF = OCF - cash PP&E purchases
Change in FCF = 46.773 - 51.397 = -4.624
Cash PP&E / OCF: 47.41% -> 63.38%
```

The deterministic observation `2026:cash_flow_divergence` exists because cash investment increased by more than OCF. This establishes a historical cash-flow relationship. It does not identify all the spending as AI, include all lease-financed investment, or establish future returns. The model is asked to interpret this relationship, not discover or recalculate it.

## 6. Filing passages and evidence IDs

Read [alphalens/filings.py](alphalens/filings.py), [alphalens/retrieval.py](alphalens/retrieval.py) and [alphalens/evidence.py](alphalens/evidence.py).

`extract_filing_excerpts()` uses BeautifulSoup and filing-section boundaries to obtain visible Item 1A risk-factor and Item 7 management-discussion text. The original reader keeps bounded opening excerpts. `load_research_filing_context()` additionally calls `select_filing_passages()` on the downloaded document.

`select_filing_passages()` uses weighted phrases for cash generation, capex, depreciation, leases, segments, competition and capacity constraints. It chooses bounded, nonoverlapping windows, recording section offsets and whether boundaries were cut. It uses no vector database and makes no model request. It can miss a relevant disclosure; a missing topic is not evidence that the company never disclosed it.

`build_evidence_book()` binds available financial facts and retrieved passages to the selected company, annual filing, dates and live/offline mode. Financial IDs look like `2026:operating_cash_flow`. Passage IDs have a `sec:` prefix and a digest of their source record. `evidence_fingerprint()` detects changes to the catalog.

The ID is a local identifier, not independent proof that the remote disclosure is authentic or supports the interpretation. The source record supplies the SEC URL, accession and exact text for inspection.

## 7. The current and historical output contracts

Read [alphalens/focused_briefing.py](alphalens/focused_briefing.py) and [alphalens/gemini_briefing.py](alphalens/gemini_briefing.py).

`build_briefing_context()` reuses the evidence and analytics. It prioritises a small set of latest-period observations, makes one compact annual comparison and selects bounded source windows with `_short_passages()`. The packet contains company/period metadata, observations, source IDs, relevant passages and limitations. Full parent records remain available locally.

Python assigns `primary_observation_id` before generation. For the current Microsoft case this is cash-flow divergence, with revenue/operating-income growth selected as the required additional development. The model interprets those separate relationships. In v3 it does not generate a separate executive: Python makes separate deep copies of the finding claims for that section, preserving each claim's own citations and inference status. It neither synthesises a new investment conclusion nor merges unrelated source scopes.

The selected system instructions treat SEC passages and user-provided content as **untrusted data**, never instructions. They prohibit numerical prose, outside facts, invented citations, unsupported AI-capex attribution and unsupported return conclusions. V3 instructions describe the finding-only fields; historical contracts retain their original layout. Prompts express intent; the validation code remains necessary because a model can ignore them.

There are two models in the dashboard's current Gemini briefing path:

- `GeminiFindingFields`: thirteen required flat fields, each a string or string list. These are the provider-facing JSON schema. There is no embedded JSON string or model-owned executive.
- `FindingInterpretations`: the strict local research model for a required primary finding, additional finding(s), risk(s), alternatives, limitations and questions. Bounds, required fields and types are checked locally.

`GeminiFindingFields.compact_payload()` changes layout only. For example, `additional_observation_id` becomes `findings[0].observation_ids[0]`. It does not fabricate omitted content or substitute a different source. The flat path produces one primary finding, one additional finding and one risk; the local compact model permits bounded collections. `GeminiBriefingFields` and `FocusedBriefingInterpretation` retain the sixteen-field v2 layout, including a model-owned executive, for historical replay and existing callers. A rejected v2 response is never automatically converted into v3.

`assemble_briefing()` verifies IDs and context integrity, binds the primary slot, attaches checked financial citations and exact source windows, assigns kinds based on the typed field meaning, and creates a `ResearchNote`. A question is classified as a question because it comes from the validated question field; Python is not guessing an omitted substantive classification in an old response.

`research_integrity.validate_observation_integrity()` adds a separate reconciliation boundary before generation, assembly and export. It compares copied observation values, dates, units, source dependencies and change formulas with retained financial/analytics records, and independently checks FCF=OCF−positive cash PP&E. A matching hash proves freshness, not arithmetic; the tests deliberately rebuild the hash after corrupting a comparison and still require rejection. This does not independently prove every formula or the model's economic explanation.

The focused Markdown reading edition in `research_exports._focused_markdown()` displays a single annual table, a cash-flow bridge and the model's unchanged interpretations/alternatives with adjacent evidence IDs. Its constructive/cautionary cases are explicitly conditional Python research frameworks, not additional Gemini findings or inferred ratings. The audit JSON retains exact unrounded values, formulas, original fields and all warnings. Streamlit export handles a stale-model TypeError after a code reload with a controlled message; reloading the recorded briefing restores the downloads without a model call.

## 8. Provider routing and the failures that shaped it

Read `generate_research_brief()` in [alphalens/ai.py](alphalens/ai.py), then `read_ai_config()` and `request_structured()` in [alphalens/providers.py](alphalens/providers.py).

`read_ai_config()` loads the project's `.env`; existing process environment values take precedence. Restart after changing settings. It reads only the explicitly selected provider's key. A configured key means presence, not authenticated access or known billing status.

For Gemini, existing API calls retain the `focused_v2` default. The Streamlit briefing explicitly passes `contract="focused_v3"` to `generate_research_brief()`, which routes to `generate_focused_briefing()`. Both native flat versions opt into `gemini_native=True`. `_validate_gemini_native_schema()` rejects unsupported nested/ref/union/constrained wire schemas locally; `request_structured()` sends the selected flat model directly to `chat.completions.parse()` and revalidates its result. Optional OpenAI callers keep their established default; explicit focused contracts remain supported.

Legacy Gemini commentary/thesis and explicit legacy research use `GeminiJSONEnvelope`, whose one field is `result_json`. `_gemini_messages()` supplies the inner schema as trusted transport instructions; the returned string must parse as JSON and satisfy the original Pydantic model. Optional OpenAI retains `responses.parse(..., store=False)`; its default research output contract is preserved. No failed request switches providers or models.

The development history contains different failures, not one generic API problem:

1. **HTTP 400:** controlled A/B requests implicated the original complex response-format configuration. The saved errors did not establish a particular unsupported schema keyword. A minimal schema accepted the long SEC prompt, so prompt length alone was not the demonstrated cause.
2. **HTTP 200, missing `kind`:** an earlier rich report omitted `missing_information[0].kind`. Parsing transport success did not make it a valid report. The original diagnostic replay remains rejected. Since20 October, the legacy Gemini research caller can opt into one local metadata repair: `repair_missing_question_kind()` derives `question` only when the sole structural error is this absent classification on an explicit diligence question. It copies the payload, changes no text, figures or citations, and validates the whole schema again. No repair API call is sent. Wrong enums, statements, multiple missing fields and substantive omissions still fail. The exact repair path appears in diagnostics, warnings and the JSON notice. The old output still fails comparative-evidence checks after its classification is repaired. The current flat `focused_v3` contract does not ask the model for this field at all.
3. **HTTP 200, malformed nested JSON:** a later envelope response contained invalid inner syntax. The application did not repair it. Removing nested serialization prospectively, by using a flat native contract, addressed this confirmed failure mechanism.
4. **Accepted historical v2 briefing:** the 17 October flat request returned HTTP 200, 5,486 input/555 output tokens and 2.219-second HTTP latency. Strict mapping, local schema and financial/source checks passed. SDK/local-validation timing was 3.313 seconds. Its original report and context remain unchanged.

Those historical accepted artifacts are in `outputs/msft_flat_live_2026-10-17/`. Commentary and Challenge the Thesis remain implemented and mock-tested; this milestone does not establish newly successful live evaluations of either.

A later, separately approved 18 October request passed both native and compact schemas but was rejected when the executive mentioned NI/EPS outside its selected revenue/operating-income observation. Its OpenAI impact disclosure was genuinely cited; the comparative error message was too coarse for that non-growth statement. Review also found blanket lease-payment exclusion wording and an unsupported claim about disclosure limitations. See `outputs/msft_recovery_live_2026-10-18/ANALYST_REVIEW.md`. No report was repaired or promoted, no retry occurred, and the historical accepted example remains separate. This demonstrates why native parsing success and real citations still do not establish an acceptable investment note.

The prospective v3 removes the separate executive generation task. One approved v3 request on 18 October returned HTTP 200 in 2.265 seconds, with 5,381 input / 560 output tokens. SDK/local validation took 3.094 seconds; total harness duration was 3.359 seconds. All required local stages passed. The current bundle is `outputs/msft_findings_live_2026-10-18/`; this is one observed success for v3, not repeated-run reliability. Python-built executive claims retain the original interpretation status and sources. No retry, fallback, billing change or thesis request occurred in that completion.

## 9. Mechanical validation versus investment judgment

The latest offline recovery adds a specific selection rule for new briefings: `build_briefing_context()` uses `_additional_development()` to select a supported observation from a different numerical family when available. For Microsoft the primary is cash-flow divergence and the required additional development is revenue/operating-income growth. This prevents two differently named cash-investment rules from filling both slots; it does not automatically establish analytical depth. The historical saved packet remains unchanged and is evaluated against its original selection policy.

`_short_passages()` reserves its competition slot for actual competitive-risk wording in Item 1A. Debt-market pricing from Item 7 is not competitive-pricing evidence. All selected windows remain exact slices of the existing source records; this change retrieves no additional filings.

The source checks include bounded lexical guards for unsupported all-AI capex attribution and categorical ROIC assertions, including the PP&E aliases actually used by the model. These are specific safeguards, not a general semantic verifier.

Read [alphalens/research.py](alphalens/research.py).

`FinancialCitation`, `PassageCitation`, `Claim` and the report models enforce structure. `validate_analysis()` calls `_check_claim()` for each item and returns a `VerificationReport`.

For reproducible evaluation, run `scripts/evaluate_research_quality.py --bundle outputs/msft_findings_live_2026-10-18 --output-dir outputs/current_scorecard`. `quality.evaluate_focused_bundle()` invokes the version-aware saved loader, checks native fields, the compact contract, deterministic assembly and financial/source validation, then produces a mechanical scorecard with an explicitly unscored reviewer rubric. The historical v2 bundle is still replayable using its explicit path. Reported model usage/latency refers to the original saved request. The older `--response` path still reproduces the real `missing_information[0].kind` rejection without filling the field in.

The checks cover exact financial values/units/periods, real source IDs, exact quotation membership, duplicate references, required section/kind relationships and numerical prose. `_comparative_issues()` checks recognised simple historical trends, period completeness and some contradictions. An acceleration assertion needs more historical support than a simple increase. `_overclaim_issues()` and focused `_prose_issues()` reject bounded classes of unsupported attribution, return and valuation statements.

These text checks are deliberately limited heuristics. They are not a general language-understanding engine. Compound clauses, indirect causal claims, subtle negation, future expectations and irrelevant-but-real quotations need human review. `semantic_review_flags()` provides transparent review cues; it does not calculate an entailment score.

Legacy validation can quarantine individual unsupported claims. The focused assembler requires zero mechanically unsupported claims before accepting the assembled report. A malformed/invalid focused response is withheld; the Streamlit dashboard keeps its financial tables and displays a safe error. No partially accepted focused draft is silently promoted.

The current accepted report demonstrates the boundary: a tentative alternative suggests non-recurring operating-profit items, but the supplied OpenAI gains disclosure concerns net income/EPS and does not establish that hypothesis. A question assumes working-capital benefits that the evidence has not demonstrated. Segment/FX citations do not substantiate every revenue-growth cause, and generic limitations do not replace missing utilisation or monetisation evidence. Read the critical review beside the unchanged actual output. Human investment review remains pending. The earlier v2 report's separate tax-wording and overlapping-finding weaknesses remain recorded in its historical review.

## 10. Streamlit state, recorded replay and exports

Read [app.py](app.py), [alphalens/research_ui.py](alphalens/research_ui.py), [alphalens/saved_research.py](alphalens/saved_research.py) and [alphalens/research_exports.py](alphalens/research_exports.py).

Streamlit reruns the script when controls change. `app.py` stores the selected `ResearchResult` in `st.session_state`, clears stale company results on a reload, and builds tables/charts from it. `show_research_tool()` manages each rich AI interface; a context/model/hypothesis fingerprint invalidates stale generated results. New generation requires a key, a consent checkbox and a button click. The request epoch resets consent after an attempt, so rerendering an error does not submit another call.

The recorded Microsoft block appears before the new-generation configuration check. `available_saved_briefing()` checks the fixed bundle exists. `load_saved_briefing()` then:

1. Reads only the nine fixed JSON filenames and their manifest, with bounded sizes and safe JSON handling.
2. Checks hashes and the saved successful single-Gemini-request ledger.
3. Selects v2 or v3 from the checked metadata, reconstructs the original context and strictly validates the corresponding actual flat response and compact mapping.
4. Reassembles and rechecks the report, comparing it with the saved report, verification and audit export.
5. Adds an explicit saved-demonstration warning to the replayed object.

It creates no API client, reads no API key, retrieves no SEC data and writes no audit file. A local manifest detects accidental changes; it is not an external signature. Revalidation of the preserved snapshot does not make the data fresh.

The default recorded bundle is now `outputs/msft_findings_live_2026-10-18/`. Historical v2 replay uses its original explicit directory; neither version is silently upgraded. Assembly fingerprints bind the selected contract, raw transport, compact interpretation, Python observations, final report and evidence.

`service.snapshot_csv()` and `snapshot_json()` export financial data with periods and provenance. `export_research_markdown()` and `export_research_json()` export research with status labels and review qualifications. `_checked()` reruns validation and checks evidence/assembly fingerprints, so a mutated result cannot inherit an old positive check. Model text is escaped and clickable source links are restricted to approved official SEC URLs.

For the safe demonstration, run `./run.ps1`, choose Microsoft offline research, open **AI Research Briefing → Recorded Microsoft briefing**, and load the recorded report. Enable its download toggle for Markdown and JSON. Keep live-generation consent unchecked. Initial installation requires Python 3.12+ and internet; this installed recorded workflow does not.

## 11. Read the tests as evidence of specific behaviour

Start with these files rather than memorising a total test count:

| Test file | What to look for |
|---|---|
| `tests/test_financials.py` | Period/unit selection, duplicate/conflicting facts and missing-data rules. |
| `tests/test_analytics.py` | Comparable annual calculations and screening observations. |
| `tests/test_gemini_native.py` | Real SDK parsing over `httpx.MockTransport`; flat wire contract, malformed output, errors and no fallback. |
| `tests/test_focused_briefing.py` / `test_focused_contract_v2.py` | Primary finding, strict assembly, numerical/source checks and contract failures. |
| `tests/test_finding_contract_v3.py` | Thirteen-field transport, Python-owned executive, distinct observations, mutation checks and refusal to reinterpret rejected v2 as v3. |
| `tests/test_research_verification.py` | Claim/citation checking and deliberately measured limits. |
| `tests/test_saved_research.py` | The actual accepted response, manifest corruption, report mutation and zero-network replay. |
| `tests/test_quality_ui.py` | No-key recorded display/downloads and usable financial UI after AI failure. |

`tests/conftest.py` isolates AI settings and blocks live model HTTP during automated tests. Authored clean/corrupted responses test specified safeguards; they do not measure overall LLM accuracy. Saved genuine failures supply additional regression cases. See `EVALUATION.md` and its JUnit records for dated test outcomes and their scope.

## 12. Rehearse a trace, not a list of technologies

Practice these five explanations with the actual files open:

1. **Trace one number:** start at displayed FY2026 OCF, inspect its `SourceFact`, dates, XBRL concept and accession, then find the same ID in the audit JSON.
2. **Trace one observation:** explain the FCF identity and why `2026:cash_flow_divergence` fires. Change nothing; point to the Python formula and its dependencies.
3. **Trace one accepted interpretation:** follow `GeminiFindingFields` → `compact_payload()` → `FindingInterpretations` → `assemble_briefing()` → `validate_analysis()` → export. Show how executive copies retain each finding's sources and inference status.
4. **Explain one rejection:** distinguish the HTTP 400, missing-field and malformed-JSON failures. State what each experiment established and what it did not.
5. **Challenge one apparently good citation:** show why the OpenAI gains disclosure concerns net income/EPS and cannot establish an explanation about non-recurring operating-profit items. Keep hypotheses separate from observed facts.

A defensible interview explanation is: “I used AI-assisted development to build a small, auditable research prototype. Python determines the figures and material annual relationships. The optional model interprets selected evidence, and strict local validation rejects specified failures. I reviewed a genuine accepted Microsoft output critically, preserved its weaknesses, and made its demonstration reproducible without another API request.” Be ready to substantiate each part in the code.

## Commentary repair: an explicit source-count boundary

`ai.generate_brief()` uses the original lightweight `ResearchBrief` contract. Each `Insight.evidence_ids` accepts at most six IDs. A real Gemini response parsed as JSON but failed that list bound. The fix keeps the bound: the prompt now says to split or narrow an observation rather than omit evidence. A controlled error reports that specific cause; `COMMENTARY_REVISION` in the app fingerprint prevents a stale pre-fix result from being reused.

The Gemini commentary envelope and OpenAI Responses path are unchanged. A subsequent genuine response passed through the Streamlit workflow with two observations and six sources each. The immutable fixture is replayed without network requests in `tests/test_commentary_recovery.py`. Its generic and partly imprecise prose remains a reminder that structural success does not verify analytical meaning.

## Commentary source binding: removing model-owned IDs

The source-count prompt patch did not stop a subsequent response inventing or selecting an unavailable financial ID. The new `commentary.build_commentary_context()` reuses `analytics.build_analytics()` and the existing complementary-development selector. It selects latest comparable annual observations and validates all source dependencies before generation. It sends only these comparisons and limitations, not the repeated full filing-fact catalogue.

The dashboard calls `ai.generate_brief(..., contract="bound_v1")`. `BoundCommentaryFields` accepts interpretation text, questions and caveats; its smaller single-observation variant omits the additional field. There is no source-ID field. `generate_bound_commentary()` attaches the preselected IDs in Python, validates `ResearchBrief`, and reuses `research.validate_analysis()` for amounts/periods/comparisons/overclaims. Caveats receive additional checks. Known metric scope and context fingerprints prevent unrelated evidence or changed sources inheriting a pass. OCF/FCF expansion is for validation only; original displayed prose is preserved.

An actual browser generation passed and displayed two FY2025/FY2026 observations. Its DOM-derived output and audit are labelled separately from a raw API response, which this browser check did not capture. One success demonstrates the workflow, not a reliability rate or proof that economic explanations are correct. Earlier outputs still replay under their explicit legacy paths; they are not upgraded into the new contract.

## Macro context without delegating facts to the model

`macro.load_macro_snapshot()` retrieves DGS10, DTWEXBGS and INDPRO from FRED only when `refresh=True` is explicit. Each series has its own CSV, raw-response disk cache, observation date, retrieval timestamp and comparison formula. The default reads the cache without network access. Missing, invalid, future or stale observations cannot silently become current facts. A cutoff date is not a historical release vintage: revised history may include information unavailable at that past date.

`investment_lens.build_investment_lens()` reuses `analytics.build_analytics()` for source-linked company anchors. Its cash bridge calculates the difference between the increases in OCF and cash PP&E. For the Microsoft snapshot, that shortfall is $4.624bn; holding current cash PP&E fixed, that much extra annual OCF restores prior annual FCF. This is an accounting identity, not an estimate of AI project returns or an investment payback period.

`macro_ui.show_macro_lens()` displays three company-specific transmission channels: demand/capacity, rates/required returns and FX/reported growth. Directional read-throughs follow the observed macro comparison; mechanisms, alternatives and disconfirmers are explicitly research judgments. Macro source IDs start with `macro:` and never enter the SEC financial evidence book or masquerade as company disclosures. The extra JSON download retains both data modes and source registries. Existing Gemini and OpenAI contracts are unchanged, and these additions require no AI request or key.

`investment_lens.build_investor_readout()` synthesises the existing comparisons into an initial investment takeaway, six source-bound cards and two conditional cases. For example, a stronger-operating-performance/cash-divergence headline requires both numerical observations; missing capex or changed accounting concepts suppress unsupported comparisons. `macro_ui._show_readout()` renders the cash bridge as a waterfall: extra OCF, less extra cash PP&E, equals the change in FCF. It is neither a forecast nor an estimate of AI returns. The direct local URL `/?view=macro` chooses this tab using Streamlit's documented default-tab parameter.
