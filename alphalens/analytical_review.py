"""Read-only, bounded analytical review beside the original research contract.

These rules identify some accounting and attribution mistakes. They are not an
entailment model, a general fact checker, or an investment-quality score. The
original Claim, CheckedClaim and saved report are never modified or revalidated
into a different historical result. All conclusions still need analyst review.
"""
from __future__ import annotations

import re

from pydantic import ValidationError

from .research import (
    Claim, _METRIC_WORDS, _clauses, _comparative_issues, _financial_issues, _metric_observations,
    _numeric_prose, _overclaim_issues, _passage_issues,
)


_CAUSAL = re.compile(r"\b(?:because|due to|driven by|supported by|caused by|reflects?|reflecting|attributable to|results? from|rely|relies)\b", re.I)
_CONDITIONAL = re.compile(r"\b(?:if|could|may|might|would|hypothes[ei]s|possible|plausible|potential|uncertain)\b", re.I)
_WC = re.compile(r"\bworking[ -]capital\b", re.I)
_OP = re.compile(r"\boperating (?:income|profit|earnings)\b", re.I)
_OCF = re.compile(r"\b(?:operating cash flow|cash (?:flow )?from operations)\b", re.I)
_NONRECURRING = re.compile(r"\b(?:non[ -]?recurring|one[ -]off|one[ -]time|investment gains?|gains? from investments?)\b", re.I)
_CAPEX = re.compile(r"\b(?:capex|capital expenditure[s]?|cash pp&e|cash purchases of property and equipment)\b", re.I)


def _flag(code, message, ids=()):
    return {"code": code, "message": message, "evidence_ids": list(dict.fromkeys(ids))}


def _sentences(text):
    return re.split(r"(?<=[.!?])\s+", text)


def _wc_disclosure(quoted):
    """Only explicit management attribution, never a receipts/tax inference."""
    for sentence in _sentences(quoted):
        if not (_WC.search(sentence) and _OCF.search(sentence)):
            continue
        if re.search(r"\b(?:not|no|never|didn't|did not|doesn't|does not)\b.{0,45}\b(?:benefit|favorable|favourable|improv|attribut)", sentence, re.I):
            continue
        if re.search(r"\b(?:benefit(?:ed|s)?|favorable|favourable|released cash|provided cash|improv(?:ed|ement))\b", sentence, re.I):
            return True
    return False


def _financial_direction_only(text):
    """Recognise a deliberately small grammar of financial-direction displays."""
    value = text.lower().strip()
    names = (r"operating cash flow|cash flow from operations|cash from operations|"
             r"free cash flow|operating income|operating profit|operating margins?|"
             r"net income|total debt|net debt|capital expenditures?|cash pp&e|revenue|sales")
    value, count = re.subn(r"\b(?:" + names + r")\b", " METRIC ", value)
    if not count:
        return False
    value = re.sub(r"\b(?:increased|decreased|grew|rose|fell|declined|expanded|contracted|improved|deteriorated)\b", " MOVED ", value)
    value = re.sub(r"\b(?:and|while|whereas|but|both|the|materially|significantly|notably|modestly|substantially)\b", " ", value)
    value = re.sub(r"[\s.,;]+", " ", value).strip()
    return "MOVED" in value and not re.sub(r"\b(?:METRIC|MOVED)\b|\s", "", value)


def _bounded_direction_checks(claim, book):
    """Check shared subjects, e.g. 'revenue and operating income declined'.

    The legacy comparative guard intentionally leaves compound clauses for
    review. This narrower display grammar can bind a single direction verb to
    each named subject. Multiple verbs in one clause remain unclassified.
    """
    if not _financial_direction_only(claim.text):
        return [], False
    cited = [book.get(c.source_id, {}) for c in claim.financial_citations]
    cited = [source for source in cited if isinstance(source, dict) and source.get("kind") == "financial"]
    patterns = {**_METRIC_WORDS, "capital_expenditure": _METRIC_WORDS["capital_expenditure"] + r"|\bcash pp&e\b"}
    issues, complete = [], True
    for clause in _clauses(claim.text):
        if not clause.strip():
            continue
        verbs = re.findall(r"\b(?:increased|decreased|grew|rose|fell|declined|expanded|contracted|improved|deteriorated)\b", clause, re.I)
        names = [metric for metric, pattern in patterns.items() if re.search(pattern, clause, re.I)]
        if len(verbs) != 1 or not names:
            complete = False
            continue
        increase = verbs[0].lower() in {"increased", "grew", "rose", "expanded", "improved"}
        for metric in names:
            levels, errors = _metric_observations(metric, cited, book)
            if errors or len(levels) < 2:
                issues.append(f"Bounded comparative support: {metric} needs two unambiguous cited annual observations.")
                continue
            change = levels[-1]["value"] - levels[-2]["value"]
            if (increase and change <= 0) or (not increase and change >= 0):
                issues.append(f"Bounded comparative direction: {metric} contradicts the cited annual values.")
    return issues, complete


