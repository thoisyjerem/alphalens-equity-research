"""Opt-in FRED observations, kept separate from company/SEC financial facts.

No HTTP request occurs until ``refresh=True`` is explicitly passed. Each series
uses its own CSV request: FRED may return ZIP content for multiple series IDs.
Macro levels are context, not evidence of a company's exposure or causality.
"""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta, timezone
import io
import json
import math
from pathlib import Path
import re

import requests
from requests.adapters import HTTPAdapter


DATA_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
SERIES = {
    "DGS10": {"label": "US ten-year Treasury constant-maturity yield",
        "frequency": "daily", "unit": "percent; not seasonally adjusted",
        "publisher": "Federal Reserve Board via FRED", "change_unit": "percentage_points"},
    "DTWEXBGS": {"label": "Nominal broad US dollar index",
        "frequency": "daily", "unit": "index, January 2006 = 100; not seasonally adjusted",
        "publisher": "Federal Reserve Board via FRED", "change_unit": "percent"},
    "INDPRO": {"label": "US industrial production index",
        "frequency": "monthly", "unit": "index, 2017 = 100; seasonally adjusted",
        "publisher": "Federal Reserve Board via FRED", "change_unit": "percent"},
}


def _date(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Invalid observation date.")
    return date.fromisoformat(value)


def _parse_csv(text, series_id):
    """Validate the complete payload before selecting observations or caching it."""
    if not isinstance(text, str):
        raise ValueError("Macro CSV payload is not text.")
    reader = csv.reader(io.StringIO(text.removeprefix("\ufeff")), strict=True)
    try:
        if next(reader, None) != ["observation_date", series_id]:
            raise ValueError("Macro CSV header does not match the requested series.")
        rows, seen, monthly_buckets = [], set(), set()
        for row in reader:
            if not row:  # Empty physical lines are not observations.
                continue
            if len(row) != 2:
                raise ValueError("Macro CSV must contain exactly two columns.")
            observed = _date(row[0])
            if series_id == "INDPRO":
                bucket = (observed.year, observed.month)
                if observed.day != 1 or bucket in monthly_buckets:
                    raise ValueError("Monthly macro observations require unique first-of-month dates.")
                monthly_buckets.add(bucket)
            if observed in seen:
                raise ValueError("Macro CSV contains duplicate observation dates.")
            seen.add(observed)
            raw = row[1].strip()
            if raw in {"", "."}:
                rows.append((observed, None))
                continue
            try:
                value = float(raw)
            except ValueError:
                raise ValueError("Macro CSV contains a non-numeric observation.") from None
            if not math.isfinite(value) or (series_id != "DGS10" and value < 0):
                raise ValueError("Macro CSV contains a non-finite or invalid index observation.")
            rows.append((observed, value))
        if not rows:
            raise ValueError("Macro CSV contains no observation rows.")
        return sorted(rows)
    except csv.Error:
        raise ValueError("Macro CSV is malformed.") from None


def _base(series_id):
    return {"series_id": series_id, "source_id": None, **SERIES[series_id],
        "source_url": f"https://fred.stlouisfed.org/series/{series_id}", "data_url": DATA_URL,
        "observation_date": None, "value": None, "comparison_date": None,
        "comparison_value": None, "change": None,
        "change_formula": "current - comparison" if series_id == "DGS10" else "(current - comparison) / comparison * 100",
        "status": "unavailable", "warnings": [], "reason": "No cached macro observations. Refresh explicitly to retrieve public FRED data.",
        "retrieved_at": None, "data_mode": "unavailable"}


def _summarize(series_id, rows, as_of):
    record = _base(series_id)
    if any(day > as_of for day, _ in rows):
        record["warnings"].append("Observations after the requested as-of date were excluded; no future observation was used.")
    available = [(day, value) for day, value in rows if day <= as_of and value is not None]
    if not available:
        record["reason"] = "No finite observation is available on or before the as-of date; missing values are not zero."
        return record
    latest, value = available[-1]
    record.update(source_id=f"macro:{series_id}:{latest.isoformat()}", observation_date=latest.isoformat(),
        value=value, status="available", reason="")
    max_age = 75 if SERIES[series_id]["frequency"] == "monthly" else 14
    if (as_of - latest).days > max_age:
        record.update(status="stale", reason="Historical observation only; too old for a current macro assessment.")
        record["warnings"].append(f"Latest observation is more than {max_age} calendar days before the as-of date.")
    if SERIES[series_id]["frequency"] == "monthly":
        comparable = [(day, item) for day, item in available if day.year == latest.year - 1 and day.month == latest.month]
        label = "Same calendar month in the previous year"
    else:
        target = latest - timedelta(days=365)
        comparable = [(day, item) for day, item in available if target - timedelta(days=10) <= day <= target]
        label = "On or before the latest observation minus three hundred sixty-five days, within ten calendar days"
    record["comparison_rule"] = label
    if not comparable:
        record["warnings"].append("A valid annual comparison observation is unavailable; annual change is N/A.")
        return record
    previous_date, previous_value = comparable[-1]
    record.update(comparison_date=previous_date.isoformat(), comparison_value=previous_value)
    if series_id != "DGS10" and previous_value <= 0:
        record["warnings"].append("Annual percentage change requires a positive comparison base; change is N/A.")
        return record
    change = value - previous_value if series_id == "DGS10" else (value - previous_value) / previous_value * 100
    if math.isfinite(change):
        record["change"] = change
    else:
        record["warnings"].append("Calculated annual change is not finite; change is N/A.")
    return record


def _cache_read(path, series_id):
    item = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(item, dict) or item.get("version") != 1 or item.get("url") != DATA_URL
            or item.get("params", {}).get("id") != series_id):
        raise ValueError("Macro cache metadata does not match the requested source.")
    params = item["params"]
    if set(params) != {"id", "cosd", "coed"} or _date(params["cosd"]) > _date(params["coed"]):
        raise ValueError("Macro cache request dates are invalid.")
    retrieved = item.get("retrieved_at")
    if not isinstance(retrieved, str):
        raise ValueError("Macro cache lacks its retrieval timestamp.")
    timestamp = datetime.fromisoformat(retrieved.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("Macro cache retrieval timestamp lacks a timezone.")
    return item, _parse_csv(item.get("csv"), series_id)


def load_macro_snapshot(cache_dir=".cache/macro", refresh=False, as_of=None, session=None):
    """Read the disk snapshot, or explicitly request each of three FRED CSVs once.

    Cache age never initiates HTTP. Refresh failures may retain explicitly
    labelled cached records, with errors disclosed. No model, API key, provider
    fallback or automatic retry is involved. Revised macro history is not a
    point-in-time historical-vintage dataset.
    """
    as_of = date.today() if as_of is None else as_of
    if not isinstance(as_of, date) or isinstance(as_of, datetime):
        raise ValueError("Macro as_of must be a calendar date.")
    if not isinstance(refresh, bool):
        raise ValueError("Macro refresh must be explicit true or false.")
    root = Path(cache_dir)
    owned_session = None
    if refresh and session is None:
        owned_session = requests.Session()
        owned_session.mount("https://", HTTPAdapter(max_retries=0))
        session = owned_session
    records, errors = [], []
    try:
        for series_id in SERIES:
            path = root / f"{series_id}.json"
            cached = None
            cache_error = None
            try:
                cached = _cache_read(path, series_id)
            except FileNotFoundError:
                pass
            except (OSError, ValueError, TypeError, KeyError, AttributeError):
                cache_error = f"{series_id}: cached macro data is invalid and was not used."
            item_rows, mode = cached, "cached" if cached else "unavailable"
            refresh_error = None
            if refresh:
                # Include the prior-year month even when the newest monthly
                # observation lags the as-of date by the permitted seventy-five days.
                params = {"id": series_id, "cosd": (as_of - timedelta(days=460)).isoformat(), "coed": as_of.isoformat()}
                response = None
                try:
                    response = session.get(DATA_URL, params=params, timeout=(5, 15), allow_redirects=False,
                        headers={"Accept": "text/csv"})
                    if response.status_code != 200:
                        raise ValueError(f"HTTP {response.status_code}; no retry was made.")
                    raw = response.text
                    rows = _parse_csv(raw, series_id)
                    item = {"version": 1, "url": DATA_URL, "params": params,
                        "retrieved_at": datetime.now(timezone.utc).isoformat(), "csv": raw}
                    item_rows, mode = (item, rows), "live"
                    try:
                        root.mkdir(parents=True, exist_ok=True)
                        temporary = path.with_suffix(".tmp")
                        temporary.write_text(json.dumps(item, ensure_ascii=False, allow_nan=False), encoding="utf-8")
                        temporary.replace(path)
                    except OSError:
                        errors.append(f"{series_id}: live response validated but could not be cached.")
                except requests.RequestException:
                    refresh_error = f"{series_id}: FRED request failed or timed out; no retry was made."
                except (ValueError, TypeError):
                    refresh_error = (f"{series_id}: FRED returned HTTP {response.status_code}; no retry was made."
                        if response is not None and response.status_code != 200 else
                        f"{series_id}: FRED returned invalid CSV; no retry was made.")
            record = _summarize(series_id, item_rows[1], as_of) if item_rows else _base(series_id)
            record["data_mode"] = mode
            if item_rows:
                record["retrieved_at"] = item_rows[0]["retrieved_at"]
            for error in (cache_error, refresh_error):
                if error:
                    errors.append(error)
                    record["warnings"].append(error)
            if refresh_error and cached:
                record["warnings"].append("Refresh failed. The displayed observations are from the existing cache, not the attempted live request.")
            if not item_rows and (cache_error or refresh_error):
                record["reason"] = "No validated macro observations are available; review the reported cache or request error."
            records.append(record)
    finally:
        if owned_session is not None:
            owned_session.close()
    usable = [row for row in records if row["value"] is not None]
    modes = {row["data_mode"] for row in usable}
    mode = "unavailable" if not usable else "cached" if "cached" in modes else "live"
    return {"as_of": as_of.isoformat(), "retrieved_at": max((row["retrieved_at"] for row in records if row["retrieved_at"]), default=None),
        "mode": mode, "series": records, "errors": errors,
        "limitations": ["Macro observations are external context, separate from SEC financial facts and company fiscal years.",
            "The as-of cutoff excludes later observation dates but does not recreate historical release vintages; FRED history may be revised.",
            "Observation date is not release date. Data may be published after the measured period.",
            "A macro movement does not establish company exposure, historical causality, a forecast, WACC or valuation.",
            "Daily annual comparisons use a prior observation on or before the anniversary within ten days; monthly comparisons use the same month one year earlier.",
            "Missing or stale observations never become zero or a current assessment. Refresh is manual; no API key, AI call or paid fallback is used."]}
