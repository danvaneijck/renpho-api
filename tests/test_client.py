"""Tests for renpho.client — RenphoClient unit tests."""

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from renpho.client import RenphoAPIError, RenphoClient, _check_response
from renpho.constants import MEASUREMENT_TABLE_NAMES, SUCCESS_CODES
from renpho.crypto import aes_decrypt, encrypt_request


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


class TestDiscoverUserTables:
    """Probing measurement tables for an account device info does not report."""

    def _make_client(self):
        client = RenphoClient("a@b.com", "p")
        client.token = "tok"
        client.user_id = 123
        return client

    def _encrypted(self, records):
        return {
            "code": 101,
            "msg": "success",
            "data": encrypt_request(records)["encryptData"],
        }

    def test_returns_only_tables_with_records(self):
        client = self._make_client()
        hit = "measurements_info_3"

        def fake_post(endpoint, body, **kwargs):
            decoded = json.loads(aes_decrypt(body["encryptData"]))
            if decoded["tableName"] == hit:
                return self._encrypted([{"id": 1, "weight": 70.0}])
            return {"code": 101, "msg": "success", "data": None}

        with patch.object(client, "_post", side_effect=fake_post):
            assert client.discover_user_tables("999") == [hit]

    def test_probes_every_table(self):
        client = self._make_client()
        with patch.object(
            client, "_post", return_value={"code": 101, "msg": "success", "data": None}
        ) as mock_post:
            assert client.discover_user_tables("999") == []
        assert mock_post.call_count == len(MEASUREMENT_TABLE_NAMES)

    def test_a_failing_probe_does_not_abort_discovery(self):
        client = self._make_client()
        calls = {"n": 0}

        def fake_post(endpoint, body, **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise requests.exceptions.HTTPError("500 boom")
            return {"code": 101, "msg": "success", "data": None}

        with patch.object(client, "_post", side_effect=fake_post):
            assert client.discover_user_tables("999") == []
        assert calls["n"] == len(MEASUREMENT_TABLE_NAMES)


class TestGetAllMeasurementsExtraUsers:
    """get_all_measurements(extra_user_ids=...) — multiple accounts on one email."""

    def _make_client(self):
        client = RenphoClient("a@b.com", "p")
        client.token = "tok"
        client.user_id = 123
        return client

    def test_merges_records_from_an_extra_account(self):
        client = self._make_client()
        device_info = {
            "scale": [{"tableName": "measurements_info_1", "count": 1, "userIds": [123]}]
        }
        mine = [{"id": 1, "weight": 70.0, "timeStamp": 1000}]
        theirs = [{"id": 7, "weight": 80.0, "timeStamp": 2000}]

        def by_table(table, uid, **kwargs):
            return mine if table == "measurements_info_1" else theirs

        with (
            patch.object(client, "get_device_info", return_value=device_info),
            patch.object(client, "get_body_composition_measurements", side_effect=by_table),
            patch.object(client, "discover_user_tables", return_value=["measurements_info_9"]),
        ):
            result = client.get_all_measurements(extra_user_ids=["999"])
        # newest first, both accounts present
        assert [m["id"] for m in result] == [7, 1]

    def test_same_table_reached_twice_is_deduped(self):
        client = self._make_client()
        device_info = {
            "scale": [{"tableName": "measurements_info_1", "count": 1, "userIds": [123]}]
        }
        records = [{"id": 1, "weight": 70.0, "timeStamp": 1000}]

        with (
            patch.object(client, "get_device_info", return_value=device_info),
            patch.object(client, "get_body_composition_measurements", return_value=records),
            patch.object(client, "discover_user_tables", return_value=["measurements_info_1"]),
        ):
            result = client.get_all_measurements(extra_user_ids=["999"])
        assert len(result) == 1

    def test_matching_ids_in_different_tables_are_both_kept(self):
        """Row ids are only unique within a table — these are distinct records."""
        client = self._make_client()
        device_info = {
            "scale": [
                {"tableName": "measurements_info_1", "count": 1, "userIds": [123]},
                {"tableName": "measurements_info_2", "count": 1, "userIds": [123]},
            ]
        }
        per_table = {
            "measurements_info_1": [{"id": 1, "weight": 70.0, "timeStamp": 1000}],
            "measurements_info_2": [{"id": 1, "weight": 80.0, "timeStamp": 2000}],
        }

        with (
            patch.object(client, "get_device_info", return_value=device_info),
            patch.object(
                client,
                "get_body_composition_measurements",
                side_effect=lambda t, u, **k: per_table[t],
            ),
        ):
            result = client.get_all_measurements()
        assert len(result) == 2
        assert {m["weight"] for m in result} == {70.0, 80.0}

    def test_no_extra_ids_does_not_probe(self):
        client = self._make_client()
        device_info = {
            "scale": [{"tableName": "measurements_info_1", "count": 1, "userIds": [123]}]
        }
        with (
            patch.object(client, "get_device_info", return_value=device_info),
            patch.object(client, "get_body_composition_measurements", return_value=[]),
            patch.object(client, "get_measurements", return_value=[]),
            patch.object(client, "discover_user_tables") as mock_probe,
        ):
            client.get_all_measurements()
        mock_probe.assert_not_called()


class TestProbeCandidateOrdering:
    """The 16-table shard naming is inferred, so authoritative names go first."""

    def _make_client(self):
        client = RenphoClient("a@b.com", "p")
        client.token = "tok"
        client.user_id = 123
        return client

    def test_explicit_tables_override_the_inferred_list(self):
        client = self._make_client()
        with patch.object(
            client, "_post", return_value={"code": 101, "msg": "success", "data": None}
        ) as mock_post:
            client.discover_user_tables("999", tables=["only_this_one"])
        assert mock_post.call_count == 1

    def test_device_info_tables_are_probed_before_the_guess(self):
        client = self._make_client()
        # a real table name that is NOT part of the inferred pattern
        real_table = "measurements_info_custom"
        device_info = {
            "scale": [{"tableName": real_table, "count": 1, "userIds": [123]}]
        }
        seen = []

        def fake_discover(user_id, *, tables=None):
            seen.extend(tables or [])
            return []

        with (
            patch.object(client, "get_device_info", return_value=device_info),
            patch.object(client, "get_body_composition_measurements", return_value=[]),
            patch.object(client, "get_measurements", return_value=[]),
            patch.object(client, "discover_user_tables", side_effect=fake_discover),
        ):
            client.get_all_measurements(extra_user_ids=["999"])

        assert seen[0] == real_table, "authoritative table name must be probed first"
        # and the inferred names still follow, without duplicating it
        assert set(MEASUREMENT_TABLE_NAMES).issubset(set(seen))
        assert len(seen) == len(set(seen))
