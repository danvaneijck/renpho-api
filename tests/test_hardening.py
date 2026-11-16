"""Regression tests for defensive handling of odd server responses."""

from unittest.mock import patch

import pytest
import requests

from renpho.cli import main
from renpho.client import RenphoAPIError, RenphoClient
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


class TestTablesListing:
    def test_string_ids_match_int_user_id(self):
        scales = [{"tableName": "t", "userIds": ["7", "42"]}]
        assert RenphoClient._tables_listing(scales, 42) == ["t"]

    def test_int_ids_match_string_user_id(self):
        scales = [{"tableName": "t", "userIds": [7, 42]}]
        assert RenphoClient._tables_listing(scales, "42") == ["t"]

    def test_only_tables_listing_the_user(self):
        scales = [
            {"tableName": "a", "userIds": [42]},
            {"tableName": "b", "userIds": [7]},
            {"tableName": "c", "userIds": 42},
        ]
        assert RenphoClient._tables_listing(scales, 42) == ["a", "c"]


# Mirrors a live account: a family member shares the owner's table, and two
# more tables list only family members. The server returns only the rows of
# the user id queried.
SHARED = {"scale": [
    {"tableName": "measurements_info_8", "count": 33, "userIds": [9, 42]},
    {"tableName": "measurements_info_16", "count": 3, "userIds": [16, 40]},
]}


def _rows_for(table, uid, *args, **kwargs):
    return [{"id": f"{table}-{uid}", "bUserId": uid, "timeStamp": int(str(uid))}]


class TestProfiles:
    def _fetch(self, client, **kwargs):
        with patch.object(client, "get_body_composition_measurements", return_value=[]), \
             patch.object(client, "get_measurements", side_effect=_rows_for) as legacy:
            rows = client.get_all_measurements(device_info=SHARED, **kwargs)
        return rows, [c.args[:2] for c in legacy.call_args_list]

    def test_default_returns_only_the_logged_in_user(self):
        """A table that doesn't list you must not fall back to someone else."""
        rows, calls = self._fetch(_client(user_id=42))
        assert calls == [("measurements_info_8", 42)]
        assert {r["bUserId"] for r in rows} == {42}

    def test_profile_user_id_fetches_that_person(self):
        rows, calls = self._fetch(_client(user_id=42), profile_user_id=16)
        assert calls == [("measurements_info_16", 16)]
        assert {r["bUserId"] for r in rows} == {16}

    def test_extra_user_ids_listed_on_scales_skip_discovery(self):
        client = _client(user_id=42)
        with patch.object(client, "discover_user_tables") as discover:
            rows, calls = self._fetch(client, extra_user_ids=[9, "16", 40])
        discover.assert_not_called()
        assert {str(r["bUserId"]) for r in rows} == {"42", "9", "16", "40"}
        assert ("measurements_info_8", 9) in calls

    def test_duplicate_ids_are_fetched_once(self):
        rows, calls = self._fetch(_client(user_id=42), extra_user_ids=["42", 42])
        assert calls == [("measurements_info_8", 42)]

    def test_unlisted_user_tries_their_computed_shard_only(self):
        client = _client(user_id=50)  # 50 % 24 == 2
        with patch.object(client, "discover_user_tables") as discover:
            rows, calls = self._fetch(client)
        discover.assert_not_called()
        assert calls == [("measurements_info_2", 50)]

    def test_null_count_does_not_crash(self):
        client = _client()
        info = {"scale": [{"tableName": "t", "count": None, "userIds": [42]}]}
        with patch.object(client, "get_body_composition_measurements", return_value=[]), \
             patch.object(client, "get_measurements", return_value=[]):
            assert client.get_all_measurements(device_info=info) == []


class TestExpectedUserId:
    @staticmethod
    def _login(client, user_id, **kwargs):
        response = _encrypted({"login": {"token": "tok", "id": user_id}})
        with patch.object(client, "_post", return_value=response):
            return client.login(**kwargs)

    def test_matching_id_logs_in(self):
        client = RenphoClient("a@b.com", "p")
        self._login(client, 42, expected_user_id="42")
        assert client.token == "tok"

    def test_mismatch_raises_and_clears_the_session(self):
        client = RenphoClient("a@b.com", "p")
        with pytest.raises(RenphoAPIError, match="expected 7"):
            self._login(client, 42, expected_user_id=7)
        assert client.token is None
        assert client.user_id is None
        assert client.user_info is None

    def test_not_checked_by_default(self):
        client = RenphoClient("a@b.com", "p")
        self._login(client, 42)
        assert client.user_id == 42


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
             patch.object(RenphoClient, "get_data_counts", return_value=info), \
             patch.object(RenphoClient, "get_family_members", return_value=[]), \
             patch.object(RenphoClient, "get_body_composition_measurements", return_value=rows), \
             patch.object(RenphoClient, "get_girth_measurements", return_value=[]):
            main()
        assert (tmp_path / "measurements.json").exists()
