"""Tests for renpho.girth and the client girth methods.

All values here are synthetic placeholders, not real measurements.
"""

from unittest.mock import patch

from renpho.client import RenphoClient
from renpho.crypto import encrypt_request
from renpho.export import format_girth, format_timestamp
from renpho.girth import (
    build_girth_record,
    girth_date,
    normalize_girth,
)

# A synthetic raw girth record shaped like the API response.
SAMPLE_RECORD = {
    "userId": 1234567890,
    "mac": "AA:BB:CC:00:11:22",
    "scaleName": "R-Y002",
    "dataSource": "Health",
    "timeStamp": 1719500400,  # 2024-06-27 15:00 UTC
    "timeZone": "-5:00",
    "neckValue": 38.0,
    "shoulderValue": 0.0,  # not measured -> omitted
    "chestValue": 100.0,
    "waistValue": 90.0,
    "hipValue": 100.0,
    "abdomenValue": 0.0,
    "armValue": 0.0,  # single field stays 0 when bilateral is used
    "leftArmValue": 33.0,
    "rightArmValue": 33.5,
    "leftThighValue": 58.0,
    "rightThighValue": 58.5,
    "leftCalfValue": 38.0,
    "rightCalfValue": 38.2,
    "whrValue": 0.9,
}


class TestNormalizeGirth:
    def test_omits_zero_sites(self):
        result = normalize_girth(SAMPLE_RECORD)
        assert "shoulder" not in result
        assert "abdomen" not in result

    def test_keeps_measured_sites_in_cm(self):
        result = normalize_girth(SAMPLE_RECORD)
        assert result["waist"] == 90.0
        assert result["neck"] == 38.0

    def test_bilateral_sites(self):
        result = normalize_girth(SAMPLE_RECORD)
        assert result["left_arm"] == 33.0
        assert result["right_arm"] == 33.5
        # the overall armValue is 0 here, so it is omitted
        assert "arm" not in result

    def test_keeps_overall_sites_when_bilateral_unused(self):
        """A tape measure may record one overall value instead of left/right."""
        record = {
            "timeStamp": 1719500400,
            "timeZone": "+0:00",
            "armValue": 34.0,
            "thighValue": 58.0,
            "calfValue": 38.0,
            "leftArmValue": 0.0,
            "rightArmValue": 0.0,
        }
        result = normalize_girth(record)
        assert result["arm"] == 34.0
        assert result["thigh"] == 58.0
        assert result["calf"] == 38.0
        assert "left_arm" not in result

    def test_includes_whr_and_date(self):
        result = normalize_girth(SAMPLE_RECORD)
        assert result["whr"] == 0.9
        # -5:00 shifts 15:00 UTC to 10:00 local, same calendar day
        assert result["date"] == "2024-06-27"

    def test_empty_record(self):
        assert normalize_girth({}) == {}


class TestGirthDate:
    def test_utc(self):
        assert girth_date({"timeStamp": 1719500400, "timeZone": "+0:00"}) == "2024-06-27"

    def test_short_form_offset(self):
        # bare "-12" short form parses too: 15:00 UTC -> 03:00 local, same day
        assert girth_date({"timeStamp": 1719500400, "timeZone": "-12"}) == "2024-06-27"

    def test_missing_timestamp(self):
        assert girth_date({"timeZone": "-5:00"}) is None

    def test_garbage_timestamp(self):
        assert girth_date({"timeStamp": "not-a-number"}) is None


