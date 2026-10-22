# Visa — deterministic second-company evidence validation

Genuine saved official SEC responses. No Gemini request, synthetic Visa figures or investment recommendation.

Issuer: VISA INC.; ticker V; CIK 0001403161. Original response capture: 2026-10-21T18:44:37.964591+00:00.

The application still supports its existing dashboard companies; this standalone driver tests whether the same financial pipeline generalises.

## Annual reported comparison

USD billions, except EPS and margins. FCF = operating cash flow − cash PP&E.

| Metric | FY2023 (2022-10-01 to 2023-09-30) | FY2024 (2023-10-01 to 2024-09-30) | FY2025 (2024-10-01 to 2025-09-30) |
| --- | ---: | ---: | ---: |
| revenue | 32.653 [2023:revenue] | 35.926 [2024:revenue] | 40.000 [2025:revenue] |
| operating income | 21.000 [2023:operating_income] | 23.595 [2024:operating_income] | 23.994 [2025:operating_income] |
| net income | 17.273 [2023:net_income] | 19.743 [2024:net_income] | 20.058 [2025:net_income] |
| diluted eps | N/A | N/A | N/A |
| operating cash flow | 20.755 [2023:operating_cash_flow] | 19.950 [2024:operating_cash_flow] | 23.059 [2025:operating_cash_flow] |
| capital expenditure | N/A | N/A | N/A |
| cash and equivalents | 16.286 [2023:cash_and_equivalents] | 11.975 [2024:cash_and_equivalents] | 17.164 [2025:cash_and_equivalents] |
| operating margin | 64.31% [2023:operating_margin] | 65.68% [2024:operating_margin] | 59.98% [2025:operating_margin] |
| free cash flow | N/A | N/A | N/A |
| total debt | N/A | N/A | N/A |
| net debt | N/A | N/A | N/A |

## Latest annual changes — Python calculations

| Calculation | Result | Formula | Raw evidence IDs |
| --- | ---: | --- | --- |
| revenue growth | +11.34% | (current revenue - prior revenue) / prior revenue | 2024:revenue, 2025:revenue |
| operating income growth | +1.69% | (current operating_income - prior operating_income) / prior operating_income | 2024:operating_income, 2025:operating_income |
| operating margin change pp | -5.692 pp | (current operating_margin - prior operating_margin) * 100 | 2024:operating_income, 2024:revenue, 2025:operating_income, 2025:revenue |
| operating cash flow growth | +15.58% | (current operating_cash_flow - prior operating_cash_flow) / prior operating_cash_flow | 2024:operating_cash_flow, 2025:operating_cash_flow |
| net income growth | +1.60% | (current net_income - prior net_income) / prior net_income | 2024:net_income, 2025:net_income |

## Screening observations — require economic interpretation

- **2024:revenue_profit_growth: Revenue and operating income increased materially** — Reported revenue and operating income grew; assess the margin comparison alongside cash investment before inferring durable profitability.
  Sources: 2023:revenue, 2024:revenue, 2023:operating_income, 2024:operating_income.
- **2025:growth_margin_tension: Revenue growth with operating-margin contraction** — Revenue rose while operating margin declined materially; investigate mix, pricing and cost changes without assuming a cause.
  Sources: 2024:revenue, 2025:revenue, 2024:operating_income, 2025:operating_income.

## Reviewer research questions — not model output or proven causes

The latest comparison separates growth in reported sales from operating-profit conversion. If the margin-contraction screen is present, an analyst should reconcile the operating-expense bridge before deciding whether the change reflects recurring cost pressure, mix or a separately disclosed charge. Companyfacts totals alone do not identify those mechanisms' causal contribution. The separately recorded filing passages below, where available, provide the company's reported explanations; recurrence and economic significance still require analyst judgment.

Compare operating cash-flow growth with operating-income and net-income growth, then inspect cash taxes, non-cash charges and working-capital movements. Do not infer working-capital improvement merely because operating cash flow increased. A sustainable cash-generation assessment requires that reconciliation.

Cash PP&E and the defined free-cash-flow measure are unavailable under the unchanged mapping. Consequently this report cannot rank Visa's reinvestment intensity against Microsoft's or conclude that a lighter investment requirement supports a valuation premium. The broader productive-asset spending concept requires a separate, explicitly defined measure.

