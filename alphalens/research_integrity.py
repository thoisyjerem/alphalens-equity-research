"""Reconcile prepared financial observations against retained Python records.

Checks cover internal numerical/provenance consistency, not remote document
authenticity, causal explanations or semantic support for model conclusions.
There are no model calls, retrieval, configuration reads or input mutations.
"""
from __future__ import annotations

from datetime import date
import math


_PERIOD = ("fiscal_year", "period_start", "period_end")
_COMPARISON = ("value", "unit", *_PERIOD)
_INSTANTS = {"total_debt", "net_debt", "cash_and_equivalents"}
_ERROR = "Financial observation integrity failed: "


def _require(condition, reason):
    if not condition:
        raise ValueError(_ERROR + reason)


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _same_number(left, right):
    # Binary-float round-off is permitted, without rounding displayed amounts.
    return _finite(left) and _finite(right) and math.isclose(left, right, rel_tol=1e-12, abs_tol=1e-9)


def _period(record):
    _require(type(record.get("fiscal_year")) is int, "invalid fiscal period.")
    try:
        start, end = date.fromisoformat(record["period_start"]), date.fromisoformat(record["period_end"])
    except (KeyError, ValueError, TypeError):
        raise ValueError(_ERROR + "invalid annual dates.") from None
    _require(350 <= (end - start).days + 1 <= 380, "comparison is not an annual duration.")
    return start, end


def validate_observation_integrity(evidence: dict, analysis: dict, observations: dict) -> None:
    """Check copied comparisons/changes and the critical cash-flow identity.

    The existing analytics engine remains the sole producer of growth rates and
    ratios. This additional boundary checks their copied observation records
    against it, and independently reconciles FCF with retained OCF/cash PP&E.
    It neither repairs a discrepancy nor supplies missing financial evidence.
    """
    try:
        _validate(evidence, analysis, observations)
    except (KeyError, TypeError, AttributeError, IndexError, OverflowError):
        raise ValueError(_ERROR + "incomplete or malformed financial records.") from None