def _bounded_cash_driver_match(claim, book, quoted):
    """A narrow disclosed-driver match, not independent causal certification.

    Deliberately accept only a limited complete sentence. Extra economic or
    forward-looking clauses cannot inherit support from the driver match.
    """
    receipts = r"(?:higher|increased) cash (?:collections|receipts|received) from customers"
    taxes = r"(?:lower|reduced) (?:cash )?income[ -]tax payments"
    driver = rf"(?:{receipts}(?: and {taxes})?|{taxes}(?: and {receipts})?)"
    fcf = (r",? while free cash flow (?:declined|contracted)(?: significantly)? as cash purchases "
           r"of property and equipment increased(?: substantially)?")
    pattern = (r"(?:operating cash flow|cash from operations) (?:increased|expanded)"
               r"(?: significantly| substantially)?(?:,)? (?:supported by|due to|because of) "
               + driver + rf"(?:{fcf})?\.?$")
    if not re.fullmatch(pattern, claim.text.strip(), re.I):
        return None
    clauses = [s for s in _sentences(quoted) if _OCF.search(s)
               and re.search(r"\b(?:due to|driven by|because|supported by)\b", s, re.I)]
    if not clauses:
        return None
    disclosure = " ".join(clauses)
    if re.search(receipts, claim.text, re.I) and not re.search(r"\bincrease in cash received from customers\b", disclosure, re.I):
        return None
    if re.search(taxes, claim.text, re.I) and not re.search(r"\bdecrease in cash used to pay income taxes\b", disclosure, re.I):
        return None
    cited = [book[c.source_id] for c in claim.financial_citations if c.source_id in book]
    ocf, errors = _metric_observations("operating_cash_flow", cited, book)
    if errors or len(ocf) < 2 or ocf[-1]["value"] <= ocf[-2]["value"]:
        return None
    if "free cash flow" in claim.text.lower():
        free, errors = _metric_observations("free_cash_flow", cited, book)
        capex, capex_errors = _metric_observations("capital_expenditure", cited, book)
        if (errors or capex_errors or len(free) < 2 or len(capex) < 2
                or free[-1]["value"] >= free[-2]["value"]
                or capex[-1]["value"] <= capex[-2]["value"]):
            return None
    return ("Bounded match to the cited management cash-flow driver clause; any free-cash-flow "
            "direction is separately reconciled to cited annual OCF and cash PP&E. This checks a "
            "disclosed explanation, not its persistence, materiality or independent economic causality.")