## Additional disclosed context — separately reviewed SEC passages

These are exact excerpts of the one identified FY2025 annual filing, preserved with document hashes and text offsets. They are company disclosures, not generated Gemini analysis or independent proof of sustainable economics.

**visa-review:f76cda4ee791d9837c0e48b1 — GAAP operating-cost drivers** ([FY2025 10-K, filed 2025-11-06](https://www.sec.gov/Archives/edgar/data/1403161/000140316125000089/v-20250930.htm))

> GAAP operating expenses increased 30% over the prior year, primarily driven by higher litigation provision and personnel expenses.

**visa-review:3ee3b4cb66834176d854e9ac — Non-GAAP operating-cost drivers (company-defined measure)** ([FY2025 10-K, filed 2025-11-06](https://www.sec.gov/Archives/edgar/data/1403161/000140316125000089/v-20250930.htm))

> Non-GAAP operating expenses increased 11% over the prior year, primarily driven by higher personnel, general and administrative, and depreciation and amortization expenses.

**visa-review:7db261b7fe33d428d580f5bd — Litigation accruals versus escrow funding** ([FY2025 10-K, filed 2025-11-06](https://www.sec.gov/Archives/edgar/data/1403161/000140316125000089/v-20250930.htm))

> Interchange multidistrict litigation. During fiscal 2025, we recorded additional accruals of $2.2 billion to address claims associated with the interchange multidistrict litigation. We also made additional deposits of $875 million into the U.S. litigation escrow account. The additional accruals related to the interchange multidistrict litigation could be higher or lower than deposits made into the U.S. litigation escrow account.

**visa-review:52d98b13570f40138db36baf — Operating-cash-flow drivers and timing** ([FY2025 10-K, filed 2025-11-06](https://www.sec.gov/Archives/edgar/data/1403161/000140316125000089/v-20250930.htm))

> Operating activities. Cash provided by operating activities increased in fiscal 2025 over the prior year primarily due to growth in our underlying business and the timing of payments related to income taxes, partially offset by higher incentive payments.

Reviewer interpretation: the company expressly attributes GAAP operating-expense growth to litigation provision and personnel costs, while its non-GAAP cost-growth disclosure also points to personnel, general and administrative costs, and depreciation/amortisation. The margin decline should therefore be investigated through both the disclosed legal charge and the underlying cost base; removing the provision does not by itself prove that all margin pressure is temporary.

The cash-flow disclosure expressly identifies income-tax payment timing and higher incentive payments alongside business growth. It supports a timing qualification, not a quantified recurring-earnings-to-cash bridge or a generic claim of improved working capital. The separate litigation-accrual and escrow-deposit disclosure also warns against equating an accounting charge with current cash paid.

Further diligence: reconcile the legal provision to legal cash payments and escrow funding; compare recurring personnel and depreciation growth with revenue; quantify the income-tax timing contribution before treating the OCF increase as repeatable. These questions are distinct from Microsoft's cash PP&E/reinvestment question and remain unresolved by the totals alone.

## Economic implications and competing explanations

PYTHON / REVIEWER FRAMEWORK — not additional Gemini findings. Financial references establish observations; the proposed mechanisms remain unverified hypotheses.

### Revenue growth with operating\-margin contraction

Deterministic observation: 2025\:growth\_margin\_tension. FY2024; 2023\-10\-01 to 2024\-09\-30 → FY2025; 2024\-10\-01 to 2025\-09\-30.

**Economic significance:** Growing revenue with a lower operating margin raises the question of how much incremental sales contribute to profit and cash available to shareholders\.

**Investment implication:** Additional revenue is accompanied by a lower operating\-profit share\. A business\-quality assessment needs to distinguish temporary growth costs from recurring pricing, mix or cost pressure before assuming sales growth will restore profitability\.

Financial evidence IDs: 2024\:revenue, 2025\:revenue, 2024\:operating\_income, 2025\:operating\_income. These do not establish a cause.

**Constructive hypothesis — unverified:** Upfront spending to support future activity could precede operating returns\.

**Cautionary hypothesis — unverified:** Pricing pressure, less profitable mix or persistent cost growth could reduce the economics of incremental activity\.

Evidence favouring the constructive case / weakening the cautionary case: Disclosed temporary deployment costs are followed by better contribution margins and cash conversion\.

Evidence favouring the cautionary case / weakening the constructive case: Like\-for\-like margin pressure persists after deployment, particularly if cash conversion also weakens\.

**Unresolved question:** Does a disclosed segment, pricing and cost bridge distinguish temporary growth investment from persistent deterioration in incremental profitability?

**Missing evidence:** Segment revenues and operating costs; pricing\/mix evidence; temporary versus recurring costs; investment deployment and cash conversion\.


## Microsoft comparison

Each company is analysed over its own latest verified annual comparison; fiscal year ends differ. These are screening patterns, not a relative valuation.

| Company | Comparison | Latest-period signals |
| --- | --- | --- |
| MSFT | 2025-06-30 to 2026-06-30 | cash_investment_tension, revenue_profit_growth, cash_flow_divergence, earnings_cash_tension, earnings_conversion_tension, investment_intensity |
| V | 2024-09-30 to 2025-09-30 | growth_margin_tension |

## Missing data / limits

- FY2023 diluted_eps: N/A — No eligible USD/shares 10-K/10-K/A fact (EarningsPerShareDiluted) for annual duration 2022-10-01 to 2023-09-30; missing, wrong-unit or incompatible-period facts are not substituted.
- FY2023 capital_expenditure: N/A — No eligible USD 10-K/10-K/A fact (PaymentsToAcquirePropertyPlantAndEquipment) for annual duration 2022-10-01 to 2023-09-30; missing, wrong-unit or incompatible-period facts are not substituted.
- FY2023 free_cash_flow: N/A — Free cash flow unavailable: No eligible USD 10-K/10-K/A fact (PaymentsToAcquirePropertyPlantAndEquipment) for annual duration 2022-10-01 to 2023-09-30; missing, wrong-unit or incompatible-period facts are not substituted.
- FY2023 total_debt: N/A — Total debt unavailable: No eligible USD 10-K/10-K/A fact (ShortTermBorrowings) for instant at 2023-09-30; missing, wrong-unit or incompatible-period facts are not substituted.
- FY2023 net_debt: N/A — Net debt unavailable: Total debt unavailable: No eligible USD 10-K/10-K/A fact (ShortTermBorrowings) for instant at 2023-09-30; missing, wrong-unit or incompatible-period facts are not substituted.
- FY2024 diluted_eps: N/A — No eligible USD/shares 10-K/10-K/A fact (EarningsPerShareDiluted) for annual duration 2023-10-01 to 2024-09-30; missing, wrong-unit or incompatible-period facts are not substituted.
- FY2024 capital_expenditure: N/A — No eligible USD 10-K/10-K/A fact (PaymentsToAcquirePropertyPlantAndEquipment) for annual duration 2023-10-01 to 2024-09-30; missing, wrong-unit or incompatible-period facts are not substituted.
- FY2024 free_cash_flow: N/A — Free cash flow unavailable: No eligible USD 10-K/10-K/A fact (PaymentsToAcquirePropertyPlantAndEquipment) for annual duration 2023-10-01 to 2024-09-30; missing, wrong-unit or incompatible-period facts are not substituted.
- FY2024 total_debt: N/A — Total debt unavailable: No eligible USD 10-K/10-K/A fact (ShortTermBorrowings) for instant at 2024-09-30; missing, wrong-unit or incompatible-period facts are not substituted.
- FY2024 net_debt: N/A — Net debt unavailable: Total debt unavailable: No eligible USD 10-K/10-K/A fact (ShortTermBorrowings) for instant at 2024-09-30; missing, wrong-unit or incompatible-period facts are not substituted.
- FY2025 diluted_eps: N/A — No eligible USD/shares 10-K/10-K/A fact (EarningsPerShareDiluted) for annual duration 2024-10-01 to 2025-09-30; missing, wrong-unit or incompatible-period facts are not substituted.
- FY2025 capital_expenditure: N/A — No eligible USD 10-K/10-K/A fact (PaymentsToAcquirePropertyPlantAndEquipment) for annual duration 2024-10-01 to 2025-09-30; missing, wrong-unit or incompatible-period facts are not substituted.
- FY2025 free_cash_flow: N/A — Free cash flow unavailable: No eligible USD 10-K/10-K/A fact (PaymentsToAcquirePropertyPlantAndEquipment) for annual duration 2024-10-01 to 2025-09-30; missing, wrong-unit or incompatible-period facts are not substituted.
- FY2025 total_debt: N/A — Total debt unavailable: No eligible USD 10-K/10-K/A fact (ShortTermBorrowings) for instant at 2025-09-30; missing, wrong-unit or incompatible-period facts are not substituted.
- FY2025 net_debt: N/A — Net debt unavailable: Total debt unavailable: No eligible USD 10-K/10-K/A fact (ShortTermBorrowings) for instant at 2025-09-30; missing, wrong-unit or incompatible-period facts are not substituted.
- Captured concept `us-gaap:PaymentsToAcquireProductiveAssets`: The cash outflow for purchases of and capital improvements on property, plant and equipment (capital expenditures), software, and other intangible assets. Not substituted for cash PP&E: this broader concept includes software and other intangible assets; PP&E-only FCF stays N/A.
- Deterministic financial validation, not a complete investment analysis or semantic claim verification.
- Payment volumes, transaction growth, take rates, segment disclosures and share-repurchase analysis were not extracted.
- Cash PP&E is consolidated cash spending, not an AI-specific or lease-inclusive investment measure.
- Latest completed years depend on annual 10-K availability; a fiscal year-end alone is not a published annual report.

## Source register

Complete exact concepts, values, periods, units, accessions, forms and filing dates are in VALIDATION.json and FINANCIAL_EVIDENCE.json.

- `2023:revenue`: 32653000000.0 USD; 2022-10-01 to 2023-09-30; [us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax — 0001403161-25-000089, 10-K, filed 2025-11-06](https://www.sec.gov/Archives/edgar/data/1403161/000140316125000089/0001403161-25-000089-index.html)
- `2023:operating_income`: 21000000000.0 USD; 2022-10-01 to 2023-09-30; [us-gaap:OperatingIncomeLoss — 0001403161-25-000089, 10-K, filed 2025-11-06](https://www.sec.gov/Archives/edgar/data/1403161/000140316125000089/0001403161-25-000089-index.html)
- `2023:net_income`: 17273000000.0 USD; 2022-10-01 to 2023-09-30; [us-gaap:NetIncomeLoss — 0001403161-25-000089, 10-K, filed 2025-11-06](https://www.sec.gov/Archives/edgar/data/1403161/000140316125000089/0001403161-25-000089-index.html)
- `2023:operating_cash_flow`: 20755000000.0 USD; 2022-10-01 to 2023-09-30; [us-gaap:NetCashProvidedByUsedInOperatingActivities — 0001403161-25-000089, 10-K, filed 2025-11-06](https://www.sec.gov/Archives/edgar/data/1403161/000140316125000089/0001403161-25-000089-index.html)
- `2023:cash_and_equivalents`: 16286000000.0 USD; instant to 2023-09-30; [us-gaap:CashAndCashEquivalentsAtCarryingValue — 0001403161-24-000058, 10-K, filed 2024-11-13](https://www.sec.gov/Archives/edgar/data/1403161/000140316124000058/0001403161-24-000058-index.html)
- `2023:operating_margin`: 0.6431262058616359 ratio; 2022-10-01 to 2023-09-30; [us-gaap:OperatingIncomeLoss — 0001403161-25-000089, 10-K, filed 2025-11-06](https://www.sec.gov/Archives/edgar/data/1403161/000140316125000089/0001403161-25-000089-index.html); [us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax — 0001403161-25-000089, 10-K, filed 2025-11-06](https://www.sec.gov/Archives/edgar/data/1403161/000140316125000089/0001403161-25-000089-index.html)
- `2024:revenue`: 35926000000.0 USD; 2023-10-01 to 2024-09-30; [us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax — 0001403161-25-000089, 10-K, filed 2025-11-06](https://www.sec.gov/Archives/edgar/data/1403161/000140316125000089/0001403161-25-000089-index.html)
- `2024:operating_income`: 23595000000.0 USD; 2023-10-01 to 2024-09-30; [us-gaap:OperatingIncomeLoss — 0001403161-25-000089, 10-K, filed 2025-11-06](https://www.sec.gov/Archives/edgar/data/1403161/000140316125000089/0001403161-25-000089-index.html)
- `2024:net_income`: 19743000000.0 USD; 2023-10-01 to 2024-09-30; [us-gaap:NetIncomeLoss — 0001403161-25-000089, 10-K, filed 2025-11-06](https://www.sec.gov/Archives/edgar/data/1403161/000140316125000089/0001403161-25-000089-index.html)
- `2024:operating_cash_flow`: 19950000000.0 USD; 2023-10-01 to 2024-09-30; [us-gaap:NetCashProvidedByUsedInOperatingActivities — 0001403161-25-000089, 10-K, filed 2025-11-06](https://www.sec.gov/Archives/edgar/data/1403161/000140316125000089/0001403161-25-000089-index.html)
- `2024:cash_and_equivalents`: 11975000000.0 USD; instant to 2024-09-30; [us-gaap:CashAndCashEquivalentsAtCarryingValue — 0001403161-25-000089, 10-K, filed 2025-11-06](https://www.sec.gov/Archives/edgar/data/1403161/000140316125000089/0001403161-25-000089-index.html)
- `2024:operating_margin`: 0.6567666870789957 ratio; 2023-10-01 to 2024-09-30; [us-gaap:OperatingIncomeLoss — 0001403161-25-000089, 10-K, filed 2025-11-06](https://www.sec.gov/Archives/edgar/data/1403161/000140316125000089/0001403161-25-000089-index.html); [us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax — 0001403161-25-000089, 10-K, filed 2025-11-06](https://www.sec.gov/Archives/edgar/data/1403161/000140316125000089/0001403161-25-000089-index.html)
- `2025:revenue`: 40000000000.0 USD; 2024-10-01 to 2025-09-30; [us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax — 0001403161-25-000089, 10-K, filed 2025-11-06](https://www.sec.gov/Archives/edgar/data/1403161/000140316125000089/0001403161-25-000089-index.html)
- `2025:operating_income`: 23994000000.0 USD; 2024-10-01 to 2025-09-30; [us-gaap:OperatingIncomeLoss — 0001403161-25-000089, 10-K, filed 2025-11-06](https://www.sec.gov/Archives/edgar/data/1403161/000140316125000089/0001403161-25-000089-index.html)
- `2025:net_income`: 20058000000.0 USD; 2024-10-01 to 2025-09-30; [us-gaap:NetIncomeLoss — 0001403161-25-000089, 10-K, filed 2025-11-06](https://www.sec.gov/Archives/edgar/data/1403161/000140316125000089/0001403161-25-000089-index.html)
- `2025:operating_cash_flow`: 23059000000.0 USD; 2024-10-01 to 2025-09-30; [us-gaap:NetCashProvidedByUsedInOperatingActivities — 0001403161-25-000089, 10-K, filed 2025-11-06](https://www.sec.gov/Archives/edgar/data/1403161/000140316125000089/0001403161-25-000089-index.html)
- `2025:cash_and_equivalents`: 17164000000.0 USD; instant to 2025-09-30; [us-gaap:CashAndCashEquivalentsAtCarryingValue — 0001403161-25-000089, 10-K, filed 2025-11-06](https://www.sec.gov/Archives/edgar/data/1403161/000140316125000089/0001403161-25-000089-index.html)
- `2025:operating_margin`: 0.59985 ratio; 2024-10-01 to 2025-09-30; [us-gaap:OperatingIncomeLoss — 0001403161-25-000089, 10-K, filed 2025-11-06](https://www.sec.gov/Archives/edgar/data/1403161/000140316125000089/0001403161-25-000089-index.html); [us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax — 0001403161-25-000089, 10-K, filed 2025-11-06](https://www.sec.gov/Archives/edgar/data/1403161/000140316125000089/0001403161-25-000089-index.html)
