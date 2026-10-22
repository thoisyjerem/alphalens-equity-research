"""Reproduce Windows cache boundary failures without any SEC HTTP request."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from alphalens.sec import SecClient, SecError


URL = "https://data.sec.gov/submissions/CIK0000789019.json"
UA = "Research Test researcher@university.ac.uk"
STAMP = "2026-10-17T10:00:00+00:00"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(SecClient, "_last_request", 0)
    response = Mock(status_code=200, headers={})
    response.json.return_value = {"cik": 789019, "revision": "new"}
    return SecClient(UA, tmp_path, session=Mock(get=Mock(return_value=response)),
                     sleep=Mock(), clock=lambda: 100)


def cache_path(client):
    return client.cache_dir / (hashlib.sha256((URL + "json").encode()).hexdigest() + ".json")


def seed_cache(client):
    path = cache_path(client)
    payload = {"url": URL, "fetched_at": STAMP, "body": {"revision": "old"}}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path, path.read_bytes()


def test_zero_ttl_disables_even_an_exactly_zero_age_cache(client, monkeypatch):
    seed_cache(client)
    # This is the exact prior intermittent boundary, independent of clock
    # resolution: cached age and configured TTL are both exactly zero.
    monkeypatch.setattr("alphalens.sec.time.time", lambda: datetime.fromisoformat(STAMP).timestamp())
    client.ttl_seconds = 0
    assert client.get_json(URL)["revision"] == "new"
    assert client.session.get.call_count == 1
    assert client.records[-1]["cached"] is False


def test_positive_ttl_still_accepts_exactly_zero_age_cache(client, monkeypatch):
    seed_cache(client)
    monkeypatch.setattr("alphalens.sec.time.time", lambda: datetime.fromisoformat(STAMP).timestamp())
    assert client.get_json(URL) == {"revision": "old"}
    client.session.get.assert_not_called()
    assert client.records[-1]["cached"] is True


def test_transient_windows_replace_denial_retries_disk_only(client, monkeypatch):
    path, _ = seed_cache(client)
    original = Path.replace
    attempts = []
    def replace(source, target):
        if target == path:
            attempts.append(source)
            if len(attempts) == 1:
                raise PermissionError(5, "Simulated Windows sharing violation")
        return original(source, target)
    monkeypatch.setattr(Path, "replace", replace)
    assert client.get_json(URL, refresh=True)["revision"] == "new"
    # Windows may deny the real second replacement transiently too. The
    # behavior under test is bounded disk-only retries and a correct final
    # cache, not an assumption that the filesystem cannot add another denial.
    assert 2 <= len(attempts) <= 3
    assert client.session.get.call_count == 1
    assert client.sleep.call_args_list[0].args == (0.025,)
    assert client.records[-1]["cached"] is False
    assert json.loads(path.read_text(encoding="utf-8"))["body"]["revision"] == "new"
    assert not list(client.cache_dir.glob("*.tmp"))


def test_persistent_replace_denial_keeps_old_cache_and_reports_failure(client, monkeypatch):
    path, original_bytes = seed_cache(client)
    attempts = []
    def denied(source, target):
        assert target == path
        attempts.append(source)
        raise PermissionError(5, "Simulated persistent Windows sharing violation")
    monkeypatch.setattr(Path, "replace", denied)
    unrelated = client.cache_dir / "another-request.tmp"
    unrelated.write_text("must remain", encoding="utf-8")
    with pytest.raises(SecError, match="could not be cached"):
        client.get_json(URL, refresh=True)
    assert len(attempts) == 3
    assert [call.args[0] for call in client.sleep.call_args_list] == [0.025, 0.05]
    assert client.session.get.call_count == 1
    assert path.read_bytes() == original_bytes
    assert not client.records  # No successful cache/write record is fabricated.
    assert list(client.cache_dir.glob("*.tmp")) == [unrelated]


def test_other_disk_errors_do_not_retry_http_or_remove_old_entry(client, monkeypatch):
    path, original_bytes = seed_cache(client)
    replace = Mock(side_effect=OSError("Simulated filesystem error"))
    monkeypatch.setattr(Path, "replace", replace)
    with pytest.raises(SecError, match="write permissions"):
        client.get_json(URL, refresh=True)
    assert replace.call_count == 1
    assert client.session.get.call_count == 1
    client.sleep.assert_not_called()
    assert path.read_bytes() == original_bytes
    assert not list(client.cache_dir.glob("*.tmp"))


def test_each_cache_write_uses_its_own_unique_temporary_file(client, monkeypatch):
    original = Path.replace
    temporary_names = []
    def record(source, target):
        temporary_names.append(source.name)
        return original(source, target)
    monkeypatch.setattr(Path, "replace", record)
    client.get_json(URL, refresh=True)
    client.get_json(URL, refresh=True)
    assert len(set(temporary_names)) == 2
    assert all(name.endswith(".tmp") for name in temporary_names)
    assert client.session.get.call_count == 2
    assert not list(client.cache_dir.glob("*.tmp"))