def review_claim(claim, evidence: dict, *, section: str = "") -> dict:
    """Review one claim without altering its text, citations or old validation.

    A flagged conditional explanation remains a hypothesis. An unsupported
    question premise is identified rather than turning the whole question into
    an asserted fact. Existence of a source never establishes semantic support.
    """
    raw_text = claim.get("text", "") if isinstance(claim, dict) else getattr(claim, "text", "")
    try:
        claim = Claim.model_validate(claim)
    except (ValidationError, TypeError, ValueError):
        return {"category": "Unsupported claim", "claim_text": raw_text if isinstance(raw_text, str) else "",
                "evidence_ids": [], "flags": [_flag("STRUCTURAL_INVALID", "Claim structure or citation fields are invalid; analytical support was not assessed.")],
                "support_basis": "Structural failure; no content was invented or repaired.", "requires_analyst_review": True}
    book = evidence if isinstance(evidence, dict) else {}
    ids = list(dict.fromkeys(c.source_id for c in claim.financial_citations + claim.passage_citations))
    flags, fatal = [], False
    issues = []
    for citation in claim.financial_citations:
        try:
            issues.extend(_financial_issues(citation, book))
        except (TypeError, ValueError, KeyError, AttributeError, ArithmeticError):
            issues.append(f"Malformed financial evidence for {citation.source_id}.")
    for citation in claim.passage_citations:
        try:
            issues.extend(_passage_issues(citation, book))
        except (TypeError, ValueError, KeyError, AttributeError, ArithmeticError):
            issues.append(f"Malformed passage evidence for {citation.source_id}.")
    try:
        issues.extend(_comparative_issues(claim, book))
        issues.extend(_overclaim_issues(claim, book))
        direction_issues, direction_checked = _bounded_direction_checks(claim, book)
        issues.extend(direction_issues)
    except (TypeError, ValueError, KeyError, AttributeError, ArithmeticError):
        direction_checked = False
        issues.append("Malformed evidence prevents period or attribution checks.")
    if _numeric_prose(claim.text, question=claim.kind == "question"):
        issues.append("Numerical prose must be rendered from the checked structured financial citations by Python.")
    if len(ids) != len(claim.financial_citations) + len(claim.passage_citations):
        issues.append("Duplicate source citations within the claim.")
    if issues:
        fatal = True
        flags.extend(_flag("MECHANICAL_EVIDENCE_FAILURE", issue, ids) for issue in dict.fromkeys(issues))
    conditional = claim.kind in {"hypothesis", "question"} or bool(_CONDITIONAL.search(claim.text))
    quoted = " ".join(c.quote for c in claim.passage_citations
                      if isinstance(book.get(c.source_id), dict) and book[c.source_id].get("kind") == "passage")
    financials = [book[c.source_id] for c in claim.financial_citations
                  if isinstance(book.get(c.source_id), dict) and book[c.source_id].get("kind") == "financial"]
    text = claim.text
    if not ids:
        flags.append(_flag("MISSING_EVIDENCE", "No supporting source is cited. A question or conditional mechanism is not established evidence."))
        if not conditional:
            fatal = True

    wc_denied = bool(re.search(r"\b(?:not|cannot|does not|doesn't|no evidence)\b.{0,60}\b(?:establish|prove|support|demonstrate|working[ -]capital)\b", text, re.I))
    if _WC.search(text) and not wc_denied and not _wc_disclosure(quoted):
        presupposed = bool(re.search(r"working[ -]capital (?:benefits|improvements|gains)\b", text, re.I)
                           and re.search(r"\b(?:observed|sustainable|sustainability|benefits)\b", text, re.I))
        flags.append(_flag("WORKING_CAPITAL_PREMISE_UNSUPPORTED" if presupposed else "WORKING_CAPITAL_RECONCILIATION_NEEDED",
                           "Customer receipts and tax payments do not by themselves establish working-capital benefits. Inspect a cash-flow/working-capital reconciliation; the proposed mechanism is unverified.", ids))
        if not conditional:
            fatal = True

    op_claim = bool(_OP.search(text))
    ni_gain = any(re.search(r"\bnet (?:income|earnings)|\bEPS\b", s, re.I)
                  and re.search(r"\bgains?\b|\binvestments?\b", s, re.I) for s in _sentences(quoted))
    op_gain = any(_OP.search(s) and _NONRECURRING.search(s) for s in _sentences(quoted))
    if op_claim and _NONRECURRING.search(text) and not op_gain:
        flags.append(_flag("NET_VS_OPERATING_SCOPE" if ni_gain else "OPERATING_NONRECURRING_DRIVER_UNESTABLISHED",
                           "The cited material does not establish a non-recurring operating-profit driver. Net-income/EPS investment gains cannot explain operating-income growth without a separate operating reconciliation.", ids))
        if not conditional:
            fatal = True

    ai_capex = bool(re.search(r"\b(?:ai|artificial intelligence)[ -](?:specific[ -])?(?:capex|capital expenditures?|cash pp&e|infrastructure spending)\b", text, re.I))
    aggregate = any(s.get("metric") == "capital_expenditure" for s in financials)
    denies_ai = bool(re.search(r"\b(?:not|cannot|does not|doesn't)\b.{0,50}\b(?:ai|artificial intelligence)\b", text, re.I))
    if aggregate and ai_capex and not denies_ai:
        flags.append(_flag("AGGREGATE_CAPEX_SCOPE", "The cited cash-PP&E amount measures company-wide purchases, not an AI-specific expenditure series or AI investment returns.", ids))
        if not conditional:
            fatal = True

    if (re.search(r"\b(?:will generate|will deliver|guarantees?|ensures?|proves?)\b.{0,70}\b(?:attractive|superior|high|strong)\b.{0,30}\breturns?\b", text, re.I)
            and not conditional and not re.search(r"\b(?:cannot|does not|doesn't|not)\b.{0,25}\b(?:guarantee|ensure|prove|will generate|will deliver)\b", text, re.I)):
        flags.append(_flag("FUTURE_RETURN_UNSUPPORTED", "Cited historical spending or earnings cannot establish or guarantee attractive future investment returns; a defensible incremental-return analysis is absent.", ids))
        fatal = True

    causal = bool(_CAUSAL.search(text))
    causal_period_problem = False
    if causal and financials and claim.passage_citations:
        current_end = max((str(s.get("period_end", "")) for s in financials), default="")
        for citation in claim.passage_citations:
            source = book.get(citation.source_id, {})
            if isinstance(source, dict) and source.get("kind") == "passage" and source.get("report_date") != current_end:
                causal_period_problem = True
        if causal_period_problem:
            flags.append(_flag("CAUSAL_PERIOD_SCOPE", "The causal passage is not tied to the latest cited financial year-end. Filing existence alone does not support the current-period explanation.", ids))
    driver_basis = None
    if not fatal and not causal_period_problem:
        try:
            driver_basis = _bounded_cash_driver_match(claim, book, quoted)
        except (TypeError, ValueError, KeyError, AttributeError, ArithmeticError):
            driver_basis = None
    if causal and not driver_basis:
        flags.append(_flag("CAUSAL_SUPPORT_REQUIRES_REVIEW", "The causal explanation is not established by the bounded disclosure checks. Inspect scope, accounting line, period and competing explanations; source existence is insufficient.", ids))
    if section in {"bull_case", "bear_case", "bull_interpretation", "bear_interpretation"}:
        flags.append(_flag("SCENARIO_IS_CONDITIONAL", "This investor case requires a cited factual basis, an economic mechanism and an observable strengthening or weakening condition; it is not a forecast or recommendation.", ids))

    if fatal:
        category, basis = "Unsupported claim", "At least one explicit structural, numerical, period, source or accounting-attribution check failed. Original text is preserved."
    elif claim.kind in {"question", "hypothesis"} or conditional or causal_period_problem:
        category, basis = "Unverified hypothesis", "A question, conditional mechanism or scope-limited interpretation requires further evidence; it is not an observed result."
    elif driver_basis:
        category, basis = "Supported interpretation", driver_basis
    elif claim.kind == "fact" and direction_checked and financials:
        calculated = bool(re.search(r"\b(?:free cash flow|operating margin|net debt)\b", text, re.I)
                          or any(s.get("derived") for s in financials))
        category = "Deterministic calculation" if calculated else "Verified observation"
        basis = "Checked cited financial values, units, dates and the bounded annual-direction statement. Economic materiality and the completeness of the explanation remain analyst judgments."
    else:
        category, basis = "Unverified hypothesis", "No bounded rule establishes the meaning of this prose. Existing citations and quotations require an analyst to assess relevance and completeness."
    return {"category": category, "claim_text": text, "evidence_ids": ids, "flags": flags,
            "support_basis": basis, "requires_analyst_review": True}


def review_research(validated) -> list[dict]:
    """Build a separate review record for every existing CheckedClaim."""
    result = []
    for checked in validated.verification.claims:
        review = review_claim(checked.claim, validated.evidence, section=checked.section)
        review.update({"section": checked.section, "index": checked.index})
        result.append(review)
    return result
