# Offline research quality evaluation

This is a replay of saved output, not a new live model test. Rejected content was not repaired.

- JSON parsing passed: True
- Whole Pydantic schema passed: True
- Complete local validation passed: True
- Source fingerprint: ba92e46a5aeb5852e564b3af6f2c8e68c44e39b5bff2a907760e32b7806f2783

## Mechanical findings

- Bundle integrity and complete replay passed: True.
- Native transport / compact schema / deterministic assembly: True / True / True.
- Model, tokens and latency describe the saved original request, not this offline replay.
- Financial citations matched: 36/36.
- Verbatim quotations matched: 7/7.
- Matching quotations are not a citation-relevance verdict.

- `performance[0]`: evidence_checked.
  - Review: Claim meaning, materiality and completeness require analyst review.
- `performance[1]`: evidence_checked.
  - Review: Claim meaning, materiality and completeness require analyst review.
- `investment_considerations[0]`: interpretation.
  - Review: Claim meaning, materiality and completeness require analyst review.
  - Review: Forward-looking disclosure: check management attribution, conditional wording and the quoted expectation; this is not an observed annual result.
  - Review: Capital attribution review: the financial amount is total corporate cash PP&E, not an AI-specific breakdown.
  - Review: Check that the selected quote supports every clause, rather than merely existing in a relevant source.
- `investment_considerations[1]`: interpretation.
  - Review: Claim meaning, materiality and completeness require analyst review.
  - Review: Forward-looking disclosure: check management attribution, conditional wording and the quoted expectation; this is not an observed annual result.
  - Review: Check that the selected quote supports every clause, rather than merely existing in a relevant source.
- `risks[0]`: interpretation.
  - Review: Claim meaning, materiality and completeness require analyst review.
  - Review: Forward-looking disclosure: check management attribution, conditional wording and the quoted expectation; this is not an observed annual result.
  - Review: Check that the selected quote supports every clause, rather than merely existing in a relevant source.
- `missing_information[0]`: question.
  - Review: Claim meaning, materiality and completeness require analyst review.
- `missing_information[1]`: question.
  - Review: Claim meaning, materiality and completeness require analyst review.
- `missing_information[2]`: question.
  - Review: Claim meaning, materiality and completeness require analyst review.
- `executive_summary[0]`: interpretation.
  - Review: Claim meaning, materiality and completeness require analyst review.
  - Review: Check that the selected quote supports every clause, rather than merely existing in a relevant source.
- `executive_summary[1]`: interpretation.
  - Review: Claim meaning, materiality and completeness require analyst review.
  - Review: Causal/forward-looking language: distinguish management disclosure, expectation and tentative analyst inference.
  - Review: Check that the selected quote supports every clause, rather than merely existing in a relevant source.
- `what_matters_most[0]`: interpretation.
  - Review: Claim meaning, materiality and completeness require analyst review.
  - Review: Check that the selected quote supports every clause, rather than merely existing in a relevant source.
- `what_matters_most[1]`: interpretation.
  - Review: Claim meaning, materiality and completeness require analyst review.
  - Review: Causal/forward-looking language: distinguish management disclosure, expectation and tentative analyst inference.
  - Review: Check that the selected quote supports every clause, rather than merely existing in a relevant source.
- `capital_allocation[0]`: evidence_checked.
  - Review: Claim meaning, materiality and completeness require analyst review.

## Review rubric — no automatic qualitative score

**Financial Accuracy** (deterministic plus analyst review; not assessed)

Every cited figure, unit and annual period matches its source; calculated metrics retain aligned input facts. Matching citations do not prove associated prose.

- not_assessed: No explicit reviewer assessment has been recorded.
- does_not_meet: A cited amount, unit, period or calculated relationship is materially wrong.
- partial: Cited amounts match, but scope, annual comparability or calculation provenance remains unresolved.
- meets: Cited amounts and calculation inputs match, periods align, and scope/definitions have been inspected.

**Evidence Traceability** (deterministic; not assessed)

