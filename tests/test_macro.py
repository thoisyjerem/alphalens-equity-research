"""FRED boundary and financial-convention regressions; all HTTP is mocked."""
from datetime import date
import json
from unittest.mock import Mock

import pytest
import requests

from alphalens.macro import DATA_URL, SERIES, load_macro_snapshot


AS_OF = date(2026, 10, 18)


def csv_for(series, prior=100, current=110):
    dates = ("2025-09-01", "2026-09-01") if series == "INDPRO" else ("2025-10-16", "2026-10-16")
    return f"observation_date,{series}\n{dates[0]},{prior}\n{dates[1]},{current}\n"


def session_for(transform=None):
    session = Mock()
    def get(url, **kwargs):
        series = kwargs["params"]["id"]
        text = transform(series) if transform else csv_for(series)
        return Mock(status_code=200, text=text)
    session.get.side_effect = get
    return session


def row(snapshot, series):
    return next(item for item in snapshot["series"] if item["series_id"] == series)


def test_empty_cache_never_fetches_or_creates_files(tmp_path):
    session = Mock()
    output = load_macro_snapshot(tmp_path, as_of=AS_OF, session=session)
    session.get.assert_not_called()
    assert output["mode"] == "unavailable"
    assert all(item["value"] is None and item["status"] == "unavailable" for item in output["series"])
    assert list(tmp_path.iterdir()) == []


def test_refresh_is_one_single_series_request_each_then_cache_only(tmp_path):
    session = session_for()
    first = load_macro_snapshot(tmp_path, refresh=True, as_of=AS_OF, session=session)
    assert first["mode"] == "live" and session.get.call_count == 3
    for call, series in zip(session.get.call_args_list, SERIES):
        assert call.args == (DATA_URL,)
        assert call.kwargs["params"] == {"id": series, "cosd": "2025-07-15", "coed": "2026-10-18"}
        assert call.kwargs["timeout"] == (5, 15) and call.kwargs["allow_redirects"] is False
        saved = json.loads((tmp_path / f"{series}.json").read_text())
        assert saved["csv"] == csv_for(series) and saved["retrieved_at"]
    second = load_macro_snapshot(tmp_path, as_of=AS_OF, session=session)
    assert session.get.call_count == 3 and second["mode"] == "cached"
    assert second["series"][0]["source_id"] == "macro:DGS10:2026-10-16"


def test_units_and_comparison_dates_are_economically_distinct(tmp_path):
    session = session_for(lambda series: csv_for(series, 4, 5) if series == "DGS10" else csv_for(series))
    output = load_macro_snapshot(tmp_path, refresh=True, as_of=AS_OF, session=session)
    yield_row, dollar, production = [row(output, name) for name in SERIES]
    assert yield_row["change"] == 1 and yield_row["change_unit"] == "percentage_points"
    assert dollar["change"] == pytest.approx(10) and dollar["change_unit"] == "percent"
    assert production["change"] == pytest.approx(10)
    assert yield_row["comparison_date"] == "2025-10-16"
    assert production["comparison_date"] == "2025-09-01"
    assert "seasonally adjusted" in production["unit"]


@pytest.mark.parametrize("payload", [
    "DATE,DGS10\n2026-10-16,4\n", "observation_date,OTHER\n2026-10-16,4\n",
    "observation_date,DGS10,extra\n2026-10-16,4,5\n",
    "observation_date,DGS10\n2026-10-16,4,5\n",
    "observation_date,DGS10\n2026-10-16,4\n2026-10-16,.\n",
    "observation_date,DGS10\n2026-02-30,4\n",
    "observation_date,DGS10\n20261016,4\n",
    "observation_date,DGS10\n2026-10-16,NaN\n",
    "observation_date,DGS10\n2026-10-16,inf\n",
    "observation_date,DGS10\n2026-10-16,not-a-number\n",
    "PK\x03\x04compressed multi-series zip", "observation_date,DGS10\n",
])
def test_bad_payload_rejected_without_cache_or_retry(tmp_path, payload):
    session = session_for(lambda series: payload if series == "DGS10" else csv_for(series))
    output = load_macro_snapshot(tmp_path, refresh=True, as_of=AS_OF, session=session)
    assert row(output, "DGS10")["status"] == "unavailable"
    assert not (tmp_path / "DGS10.json").exists()
    assert session.get.call_count == 3 and output["errors"]


def test_missing_values_are_not_zero_and_future_rows_excluded(tmp_path):
    payload = "observation_date,DGS10\n2025-10-15,4\n2026-10-15,5\n2026-10-16,.\n2026-10-17,\n2026-10-19,8\n"
    output = load_macro_snapshot(tmp_path, refresh=True, as_of=AS_OF,
        session=session_for(lambda name: payload if name == "DGS10" else csv_for(name)))
    item = row(output, "DGS10")
    assert item["value"] == 5 and item["observation_date"] == "2026-10-15"
    assert item["comparison_date"] == "2025-10-15" and item["change"] == 1
    assert any("after" in warning for warning in item["warnings"])


def test_daily_annual_comparison_never_uses_after_anniversary_or_outside_window(tmp_path):
    payload = "observation_date,DGS10\n2025-10-05,3\n2025-10-17,4\n2026-10-16,5\n"
    output = load_macro_snapshot(tmp_path, refresh=True, as_of=AS_OF,
        session=session_for(lambda name: payload if name == "DGS10" else csv_for(name)))
    item = row(output, "DGS10")
    assert item["comparison_date"] is None and item["change"] is None


