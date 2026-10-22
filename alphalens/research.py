"""Typed research outputs and deterministic citation checks.

Evidence checks establish exact cited values, periods and quote membership.
They do not establish that prose follows logically from its cited evidence.
Interpretations always remain analyst judgements, even with checked citations.
"""
from __future__ import annotations

from decimal import Decimal
from copy import deepcopy
from datetime import date
import math
import re
import unicodedata
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .evidence import evidence_fingerprint


class _StrictModel(BaseModel):
    # Responses may arrive as SDK model instances as well as JSON mappings.
    # Revalidate instances so a modified mock/model cannot bypass field guards.
    model_config = ConfigDict(extra="forbid", revalidate_instances="always")


class FinancialCitation(_StrictModel):
    source_id: Annotated[str, Field(min_length=1, max_length=120)]
    value: float
    unit: Annotated[str, Field(min_length=1, max_length=30)]
    fiscal_year: int
    period_start: str | None
    period_end: str

    @field_validator("value", mode="before")
    @classmethod
    def finite_number(cls, value):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("A financial citation must use a finite JSON number.")
        return value

    @field_validator("fiscal_year", mode="before")
    @classmethod
    def integer_year(cls, value):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("Fiscal year must be an integer.")
        return value


class PassageCitation(_StrictModel):
    source_id: Annotated[str, Field(min_length=1, max_length=120)]
    quote: Annotated[str, Field(min_length=24, max_length=800)]


class Claim(_StrictModel):
    text: Annotated[str, Field(min_length=12, max_length=900)]
    kind: Literal["fact", "inference", "hypothesis", "question"]
    financial_citations: Annotated[list[FinancialCitation], Field(max_length=6)] = Field(default_factory=list)
    passage_citations: Annotated[list[PassageCitation], Field(max_length=4)] = Field(default_factory=list)


_Claims = Annotated[list[Claim], Field(max_length=5)]


class ResearchAnalysis(_StrictModel):
    performance: Annotated[list[Claim], Field(min_length=1, max_length=5)]
    business_developments: _Claims
    investment_considerations: _Claims
    risks: _Claims
    missing_information: Annotated[list[Claim], Field(min_length=1, max_length=5)]


class ResearchNote(ResearchAnalysis):
    """Extended note without changing the frozen original research contract."""

    executive_summary: _Claims = Field(default_factory=list)
    what_matters_most: _Claims = Field(default_factory=list)
    capital_allocation: _Claims = Field(default_factory=list)


class ThesisChallenge(_StrictModel):
    assumptions: Annotated[list[Claim], Field(min_length=1, max_length=5)]
    supporting_evidence: _Claims
    contradictory_evidence: _Claims
    risks: _Claims
    missing_information: Annotated[list[Claim], Field(min_length=1, max_length=5)]
    invalidation_conditions: Annotated[list[Claim], Field(min_length=1, max_length=5)]


def repair_missing_question_kind(payload, schema, error):
    """One local, schema-specific metadata repair; never a second API request.

    Only a sole missing classification on an explicit diligence question can
    be derived from its section. Wrong enums, citations, facts and substantive
    missing fields remain errors. Validate the complete candidate again and
    leave the original response untouched for diagnostic replay.
    """
    if schema not in {ResearchAnalysis, ResearchNote, ThesisChallenge}:
        raise error
    errors = error.errors(include_url=False, include_context=False, include_input=False)
    if len(errors) != 1:
        raise error
    issue = errors[0]
    location = issue.get("loc", ())
    if (issue.get("type") != "missing" or len(location) != 3
            or location[0] != "missing_information" or type(location[1]) is not int
            or location[2] != "kind"):
        raise error
    question = payload["missing_information"][location[1]]
    text = question.get("text", "")
    if (not isinstance(text, str) or not text.rstrip().endswith("?")
            or not re.match(r"^(?:what|which|how|why|when|where|who|can|could|would|does|do|is|are|should|will)\b", text, re.I)):
        raise error
    candidate = deepcopy(payload)
    candidate["missing_information"][location[1]]["kind"] = "question"
    return schema.model_validate(candidate), [f"missing_information[{location[1]}].kind"]