def _validate(evidence, analysis, observations):
    _require(isinstance(evidence, dict) and isinstance(analysis, dict) and isinstance(observations, dict),
             "expected prepared financial mappings.")
    rows = analysis.get("metrics", [])
    _require(isinstance(rows, list), "analytics records are missing.")
    calculated = {row["source_id"]: row for row in rows}
    _require(len(calculated) == len(rows), "duplicate analytics source identifiers.")

    def financial(source_id):
        record = evidence.get(source_id)
        _require(isinstance(record, dict) and record.get("kind") == "financial" and _finite(record.get("value")),
                 "raw source is unknown, unavailable or not financial.")
        _require(source_id == f"{record['fiscal_year']}:{record['metric']}", "raw source identity disagrees with metric or fiscal year.")
        return record

    for observation_id, observation in observations.items():
        current, prior = observation["current_period"], observation["prior_period"]
        start, _ = _period(current)
        _, previous_end = _period(prior)
        _require(current["fiscal_year"] == prior["fiscal_year"] + 1 and (start - previous_end).days == 1,
                 "annual comparisons are not consecutive and contiguous.")
        _require(observation.get("id") == observation_id == f"{current['fiscal_year']}:{observation['type']}",
                 "observation identity disagrees with fiscal year or type.")
        comparisons, refs = observation["comparisons"], []
        _require([item["metric"] for item in comparisons] == observation["metrics"] and len(comparisons) > 0,
                 "comparison metrics disagree with the observation.")
        for comparison in comparisons:
            for side, period in (("prior", prior), ("current", current)):
                entry = comparison[side]
                source_id = entry["source_id"]
                derived = ":analytics." in source_id
                record = calculated.get(source_id) if derived else financial(source_id)
                _require(isinstance(record, dict) and _finite(record.get("value")), "comparison calculation is unknown or unavailable.")
                expected_id = f"{period['fiscal_year']}:" + ("analytics." if derived else "") + comparison["metric"]
                _require(source_id == expected_id, "comparison source identity differs from the expected metric and fiscal year.")
                _require(record.get("metric") == comparison["metric"] and all(entry.get(key) == record.get(key) for key in _COMPARISON),
                         "comparison value, metric, unit or period differs from its financial record.")
                expected = {**period, "period_start": None if comparison["metric"] in _INSTANTS else period["period_start"]}
                _require(all(entry.get(key) == expected[key] for key in _PERIOD), "comparison fiscal dates differ from observation periods.")
                dependencies = record.get("raw_dependencies") if derived else [source_id]
                _require(isinstance(dependencies, list) and len(dependencies) > 0 and entry.get("raw_source_ids") == dependencies,
                         "comparison dependencies disagree with its financial record.")
                refs.extend(dependencies)
        for change in observation["changes"]:
            record = calculated.get(change["source_id"])
            _require(isinstance(record, dict) and _finite(record.get("value")), "change calculation is unknown or unavailable.")
            _require(change["source_id"] == f"{current['fiscal_year']}:analytics.{change['metric']}",
                     "change source identity differs from its metric and fiscal year.")
            _require(all(change.get(key) == record.get(key) for key in ("metric", "value", "unit", "dependencies"))
                     and all(record.get(key) == current[key] for key in _PERIOD), "observation change differs from its analytics record or period.")
            _require(change.get("formula") == record.get("calculation") and bool(change.get("formula")),
                     "observation change formula differs from its analytics record.")
            direction = "increase" if record["value"] > 0 else "decrease" if record["value"] < 0 else "unchanged"
            _require(change.get("direction") == direction, "observation change direction contradicts its value.")
            refs.extend(change["dependencies"])
        _require(set(observation["source_ids"]) == set(refs) and len(observation["source_ids"]) == len(set(refs)),
                 "observation raw sources do not cover its comparisons and changes.")
        periods = {period["fiscal_year"]: period for period in (prior, current)}
        for source_id in observation["source_ids"]:
            record = financial(source_id)
            period = periods.get(record["fiscal_year"])
            _require(period is not None and record.get("unit") == "USD", "raw dependency has an incompatible period or unit.")
            expected_start = None if record["metric"] in _INSTANTS else period["period_start"]
            _require(record.get("period_start") == expected_start and record.get("period_end") == period["period_end"],
                     "raw dependency dates disagree with observation periods.")
        for year, period in periods.items():
            fcf = calculated.get(f"{year}:analytics.free_cash_flow")
            if fcf is None or fcf.get("value") is None:
                continue  # Missing data remains unavailable, never zero-filled.
            ocf_id, capex_id = f"{year}:operating_cash_flow", f"{year}:capital_expenditure"
            ocf, capex = financial(ocf_id), financial(capex_id)
            _require(capex["value"] >= 0, "cash PP&E violates the positive-outflow convention.")
            _require(all(row.get("unit") == "USD" and all(row.get(key) == period[key] for key in _PERIOD)
                         for row in (ocf, capex, fcf)), "cash-flow identity mixes units or fiscal periods.")
            _require(fcf.get("input_ids") == [ocf_id, capex_id]
                     and fcf.get("dependencies") == [ocf_id, capex_id]
                     and fcf.get("calculation") == "operating_cash_flow - cash_PP&E_purchases"
                     and _same_number(fcf.get("value"), ocf["value"] - capex["value"]),
                     "free cash flow does not reconcile with operating cash flow less cash PP&E.")
            extracted = evidence.get(f"{year}:free_cash_flow")
            if extracted is not None:
                _require(extracted.get("kind") == "financial" and extracted.get("unit") == "USD"
                         and _same_number(extracted.get("value"), fcf["value"])
                         and all(extracted.get(key) == period[key] for key in _PERIOD),
                         "displayed free cash flow conflicts with the reconciled cash-flow identity.")
