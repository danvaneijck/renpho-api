"""Tests for renpho.client — RenphoClient unit tests."""

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from renpho.client import RenphoAPIError, RenphoClient, _check_response
from renpho.constants import ENDPOINTS, MEASUREMENT_TABLE_NAMES, SUCCESS_CODES
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


def _encrypted(records):
    return {
        "code": 101,
        "msg": "success",
        "data": encrypt_request(records)["encryptData"],
    }


class TestMeasurementTableFor:
    """Rows live in measurements_info_<user_id % 24>, verified on a live account."""

    def test_computes_the_shard(self):
        # the three user ids observed on a real account, with their real tables
        assert RenphoClient.measurement_table_for(5850419884014272384) == (
            "measurements_info_8"
        )
        assert RenphoClient.measurement_table_for(6000380382810832768) == (
            "measurements_info_16"
        )
        assert RenphoClient.measurement_table_for(6000377260861423488) == (
            "measurements_info_0"
        )

    def test_accepts_string_ids(self):
        assert RenphoClient.measurement_table_for("48") == "measurements_info_0"

    def test_returns_none_for_underivable_ids(self):
        assert RenphoClient.measurement_table_for("not-a-number") is None
        assert RenphoClient.measurement_table_for(None) is None

    def test_every_shard_is_a_real_table_name(self):
        shards = {
            RenphoClient.measurement_table_for(i) for i in range(200)
        }
        assert shards == set(MEASUREMENT_TABLE_NAMES)


class TestMeasurementTableNames:
    def test_are_decimal_zero_to_twentythree(self):
        assert len(MEASUREMENT_TABLE_NAMES) == 24
        assert MEASUREMENT_TABLE_NAMES[0] == "measurements_info_0"
        assert MEASUREMENT_TABLE_NAMES[-1] == "measurements_info_23"

    def test_no_hex_suffixes(self):
        """measurements_info_A..F were generated by an earlier revision and 404."""
        assert not any(
            t.endswith(("_A", "_B", "_C", "_D", "_E", "_F"))
            for t in MEASUREMENT_TABLE_NAMES
        )


class TestDiscoverUserTables:
    def _make_client(self):
        client = RenphoClient("a@b.com", "p")
        client.token = "tok"
        client.user_id = 123
        return client

    def test_computed_shard_short_circuits_the_sweep(self):
        """The shard is derivable, so a hit there costs one lookup, not 24."""
        client = self._make_client()
        uid = 6000380382810832768  # -> measurements_info_16
        probed = []

        def fake_has(table, user_id):
            probed.append(table)
            return table == "measurements_info_16"

        with patch.object(client, "_table_has_records", side_effect=fake_has):
            assert client.discover_user_tables(uid) == ["measurements_info_16"]
        assert probed == ["measurements_info_16"]

    def test_falls_back_to_full_sweep_when_the_shard_is_empty(self):
        client = self._make_client()
        uid = 6000380382810832768
        probed = []

        def fake_has(table, user_id):
            probed.append(table)
            return table == "measurements_info_3"

        with patch.object(client, "_table_has_records", side_effect=fake_has):
            assert client.discover_user_tables(uid) == ["measurements_info_3"]
        # shard first, then the rest — and never the same table twice
        assert probed[0] == "measurements_info_16"
        assert "measurements_info_16" not in probed[1:]

    def test_explicit_tables_override_the_default(self):
        client = self._make_client()
        with patch.object(client, "_table_has_records", return_value=False) as mock_has:
            assert client.discover_user_tables("999", tables=["only_this_one"]) == []
        assert mock_has.call_count == 1

    def test_probe_tries_the_legacy_endpoint_when_body_composition_is_empty(self):
        """Some accounts answer empty on body composition but hold rows on legacy."""
        client = self._make_client()

        def fake_post(endpoint, body, **kwargs):
            if endpoint == ENDPOINTS["body_composition_measurements"]:
                return _encrypted([])
            return _encrypted([{"id": 1, "weight": 70.0}])

        with patch.object(client, "_post", side_effect=fake_post):
            assert client._table_has_records("measurements_info_8", 123) is True

    def test_a_failing_probe_does_not_abort_discovery(self):
        client = self._make_client()

        def fake_post(endpoint, body, **kwargs):
            raise requests.exceptions.HTTPError("500 boom")

        with patch.object(client, "_post", side_effect=fake_post):
            assert client.discover_user_tables(48) == []


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
        assert [m["id"] for m in result] == [7, 1]

    def test_extra_account_falls_back_to_the_legacy_endpoint(self):
        """Mirrors the main loop: body composition empty must not mean no data."""
        client = self._make_client()
        device_info = {"scale": []}
        legacy = [{"id": 7, "weight": 80.0, "timeStamp": 2000}]

        with (
            patch.object(client, "get_device_info", return_value=device_info),
            patch.object(client, "get_body_composition_measurements", return_value=[]),
            patch.object(client, "get_measurements", return_value=legacy) as mock_legacy,
            patch.object(client, "discover_user_tables", return_value=["measurements_info_9"]),
        ):
            result = client.get_all_measurements(extra_user_ids=["999"])
        mock_legacy.assert_called_once_with("measurements_info_9", "999")
        assert result == legacy

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


class TestGetMeasurementsUnknownCount:
    def _make_client(self):
        client = RenphoClient("a@b.com", "p")
        client.token = "tok"
        client.user_id = 123
        return client

    def test_paginates_until_a_short_page_when_count_is_unknown(self):
        client = self._make_client()
        page1 = [{"id": i, "weight": 70.0} for i in range(50)]
        page2 = [{"id": 99, "weight": 71.0}]
        with patch.object(
            client, "_post", side_effect=[_encrypted(page1), _encrypted(page2)]
        ) as mock_post:
            result = client.get_measurements("measurements_info_8", 123)
        assert len(result) == 51
        assert mock_post.call_count == 2

    def test_still_honours_an_explicit_count(self):
        client = self._make_client()
        page = [{"id": i, "weight": 70.0} for i in range(50)]
        with patch.object(client, "_post", return_value=_encrypted(page)) as mock_post:
            result = client.get_measurements("measurements_info_8", 123, 50)
        assert len(result) == 50
        assert mock_post.call_count == 1