class CheckedClaim(_StrictModel):
    section: str
    index: int
    claim: Claim
    status: Literal["evidence_checked", "interpretation", "hypothesis", "question", "unsupported"]
    issues: list[str]
    review_flags: list[str] = Field(default_factory=list)
    semantic_review: Literal["requires_analyst_review"] = "requires_analyst_review"


class VerificationReport(_StrictModel):
    claims: list[CheckedClaim]
    source_fingerprint: str

    @property
    def unsupported_count(self) -> int:
        return sum(claim.status == "unsupported" for claim in self.claims)

    @property
    def evidence_checked_count(self) -> int:
        return sum(claim.status == "evidence_checked" for claim in self.claims)

    @property
    def interpretation_count(self) -> int:
        return sum(claim.status == "interpretation" for claim in self.claims)


_WORD_QUANTITIES = re.compile(
    r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|"
    r"forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|billion|"
    r"trillion|percent|percentage|doubled?|tripled?|halved|twice|thrice)\b", re.I)


def _numeric_prose(text: str, *, question: bool = False) -> bool:
    """Detect amounts/dates, without treating bounded research idioms as figures.

    This is a lexical guard, not semantic verification. Only the validation
    copy is normalised; the returned model prose is never repaired or rewritten.
    """
    # Check raw characters first: no exception can hide a digit, currency sign,
    # percentage sign or disguised Unicode numeric amount.
    if any(char.isnumeric() or unicodedata.category(char) == "Sc"
           or char in "%％‰‱" for char in text):
        return True
    words = unicodedata.normalize("NFKC", text)
    # These describe a nonrecurring event, not a quantity. Remaining amounts
    # in the same sentence ("one-off costs of one billion") are still checked.
    words = re.sub(r"\bone[-\u2010-\u2015](?:off|time)\b", "nonrecurring", words, flags=re.I)
    if question and text.rstrip().endswith("?"):
        # Asking for an unknown proportion does not assert a financial figure.
        # Only this interrogative phrase is exempt; "forty percent" stays banned.
        words = re.sub(r"\b(?:what|which)\s+(?:percentage|percent)\b", "requested proportion", words, flags=re.I)
    return bool(_WORD_QUANTITIES.search(words))


def _normalized(text: str) -> str:
    return " ".join(text.split())


def _financial_issues(citation: FinancialCitation, book: dict) -> list[str]:
    source = book.get(citation.source_id)
    if not isinstance(source, dict) or source.get("kind") != "financial":
        return [f"Unknown or non-financial source ID: {citation.source_id}."]
    issues = []
    # No tolerances, rescaling, inferred fiscal labels or rounding are accepted.
    if Decimal(str(citation.value)) != Decimal(str(source.get("value"))):
        issues.append(f"Financial figure mismatch for {citation.source_id}.")
    for field in ("unit", "fiscal_year", "period_start", "period_end"):
        if getattr(citation, field) != source.get(field):
            issues.append(f"Financial {field} mismatch for {citation.source_id}.")
    return issues


def _passage_issues(citation: PassageCitation, book: dict) -> list[str]:
    source = book.get(citation.source_id)
    if not isinstance(source, dict) or source.get("kind") != "passage":
        return [f"Unknown or non-passage source ID: {citation.source_id}."]
    quote = _normalized(citation.quote)
    if len(quote) < 24 or quote not in _normalized(source["text"]):
        return [f"Quoted passage was not found verbatim in {citation.source_id}."]
    return []


