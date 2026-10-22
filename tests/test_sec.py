"""HTTP-boundary tests. Every response here is mocked; no SEC requests."""
import json
from unittest.mock import Mock

import pytest
import requests

from alphalens.sec import SecClient, SecError, validate_user_agent

UA = "Research Test researcher@university.ac.uk"
URL = "https://data.sec.gov/submissions/CIK0000789019.json"


def response(status=200, body=None, headers=None):
    item = Mock(status_code=status, headers=headers or {}, text="<html>Filing</html>")
    item.json.return_value = {"cik": 789019} if body is None else body
    return item


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(SecClient, "_last_request", 0)
    return SecClient(UA, tmp_path, session=Mock(), sleep=Mock(), clock=lambda: 100)


def test_exact_identified_header_timeout_and_encoding(client):
    client.session.get.return_value = response()
    assert client.get_json(URL)["cik"] == 789019
    args = client.session.get.call_args.kwargs
    assert args["headers"]["User-Agent"] == UA
    assert args["headers"]["Accept-Encoding"] == "gzip, deflate"
    assert args["timeout"] == (10, 40)
    assert args["allow_redirects"] is False


@pytest.mark.parametrize("bad", ["", "researcher", "Test a@example.com", "a@valid.ac.uk", "Name a@valid.ac.uk\nX: y"])
def test_missing_or_placeholder_contact_rejected(bad):
    with pytest.raises(ValueError):
        validate_user_agent(bad)


def test_cache_does_not_repeat_http(client):
    client.session.get.return_value = response()
    assert client.get_json(URL) == client.get_json(URL)
    assert client.session.get.call_count == 1
    assert client.records[-1]["cached"] is True


def test_expired_cache_fetches_again(client):
    client.session.get.return_value = response()
    client.get_json(URL)
    client.ttl_seconds = 0
    client.get_json(URL)
    assert client.session.get.call_count == 2


def test_corrupt_cache_is_refetched(client):
    client.session.get.return_value = response()
    client.get_json(URL)
    next(client.cache_dir.glob("*.json")).write_text("broken", encoding="utf-8")
    client.get_json(URL)
    assert client.session.get.call_count == 2


def test_forbidden_is_not_retried_or_cached(client):
    client.session.get.return_value = response(403)
    with pytest.raises(SecError, match="403"):
        client.get_json(URL)
    assert client.session.get.call_count == 1
    assert not list(client.cache_dir.glob("*.json"))


@pytest.mark.parametrize("status", [429, 500, 503])
def test_retry_success_and_backoff(client, status):
    client.session.get.side_effect = [response(status), response(status), response()]
    assert client.get_json(URL)["cik"] == 789019
    assert client.session.get.call_count == 3
    delays = [call.args[0] for call in client.sleep.call_args_list]
    assert 1 in delays and 2 in delays


def test_retry_after_respected_bounded(client):
    client.session.get.side_effect = [response(429, headers={"Retry-After": "15"}), response()]
    client.get_json(URL)
    assert any(c.args[0] == 15 for c in client.sleep.call_args_list)


def test_long_retry_after_stops_instead_of_retrying_early(client):
    client.session.get.return_value = response(429, headers={"Retry-After": "90"})
    with pytest.raises(SecError, match="longer retry delay"):
        client.get_json(URL)
    assert client.session.get.call_count == 1


def test_persistent_server_error_stops(client):
    client.session.get.return_value = response(503)
    with pytest.raises(SecError, match="503"):
        client.get_json(URL)
    assert client.session.get.call_count == 3


def test_timeout_has_actionable_error(client):
    client.session.get.side_effect = requests.Timeout("test timeout")
    with pytest.raises(SecError, match="connection failed"):
        client.get_json(URL)
    assert client.session.get.call_count == 3


@pytest.mark.parametrize("status", [301, 404])
def test_other_status_is_clear(client, status):
    client.session.get.return_value = response(status)
    with pytest.raises(SecError, match=str(status)):
        client.get_json(URL)


def test_non_json_error_not_cached(client):
    client.session.get.return_value = response()
    client.session.get.return_value.json.side_effect = ValueError("html")
    with pytest.raises(SecError, match="invalid JSON"):
        client.get_json(URL)


def test_conservative_request_spacing(client):
    client.session.get.return_value = response()
    client.get_json(URL, refresh=True)
    client.get_json(URL, refresh=True)
    assert any(c.args[0] == .5 for c in client.sleep.call_args_list)


@pytest.mark.parametrize("url", ["http://data.sec.gov/x", "https://attacker.test/x", "https://data.sec.gov.attacker.test/x"])
def test_only_official_https_hosts(client, url):
    with pytest.raises(ValueError):
        client.get_json(url)
    client.session.get.assert_not_called()


def test_cik_padding_and_validation():
    assert SecClient.padded_cik(789019) == "0000789019"
    for bad in [0, -1, "x", "12345678901", "../x"]:
        with pytest.raises(ValueError):
            SecClient.padded_cik(bad)


def test_text_filing_cache(client):
    client.session.get.return_value = response()
    assert client.get_text(URL) == "<html>Filing</html>"
    assert client.get_text(URL) == "<html>Filing</html>"
    assert client.session.get.call_count == 1
