"""Regression tests for defensive handling of odd server responses."""

from unittest.mock import patch

import pytest
import requests

from renpho.cli import main
from renpho.client import RenphoClient
from renpho.crypto import encrypt_request


def _encrypted(data):
    return {"code": 101, "msg": "success", "data": encrypt_request(data)["encryptData"]}


def _client(user_id=42):
    client = RenphoClient("a@b.com", "p")
    client.token = "tok"
    client.user_id = user_id
    return client


class TestUserIdsNormalization:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ([1, 2], [1, 2]),
            (["1", "2"], ["1", "2"]),
            (42, [42]),
            ("42", ["42"]),
            (None, []),
            ([1, None, 2], [1, 2]),
        ],
    )
    def test_normalize(self, raw, expected):
        assert RenphoClient._normalize_user_ids(raw) == expected

    def test_device_info_scalar_user_ids_become_lists(self):
        client = _client()
        info = {"scale": [{"tableName": "t", "count": 1, "userIds": 42}]}
        with patch.object(client, "_post", return_value=_encrypted(info)):
            assert client.get_device_info()["scale"][0]["userIds"] == [42]


class TestScaleOwner:
    def test_string_ids_still_match_int_login_id(self):
        """A list of str ids must not fall through to someone else's id."""
        client = _client(user_id=42)
        assert client._scale_owner(["7", "42"]) == 42

    def test_int_ids_match_string_login_id(self):
        client = _client(user_id="42")
        assert client._scale_owner([7, 42]) == "42"

    def test_falls_back_to_first_listed_id(self):
        assert _client(user_id=42)._scale_owner(["7", "8"]) == "7"

    def test_no_ids_means_logged_in_user(self):
        assert _client(user_id=42)._scale_owner([]) == 42

    def test_get_all_measurements_queries_logged_in_user(self):
        client = _client(user_id=42)
        info = {"scale": [{"tableName": "t", "count": 1, "userIds": ["7", "42"]}]}
        with patch.object(client, "get_body_composition_measurements", return_value=[]) as bc, \
             patch.object(client, "get_measurements", return_value=[]):
            client.get_all_measurements(device_info=info)
        assert bc.call_args.args == ("t", 42)

    def test_null_count_does_not_crash(self):
        client = _client()
        info = {"scale": [{"tableName": "t", "count": None, "userIds": [42]}]}
        with patch.object(client, "get_body_composition_measurements", return_value=[]):
            assert client.get_all_measurements(device_info=info) == []


class TestRepeatedPages:
    """A server that ignores pageNum must not cause an endless loop."""

    @staticmethod
    def _full_page(n=2):
        return _encrypted([{"id": i, "weight": 70 + i} for i in range(n)])

    def test_body_composition_stops_on_repeated_page(self):
        client = _client()
        with patch.object(client, "_post", return_value=self._full_page()) as post:
            records = client.get_body_composition_measurements("t", 42, page_size=2)
        assert len(records) == 2
        assert post.call_count == 2

    def test_girth_stops_on_repeated_page(self):
        client = _client()
        page = _encrypted([{"id": i, "neckValue": 30} for i in range(2)])
        with patch.object(client, "_post", return_value=page) as post:
            records = client.get_girth_measurements(page_size=2)
        assert len(records) == 2
        assert post.call_count == 2

    def test_measurements_unknown_count_stops_on_repeated_page(self):
        client = _client()
        with patch.object(client, "_post", return_value=self._full_page()) as post:
            records = client.get_measurements("t", 42, None, page_size=2)
        assert len(records) == 2
        assert post.call_count == 2

    def test_measurements_known_count_does_not_pad_with_repeats(self):
        client = _client()
        with patch.object(client, "_post", return_value=self._full_page()):
            records = client.get_measurements("t", 42, 10, page_size=2)
        assert [r["id"] for r in records] == [0, 1]

    def test_records_without_ids_compare_by_content(self):
        client = _client()
        page = _encrypted([{"weight": 70}, {"weight": 71}])
        with patch.object(client, "_post", return_value=page) as post:
            records = client.get_body_composition_measurements("t", 42, page_size=2)
        assert len(records) == 2
        assert post.call_count == 2


class TestProbeTransportErrors:
    def test_timeout_during_probe_is_a_miss_not_a_crash(self):
        client = _client()
        with patch.object(client, "_post", side_effect=requests.exceptions.ReadTimeout("slow")):
            assert client._table_has_records("measurements_info_0", 42) is False


class TestCliUsesLibraryFetch:
    def test_reads_tables_reported_with_zero_count(self, tmp_path, monkeypatch):
        """The CLI used to skip count == 0 tables, missing body composition data."""
        monkeypatch.setenv("RENPHO_EMAIL", "a@b.com")
        monkeypatch.setenv("RENPHO_PASSWORD", "p")
        monkeypatch.delenv("RENPHO_FRIEND_ID", raising=False)
        monkeypatch.setenv("RENPHO_OUTPUT_DIR", str(tmp_path))
        info = {"scale": [{"tableName": "t", "count": 0, "userIds": [42]}]}
        rows = [{"id": 1, "timeStamp": 1700000000, "weight": 70.0, "bUserId": 42}]

        def fake_login(self):
            self.token, self.user_id = "tok", 42

        with patch.object(RenphoClient, "login", fake_login), \
             patch.object(RenphoClient, "get_device_info", return_value=info), \
             patch.object(RenphoClient, "get_family_members", return_value=[]), \
             patch.object(RenphoClient, "get_body_composition_measurements", return_value=rows), \
             patch.object(RenphoClient, "get_girth_measurements", return_value=[]):
            main()
        assert (tmp_path / "measurements.json").exists()
