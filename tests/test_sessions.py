"""Tests for 0.5.0: session reuse, error types, data counts, experimental reads."""

import base64
import json
import os
import stat
import time
from unittest.mock import MagicMock, patch

import pytest

from renpho.cli import main
from renpho.client import (
    RenphoAPIError,
    RenphoAuthError,
    RenphoClient,
    RenphoRateLimitError,
    RenphoSessionError,
    _check_response,
)
from renpho.constants import ENDPOINTS, LOGIN_DEVICE_TYPES
from renpho.crypto import aes_decrypt, encrypt_request


def _jwt(exp):
    def b64(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")
    return f"{b64({'alg': 'HS256'})}.{b64({'exp': exp, 'iat': exp - 90 * 86400, 'userId': 42})}.sig"


def _encrypted(data):
    return {"code": 101, "msg": "success", "data": encrypt_request(data)["encryptData"]}


def _client(**kwargs):
    client = RenphoClient("a@b.com", "p", **kwargs)
    client.token = _jwt(int(time.time()) + 86400)
    client.user_id = 42
    return client


def _response(status, body):
    resp = MagicMock(status_code=status)
    resp.json.return_value = body
    resp.text = json.dumps(body)
    resp.raise_for_status.side_effect = None if status < 400 else Exception(f"HTTP {status}")
    return resp


# ----- error types -----

class TestErrorTypes:
    @pytest.mark.parametrize("code, cls", [
        (104, RenphoAuthError), ("106", RenphoAuthError), (20001, RenphoAuthError),
        (401, RenphoSessionError), ("403", RenphoSessionError),
        (429, RenphoRateLimitError),
        (-114, RenphoAPIError), (500, RenphoAPIError),
    ])
    def test_codes_map_to_classes(self, code, cls):
        with pytest.raises(cls) as exc:
            _check_response({"code": code, "msg": "nope"}, "Ctx")
        assert type(exc.value) is cls
        assert exc.value.code == code

    def test_subclasses_are_still_api_errors(self):
        for cls in (RenphoAuthError, RenphoSessionError, RenphoRateLimitError):
            assert issubclass(cls, RenphoAPIError)

    def test_wrong_password_on_login(self):
        client = RenphoClient("a@b.com", "wrong")
        with patch.object(client, "_post", return_value={"code": 104, "msg": "wrong user name or password"}):
            with pytest.raises(RenphoAuthError):
                client.login()

    def test_expected_user_id_mismatch_is_auth_error(self):
        client = RenphoClient("a@b.com", "p")
        with patch.object(client, "_post", return_value=_encrypted({"login": {"token": "t", "id": 1}})):
            with pytest.raises(RenphoAuthError):
                client.login(expected_user_id=2)


# ----- dead sessions and auto re-login -----

class TestSessionErrors:
    def test_code_403_in_body_raises_session_error(self):
        client = _client()
        with patch.object(client._session, "post", return_value=_response(200, {"code": 403, "msg": "Forbidden"})):
            with pytest.raises(RenphoSessionError):
                client._post(ENDPOINTS["device_info"], {"encryptData": "x"})

    def test_http_401_raises_session_error(self):
        client = _client()
        with patch.object(client._session, "post", return_value=_response(401, {})):
            with pytest.raises(RenphoSessionError):
                client._post(ENDPOINTS["device_info"], {"encryptData": "x"})

    def test_success_passes_through(self):
        client = _client()
        ok = {"code": 101, "msg": "success", "data": None}
        with patch.object(client._session, "post", return_value=_response(200, ok)):
            assert client._post(ENDPOINTS["device_info"], {"encryptData": "x"}) == ok

    def test_auto_relogin_logs_in_once_and_retries(self):
        client = _client(auto_relogin=True)
        dead = _response(200, {"code": 403, "msg": "Forbidden"})
        ok = _response(200, {"code": 101, "msg": "success"})

        def fake_login():
            client.token = "fresh"

        with patch.object(client._session, "post", side_effect=[dead, ok]) as post, \
             patch.object(client, "login", side_effect=fake_login) as login:
            result = client._post(ENDPOINTS["device_info"], {"encryptData": "x"})
        login.assert_called_once()
        assert result["code"] == 101
        assert post.call_args.kwargs["headers"]["token"] == "fresh"

    def test_auto_relogin_does_not_loop(self):
        client = _client(auto_relogin=True)
        dead = _response(200, {"code": 403, "msg": "Forbidden"})
        with patch.object(client._session, "post", side_effect=[dead, dead]), \
             patch.object(client, "login") as login:
            with pytest.raises(RenphoSessionError):
                client._post(ENDPOINTS["device_info"], {"encryptData": "x"})
        login.assert_called_once()

    def test_no_auto_relogin_by_default(self):
        client = _client()
        with patch.object(client._session, "post", return_value=_response(200, {"code": 403})), \
             patch.object(client, "login") as login:
            with pytest.raises(RenphoSessionError):
                client._post(ENDPOINTS["device_info"], {"encryptData": "x"})
        login.assert_not_called()

    def test_login_failure_is_not_a_session_error(self):
        """Unauthenticated calls (login) keep the normal error path."""
        client = RenphoClient("a@b.com", "p")
        with patch.object(client._session, "post", return_value=_response(200, {"code": 403, "msg": "x"})):
            assert client._post(ENDPOINTS["login"], {"encryptData": "x"}, auth=False)["code"] == 403


# ----- saving and loading sessions -----

class TestSessionFiles:
    def test_token_expiry_is_decoded_from_the_jwt(self):
        exp = int(time.time()) + 1000
        client = _client()
        client.token = _jwt(exp)
        assert client.token_expires_at == exp

    def test_non_jwt_token_has_no_expiry(self):
        client = _client()
        client.token = "opaque"
        assert client.token_expires_at is None

    def test_save_and_load_round_trip(self, tmp_path):
        path = tmp_path / "s" / "session.json"
        saved = _client()
        saved.save_session(path)
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600

        fresh = RenphoClient("A@B.com", "p")
        assert fresh.load_session(path) is True
        assert (fresh.token, fresh.user_id) == (saved.token, 42)

    def test_other_email_is_ignored(self, tmp_path):
        path = tmp_path / "session.json"
        _client().save_session(path)
        other = RenphoClient("someone@else.com", "p")
        assert other.load_session(path) is False
        assert other.token is None

    def test_expired_token_is_ignored(self, tmp_path):
        client = _client()
        client.token = _jwt(int(time.time()) - 10)
        path = tmp_path / "session.json"
        client.save_session(path)
        assert RenphoClient("a@b.com", "p").load_session(path) is False

    def test_missing_or_corrupt_file(self, tmp_path):
        client = RenphoClient("a@b.com", "p")
        assert client.load_session(tmp_path / "missing.json") is False
        (tmp_path / "bad.json").write_text("{not json")
        assert client.load_session(tmp_path / "bad.json") is False

    def test_export_requires_a_session(self):
        with pytest.raises(RenphoSessionError):
            RenphoClient("a@b.com", "p").export_session()

    def test_session_file_is_used_instead_of_logging_in(self, tmp_path):
        path = tmp_path / "session.json"
        _client().save_session(path)
        client = RenphoClient("a@b.com", "p", session_file=path)
        with patch.object(client, "login") as login, \
             patch.object(client, "_post", return_value=_encrypted([{"userId": "42", "count": 7}])):
            assert client.get_measurement_count() == 7
        login.assert_not_called()

    def test_login_saves_the_session_file(self, tmp_path):
        path = tmp_path / "session.json"
        client = RenphoClient("a@b.com", "p", session_file=path)
        token = _jwt(int(time.time()) + 3600)
        with patch.object(client, "_post", return_value=_encrypted({"login": {"token": token, "id": 42}})):
            client.login()
        assert json.loads(path.read_text())["token"] == token

    def test_get_token_info_drops_the_token(self):
        client = _client()
        data = {"issAt": 1, "expAt": 2, "userId": 42, "token": None}
        with patch.object(client, "_post", return_value=_encrypted(data)) as post:
            assert client.get_token_info() == {"issAt": 1, "expAt": 2, "userId": 42}
        assert post.call_args.args[0] == ENDPOINTS["token_time"]


# ----- devices from the login response -----

class TestDevices:
    def test_login_sends_app_device_types_and_collects_devices(self):
        client = RenphoClient("a@b.com", "p")
        response = {
            "login": {"token": "t", "id": 1},
            "bindingList": {"bluetooth": [{"deviceModel": "ES-CS20M"}], "wifi": [{"deviceModel": "W1"}]},
        }
        with patch.object(client, "_post", return_value=_encrypted(response)) as post:
            client.login()
        sent = json.loads(aes_decrypt(post.call_args.args[1]["encryptData"]))
        assert sent["bindingList"]["deviceTypes"] == LOGIN_DEVICE_TYPES
        assert client.devices == [
            {"deviceModel": "ES-CS20M", "connection": "bluetooth"},
            {"deviceModel": "W1", "connection": "wifi"},
        ]

    def test_no_binding_list_means_no_devices(self):
        client = RenphoClient("a@b.com", "p")
        with patch.object(client, "_post", return_value=_encrypted({"login": {"token": "t", "id": 1}})):
            client.login()
        assert client.devices == []


# ----- data counts and per-store fetching -----

COUNTS = {
    "scale": [{"tableName": "measurements_info_18", "count": 5, "userIds": [42]}],
    "compositionScale": [{"tableName": "measurements_info_18", "count": 0, "userIds": "42"}],
}


class TestDataCounts:
    def test_names_make_one_request(self):
        client = _client()
        with patch.object(client, "_post", return_value=_encrypted(COUNTS)) as post:
            data = client.get_data_counts(names=["scale", "compositionScale"])
        assert post.call_count == 1
        assert json.loads(aes_decrypt(post.call_args.args[1]["encryptData"])) == {"names": ["scale", "compositionScale"]}
        assert data["compositionScale"][0]["userIds"] == ["42"]  # scalar normalized

    def test_default_merges_full_counts_with_composition(self):
        client = _client()
        full = {"girth": 2, "scale": COUNTS["scale"]}
        with patch.object(client, "_post", side_effect=[_encrypted(full), _encrypted(COUNTS)]) as post:
            data = client.get_data_counts()
        assert post.call_count == 2
        assert data["girth"] == 2 and "compositionScale" in data

    def test_measurement_count_picks_the_logged_in_user(self):
        client = _client()
        rows = [{"userId": "7", "count": 3}, {"userId": "42", "count": 31}]
        with patch.object(client, "_post", return_value=_encrypted(rows)):
            assert client.get_measurement_count() == 31

    def test_measurement_count_zero_when_absent(self):
        client = _client()
        with patch.object(client, "_post", return_value={"code": 101, "msg": "success", "data": None}):
            assert client.get_measurement_count() == 0


class TestPerStoreFetching:
    def _run(self, counts):
        client = _client()
        with patch.object(client, "get_body_composition_measurements", return_value=[{"id": 1, "fat": 20}]) as bc, \
             patch.object(client, "get_measurements", return_value=[{"id": 1, "weight": 70}]) as legacy:
            rows = client.get_all_measurements(device_info=counts)
        return rows, bc.call_count, legacy.call_count

    def test_empty_composition_store_is_skipped(self):
        rows, bc, legacy = self._run(COUNTS)
        assert (bc, legacy) == (0, 1)
        assert rows == [{"id": 1, "weight": 70}]

    def test_both_stores_read_when_both_hold_rows(self):
        counts = {
            "scale": [{"tableName": "t", "count": 3, "userIds": [42]}],
            "compositionScale": [{"tableName": "t", "count": 4, "userIds": [42]}],
        }
        rows, bc, legacy = self._run(counts)
        assert (bc, legacy) == (1, 1)
        # Same row id in both stores: both kept, because the stores number independently.
        assert len(rows) == 2

    def test_both_counts_zero_falls_back_to_trying_both(self):
        counts = {
            "scale": [{"tableName": "t", "count": 0, "userIds": [42]}],
            "compositionScale": [{"tableName": "t", "count": 0, "userIds": [42]}],
        }
        rows, bc, legacy = self._run(counts)
        assert bc == 1  # composition tried first; it returned rows, so legacy skipped
        assert legacy == 0

    def test_without_composition_counts_old_behaviour(self):
        counts = {"scale": [{"tableName": "t", "count": 0, "userIds": [42]}]}
        _, bc, _ = self._run(counts)
        assert bc == 1

    def test_default_uses_data_counts(self):
        client = _client()
        with patch.object(client, "get_data_counts", return_value={"scale": []}) as counts, \
             patch.object(client, "get_measurements", return_value=[]), \
             patch.object(client, "get_body_composition_measurements", return_value=[]):
            client.get_all_measurements()
        counts.assert_called_once_with(names=["scale", "compositionScale"])


# ----- experimental reads -----

def _sent(post):
    return json.loads(aes_decrypt(post.call_args.args[1]["encryptData"]))


class TestExperimental:
    def test_unassigned_measurements_payload(self):
        client = _client()
        page = {"total": 0, "list": [{"measurements": [], "unknownMeasurements": []}]}
        with patch.object(client, "_post", return_value=_encrypted(page)) as post:
            assert client.get_unassigned_measurements() == page
        assert post.call_args.args[0] == ENDPOINTS["unassigned_measurements"]
        assert _sent(post) == {"userId": 42, "pageSize": 20, "unknown": True, "getAll": 0}

    def test_third_party_measurements_paginate(self):
        client = _client()
        pages = [_encrypted([{"id": 1}, {"id": 2}]), _encrypted([{"id": 3}])]
        with patch.object(client, "_post", side_effect=pages) as post:
            rows = client.get_third_party_measurements(page_size=2)
        assert [r["id"] for r in rows] == [1, 2, 3]
        assert _sent(post) == {"userId": 42, "pageSize": "2", "pageNum": 2}

    def test_third_party_measurements_stop_on_repeated_page(self):
        client = _client()
        with patch.object(client, "_post", return_value=_encrypted([{"id": 1}, {"id": 2}])) as post:
            rows = client.get_third_party_measurements(page_size=2)
        assert len(rows) == 2 and post.call_count == 2

    def test_third_party_sources(self):
        client = _client()
        with patch.object(client, "_post", return_value=_encrypted([{"type": 1}])) as post:
            assert client.get_third_party_sources() == [{"type": 1}]
        assert _sent(post) == {"userId": 42}

    def test_goals(self):
        client = _client()
        with patch.object(client, "_post", side_effect=[_encrypted([{"targetValue": 70}]), _encrypted([])]) as post:
            assert client.get_goals() == {"scale": [{"targetValue": 70}], "girth": []}
        assert [c.args[0] for c in post.call_args_list] == [ENDPOINTS["scale_goals"], ENDPOINTS["girth_goals"]]


# ----- CLI -----

class TestCliSecretsAndSessions:
    @staticmethod
    def _env(monkeypatch, tmp_path, **extra):
        monkeypatch.setenv("RENPHO_EMAIL", "a@b.com")
        monkeypatch.setenv("RENPHO_PASSWORD", "p")
        monkeypatch.setenv("RENPHO_OUTPUT_DIR", str(tmp_path / "out"))
        monkeypatch.delenv("RENPHO_FRIEND_ID", raising=False)
        monkeypatch.delenv("RENPHO_SESSION_FILE", raising=False)
        for k, v in extra.items():
            monkeypatch.setenv(k, v)

    @staticmethod
    def _run_cli(login):
        info = {"scale": [{"tableName": "t", "count": 1, "userIds": [42]}]}
        family = [{"id": 7, "accountName": "Kid", "token": "secret", "encryptedPassword": "x"}]
        with patch.object(RenphoClient, "login", login), \
             patch.object(RenphoClient, "get_data_counts", return_value=info), \
             patch.object(RenphoClient, "get_family_members", return_value=family), \
             patch.object(RenphoClient, "get_all_measurements", return_value=[]), \
             patch.object(RenphoClient, "get_girth_measurements", return_value=[]):
            main()

    def test_no_tokens_written_to_disk(self, tmp_path, monkeypatch):
        self._env(monkeypatch, tmp_path)

        def fake_login(self):
            self.token, self.user_id = "session-token", 42
            self.user_info = {"id": 42, "accountName": "Me", "token": "session-token"}

        self._run_cli(fake_login)
        out = tmp_path / "out"
        for name in ("user_profile.json", "family_members.json"):
            text = (out / name).read_text()
            assert "secret" not in text and "session-token" not in text and '"token"' not in text
        assert json.loads((out / "user_profile.json").read_text())["accountName"] == "Me"

    def test_session_file_reused_without_login(self, tmp_path, monkeypatch):
        path = tmp_path / "session.json"
        _client().save_session(path)
        self._env(monkeypatch, tmp_path, RENPHO_SESSION_FILE=str(path))
        login = MagicMock()
        self._run_cli(login)
        login.assert_not_called()