_TREND = re.compile(r"\b(?:increase[ds]?|increasing|decrease[ds]?|decreasing|grew|grow(?:th|s|ing)?|rose|rise[sn]?|rising|fell|fall(?:s|ing)?|decline[ds]?|declining|expand(?:ed|s|ing)?|contract(?:ed|s|ing)?|improv(?:ed|es|ing|ement)|deteriorat(?:ed|es|ing|ion)|accelerat\w*|decelerat\w*|higher|lower|faster|slower)\b", re.I)
_ACCELERATION = re.compile(r"\b(?:accelerat\w*|decelerat\w*)\b", re.I)
_METRIC_WORDS = {
    "revenue": r"\b(?:revenue|sales)\b",
    "operating_income": r"\boperating (?:income|profit)\b",
    "net_income": r"\b(?:net income|net earnings)\b",
    "diluted_eps": r"\b(?:diluted earnings per share|diluted eps|eps)\b",
    "operating_cash_flow": r"\b(?:operating cash flow|cash flow from operations|cash from operations)\b",
    "free_cash_flow": r"\b(?:free cash flow|free cashflow)\b",
    "capital_expenditure": r"\b(?:capex|capital expenditure[s]?|capital spending|(?:spending|expenditures?) (?:on|for) property and equipment)\b",
    "operating_margin": r"\boperating margin[s]?\b",
    "total_debt": r"\b(?:total debt|(?<!net )debt)\b",
    "net_debt": r"\bnet debt\b",
}


def _clauses(text: str) -> list[str]:
    return re.split(r"[.;]|\b(?:while|whereas|but)\b", text, flags=re.I)


def _metric_acceleration(clause: str, metric: str) -> str | None:
    """Bind simple acceleration language to its named financial subject.

    A nearby explanation such as ``reflecting accelerated investment`` does
    not assert that an operating-cash-flow growth rate accelerated. This is a
    bounded grammatical check, not a general semantic interpretation.
    """
    movement = r"(?:growth(?:\s+rate)?|decline|contraction|deterioration)"
    subject = (rf"(?:{movement}\s+(?:in|of)\s+)?{_METRIC_WORDS[metric]}"
               rf"(?:\s+{movement})?")
    modifier = r"(?:has|have|had|is|are|was|were|been|also|further|now|\w+ly)"
    forward = rf"{subject}(?:,\s*which)?(?:\s+{modifier}){{0,5}}\s+{_ACCELERATION.pattern}"
    backward = (rf"{_ACCELERATION.pattern}(?:\s+{movement})?"
                rf"(?:\s+(?:in|of|for|the)){{0,2}}\s+{_METRIC_WORDS[metric]}"
                rf"(?:\s+{movement})?")
    match = re.search(rf"(?:{forward}|{backward})", clause, re.I)
    return match.group(0) if match else None


def _future_only(clause: str) -> bool:
    # Future disclosed expectations are not historical annual comparisons. A
    # mixed clause retaining an explicit past movement still needs its periods.
    future = re.search(r"\b(?:may|might|could|would|will|expects?|expected|anticipates?|forecasts?|potential)\b", clause, re.I)
    historical = re.search(r"\b(?:increased|decreased|grew|rose|fell|declined|expanded|contracted|improved|deteriorated|accelerated|decelerated)\b", clause, re.I)
    return bool(future and not historical)


