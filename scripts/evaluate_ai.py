"""Deterministic, offline evaluation of authored mock LLM responses.

No OpenAI client is created and no API request is made. This is a corruption
test of the citation/structure contract, not a benchmark of model accuracy or
semantic entailment. Run from the project root: python scripts/evaluate_ai.py.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from alphalens.evidence import build_evidence_book, evidence_fingerprint
from alphalens.research import ResearchAnalysis, ThesisChallenge, validate_analysis
from alphalens.service import load_research

CASES_PATH = ROOT / "fixtures" / "ai_eval_cases.json"
HYPOTHESIS = "Microsoft's reinvestment can support durable cash generation without weakening the quality of the business."


def load_cases() -> list[dict]:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]


def load_evaluation_sources():
    """Load only integrity-checked local SEC snapshots; never fetch or invent."""
    from alphalens.service import load_offline_filing_context

    result = load_research("MSFT", "offline")
    context = load_offline_filing_context(result)
    contexts = [context] if isinstance(context, dict) else context
    book = build_evidence_book(result, contexts)
    if not any(row["kind"] == "passage" for row in book.values()):
        raise RuntimeError("Evaluation requires genuine retrieved SEC passage fixtures; none were available.")
    return result, contexts, book


def _financial(book: dict, source_id: str) -> dict:
    source = book[source_id]
    return {"source_id": source_id, **{key: source[key] for key in
        ("value", "unit", "fiscal_year", "period_start", "period_end")}}


def _passage(book: dict, item: str) -> dict:
    source_id, source = next((key, row) for key, row in book.items()
                             if row["kind"] == "passage" and row["item"] == item)
    # Exact contiguous text, not a generated summary. It remains in the source
    # citation only; numerical prose is prohibited by the claim contract.
    quote = source["text"][: min(380, len(source["text"]))].strip()
    if len(quote) < 24:
        raise RuntimeError("A substantial SEC passage is required for evaluation.")
    return {"source_id": source_id, "quote": quote}


def _claim(text, kind="fact", financial=(), passages=()):
    return {"text": text, "kind": kind,
            "financial_citations": list(financial), "passage_citations": list(passages)}


def build_clean_response(result, book: dict, feature: str) -> dict:
    """Realistic authored mock response, dynamically grounded in actual inputs."""
    latest = result.periods[-1]
    previous = result.periods[-2]
    revenue = _financial(book, f"{latest.fiscal_year}:revenue")
    fcf = _financial(book, f"{latest.fiscal_year}:free_cash_flow")
    prior_fcf = _financial(book, f"{previous.fiscal_year}:free_cash_flow")
    capex = _financial(book, f"{latest.fiscal_year}:capital_expenditure")
    business = _passage(book, "7")
    risk = _passage(book, "1A")
    common_risk = _claim(
        "The disclosed risk factors require further consideration before underwriting durable cash generation.",
        "inference", passages=[risk])
    question = _claim(
        "Which additional segment and demand evidence would establish the durability of cash generation?",
        "question")
    if feature == "brief":
        return {
            "performance": [
                _claim("Revenue is reported for the cited completed annual fiscal period.", financial=[revenue]),
                _claim("Free cash flow and capital expenditure warrant joint review when assessing reinvestment demands.",
                       "inference", financial=[fcf, capex]),
            ],
            "business_developments": [_claim(
                "Management's discussion provides context for the reported operating performance.", passages=[business])],
            "investment_considerations": [_claim(
                "The relationship between reinvestment and cash generation requires an explicit durability assumption.",
                "inference", financial=[fcf, capex])],
            "risks": [common_risk],
            "missing_information": [question],
        }
    if feature == "challenge":
        return {
            "assumptions": [_claim(
                "Assumption: reinvestment will produce durable demand and acceptable cash returns.", "hypothesis")],
            "supporting_evidence": [_claim(
                "Reported revenue provides a financial starting point for testing the durability hypothesis.", financial=[revenue])],
            "contradictory_evidence": [_claim(
                "Cash generation across the cited annual periods warrants scrutiny alongside the reinvestment burden.",
                "inference", financial=[prior_fcf, fcf, capex])],
            "risks": [common_risk],
            "missing_information": [question],
            "invalidation_conditions": [_claim(
                "If sustained reinvestment fails to produce durable cash generation, reconsider the hypothesis.", "hypothesis")],
        }
    raise ValueError("Unknown mock feature")


def build_case_response(result, book: dict, case: dict) -> dict:
    output = deepcopy(build_clean_response(result, book, case["feature"]))
    mutation = case["mutation"]
    if mutation == "none":
        return output
    section = "performance" if case["feature"] == "brief" else "contradictory_evidence"
    claim = output[section][0]
    citation = claim["financial_citations"][0] if claim["financial_citations"] else None
    if mutation == "wrong_value":
        citation["value"] += 1_000_000_000
    elif mutation == "rounded_value":
        citation["value"] = round(citation["value"] / 1e9) * 1e9
    elif mutation == "unknown_financial_id":
        citation["source_id"] = "2099:invented_revenue"
    elif mutation == "unavailable_debt":
        citation.update(source_id=f"{result.periods[-1].fiscal_year}:total_debt", value=0)
    elif mutation == "wrong_unit":
        citation["unit"] = "USD/share"
    elif mutation == "wrong_fiscal_year":
        citation["fiscal_year"] -= 1
    elif mutation == "quarterly_start":
        citation["period_start"] = f"{result.periods[-1].fiscal_year}-04-01"
    elif mutation == "wrong_period_end":
        citation["period_end"] = f"{result.periods[-1].fiscal_year}-12-31"
    elif mutation in {"unknown_passage_id", "fabricated_quote", "financial_only_business"}:
        claim = output["business_developments"][0]
        if mutation == "unknown_passage_id":
            claim["passage_citations"][0]["source_id"] = "sec:fabricated-passage-not-in-source-book"
        elif mutation == "fabricated_quote":
            claim["passage_citations"][0]["quote"] = "Management guarantees that every customer will expand spending indefinitely without competitive pressure."
        else:
            claim.update(text="Management launched a new cloud platform with guaranteed customer adoption.",
                         passage_citations=[], financial_citations=[citation])
    elif mutation == "cross_type_source":
        citation["source_id"] = _passage(book, "7")["source_id"]
    elif mutation == "duplicate_citation":
        claim["financial_citations"].append(deepcopy(citation))
    elif mutation == "unsourced_fact":
        claim.update(text="The company has secured exclusive customer contracts that guarantee future profitability.",
                     financial_citations=[], passage_citations=[])
    elif mutation == "numeric_prose":
        claim["text"] = "Revenue was $999 billion during the latest annual fiscal period."
    elif mutation == "unicode_numeric_prose":
        claim["text"] = "Revenue was ９９９ billion dollars during the latest annual fiscal period."
    elif mutation == "spelled_numeric_prose":
        claim["text"] = "Revenue was nine hundred billion dollars during the latest annual fiscal period."
    elif mutation == "mislabelled_question":
        claim.update(kind="question", text="The company dominates its markets and has guaranteed future profitability.",
                     financial_citations=[], passage_citations=[])
    elif mutation == "unsourced_counterevidence":
        claim.update(kind="fact", text="A competitor has already taken the company's largest customer contracts.",
                     financial_citations=[], passage_citations=[])
    elif mutation == "no_contradiction_available":
        output["contradictory_evidence"] = []
        output["missing_information"].append(_claim(
            "What independent evidence would contradict the proposed reinvestment and cash-generation hypothesis?", "question"))
    elif mutation == "unconditional_invalidation":
        output["invalidation_conditions"][0]["text"] = "The thesis has already failed because customers have permanently stopped buying."
    elif mutation == "extra_field":
        output["price_target"] = "Invented and forbidden"
    elif mutation == "boolean_value":
        citation["value"] = True
    else:
        raise ValueError(f"Unknown evaluation mutation: {mutation}")
    return output


def evaluate_case(result, book: dict, case: dict) -> dict:
    payload = build_case_response(result, book, case)
    schema = ResearchAnalysis if case["feature"] == "brief" else ThesisChallenge
    row = {key: case[key] for key in ("id", "feature", "description", "expected")}
    try:
        output = schema.model_validate(payload)
    except ValidationError as exc:
        row.update(actual="schema_rejected", schema_errors=exc.error_count(), claim_counts={}, issues=[])
    else:
        report = validate_analysis(output, book)
        counts = Counter(claim.status for claim in report.claims)
        row.update(actual="quarantined" if report.unsupported_count else "accepted",
                   schema_errors=0, claim_counts=dict(sorted(counts.items())),
                   issues=[{"section": claim.section, "index": claim.index, "reasons": claim.issues}
                           for claim in report.claims if claim.status == "unsupported"])
    row["passed"] = row["actual"] == row["expected"]
    if row["expected"] == "quarantined":
        # Check that a corrupted claim is quarantined individually and the valid
        # remainder survives. This is more useful than rejecting all output.
        row["passed"] = bool(row["passed"] and row["claim_counts"].get("unsupported") == 1
                             and sum(count for status, count in row["claim_counts"].items()
                                     if status != "unsupported") > 0)
    return row


def measure_semantic_boundary(result, book: dict) -> dict:
    """Demonstrate a known limit without scoring it as validation success.

    A deliberately misleading qualitative assertion uses an existing revenue
    source and its exact value/period. Mechanical grounding cannot establish
    whether that prose follows from the evidence. The UI must disclose this.
    """
    payload = build_clean_response(result, book, "brief")
    text = "Microsoft has permanently eliminated competitive risk and secured guaranteed future profitability."
    payload["performance"][0]["text"] = text
    output = ResearchAnalysis.model_validate(payload)
    checked = validate_analysis(output, book).claims[0]
    return {
        "id": "real_citation_does_not_prove_prose_meaning",
        "expected_limitation": "semantic_entailment_not_established",
        "authored_adversarial_mock_claim": text,
        "observed_mechanical_status": checked.status,
        "mechanical_issues": checked.issues,
        "source_id": checked.claim.financial_citations[0].source_id,
        "exact_financial_fields_checked": checked.status == "evidence_checked",
        "meaning_verified": False,
        "analyst_review_required": True,
        "included_in_scenario_pass_score": False,
        "display_policy": "Source/figure checks passed — claim meaning unverified; analyst review required",
        "explanation": "The actual annual revenue citation and its exact copied figure pass reference/period checks, but do not substantiate an assertion that competition or future profitability risk has disappeared.",
    }


def run_evaluation(output_dir: Path | None = None) -> dict:
    result, _contexts, book = load_evaluation_sources()
    rows = [evaluate_case(result, book, case) for case in load_cases()]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "Offline deterministic authored mock-response corruption tests; no OpenAI requests and no live AI verification.",
        "ticker": result.ticker, "data_mode": result.mode,
        "source_fingerprint": evidence_fingerprint(book),
        "financial_source_count": sum(row["kind"] == "financial" for row in book.values()),
        "passage_source_count": sum(row["kind"] == "passage" for row in book.values()),
        "scenario_count": len(rows), "passed": sum(row["passed"] for row in rows),
        "failed": sum(not row["passed"] for row in rows),
        "live_ai_tested": False, "paid_api_requests": 0,
        "semantic_boundary_demonstration": measure_semantic_boundary(result, book),
        "limitations": [
            "These are authored clean/corrupted responses, not sampled model outputs; pass rates do not measure model accuracy.",
            "Citation membership, exact values, units, annual periods and verbatim quote presence are deterministic checks. They do not prove semantic entailment or completeness.",
            "Qualitative interpretations, hypotheses and questions remain analyst judgements. A genuine but irrelevant citation can still accompany misleading prose.",
            "Financial figures and periods are rendered from checked structured evidence by Python; numerical prose is quarantined rather than parsed or recalculated.",
            "Narrative excerpts are bounded and may omit relevant disclosures. No current prices, valuation model or investment recommendation is generated.",
        ],
        "scenarios": rows,
    }
    if output_dir is not None:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "AI_EVALUATION.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        lines = ["# AlphaLens AI evaluation", "", report["scope"], "",
                 f"Executed: {report['generated_at']}", "",
                 f"Result: **{report['passed']}/{report['scenario_count']} scenarios passed; {report['failed']} failed.**", "",
                 f"Grounding: {report['financial_source_count']} annual financial entries and {report['passage_source_count']} SEC passage entries from the explicitly labelled offline Microsoft snapshot.", "",
                 "This is a deterministic corruption test of the validation contract, not a model-accuracy benchmark. Live OpenAI integration remains untested; no paid API requests were made.", "",
                 "| Scenario | Expected | Actual | Result |", "| --- | --- | --- | --- |"]
        lines.extend(f"| {row['id']} | {row['expected']} | {row['actual']} | {'PASS' if row['passed'] else 'FAIL'} |" for row in rows)
        boundary = report["semantic_boundary_demonstration"]
        lines.extend(["", "## Observed semantic boundary (excluded from the pass score)", "",
                      f"Expected limitation: `{boundary['expected_limitation']}`.", "",
                      "A deliberately misleading authored mock assertion used a real annual revenue citation with its exact figure, unit and period. "
                      f"The observed mechanical status was `{boundary['observed_mechanical_status']}`. **The meaning of the assertion is not verified.**", "",
                      boundary["explanation"], "",
                      f"The dashboard labels this status: **{boundary['display_policy']}**. This demonstration is a disclosed boundary of deterministic validation, not an AI-accuracy result or a claim of investment truth."])
        lines.extend(["", "## Limits", ""] + [f"- {text}" for text in report["limitations"]])
        lines.extend(["", "Reproduce from the project root:", "", "```powershell",
                      r".\.venv\Scripts\python.exe scripts\evaluate_ai.py", "```", ""])
        (output_dir / "AI_EVALUATION.md").write_text("\n".join(lines), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "outputs")
    args = parser.parse_args()
    report = run_evaluation(args.output_dir)
    print(f"{report['passed']}/{report['scenario_count']} deterministic AI scenarios passed; {report['failed']} failed. No API requests.")
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
