"""Tests for renpho.constants — sanity checks on configuration."""

from renpho.constants import (
    API_BASE_URL,
    BODY_WEIGHT_SCALES,
    ENCRYPTION_KEY,
    ENDPOINTS,
    GIRTH_METRICS,
    METRICS,
)


def test_encryption_key_length():
    assert len(ENCRYPTION_KEY) == 16  # AES-128 requires 16-byte key


def test_api_base_url_is_https():
    assert API_BASE_URL.startswith("https://")


def test_endpoints_all_present():
    required = {
        "login",
        "token_time",
        "device_info",
        "family",
        "measurements",
        "body_composition_measurements",
        "girth_measurements",
    }
    assert required.issubset(ENDPOINTS.keys())


def test_body_weight_scales_nonempty():
    assert len(BODY_WEIGHT_SCALES) > 0


def test_metrics_structure():
    for key, label, unit in METRICS:
        assert isinstance(key, str)
        assert isinstance(label, str)
        assert isinstance(unit, str)


def test_girth_metrics_structure():
    assert len(GIRTH_METRICS) > 0
    for key, label, unit in GIRTH_METRICS:
        assert isinstance(key, str)
        assert isinstance(label, str)
        assert isinstance(unit, str)