def _date_value(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _annual_window_reason(rows: list[dict]) -> str:
    for row in rows:
        if type(row.get("fiscal_year")) is not int:
            return "fiscal labels are not explicit integers"
        end, start = _date_value(row.get("period_end")), _date_value(row.get("period_start"))
        if end is None or (row.get("period_start") is not None and
                           (start is None or not 350 <= (end - start).days + 1 <= 380)):
            return "period dates do not establish annual observations"
    for prior, current in zip(rows, rows[1:]):
        if current.get("fiscal_year") != prior.get("fiscal_year") + 1:
            return "fiscal labels are not consecutive"
        old_end, new_end = _date_value(prior.get("period_end")), _date_value(current.get("period_end"))
        start = _date_value(current.get("period_start"))
        if (prior.get("period_start") is None) != (current.get("period_start") is None):
            return "duration and instant observations were mixed"
        if start is not None and (start - old_end).days != 1:
            return "annual dates contain a gap or overlap"
        if start is None and not 350 <= (new_end - old_end).days <= 380:
            return "instant dates do not represent consecutive year ends"
    return ""


def _metric_observations(metric: str, cited: list[dict], book: dict) -> tuple[list[dict], list[str]]:
    """Recover only explicitly cited levels or the dependencies of a calculation."""
    expanded = list(cited)
    errors = []
    for source in cited:
        if source.get("derived"):
            periods = source.get("comparison_periods", [])
            if periods and _annual_window_reason(periods):
                errors.append("calculation comparison dates are not consecutive annual periods")
            for dependency in source.get("dependencies", []):
                record = book.get(dependency)
                if isinstance(record, dict) and record.get("kind") == "financial":
                    expanded.append(record)
    inputs = {"free_cash_flow": ("operating_cash_flow", "capital_expenditure"),
        "operating_margin": ("operating_income", "revenue"),
        "net_debt": ("total_debt", "cash_and_equivalents")}.get(metric)
    levels = [s for s in expanded if s.get("metric") == metric]
    if inputs:
        for year in {s.get("fiscal_year") for s in expanded}:
            if any(s.get("fiscal_year") == year for s in levels):
                continue
            components = [next((s for s in expanded if s.get("metric") == key and s.get("fiscal_year") == year), None)
                          for key in inputs]
            if any(row is None for row in components):
                continue
            left, right = components
            if any(left.get(field) != right.get(field) for field in ("period_start", "period_end", "unit")):
                errors.append(f"{metric} inputs have inconsistent periods or units")
                continue
            a, b = left.get("value"), right.get("value")
            if any(type(value) not in (int, float) or not math.isfinite(value) for value in (a, b)):
                continue
            if metric == "operating_margin" and b <= 0:
                errors.append("operating margin has a non-positive revenue denominator")
                continue
            levels.append({**left, "metric": metric, "value": a / b if metric == "operating_margin" else a - b,
                "unit": "ratio" if metric == "operating_margin" else left.get("unit"),
                "sources": left.get("sources", []) + right.get("sources", [])})
    unique = {}
    for level in levels:
        year = level.get("fiscal_year")
        if type(year) is not int:
            continue
        if year in unique and any(unique[year].get(field) != level.get(field)
                                  for field in ("value", "unit", "period_start", "period_end")):
            errors.append(f"{metric} has ambiguous observations for a fiscal year")
        unique[year] = level
    return [unique[year] for year in sorted(unique)], errors


def _comparative_issues(claim: Claim, book: dict) -> list[str]:
    """Check simple historical comparisons, not general semantic entailment.

    Fiscal labels alone cannot establish comparable annual durations. Direct
    comparisons retain dates, units and matching concept sets; acceleration is
    compared using positive-base growth intervals. Ambiguous clauses and future
    management expectations remain explicit analyst-review responsibilities.
    """
    if claim.kind not in {"fact", "inference"}:
        return []
    # Retain clause boundaries: joining first makes a movement in one clause
    # appear to qualify a different metric mentioned only in another clause.
    historical_clauses = [clause for clause in _clauses(claim.text) if not _future_only(clause)]
    historical = " ".join(historical_clauses)
    if not _TREND.search(historical):
        return []
    cited = [book.get(c.source_id, {}) for c in claim.financial_citations]
    cited = [source for source in cited if source.get("kind") == "financial"]
    if not cited:
        return []  # Narrative segment comparisons need semantic review, not a false consolidated series.
    metrics = [metric for metric, pattern in _METRIC_WORDS.items() if re.search(pattern, historical, re.I)]
    issues = []
    for metric in metrics:
        clauses = [clause for clause in historical_clauses
                   if re.search(_METRIC_WORDS[metric], clause, re.I) and _TREND.search(clause)]
        if not clauses:
            continue  # A disclosed impact is not automatically a historical comparison.
        accelerated = any(_metric_acceleration(clause, metric) for clause in clauses)
        needed = 3 if accelerated else 2
        levels, errors = _metric_observations(metric, cited, book)
        if len(levels) < needed:
            issues.append(f"Comparative completeness: {metric} requires {needed} consecutive annual periods, or a Python comparison source retaining those periods.")
            continue
        rows = levels[-needed:]
        reason = _annual_window_reason(rows)
        concepts = [{s.get("concept") for s in row.get("sources", []) if isinstance(s, dict)} for row in rows]
        if not reason and (not all(concepts) or any(value != concepts[0] for value in concepts[1:])):
            reason = "underlying XBRL concept sets changed or are missing"
        if not reason and len({row.get("unit") for row in rows}) != 1:
            reason = "units differ across annual observations"
        if reason or errors:
            issues.append(f"Comparative comparability: {metric}: {reason or '; '.join(errors)}.")
            continue
        values = [row.get("value") for row in rows]
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in values):
            issues.append(f"Comparative comparability: {metric} contains unavailable or non-finite values.")
            continue
        for clause in clauses:
            # Numerator/denominator movements are not the movement of a ratio.
            ratio = re.search(r"\b(?:ratio|conversion|proportion|percentage|relative to|as a share|as a proportion|to revenue|to operating cash flow)\b", clause, re.I)
            if ratio or metric != "operating_margin" and re.search(r"\bmargin\b", clause, re.I):
                continue
            acceleration = _metric_acceleration(clause, metric)
            if acceleration:
                if values[0] <= 0 or values[1] <= 0 or values[2] < 0:
                    issues.append(f"Comparative acceleration: {metric} requires positive growth bases and non-negative current values.")
                    continue
                prior_rate, current_rate = values[1] / values[0] - 1, values[2] / values[1] - 1
                delta = current_rate - prior_rate
                increasing = bool(re.search(r"\baccelerat\w*\b", acceleration, re.I))
                decreasing = bool(re.search(r"\bdecelerat\w*\b", acceleration, re.I))
                # 'Decline accelerated' has the opposite sign to accelerating growth.
                decline = bool(re.search(r"\b(?:decline|contraction|deterioration)\b", acceleration, re.I))
                if decline:
                    delta = -delta
                if increasing != decreasing and ((increasing and delta <= 1e-12) or (decreasing and delta >= -1e-12)):
                    issues.append(f"Comparative acceleration: {metric} prose contradicts the consecutive annual growth intervals.")
                continue
            if re.search(r"\bgrowth(?: rate)?\b", clause, re.I) and (values[-2] <= 0 or values[-1] < 0):
                issues.append(f"Comparative growth: {metric} has a non-positive base or negative current value; a growth-rate assertion is misleading.")
                continue
            # A direction word attached to one metric cannot be attributed to
            # another in a compound clause. Completeness is still checked above.
            if sum(bool(re.search(pattern, clause, re.I)) for pattern in _METRIC_WORDS.values()) > 1:
                continue
            # Handle only an explicit, single-metric historical denial ending
            # the clause. Materiality qualifiers, counterfactuals and more
            # complicated negation remain subject to analyst review.
            if re.search(r"\b(?:not|never|cannot|didn't|did not)\b", clause, re.I):
                denied = re.search(r"\b(?:did not|didn't)\s+"
                    r"(increase|rise|grow|expand|decrease|fall|decline|contract)\s*$", clause, re.I)
                conditional = re.search(r"\b(?:if|unless|assuming|hypothetical|may|might|could|would|should)\b", clause, re.I)
                if denied and not conditional:
                    delta = values[-1] - values[-2]
                    denial_of_increase = denied.group(1).lower() in {"increase", "rise", "grow", "expand"}
                    if (denial_of_increase and delta > 0) or (not denial_of_increase and delta < 0):
                        issues.append(f"Comparative direction: negated {metric} movement contradicts the cited annual values.")
                continue
            up = bool(re.search(r"\b(?:increased|rose|grew|expanded|improved|higher|rising)\b", clause, re.I))
            down = bool(re.search(r"\b(?:decreased|fell|declined|contracted|contracting|deteriorated|lower|falling)\b", clause, re.I))
            if up != down:
                delta = values[-1] - values[-2]
                if (up and delta <= 0) or (down and delta >= 0):
                    issues.append(f"Comparative direction: {metric} prose contradicts the cited annual values.")
    return list(dict.fromkeys(issues))