class TestBuildGirthRecord:
    def test_defaults_unmeasured_to_zero_strings(self):
        record = build_girth_record(
            {"waist": 90.0}, user_id=1234567890, timestamp=1719500400
        )
        assert record["waistValue"] == "90.0"
        assert record["neckValue"] == "0"
        assert record["neckUnit"] == "0"  # 0 = cm

    def test_values_are_strings(self):
        record = build_girth_record(
            {"left_arm": 33.0}, user_id=1234567890, timestamp=1719500400
        )
        assert isinstance(record["leftArmValue"], str)
        assert record["timeStamp"] == "1719500400"
        assert record["userId"] == "1234567890"

    def test_writes_overall_sites(self):
        record = build_girth_record(
            {"arm": 34.0, "thigh": 58.0, "calf": 38.0},
            user_id=1234567890,
            timestamp=1719500400,
        )
        assert record["armValue"] == "34.0"
        assert record["thighValue"] == "58.0"
        assert record["calfValue"] == "38.0"
        assert record["leftArmValue"] == "0"

    def test_ignores_unknown_site(self):
        record = build_girth_record(
            {"forearm": 30.0}, user_id=1234567890, timestamp=1719500400
        )
        # forearm has no Renpho field -> nothing populated, all defaults stay "0"
        assert all(
            record[field] == "0"
            for field in record
            if field.endswith("Value")
        )

    def test_ignores_non_positive(self):
        record = build_girth_record(
            {"waist": 0}, user_id=1234567890, timestamp=1719500400
        )
        assert record["waistValue"] == "0"

    def test_round_trip_through_normalize(self):
        built = build_girth_record(
            {"waist": 90.0, "left_arm": 33.0},
            user_id=1234567890,
            timestamp=1719500400,
            time_zone="+0:00",
        )
        back = normalize_girth(built)
        assert back["waist"] == 90.0
        assert back["left_arm"] == 33.0


class TestFormatGirth:
    def test_contains_labels_and_date(self):
        text = format_girth(SAMPLE_RECORD)
        # rendered via format_timestamp, so compare against it rather than a
        # literal date (the run's local timezone decides the calendar day)
        assert format_timestamp(SAMPLE_RECORD["timeStamp"]) in text
        assert "Waist" in text
        assert "Left Arm" in text
        assert "Waist-to-Hip Ratio" in text
        # an unmeasured site is not shown
        assert "Shoulder" not in text

    def test_shows_overall_arm_when_bilateral_unused(self):
        record = {"timeStamp": 1719500400, "armValue": 34.0, "thighValue": 58.0}
        text = format_girth(record)
        assert "Arm" in text
        assert "Thigh" in text


def _encrypted(payload):
    """Wrap a payload the way the API returns it (code 101 + encrypted data)."""
    return {"code": 101, "msg": "success", "data": encrypt_request(payload)["encryptData"]}


class TestClientGirths:
    def _make_client(self):
        client = RenphoClient("user@example.com", "password")
        client.token = "tok"
        client.user_id = 1234567890
        return client

    def test_get_girth_measurements_returns_list(self):
        client = self._make_client()
        records = [SAMPLE_RECORD]
        with patch.object(client, "_post", return_value=_encrypted(records)) as mock_post:
            result = client.get_girth_measurements()
        assert result == records
        # read path must not send the write-only headers
        _, kwargs = mock_post.call_args
        assert "extra_headers" not in kwargs or kwargs["extra_headers"] is None

    def test_get_girth_measurements_empty_data(self):
        client = self._make_client()
        with patch.object(
            client, "_post", return_value={"code": 101, "msg": "success", "data": None}
        ):
            assert client.get_girth_measurements() == []

    def test_upload_sends_write_headers(self):
        client = self._make_client()
        acks = [{"id": 555, "timeStamp": 1719500400}]
        record = build_girth_record(
            {"waist": 90.0}, user_id=client.user_id, timestamp=1719500400
        )
        with patch.object(client, "_post", return_value=_encrypted(acks)) as mock_post:
            result = client.upload_girth_measurements(
                [record], time_zone="-5", zone_id="America/New_York"
            )
        assert result == acks
        _, kwargs = mock_post.call_args
        headers = kwargs["extra_headers"]
        # the timeZone header is the one the endpoint 400s without
        assert headers["timezone"] == "-5"
        assert headers["zoneid"] == "America/New_York"
        assert headers["userid"] == "1234567890"

    def test_upload_headers_win_over_auth_headers(self):
        """The write header set must not be shadowed by the default auth ones."""
        client = self._make_client()
        record = build_girth_record({"waist": 90.0}, user_id=1, timestamp=1719500400)
        sent = {}

        def fake_post(endpoint, body, *, auth=True, extra_headers=None):
            headers = {}
            if auth and client.token:
                headers.update({"userId": str(client.user_id), "platform": "android"})
            if extra_headers:
                headers.update(extra_headers)
            sent.update(headers)
            return {"code": 101, "msg": "success", "data": None}

        with patch.object(client, "_post", side_effect=fake_post):
            client.upload_girth_measurements([record])
        # requests folds header names case-insensitively; the write value must win
        assert sent["platform"] == "ios"
