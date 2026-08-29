"""Shared fixtures. No network access is used anywhere in this suite."""
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"status {self.status_code}",
                request=httpx.Request("GET", "https://example.test"),
                response=httpx.Response(self.status_code),
            )


class FakeClient:
    """Stands in for httpx.AsyncClient as an async context manager."""

    def __init__(self, payload, status_code=200):
        self._payload = payload
        self._status = status_code
        self.requested_urls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, **kwargs):
        self.requested_urls.append(url)
        return FakeResponse(self._payload, self._status)


@pytest.fixture
def patch_client(monkeypatch):
    """Swap get_client() in a tools module for one returning a canned payload."""

    def _patch(module, payload, status_code=200):
        client = FakeClient(payload, status_code)
        monkeypatch.setattr(module, "get_client", lambda: client)
        return client

    return _patch


@pytest.fixture
def company_tickers():
    return {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "1": {"cik_str": 789019, "ticker": "MSFT", "title": "MICROSOFT CORP"},
        "2": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
    }


@pytest.fixture
def apple_submissions():
    return {
        "name": "Apple Inc.",
        "filings": {
            "recent": {
                "form": ["10-K", "8-K", "10-Q", "10-K"],
                "filingDate": ["2025-11-01", "2025-10-30", "2025-08-01", "2024-11-01"],
                "accessionNumber": [
                    "0000320193-25-000123",
                    "0000320193-25-000119",
                    "0000320193-25-000081",
                    "0000320193-24-000123",
                ],
            }
        },
    }


def loads(raw):
    """Tool impls return JSON strings; this unwraps them for assertions."""
    return json.loads(raw)