def _accounting_and_disclosure_issues(text: str) -> list[str]:
    """Bounded wording checks, not a general accounting or entailment parser."""
    issues = []
    if re.search(r"\b(?:free cash flow|fcf)\b", text) and not _future_only(text):
        lease_payment = (r"(?:(?:all|any|the)\s+)?(?:(?:finance|operating)[ -])?"
            r"lease(?:[- ]related)?\s+(?:(?:principal|interest)\s+)?(?:payments?|repayments?|cash outflows?)")
        exclusions = re.finditer(r"\b(?:exclud(?:e[ds]?|ing)|omit(?:s|ted|ting)?|does not include|without)\s+"
            r"(?P<payments>" + lease_payment + r")\b", text, re.I)
        for exclusion in exclusions:
            before = text[max(0, exclusion.start() - 18):exclusion.start()]
            if re.search(r"\b(?:not|never|doesn't|does not)\s*$", before, re.I):
                continue
            if not re.search(r"\bfinance[- ]lease\s+principal\s+(?:payments?|repayments?)\b",
                             exclusion.group("payments"), re.I):
                issues.append("Lease accounting: this cash-PP&E free-cash-flow measure excludes finance-lease principal repayments, not all lease payments; operating lease cash costs may already enter OCF.")
    availability_claim = re.search(
        r"\b(?:company|microsoft|management|filing)\s+(?:does not|doesn't|has not|hasn't)\s+"
        r"(?:disclose[ds]?|provide[ds]?|report(?:ed|s)?|publish(?:ed|es)?|quantif(?:y|ied|ies)|breaks? out|broken out)\b|"
        r"\b(?:disclosures?|breakouts?|breakdowns?|information|data)\s+(?:are|is|remains?)\s+"
        r"(?:limited|unavailable|absent|missing|not (?:available|provided|disclosed|reported))\b", text, re.I)
    packet_scope = re.search(r"\b(?:packet|excerpts?|selected passages?|bounded passages?|supplied context|"
        r"provided context|research context|available evidence|selected evidence|provided sources?)\b", text, re.I)
    if availability_claim and not packet_scope:
        issues.append("Disclosure scope: absence or limited detail in selected evidence does not establish company non-disclosure; qualify the limitation to the supplied packet or passages.")
    return issues