Every material fact or inference has a known issuer-bound source; quotations are contiguous source spans; all required citation fields are present.

- not_assessed: No explicit reviewer assessment has been recorded.
- does_not_meet: Material assertions have fabricated, missing or unusable references.
- partial: Some assertions trace to evidence, but individual clauses or derived inputs remain untraceable.
- meets: Each material factual assertion has an inspectable issuer-bound record with retained source provenance.

**Citation Relevance** (analyst judgement; not assessed)

Read each selected quote and source context. It must support every factual clause, the business scope, timing and strength of the claim. Existing source IDs alone are insufficient.

- not_assessed: No explicit reviewer assessment has been recorded.
- does_not_meet: A quotation exists but contradicts or does not support a material associated assertion.
- partial: Citations support some clauses, while scope, timing or omitted qualifications require clarification.
- meets: The reviewer read the source context and confirmed support for each factual clause and its qualifications.

**Comparative Analysis** (deterministic cues plus analyst judgement; not assessed)

Trend claims retain consecutive comparative observations; acceleration needs consecutive growth intervals. Review whether material Python-identified tensions are explained rather than omitted.

- not_assessed: No explicit reviewer assessment has been recorded.
- does_not_meet: Comparisons contradict annual figures, mix periods or omit the central material tension.
- partial: Comparisons are mechanically sound but important drivers or competing explanations remain unexplored.
- meets: Relevant annual changes and deterministic tensions are sourced and economically interpreted with limitations.

**Investment Insight** (analyst judgement; not assessed)

Connect sourced operating developments to cash economics, reinvestment and competitive mechanisms; distinguish corporate cash PP&E from AI attribution and identify what evidence would change the interpretation.

- not_assessed: No explicit reviewer assessment has been recorded.
- does_not_meet: The report restates disclosures or claims durable returns without an economic mechanism.
- partial: Some mechanisms link operations to cash returns, but attribution or decision-relevant evidence is incomplete.
- meets: Company-specific mechanisms, cash economics and critical unresolved evidence are tied to a testable interpretation.

**Analytical Balance** (analyst judgement; not assessed)

State plausible competing explanations, missing evidence and uncertainty. Do not manufacture contradictory evidence or equate spending with attractive incremental ROIC.

- not_assessed: No explicit reviewer assessment has been recorded.
- does_not_meet: Unsupported certainties, invented counterarguments or missing downside dominate the conclusion.
- partial: Uncertainty is acknowledged, but competing explanations or invalidation conditions are generic.
- meets: Plausible alternative explanations, genuine contrary evidence and observable uncertainty are explicitly distinguished.

**Schema Reliability** (deterministic; not assessed)

Complete response decodes without repair and satisfies its declared transport and local Pydantic contracts. Python-owned classifications must not be invented as model content.

- not_assessed: No explicit reviewer assessment has been recorded.
- does_not_meet: A response is malformed, missing required fields or accepted after substantive repair.
- partial: The schema passes, but optional analytical sections are incomplete or generation reliability remains untested.
- meets: The complete response passes the intended strict contract without inferred substantive fields; live provenance is recorded.

**Practical Usefulness** (analyst judgement; not assessed)

A reviewer can trace the central financial tension, distinguish fact from interpretation and prioritise specific diligence questions. A disclosure summary alone is insufficient for an investment recommendation.

- not_assessed: No explicit reviewer assessment has been recorded.
- does_not_meet: An analyst cannot trace claims or identify a useful next research decision.
- partial: The output is an inspectable starting summary, but prioritisation or investment implications remain shallow.
- meets: An analyst can inspect sources, understand the central tension and prioritise specific thesis-changing diligence.

## Limits

- Per-claim inspection of a rejected report is not whole-report acceptance.
- Exact value, period and quote matches do not establish semantic entailment, causal truth or investment merit.
- Lexical comparison and attribution checks are conservative cues, not comprehensive natural-language understanding.
- No model accuracy percentage, analyst-quality score, productivity saving or investment performance is inferred.