def test_monthly_comparison_requires_same_month_not_nearest_date(tmp_path):
    payload = "observation_date,INDPRO\n2025-08-01,90\n2025-10-01,100\n2026-09-01,110\n"
    output = load_macro_snapshot(tmp_path, refresh=True, as_of=AS_OF,
        session=session_for(lambda name: payload if name == "INDPRO" else csv_for(name)))
    assert row(output, "INDPRO")["change"] is None


@pytest.mark.parametrize("dates", [("2026-09-15",), ("2026-09-01", "2026-09-01"), ("2026-09-01", "2026-09-15")])
def test_monthly_period_labels_require_unique_first_of_month(tmp_path, dates):
    payload = "observation_date,INDPRO\n" + "".join(f"{observed},110\n" for observed in dates)
    output = load_macro_snapshot(tmp_path, refresh=True, as_of=AS_OF,
        session=session_for(lambda name: payload if name == "INDPRO" else csv_for(name)))
    assert row(output, "INDPRO")["status"] == "unavailable"
    assert not (tmp_path / "INDPRO.json").exists()


@pytest.mark.parametrize("series,age,status", [("DGS10", 14, "available"), ("DGS10", 15, "stale"),
    ("INDPRO", 75, "available"), ("INDPRO", 76, "stale")])
def test_stale_boundaries_preserve_historical_values(tmp_path, series, age, status):
    from datetime import timedelta
    # INDPRO monthly labels are always the first day; shift as-of to test the
    # exact staleness boundary without inventing a daily observation in a month.
    observed = date(2026, 8, 1) if series == "INDPRO" else AS_OF - timedelta(days=age)
    as_of = observed + timedelta(days=age)
    payload = f"observation_date,{series}\n{observed.isoformat()},100\n"
    output = load_macro_snapshot(tmp_path, refresh=True, as_of=as_of,
        session=session_for(lambda name: payload if name == series else csv_for(name)))
    item = row(output, series)
    assert item["status"] == status and item["value"] == 100
    if status == "stale":
        assert "current" in item["reason"]


def test_negative_yields_valid_negative_index_rejected_and_zero_base_abstains(tmp_path):
    payloads = {"DGS10": csv_for("DGS10", -1, -0.5), "DTWEXBGS": csv_for("DTWEXBGS", 0, 100),
        "INDPRO": csv_for("INDPRO", 100, -1)}
    output = load_macro_snapshot(tmp_path, refresh=True, as_of=AS_OF, session=session_for(payloads.get))
    assert row(output, "DGS10")["change"] == 0.5
    assert row(output, "DTWEXBGS")["comparison_value"] == 0
    assert row(output, "DTWEXBGS")["change"] is None
    assert row(output, "INDPRO")["value"] is None


def test_refresh_failure_is_explicit_cached_data_not_fresh_success(tmp_path):
    load_macro_snapshot(tmp_path, refresh=True, as_of=AS_OF, session=session_for())
    failing = Mock()
    failing.get.side_effect = requests.Timeout("never expose exception data")
    output = load_macro_snapshot(tmp_path, refresh=True, as_of=AS_OF, session=failing)
    assert output["mode"] == "cached" and len(output["errors"]) == 3 and failing.get.call_count == 3
    assert all(item["data_mode"] == "cached" and item["value"] is not None for item in output["series"])
    assert all(any("Refresh failed" in warning for warning in item["warnings"]) for item in output["series"])
    assert "never expose" not in json.dumps(output)


@pytest.mark.parametrize("status", [301, 403, 429, 500])
def test_http_failures_no_retry_or_automatic_provider_fallback(tmp_path, status):
    session = Mock()
    session.get.return_value = Mock(status_code=status, text="private error body")
    output = load_macro_snapshot(tmp_path, refresh=True, as_of=AS_OF, session=session)
    assert output["mode"] == "unavailable" and session.get.call_count == 3
    assert "private error body" not in json.dumps(output)
    assert all(f"HTTP {status}" in error for error in output["errors"])


@pytest.mark.parametrize("corrupt", ["not JSON", '{"version":1}', None])
def test_corrupt_cache_is_unavailable_without_contacting_network(tmp_path, corrupt):
    load_macro_snapshot(tmp_path, refresh=True, as_of=AS_OF, session=session_for())
    path = tmp_path / "DGS10.json"
    if corrupt is None:
        item = json.loads(path.read_text())
        item["csv"] = csv_for("OTHER")
        corrupt = json.dumps(item)
    path.write_text(corrupt)
    session = Mock()
    output = load_macro_snapshot(tmp_path, as_of=AS_OF, session=session)
    session.get.assert_not_called()
    assert row(output, "DGS10")["status"] == "unavailable" and output["errors"]


def test_asof_does_not_claim_point_in_time_vintage_and_no_auto_refresh(tmp_path):
    load_macro_snapshot(tmp_path, refresh=True, as_of=AS_OF, session=session_for())
    session = Mock()
    output = load_macro_snapshot(tmp_path, as_of=date(2027, 10, 18), session=session)
    session.get.assert_not_called()
    assert all(item["status"] == "stale" for item in output["series"])
    assert any("vintages" in item for item in output["limitations"])


def test_all_missing_is_unavailable_and_serializable(tmp_path):
    output = load_macro_snapshot(tmp_path, refresh=True, as_of=AS_OF,
        session=session_for(lambda name: f"observation_date,{name}\n{'2026-10-01' if name == 'INDPRO' else '2026-10-16'},.\n"))
    assert output["mode"] == "unavailable"
    assert all(item["source_id"] is None and item["value"] is None for item in output["series"])
    json.dumps(output, allow_nan=False)