def _overclaim_issues(claim: Claim, book: dict) -> list[str]:
    if claim.kind not in {"fact", "inference"}:
        return []
    issues = []
    # Scope negation locally: an unrelated 'unknown' elsewhere must not excuse
    # a positive categorical assertion about all AI expenditure or proven ROIC.
    for text in _clauses(claim.text.lower()):
        issues.extend(_accounting_and_disclosure_issues(text))
        # Use the cash-PP&E wording actually supplied to the model as well as
        # the conventional capex label. An alias changes neither the measured
        # cash-purchases definition nor the scope of the attribution safeguard.
        capex = bool(re.search(r"\b(?:capex|capital expenditure[s]?|capital spending|"
            r"(?:cash\s+)?pp&e(?:\s+(?:purchases|additions|spending))?|"
            r"(?:cash\s+)?(?:purchases|additions|spending)\s+(?:of|on|for)\s+property and equipment|"
            r"property and equipment\s+(?:purchases|additions|spending))\b", text))
        ai = bool(re.search(r"\b(?:ai|artificial intelligence)\b", text))
        total = bool(re.search(r"\b(?:all|entire|entirely|exclusively|wholly)\b", text))
        denies_attribution = bool(re.search(
            r"\b(?:not all|not entirely|not exclusively|not wholly|(?:cannot|does not|doesn't)\s+(?:\w+\s+){0,4}(?:establish|attribute|equate|identify)|(?:is|are|was|were) not\s+(?:\w+\s+){0,4}(?:ai|artificial intelligence))\b", text))
        if capex and ai and total and not denies_attribution:
            issues.append("Capital attribution: total corporate cash PP&E does not establish that all capex is AI-specific.")
        returns = r"(?:roic|returns? on invested capital|incremental returns?)"
        if re.search(r"\b" + returns + r"\b", text):
            uncertain_returns = bool(re.search(
                r"\b(?:no|unknown|unavailable|unproven|uncertain|insufficient)\s+(?:\w+\s+){0,3}" + returns + r"\b|\b" + returns +
                r"\s+(?:(?:is|are|remains?|were|was)\s+)?(?:not |unproven|unknown|uncertain|unavailable)", text))
            disclosed_expectation = bool(claim.passage_citations and _future_only(text)
                and re.search(r"\b(?:management|company|filing)\b.{0,45}\b(?:expects?|anticipates?|warns?|discloses?|forecasts?)\b", text))
            # A categorical level judgment remains unsupported when unrelated
            # uncertainty appears elsewhere in this clause or the whole claim.
            # Match only simple asserted predicates; questions, mechanisms and
            # conditional interpretations are not silently treated as estimates.
            asserted_return_level = bool(re.search(r"\b" + returns +
                r"\s+(?:is|are|was|were|remains?|(?:has|have|had) been)\s+"
                r"(?:(?:very|particularly|demonstrably|already|consistently|historically)\s+){0,2}"
                r"(?:attractive|unattractive|high|low|strong|weak|superior|inferior|positive|negative|robust|poor|healthy)\b", text))
            if asserted_return_level and not disclosed_expectation:
                issues.append("Return attribution: a categorical ROIC or incremental-return judgment is not established by the cited spending or growth.")
            if not uncertain_returns and not disclosed_expectation:
                if claim.kind == "fact" and not any("roic" in book.get(c.source_id, {}).get("metric", "") for c in claim.financial_citations):
                    issues.append("Return attribution: no defensible ROIC calculation is present in the cited financial evidence.")
                elif re.search(r"\b(?:proves?|guarantees?|ensures?|will generate|will deliver)\b", text):
                    issues.append("Return attribution: cited spending or growth cannot guarantee attractive investment returns.")
            elif not uncertain_returns and re.search(r"\b(?:proves?|guarantees?|ensures?)\b", text):
                issues.append("Return attribution: cited spending or growth cannot guarantee attractive investment returns.")
        valuation = bool(re.search(r"\b(?:undervalued|overvalued|price target|buy rating|sell rating)\b", text)
            or re.search(r"\b(?:shares?|stock|equity|company)\b.{0,35}\bfair value\b", text))
        denies_valuation = bool(re.search(r"\b(?:not|no|cannot|does not|doesn't)\b.{0,45}\b(?:undervalued|overvalued|price target|buy rating|sell rating|fair value)\b", text))
        if valuation and not denies_valuation:
            issues.append("Valuation conclusion is unsupported by the available reported-financial evidence.")
    return list(dict.fromkeys(issues))


