"""Conservative extraction of annual, consolidated US-GAAP company facts.

Only 350–380 day duration facts from 10-K/10-K/A filings are eligible. A fact's
``fy`` describes its filing, so comparative facts are grouped by their actual
start/end, never by ``fy``. Latest-filed comparatives/restatements are used;
equally recent contradictory disclosures become N/A. Every calculation retains
the individual input facts. No estimates or silent zero filling occur here.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date
import math
import re
from typing import Iterable

from .models import AnnualPeriod, MetricValue, SourceFact

ANNUAL_FORMS = {"10-K", "10-K/A"}
REVENUE_TAGS = (
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
)

_DEFINITIONS = {
    "revenue": {
        "label": "Revenue", "unit": "USD", "concepts": list(REVENUE_TAGS),
        "description": "Consolidated revenue, excluding assessed taxes. Goods-only and service-only concepts are not substituted for total revenue.",
    },
    "operating_income": {
        "label": "Operating income", "unit": "USD", "concepts": ["OperatingIncomeLoss"],
        "description": "Reported consolidated operating income (loss).",
    },
    "operating_margin": {
        "label": "Operating margin", "unit": "ratio", "concepts": ["OperatingIncomeLoss", *REVENUE_TAGS],
        "description": "Python: operating income / revenue for the exact same annual dates; displayed as a percentage. Undefined if revenue is zero.",
    },
    "net_income": {
        "label": "Net income", "unit": "USD", "concepts": ["NetIncomeLoss"],
        "description": "Net income (loss) attributable to the parent. ProfitLoss is not substituted because its noncontrolling-interest scope differs.",
    },
    "diluted_eps": {
        "label": "Diluted EPS", "unit": "USD/shares", "concepts": ["EarningsPerShareDiluted"],
        "description": "Reported diluted earnings per share; not recalculated or substituted with basic EPS.",
    },
    "operating_cash_flow": {
        "label": "Operating cash flow", "unit": "USD", "concepts": ["NetCashProvidedByUsedInOperatingActivities"],
        "description": "Reported net cash from operating activities, including any discontinued operations.",
    },
    "capital_expenditure": {
        "label": "Capital expenditure", "unit": "USD", "concepts": ["PaymentsToAcquirePropertyPlantAndEquipment"],
        "description": "Cash payments to acquire property, plant and equipment, shown as a positive cash outflow. Excludes acquisitions, finance lease additions and non-cash capex.",
    },
    "free_cash_flow": {
        "label": "Free cash flow", "unit": "USD", "concepts": ["NetCashProvidedByUsedInOperatingActivities", "PaymentsToAcquirePropertyPlantAndEquipment"],
        "description": "Python: operating cash flow − cash payments for PP&E. Analyst-defined, non-GAAP measure; excludes finance lease principal repayments.",
    },
    "cash_and_equivalents": {
        "label": "Cash and cash equivalents", "unit": "USD", "concepts": ["CashAndCashEquivalentsAtCarryingValue"],
        "description": "Cash and cash equivalents at fiscal year end. Excludes short-term investments, marketable securities and restricted cash.",
    },
    "total_debt": {
        "label": "Total debt", "unit": "USD", "concepts": ["LongTermDebtNoncurrent", "LongTermDebtCurrent", "LongTermDebt", "ShortTermBorrowings", "CommercialPaper"],
        "description": "Interest-bearing borrowings at carrying value; excludes leases. Current/noncurrent long-term debt plus short-term borrowings. LongTermDebt is the total current + noncurrent long-term-debt alternative, never added to its components. DebtCurrent is not used because its scope can include leases. No missing component is assumed zero. CommercialPaper represents the separate short-term-debt line only for the verified MSFT/AAPL profiles.",
    },
    "net_debt": {
        "label": "Net debt", "unit": "USD", "concepts": ["LongTermDebtNoncurrent", "LongTermDebtCurrent", "LongTermDebt", "ShortTermBorrowings", "CommercialPaper", "CashAndCashEquivalentsAtCarryingValue"],
        "description": "Python: total debt − cash and cash equivalents. Negative values mean net cash under this definition. Short-term investments and lease liabilities are excluded.",
    },
}


def metric_definitions() -> dict:
    """Return the public metric mapping without exposing mutable module state."""
    return deepcopy(_DEFINITIONS)


def _date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def _annual(fact: dict) -> bool:
    start, end = _date(fact.get("start")), _date(fact.get("end"))
    return bool(start and end and 350 <= (end - start).days + 1 <= 380)


def _eligible(fact: dict, instant: bool) -> bool:
    value = fact.get("val")
    return (
        fact.get("form") in ANNUAL_FORMS
        and isinstance(value, (int, float)) and not isinstance(value, bool)
        and math.isfinite(value)
        and _date(fact.get("filed")) is not None
        and _date(fact.get("end")) is not None
        and _date(fact["filed"]) >= _date(fact["end"])
        and bool(re.fullmatch(r"\d{10}-\d{2}-\d{6}", str(fact.get("accn", ""))))
        and ((not fact.get("start")) if instant else _annual(fact))
    )


def _facts(companyfacts: dict, tag: str, unit: str, instant: bool = False) -> list[dict]:
    values = companyfacts.get("facts", {}).get("us-gaap", {}).get(tag, {}).get("units", {}).get(unit, [])
    return [f for f in values if isinstance(f, dict) and _eligible(f, instant)]


def _source(companyfacts: dict, tag: str, unit: str, fact: dict) -> SourceFact:
    cik = str(companyfacts.get("cik", "")).lstrip("0") or "0"
    accn = fact["accn"]
    url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn.replace('-', '')}/{accn}-index.html"
    return SourceFact(
        concept=f"us-gaap:{tag}", unit=unit, value=float(fact["val"]),
        start=fact.get("start"), end=fact["end"], accession=accn,
        filed=fact["filed"], form=fact["form"], url=url,
    )


def _missing(unit: str, reason: str) -> MetricValue:
    return MetricValue(None, unit, [], reason)


def _select(companyfacts: dict, tags: Iterable[str], unit: str, start: str | None,
            end: str, *, instant: bool = False) -> MetricValue:
    """Use latest filed data across equivalent tags; never resolve a conflict arbitrarily."""
    tags = tuple(tags)
    candidates = [
        (tag, fact)
        for tag in tags for fact in _facts(companyfacts, tag, unit, instant)
        if fact["end"] == end and (instant or fact.get("start") == start)
    ]
    if not candidates:
        kind = f"instant at {end}" if instant else f"annual duration {start} to {end}"
        return _missing(unit, f"No eligible {unit} 10-K/10-K/A fact ({', '.join(tags)}) for {kind}; missing, wrong-unit or incompatible-period facts are not substituted.")
    latest = max(f["filed"] for _, f in candidates)
    selected = [(tag, f) for tag, f in candidates if f["filed"] == latest]
    # SEC companyfacts has filing dates but no acceptance times. Conflicting
    # filings on the same date cannot safely be ordered by accession or form.
    values = {float(f["val"]) for _, f in selected}
    sources = [_source(companyfacts, tag, unit, f) for tag, f in selected]
    unique = {tuple(vars(s).values()): s for s in sources}
    sources = list(unique.values())
    if len(values) != 1:
        return MetricValue(None, unit, sources,
                           f"Conflicting {unit} facts in the latest eligible filing date ({latest}); review the linked disclosures.")
    return MetricValue(next(iter(values)), unit, sources)


def _recent_filings(submissions: dict) -> list[dict]:
    """Support SEC columnar recent filings plus root-service merged history."""
    recent = submissions.get("filings", {}).get("recent", {})
    if isinstance(recent, list):
        return recent
    if not isinstance(recent, dict):
        return []
    forms = recent.get("form", [])
    return [{key: value[i] for key, value in recent.items()
             if isinstance(value, list) and i < len(value)} for i in range(len(forms))]


def _periods(companyfacts: dict, submissions: dict, years: int) -> list[tuple[int, str, str]]:
    filings = [f for f in _recent_filings(submissions)
               if f.get("form") in ANNUAL_FORMS and _date(f.get("reportDate"))]
    anchors = {f["reportDate"] for f in filings}
    # Revenue is the primary duration anchor. Other consolidated statement totals
    # allow a missing revenue tag without deriving a year from an instant fact.
    duration_tags = (*REVENUE_TAGS, "OperatingIncomeLoss", "NetIncomeLoss", "NetCashProvidedByUsedInOperatingActivities")
    candidates = [(tag, f) for tag in duration_tags for f in _facts(companyfacts, tag, "USD")]
    if not candidates:
        return []
    own_fiscal_labels = {}
    for filing_end in anchors:
        accessions = {f.get("accessionNumber") for f in filings if f["reportDate"] == filing_end}
        labels = {f["fy"] for _, f in candidates if f["end"] == filing_end
                  and f["accn"] in accessions and isinstance(f.get("fy"), int)
                  and not isinstance(f.get("fy"), bool)}
        if len(labels) == 1:
            own_fiscal_labels[filing_end] = next(iter(labels))
    revenue_ends = {f["end"] for tag, f in candidates if tag in REVENUE_TAGS}
    ends = (anchors | revenue_ends) if anchors else revenue_ends
    # If revenue is entirely unavailable, completed annual filings can still be
    # anchored by another actual annual duration, but never solely balance sheets.
    if not ends:
        ends = {f["end"] for _, f in candidates}
    result = []
    # Choose the requested reporting years before checking extraction success.
    # An unavailable latest report must not be silently replaced by an old year.
    for end in sorted(ends, reverse=True)[:years]:
        rows = [(tag, f) for tag, f in candidates if f["end"] == end]
        if not rows:
            continue
        own_accessions = {f.get("accessionNumber") for f in filings if f["reportDate"] == end}
        own = [(tag, f) for tag, f in rows if f["accn"] in own_accessions]
        revenue = [(tag, f) for tag, f in (own or rows) if tag in REVENUE_TAGS]
        pool = revenue or own or rows
        latest = max(f["filed"] for _, f in pool)
        latest_rows = [(tag, f) for tag, f in pool if f["filed"] == latest]
        starts = {f["start"] for _, f in latest_rows}
        if len(starts) != 1:
            # Conflicting near-annual periods cannot safely be merged or guessed.
            continue
        start = next(iter(starts))
        # Only the fy from the report's own accession is a fiscal label. A later
        # filing's comparative fy is deliberately ignored.
        fiscal_year = own_fiscal_labels.get(end)
        if fiscal_year is None:
            # Older original submissions can fall outside the API's recent list.
            # Carry a verified fiscal label back by actual annual spacing, so a
            # January year-end is not automatically called its calendar year.
            inferred = set()
            for labelled_end, label in own_fiscal_labels.items():
                days = (_date(end) - _date(labelled_end)).days
                offset = round(days / 365.25)
                if abs(days - offset * 365.25) <= 30:
                    inferred.add(label + offset)
            fiscal_year = inferred.pop() if len(inferred) == 1 else _date(end).year
        result.append((fiscal_year, start, end))
    return result


def _combine(inputs: list[MetricValue], unit: str, name: str, operation) -> MetricValue:
    sources = list({tuple(vars(s).values()): s for m in inputs for s in m.sources}.values())
    missing = [m.reason for m in inputs if m.value is None]
    if missing:
        return MetricValue(None, unit, sources, f"{name} unavailable: " + " ".join(missing))
    duration_dates = {(s.start, s.end) for s in sources if s.start is not None}
    instant_dates = {s.end for s in sources if s.start is None}
    if len(duration_dates) > 1 or len(instant_dates) > 1 or (
        duration_dates and instant_dates and {d[1] for d in duration_dates} != instant_dates
    ):
        return MetricValue(None, unit, sources, f"{name} unavailable: input reporting periods differ.")
    value = operation(*[m.value for m in inputs])
    if value is None or not math.isfinite(value):
        return MetricValue(None, unit, sources, f"{name} unavailable: zero revenue makes the margin undefined.")
    return MetricValue(float(value), unit, sources)


def _debt(companyfacts: dict, start: str, end: str) -> MetricValue:
    def select(tag):
        metric = _select(companyfacts, [tag], "USD", start, end, instant=True)
        if metric.value is not None and metric.value < 0:
            return MetricValue(None, "USD", metric.sources,
                               f"Negative debt balance ({tag}) is inconsistent with the carrying-value definition; review filing.")
        return metric
    noncurrent = select("LongTermDebtNoncurrent")
    total_long = select("LongTermDebt")
    current_long = select("LongTermDebtCurrent")
    short = select("ShortTermBorrowings")
    # The balance sheets of these two supported companies explicitly use CP as
    # their separate short-term-debt line. Do not generalise that identity.
    cik = str(companyfacts.get("cik", "")).lstrip("0")
    if short.value is None and not short.sources and cik in {"789019", "320193"}:
        short = select("CommercialPaper")
    # A valid aggregate is not permission to hide contradictory/negative detail.
    # Missing detail is acceptable when the total is explicitly reported; an
    # explicit invalid disclosure requires review, even if not used in the sum.
    components = [total_long, current_long, noncurrent, short]
    invalid = [m for m in components if m.sources and m.value is None]
    if invalid:
        sources = list({tuple(vars(s).values()): s for m in components for s in m.sources}.values())
        return MetricValue(None, "USD", sources, "Total debt unavailable: " + " ".join(m.reason for m in invalid))
    if total_long.value is not None:
        long_debt = total_long
        if current_long.value is not None and noncurrent.value is not None:
            component_total = current_long.value + noncurrent.value
            if not math.isclose(total_long.value, component_total, rel_tol=1e-10, abs_tol=0.01):
                return MetricValue(None, "USD", total_long.sources + current_long.sources + noncurrent.sources,
                                   "Total debt unavailable: reported long-term debt disagrees with its current/noncurrent components.")
    else:
        long_debt = _combine([current_long, noncurrent], "USD", "Long-term debt", lambda a, b: a + b)
    return _combine([long_debt, short], "USD", "Total debt", lambda a, b: a + b)


def extract_annuals(companyfacts: dict, submissions: dict, years: int = 3) -> list[AnnualPeriod]:
    """Extract latest completed annual periods, oldest first, with full provenance.

    Latest-filed historical values may be restated; this is not point-in-time
    backtest data. Missing/conflicting figures stay None, displayed as N/A by UI.
    """
    if not isinstance(years, int) or isinstance(years, bool) or years < 1:
        raise ValueError("years must be a positive integer")
    output = []
    for fiscal_year, start, end in _periods(companyfacts, submissions, years):
        metrics = {}
        for key in ("revenue", "operating_income", "net_income", "diluted_eps", "operating_cash_flow", "capital_expenditure", "cash_and_equivalents"):
            definition = _DEFINITIONS[key]
            metrics[key] = _select(companyfacts, definition["concepts"], definition["unit"], start, end,
                                   instant=key == "cash_and_equivalents")
        capex = metrics["capital_expenditure"]
        if capex.value is not None and capex.value < 0:
            metrics["capital_expenditure"] = MetricValue(None, "USD", capex.sources,
                "Negative PaymentsToAcquirePropertyPlantAndEquipment contradicts the positive cash-payment convention; review filing rather than silently reversing its sign.")
        metrics["operating_margin"] = _combine([metrics["operating_income"], metrics["revenue"]], "ratio", "Operating margin",
                                                lambda income, revenue: income / revenue if revenue else None)
        metrics["free_cash_flow"] = _combine([metrics["operating_cash_flow"], metrics["capital_expenditure"]], "USD", "Free cash flow", lambda ocf, capex: ocf - capex)
        metrics["total_debt"] = _debt(companyfacts, start, end)
        metrics["net_debt"] = _combine([metrics["total_debt"], metrics["cash_and_equivalents"]], "USD", "Net debt", lambda debt, cash: debt - cash)
        output.append(AnnualPeriod(fiscal_year, start, end, metrics))
    return list(reversed(output))
