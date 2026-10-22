"""Small, identified SEC client. Never changes identity to evade a refusal."""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import requests


class SecError(RuntimeError):
    """A user-actionable SEC access or response error."""


def validate_user_agent(value: str) -> str:
    value = value.strip()
    match = re.search(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})", value)
    if not match or len(value.split()) < 2 or '\n' in value or '\r' in value:
        raise ValueError("Set SEC_USER_AGENT to your name/organisation and legitimate contact email.")
    domain = match.group(1).lower()
    if domain in {"example.com", "example.org", "example.net", "domain.com", "test.com"} or domain.endswith(".invalid"):
        raise ValueError("Replace the example SEC contact email with your legitimate contact email.")
    return value


class SecClient:
    _lock = threading.Lock()
    _last_request = 0.0

    def __init__(self, user_agent: str, cache_dir: str | Path = ".cache/sec", ttl_hours: float = 24,
                 session=None, sleep=time.sleep, clock=time.monotonic):
        self.user_agent = validate_user_agent(user_agent)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = max(0, float(ttl_hours)) * 3600
        self.session = session or requests.Session()
        self.sleep = sleep
        self.clock = clock
        self.records: list[dict] = []

    def _throttle(self):
        # Shared by all client instances and Streamlit sessions in this process.
        with self._lock:
            delay = max(0.0, 0.5 - (self.clock() - SecClient._last_request))
            if delay:
                self.sleep(delay)
            SecClient._last_request = self.clock()

    def _get(self, url: str, kind: str, refresh: bool = False):
        parts = urlparse(url)
        if parts.scheme != "https" or parts.hostname not in {"www.sec.gov", "data.sec.gov"} or parts.username:
            raise ValueError("Only official HTTPS SEC URLs are allowed.")
        key = hashlib.sha256((url + kind).encode()).hexdigest()
        path = self.cache_dir / f"{key}.json"
        # A zero TTL explicitly disables cache reads, even when a coarse system
        # clock reports an exactly zero age immediately after a write.
        if self.ttl_seconds > 0 and path.exists() and not refresh:
            try:
                cached = json.loads(path.read_text(encoding="utf-8"))
                age = time.time() - datetime.fromisoformat(cached["fetched_at"]).timestamp()
                if cached["url"] == url and 0 <= age <= self.ttl_seconds:
                    body = cached["body"]
                    if (kind == "json" and isinstance(body, dict)) or (kind == "text" and isinstance(body, str)):
                        self.records.append({"url": url, "fetched_at": cached["fetched_at"], "cached": True})
                        return body
            except (ValueError, KeyError, TypeError, OSError):
                pass
        for attempt in range(3):
            self._throttle()
            try:
                response = self.session.get(url, headers={"User-Agent": self.user_agent,
                    "Accept-Encoding": "gzip, deflate", "Accept": "application/json" if kind == "json" else "text/html"},
                    timeout=(10, 40), allow_redirects=False)
            except requests.RequestException as exc:
                if attempt < 2:
                    self.sleep(2 ** attempt)
                    continue
                raise SecError("SEC connection failed after three attempts. Check your connection or select Offline demonstration.") from exc
            status = response.status_code
            if status == 403:
                raise SecError("SEC returned HTTP 403. Verify your identified SEC_USER_AGENT and try later. No restriction bypass was attempted; offline mode is available.")
            if status == 429 or 500 <= status <= 599:
                if attempt < 2:
                    try:
                        retry_after = float(response.headers.get("Retry-After", 0))
                    except (ValueError, TypeError):
                        try:
                            retry_after = max(0, parsedate_to_datetime(response.headers["Retry-After"]).timestamp() - time.time())
                        except (KeyError, ValueError, TypeError, OverflowError):
                            retry_after = 0
                    if retry_after > 30:
                        raise SecError("SEC requested a longer retry delay. Wait before retrying or use Offline demonstration; the server's delay was not bypassed.")
                    self.sleep(max(2 ** attempt, retry_after))
                    continue
                raise SecError(f"SEC returned HTTP {status} after three attempts. Wait before retrying or use Offline demonstration.")
            if status != 200:
                raise SecError(f"SEC returned HTTP {status}; the requested official resource could not be loaded.")
            try:
                body = response.json() if kind == "json" else response.text
                if kind == "json" and not isinstance(body, dict):
                    raise ValueError("Expected a JSON object")
            except (ValueError, requests.exceptions.JSONDecodeError) as exc:
                raise SecError("SEC returned an invalid JSON response; no financial results were generated.") from exc
            stamp = datetime.now(timezone.utc).isoformat()
            payload = {"url": url, "fetched_at": stamp, "body": body}
            # Atomic replacement avoids partially written files on interrupted fetches.
            # A unique sibling prevents collisions between processes or nested
            # calls in the same thread. Windows scanners/readers may briefly
            # hold the destination open; retry only the local atomic replace.
            temporary = path.with_suffix(f".{uuid4().hex}.tmp")
            try:
                temporary.write_text(json.dumps(payload), encoding="utf-8")
                for cache_attempt in range(3):
                    try:
                        temporary.replace(path)
                        break
                    except PermissionError:
                        if cache_attempt == 2:
                            raise
                        self.sleep(0.025 * (2 ** cache_attempt))
            except OSError as exc:
                raise SecError("The SEC response could not be cached. Check project folder write permissions.") from exc
            finally:
                # Only this request's unique temporary file is eligible for
                # cleanup; a previous valid cache entry is never removed.
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
            self.records.append({"url": url, "fetched_at": stamp, "cached": False})
            return body

    def get_json(self, url: str, refresh: bool = False) -> dict:
        return self._get(url, "json", refresh)

    def get_text(self, url: str, refresh: bool = False) -> str:
        return self._get(url, "text", refresh)

    def company_tickers(self) -> dict:
        return self.get_json("https://www.sec.gov/files/company_tickers.json")

    @staticmethod
    def padded_cik(cik: str | int) -> str:
        value = str(cik)
        if not value.isdigit() or not 1 <= len(value) <= 10 or int(value) <= 0:
            raise ValueError("CIK must be a positive identifier of at most ten digits.")
        return value.zfill(10)

    def submissions(self, cik: str | int) -> dict:
        return self.get_json(f"https://data.sec.gov/submissions/CIK{self.padded_cik(cik)}.json")

    def company_facts(self, cik: str | int) -> dict:
        return self.get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{self.padded_cik(cik)}.json")