def semantic_review_flags(claim: Claim, book: dict) -> list[str]:
    """Transparent review cues only; never an automated entailment score."""
    flags = ["Claim meaning, materiality and completeness require analyst review."]
    text = claim.text.lower()
    if _TREND.search(text) and claim.passage_citations and not claim.financial_citations:
        flags.append("Narrative comparison: inspect the quoted period and scope; filing report date alone does not establish the comparison.")
    if claim.passage_citations and any(_future_only(clause) for clause in _clauses(text)):
        flags.append("Forward-looking disclosure: check management attribution, conditional wording and the quoted expectation; this is not an observed annual result.")
    if re.search(r"\b(?:ai|artificial intelligence)\b", text) and any(
            book.get(c.source_id, {}).get("metric") == "capital_expenditure" for c in claim.financial_citations):
        flags.append("Capital attribution review: the financial amount is total corporate cash PP&E, not an AI-specific breakdown.")
    if re.search(r"\b(?:because|due to|driven by|caused|demonstrates|therefore|will increase|continue to)\b", text):
        flags.append("Causal/forward-looking language: distinguish management disclosure, expectation and tentative analyst inference.")
    if claim.passage_citations:
        flags.append("Check that the selected quote supports every clause, rather than merely existing in a relevant source.")
    return flags


