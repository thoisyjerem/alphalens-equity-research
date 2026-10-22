# Microsoft — growth, cash generation and reinvestment

AlphaLens | Recorded genuine Gemini briefing, 18 October 2026 | Annotated demonstration edition

**Status:** strict local structure, financial, period and provenance checks passed. AI-assisted critical review completed; **human investment review remains pending**. This concise edition combines unchanged actual model text with Python financial displays and explicitly labelled review annotations. Full original response and audit export remain available alongside it.

## Verified annual comparison

Historical SEC snapshot retrieved 16 October 2026, not current market data. USD billions. FY2025: 1 July 2024–30 June 2025; FY2026: 1 July 2025–30 June 2026. Growth calculated in Python from comparable annual facts.

| Metric | FY2025 | FY2026 | Change |
|---|---:|---:|---:|
| Revenue | 281.724 | 331.839 | +17.79% |
| Operating income | 128.528 | 155.237 | +20.78% |
| Operating cash flow | 136.162 | 182.935 | +34.35% |
| Cash PP&E purchases | 64.551 | 115.948 | +79.62% |
| Defined free cash flow | 71.611 | 66.987 | -6.46% |

Operating margin rose from 45.62% to 46.78% (+1.16 percentage points). Cash PP&E/OCF rose from 47.41% to 63.38%. The USD51.397bn increase in cash PP&E exceeded the USD46.773bn increase in OCF, reducing defined FCF by USD4.624bn. These are deterministic observations, not model calculations.

**Definition:** FCF = OCF − cash PP&E purchases. This is a defined cash measure, not an SEC accounting subtotal or total infrastructure investment. Finance-lease principal repayments, noncash lease additions and commitments are not included in cash PP&E; operating lease cash costs are already reflected within OCF. Corporate PP&E cannot establish AI-only expenditure or project ROIC.

## Two actual model findings

**Cash generation versus investment — observation `2026:cash_flow_divergence`.**

> Operating cash flow expanded significantly, supported by higher cash collections from customers and lower income-tax payments, while free cash flow contracted as cash purchases of property and equipment increased substantially.

Source passage `sec:838fe0caa8c807af7d81b902` states higher customer receipts and lower cash-tax payments, partly offset by supplier payments. The separate financial inputs support the capex/FCF relationship. The source is a management disclosure, not independent proof of sustainable cash generation.

**Operating performance — observation `2026:revenue_profit_growth`.**

> Both revenue and operating income advanced notably, driven by expansion across key business segments including Productivity and Business Processes and Intelligent Cloud, aided by modest favorable currency movements.

**Review qualification:** `sec:2b952351bdb846469a21de3f` explicitly supports operating-income segment drivers and favorable FX effects. It does not independently establish every revenue-driver clause in this combined sentence. Annual revenue and operating-income growth are independently supported by the financial records.

## Risks, alternatives and diligence

The actual model risk concerns power availability, utility delays and constraints on datacenter expansion. The conditional wording is supported by Item 1A passage `sec:56d67b25b672d6b595978ea9`; it does not establish that delays or a financial loss have occurred.

The proposed working-capital timing explanation is plausible but unproven. Higher collections do not themselves demonstrate working-capital release. The model's suggestion of non-recurring support for operating profit is also unestablished: the nearby OpenAI investment-gains disclosure affects **net income/EPS**, not operating income. These are research hypotheses requiring testing, not accepted causes.

The most useful next work is to normalise cash taxes; reconcile cash PP&E with finance leases and commitments; and examine deployed capacity, utilisation and subsequent monetisation. Higher capex does not by itself imply poor returns. The current packet cannot distinguish temporary investment timing from structurally weaker cash conversion or establish an attractive incremental return.

Actual model questions (the first contains the unverified working-capital premise flagged above):

- How sustainable are the working capital benefits and lower cash income-tax payments observed in operating cash flow?
- What specific capacity utilization rates and monetization milestones accompany the rising capital expenditure program?
- Will power availability bottlenecks constrain future datacenter deployment schedules?

## Sources and reproducibility

Source: [Microsoft FY2026 SEC 10-K](https://www.sec.gov/Archives/edgar/data/789019/000119312526323660/msft-20260630.htm), CIK `0000789019`, accession `0001193125-26-323660`, filed 29 July 2026. Financial IDs are `2025:`/`2026:` plus `revenue`, `operating_income`, `operating_cash_flow`, `capital_expenditure`, `free_cash_flow`; the source catalogue retains original XBRL concepts, units, dates and filings. Derived observations retain formulas and input IDs. No annual/quarterly/YTD mixing is used.

The genuine `gemini-3.5-flash-lite` request returned HTTP 200 in 2.265s (3.094s SDK/local validation), using 5,381 input and 560 output tokens. Exactly one request was made in this completion stage, with no retry or fallback. Expected API expenditure is USD0 on the owner-confirmed Free Tier with billing disabled; the API reports no monetary charge information.

Use the recorded result in Streamlit for a repeatable, no-key demonstration. Mechanical checks, this AI-assisted review, and a future human investment decision are separate. No price target, rating, forecast or AI-specific ROIC is supplied. This is a supervised research prototype, not a completed professional investment recommendation.
