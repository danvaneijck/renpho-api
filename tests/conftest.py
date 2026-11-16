"""Shared test configuration."""

import pytest
import requests


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Fail any test that would make a real HTTP request.

    Tests mock ``RenphoClient._post`` or the session; a request that gets past
    those mocks would otherwise reach the live Renpho API.
    """

    def refuse(self, request, *args, **kwargs):
        raise RuntimeError(f"Network access in tests: {request.method} {request.url}")

    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", refuse)
