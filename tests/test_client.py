"""Tests for renpho.client — RenphoClient unit tests."""

import json
from unittest.mock import MagicMock, patch

import pytest

from renpho.client import RenphoAPIError, RenphoClient, _check_response
from renpho.constants import SUCCESS_CODES
from renpho.crypto import encrypt_request


class TestCheckResponse:
    def test_success_by_msg(self):
        _check_response({"code": 999, "msg": "success"})

    @pytest.mark.parametrize("code", [0, "0", 200, "200", 20000, "20000"])
    def test_success_by_code(self, code):
        _check_response({"code": code, "msg": ""})

    def test_raises_on_failure(self):
        with pytest.raises(RenphoAPIError) as exc_info:
            _check_response({"code": 401, "msg": "Unauthorized"})
        assert exc_info.value.code == 401
        assert "Unauthorized" in str(exc_info.value)


class TestExtractRecords:
    def test_list_input(self):
        records = [{"weight": 70}, {"weight": 71}]
        assert RenphoClient._extract_records(records) == records

    def test_empty_list(self):
        assert RenphoClient._extract_records([]) is None

    def test_dict_with_list_key(self):
        data = {"list": [{"weight": 70}]}
        assert RenphoClient._extract_records(data) == [{"weight": 70}]

    def test_dict_with_data_key(self):
        data = {"data": [{"weight": 70}]}
        assert RenphoClient._extract_records(data) == [{"weight": 70}]

    def test_single_measurement_dict(self):
        data = {"weight": 70, "bmi": 22}
        assert RenphoClient._extract_records(data) == [data]

    def test_single_girth_dict(self):
        data = {"neckValue": 40.0, "waistValue": 90.0}
        assert RenphoClient._extract_records(data) == [data]

    def test_unknown_dict(self):
        data = {"foo": "bar"}
        assert RenphoClient._extract_records(data) is None

    def test_none_input(self):
        assert RenphoClient._extract_records(None) is None


class TestRenphoClient:
    def test_init(self):
        client = RenphoClient("test@example.com", "pass123")
        assert client.email == "test@example.com"
        assert client.password == "pass123"
        assert client.token is None
        assert client.debug is False

    def test_init_debug(self):
        client = RenphoClient("a@b.com", "p", debug=True)
        assert client.debug is True


class TestGetBodyCompositionMeasurements:
    def _make_client(self):
        client = RenphoClient("a@b.com", "p")
        client.token = "tok"
        client.user_id = 123
        return client

    def _encrypted_records(self, records):
        from renpho.crypto import encrypt_request
        return {"code": 101, "msg": "success", "data": encrypt_request(records)["encryptData"]}

    def test_returns_records_single_page(self):
        client = self._make_client()
        records = [{"weight": 70.0, "timeStamp": 1000}]
        with patch.object(client, "_post", return_value=self._encrypted_records(records)):
            result = client.get_body_composition_measurements("measurements_info_0", 123)
        assert result == records

    def test_paginates_until_empty(self):
        client = self._make_client()
        page1 = [{"weight": float(i), "timeStamp": i} for i in range(50)]
        page2 = [{"weight": 99.0, "timeStamp": 9999}]
        responses = [
            self._encrypted_records(page1),
            self._encrypted_records(page2),
            self._encrypted_records([]),
        ]
        with patch.object(client, "_post", side_effect=responses):
            result = client.get_body_composition_measurements("measurements_info_0", 123)
        assert len(result) == 51

    def test_returns_empty_when_no_data(self):
        client = self._make_client()
        with patch.object(client, "_post", return_value={"code": 101, "msg": "success", "data": None}):
            result = client.get_body_composition_measurements("measurements_info_0", 123)
        assert result == []


class TestGetGirthMeasurements:
    def _make_client(self):
        client = RenphoClient("a@b.com", "p")
        client.token = "tok"
        client.user_id = 123
        return client

    def _encrypted_records(self, records):
        from renpho.crypto import encrypt_request
        return {"code": 101, "msg": "success", "data": encrypt_request(records)["encryptData"]}

    def test_returns_records_single_page(self):
        client = self._make_client()
        records = [{"neckValue": 40.0, "waistValue": 90.0, "timeStamp": 1000}]
        with patch.object(client, "_post", return_value=self._encrypted_records(records)):
            result = client.get_girth_measurements()
        assert result == records

    def test_sorts_newest_first(self):
        client = self._make_client()
        records = [
            {"waistValue": 90.0, "timeStamp": 1000},
            {"waistValue": 88.0, "timeStamp": 3000},
            {"waistValue": 89.0, "timeStamp": 2000},
        ]
        with patch.object(client, "_post", return_value=self._encrypted_records(records)):
            result = client.get_girth_measurements()
        assert [r["timeStamp"] for r in result] == [3000, 2000, 1000]

    def test_paginates_until_short_page(self):
        client = self._make_client()
        page1 = [{"waistValue": float(i), "timeStamp": i} for i in range(100)]
        page2 = [{"waistValue": 99.0, "timeStamp": 9999}]
        responses = [
            self._encrypted_records(page1),
            self._encrypted_records(page2),
        ]
        with patch.object(client, "_post", side_effect=responses):
            result = client.get_girth_measurements()
        assert len(result) == 101

    def test_returns_empty_when_no_data(self):
        client = self._make_client()
        with patch.object(
            client, "_post", return_value={"code": 101, "msg": "success", "data": None}
        ):
            result = client.get_girth_measurements()
        assert result == []


class TestGetAllMeasurementsCountZero:
    """get_all_measurements should fetch even when device_info reports count=0."""

    def _make_client(self):
        client = RenphoClient("a@b.com", "p")
        client.token = "tok"
        client.user_id = 123
        return client

    def _encrypted_records(self, records):
        from renpho.crypto import encrypt_request
        return {"code": 101, "msg": "success", "data": encrypt_request(records)["encryptData"]}

    def test_fetches_when_count_is_zero(self):
        client = self._make_client()
        records = [{"weight": 72.0, "timeStamp": 1000}]
        device_info = {
            "scale": [{"tableName": "measurements_info_8", "count": 0, "userIds": [123]}]
        }
        with (
            patch.object(client, "get_device_info", return_value=device_info),
            patch.object(client, "get_body_composition_measurements", return_value=records),
        ):
            result = client.get_all_measurements()
        assert result == records

    def test_falls_back_to_get_measurements_when_body_composition_empty(self):
        client = self._make_client()
        records = [{"weight": 70.0, "timeStamp": 2000}]
        device_info = {
            "scale": [{"tableName": "measurements_info_8", "count": 5, "userIds": [123]}]
        }
        with (
            patch.object(client, "get_device_info", return_value=device_info),
            patch.object(client, "get_body_composition_measurements", return_value=[]),
            patch.object(client, "get_measurements", return_value=records) as mock_get,
        ):
            result = client.get_all_measurements()
        mock_get.assert_called_once_with("measurements_info_8", 123, 5)
        assert result == records