def _check_claim(section: str, claim: Claim, book: dict) -> tuple[str, list[str]]:
    issues = []
    if not claim.text.strip():
        issues.append("The claim text is empty.")
    if _numeric_prose(claim.text, question=section == "missing_information" and claim.kind == "question"):
        issues.append("Numerical prose is not permitted; figures and periods must be displayed from checked structured citations by Python.")
    ids = [citation.source_id for citation in claim.financial_citations + claim.passage_citations]
    if len(ids) != len(set(ids)):
        issues.append("Duplicate source references within the claim.")
    for citation in claim.financial_citations:
        issues.extend(_financial_issues(citation, book))
    for citation in claim.passage_citations:
        issues.extend(_passage_issues(citation, book))
    issues.extend(_comparative_issues(claim, book))
    issues.extend(_overclaim_issues(claim, book))

    # Section and kind are both constrained, so unsupported assertions cannot be
    # silently promoted by labelling ordinary prose as an uncited question.
    if section == "missing_information":
        if claim.kind != "question" or not claim.text.rstrip().endswith("?"):
            issues.append("Missing information must be phrased as an explicit diligence question.")
    elif section == "assumptions":
        if claim.kind != "hypothesis" or not claim.text.startswith("Assumption:"):
            issues.append("Assumptions must be labelled hypotheses beginning 'Assumption:'.")
    elif section == "invalidation_conditions":
        if claim.kind != "hypothesis" or not claim.text.startswith("If "):
            issues.append("Invalidation conditions must be conditional hypotheses beginning 'If '.")
    elif claim.kind not in {"fact", "inference"}:
        issues.append("This section requires a cited fact or an explicitly labelled interpretation.")

    if claim.kind in {"fact", "inference"} and not ids:
        issues.append("A material factual claim or interpretation has no supporting source citation.")
    # Narrative business developments require actual narrative evidence; annual
    # consolidated financial totals alone cannot substantiate product events.
    if section == "business_developments" and not claim.passage_citations:
        issues.append("Business developments require a retrieved filing passage citation.")
    if issues:
        return "unsupported", issues
    return {"fact": "evidence_checked", "inference": "interpretation",
            "hypothesis": "hypothesis", "question": "question"}[claim.kind], []


def validate_analysis(output: ResearchAnalysis | ThesisChallenge, book: dict[str, dict]) -> VerificationReport:
    """Quarantine individual unsupported claims without discarding valid claims.

    'evidence_checked' means references and explicit figures/quotes passed the
    deterministic contract. Semantic entailment and completeness require human
    review; a real but irrelevant citation can still accompany false prose.
    """
    if not isinstance(output, (ResearchAnalysis, ThesisChallenge)):
        raise TypeError("Expected a validated ResearchAnalysis or ThesisChallenge.")
    claims = []
    for section in type(output).model_fields:
        for index, claim in enumerate(getattr(output, section)):
            status, issues = _check_claim(section, claim, book)
            claims.append(CheckedClaim(section=section, index=index, claim=claim, status=status, issues=issues,
                review_flags=semantic_review_flags(claim, book)))
    return VerificationReport(claims=claims, source_fingerprint=evidence_fingerprint(book))
