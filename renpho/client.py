"""Renpho API client for fetching scale measurements."""

import base64
import json
import os
import time
from pathlib import Path

import requests

from .constants import (
    API_BASE_URL,
    APP_VERSION,
    AUTH_ERROR_CODES,
    ENDPOINTS,
    FRIEND_TREND_PARAMS,
    GIRTH_WRITE_PLATFORM,
    LOGIN_DEVICE_TYPES,
    MEASUREMENT_TABLE_NAMES,
    MEASUREMENT_TABLE_SHARDS,
    PLATFORM,
    RATE_LIMIT_CODES,
    REQUEST_TIMEOUT,
    SESSION_ERROR_CODES,
    SUCCESS_CODES,
    SYSTEM_VERSION,
)
from .crypto import (
    decrypt_response,
    encrypt_empty_bytes,
    encrypt_empty_object,
    encrypt_request,
)


class RenphoAPIError(Exception):
    """Raised when the Renpho API returns an error response."""

    def __init__(self, context: str, code, msg: str):
        self.context = context
        self.code = code
        self.msg = msg
        super().__init__(f"{context} failed: code={code}, msg={msg}")


class RenphoAuthError(RenphoAPIError):
    """The credentials were rejected (wrong password, unknown email), or the
    login landed on a different account than ``expected_user_id``."""


class RenphoSessionError(RenphoAPIError):
    """The session token is no longer valid.

    Tokens last 90 days, but Renpho allows one active session per account: any
    other login (the phone app, another script) ends this one. Log in again,
    or pass ``auto_relogin=True`` to :class:`RenphoClient`.
    """


class RenphoRateLimitError(RenphoAPIError):
    """The server is rate limiting requests (code 429). Wait and retry."""


def _error_class(code) -> type[RenphoAPIError]:
    code = str(code)
    if code in AUTH_ERROR_CODES:
        return RenphoAuthError
    if code in SESSION_ERROR_CODES:
        return RenphoSessionError
    if code in RATE_LIMIT_CODES:
        return RenphoRateLimitError
    return RenphoAPIError


def _token_expiry(token: str | None) -> int | None:
    """The ``exp`` claim (unix seconds) of a JWT session token, or None."""
    parts = (token or "").split(".")
    if len(parts) != 3:
        return None
    try:
        claims = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
        return int(claims["exp"])
    except (ValueError, KeyError, TypeError):
        return None


def _check_response(result: dict, context: str = "API call") -> None:
    """Raise :class:`RenphoAPIError` (or a subclass) if the response indicates failure."""
    code = result.get("code")
    # The API is inconsistent about the field holding the human-readable text:
    # the older endpoints answer "msg", the gateway's own errors (-113, -114)
    # answer "message". Reading only one of them silently threw away the
    # diagnostic and left callers with a bare code to go on. Either may also be
    # explicitly null, hence the coalesce to "" rather than a dict default.
    msg = result.get("msg") or result.get("message") or ""
    if str(msg).lower() == "success" or code in SUCCESS_CODES:
        return
    raise _error_class(code)(context, code, str(msg))


class RenphoClient:
    """Client for the Renpho cloud API.

    Example::

        client = RenphoClient("user@example.com", "password")
        client.login()
        measurements = client.get_all_measurements()
        for m in measurements:
            print(m["weight"], m.get("bodyfat"))
    """

    def __init__(
        self,
        email: str,
        password: str,
        *,
        debug: bool = False,
        timeout: float | tuple[float, float] | None = REQUEST_TIMEOUT,
        session_file: str | os.PathLike | None = None,
        auto_relogin: bool = False,
    ):
        """
        Args:
            email: Renpho account email.
            password: Renpho account password.
            debug: Print request/response details.
            timeout: Per-request timeout in seconds, either one number or a
                ``(connect, read)`` pair. Defaults to
                :data:`~renpho.constants.REQUEST_TIMEOUT`. ``None`` disables it
                (not recommended: a stalled server then blocks forever).
            session_file: Reuse the session across runs. A saved session is
                loaded instead of logging in, and every new login is saved
                here (file mode 0600). See :meth:`save_session`.
            auto_relogin: When a call fails because the session was replaced
                or expired, log in again once and retry the call. Off by
                default: logging in signs out every other session on the
                account, including the phone app.
        """
        self.email = email
        self.password = password
        self.debug = debug
        self.timeout = timeout
        self.session_file = Path(session_file).expanduser() if session_file else None
        self.auto_relogin = auto_relogin
        self.token: str | None = None
        self.user_id: int | str | None = None
        self.user_info: dict | None = None
        self.devices: list[dict] = []
        self._session = requests.Session()

    # ----- internal helpers -----

    def _post(
        self,
        endpoint: str,
        body: dict,
        *,
        auth: bool = True,
        extra_headers: dict[str, str] | None = None,
        _retried: bool = False,
    ) -> dict:
        """Make an encrypted POST request to the Renpho API.

        Args:
            endpoint: Endpoint path (from :data:`~renpho.constants.ENDPOINTS`).
            body: Already-encrypted request body (``{"encryptData": ...}``).
            auth: Attach the standard auth headers (token/userId/...).
            extra_headers: Additional headers merged on top of the auth headers.
                Some endpoints (e.g. the girth upload) require a fuller header
                set than the default reads.

        Raises:
            RenphoSessionError: The session was replaced or expired (and
                ``auto_relogin`` is off, or the retry failed too).
        """
        url = f"{API_BASE_URL}/{endpoint}"
        # ``appVersion`` is what the gateway keys payload decryption off, so it
        # has to go out on *every* call — including the unauthenticated login,
        # which used to send no headers at all. Without it the server cannot
        # pick a key and answers code -114 ("Decryption failed, please check
        # the parameters or key, ..."), which reads like a wrong key but is
        # really a missing header. See APP_VERSION in constants.py.
        headers: dict[str, str] = {
            "appVersion": APP_VERSION,
            "platform": PLATFORM,
        }
        if auth and self.token:
            headers["token"] = self.token
            headers["userId"] = str(self.user_id)
        if extra_headers:
            headers.update(extra_headers)

        if self.debug:
            print(f"  POST {url}")
            if auth and self.token:
                print(f"  Headers: token={self.token[:20]}..., userId={self.user_id}")

        resp = self._session.post(
            url, json=body, headers=headers, timeout=self.timeout
        )

        if self.debug:
            print(f"  Status: {resp.status_code}")
            print(f"  Response: {resp.text[:300]}")

        result = None
        if auth and self.token:
            # A dead session shows up as code 403 in an HTTP 200 body, or as an
            # HTTP 401/403 status.
            if resp.status_code not in (401, 403):
                resp.raise_for_status()
                result = resp.json()
            code = resp.status_code if result is None else result.get("code")
            if str(code) in SESSION_ERROR_CODES:
                if self.auto_relogin and not _retried:
                    if self.debug:
                        print("  Session replaced or expired; logging in again")
                    self.login()
                    return self._post(
                        endpoint, body, auth=auth,
                        extra_headers=extra_headers, _retried=True,
                    )
                msg = "" if result is None else (result.get("msg") or result.get("message") or "")
                raise RenphoSessionError(endpoint, code, str(msg) or (
                    "session replaced by another login or expired; log in again"
                ))
            return result

        resp.raise_for_status()
        return resp.json()

    # ----- sessions -----

    @property
    def token_expires_at(self) -> int | None:
        """When the current token expires (unix seconds), decoded from the token.

        Renpho tokens are JWTs valid for 90 days. Another login ends the session
        earlier, which the token cannot tell you; :meth:`get_token_info` asks
        the server instead.
        """
        return _token_expiry(self.token)

    def export_session(self) -> dict:
        """The current session as a dict for :meth:`import_session`.

        Contains the session token, which grants access to the account until
        it expires: store it like a password.
        """
        if not self.token:
            raise RenphoSessionError("export_session", None, "not logged in")
        return {
            "version": 1,
            "email": self.email,
            "user_id": self.user_id,
            "token": self.token,
            "expires_at": self.token_expires_at,
            "saved_at": int(time.time()),
        }

    def import_session(self, session: dict) -> bool:
        """Use a session from :meth:`export_session` instead of logging in.

        Returns False (and changes nothing) if the session belongs to another
        email or its token has expired. A session that another login has since
        replaced still imports; the first call then raises
        :class:`RenphoSessionError` (or logs in again with ``auto_relogin``).
        """
        token = session.get("token")
        if not token or str(session.get("email", "")).lower() != self.email.lower():
            return False
        exp = _token_expiry(token) or session.get("expires_at")
        if exp and exp <= time.time() + 60:
            return False
        self.token = token
        self.user_id = session.get("user_id")
        return True

    def save_session(self, path: str | os.PathLike | None = None) -> Path:
        """Write the session to *path* (default: ``session_file``), mode 0600."""
        target = Path(path).expanduser() if path else self.session_file
        if target is None:
            raise ValueError("no path given and no session_file configured")
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(self.export_session(), f)
        os.replace(tmp, target)
        return target

    def load_session(self, path: str | os.PathLike | None = None) -> bool:
        """Load a session saved by :meth:`save_session`. Returns True if used."""
        source = Path(path).expanduser() if path else self.session_file
        if source is None or not source.exists():
            return False
        try:
            session = json.loads(source.read_text())
        except (OSError, ValueError):
            return False
        return isinstance(session, dict) and self.import_session(session)

    def _ensure_session(self) -> None:
        """Make sure there is a token: reuse ``session_file`` if possible, else log in."""
        if self.token:
            return
        if self.session_file and self.load_session():
            if self.debug:
                print(f"  Reusing saved session from {self.session_file}")
            return
        self.login()

    def get_token_info(self) -> dict:
        """Ask the server about the current token: ``{"issAt", "expAt", "userId"}``.

        ``issAt``/``expAt`` are unix milliseconds. Raises
        :class:`RenphoSessionError` if the session is no longer valid, so this
        doubles as a cheap "is my saved session still alive?" check.
        """
        self._ensure_session()
        result = self._post(ENDPOINTS["token_time"], encrypt_empty_object())
        _check_response(result, "GetTokenTime")
        data = decrypt_response(result["data"]) if result.get("data") else {}
        return {k: v for k, v in data.items() if k != "token"} if isinstance(data, dict) else {}

    def _post_empty(self, endpoint: str, context: str):
        """POST an empty encrypted body and return the decrypted ``data``.

        Tries the empty-bytes body first and falls back to an empty object,
        since endpoints differ in which one they accept.
        """
        for attempt, body_fn in enumerate([encrypt_empty_bytes, encrypt_empty_object]):
            try:
                result = self._post(endpoint, body_fn())
                break
            except requests.exceptions.HTTPError as e:
                if attempt == 0:
                    if self.debug:
                        print(
                            f"  Attempt 1 failed ({e}), retrying with empty object..."
                        )
                    continue
                raise

        _check_response(result, context)
        if not result.get("data"):
            return None
        return decrypt_response(result["data"])

    # ----- public API -----

    def login(self, *, expected_user_id=None) -> dict:
        """Authenticate and store the session token.

        Returns the full decrypted login response (includes user profile).
        Sets :attr:`token`, :attr:`user_id`, :attr:`user_info` and
        :attr:`devices` (the account's bound devices, each with a
        ``connection`` key of ``"bluetooth"`` or ``"wifi"``), and saves the
        session if ``session_file`` is set.

        Logging in ends every other session on the account, including the
        phone app's.

        Args:
            expected_user_id: If given, the login must land on this user id.
                Some emails have two Renpho accounts (e.g. one left over from a
                Google SSO migration), and a password login can reach the wrong
                one. On a mismatch the session is cleared and an error raised,
                so no later call reads the wrong account's data.

        Raises:
            RenphoAPIError: If the API rejects the credentials, or the account
                is not *expected_user_id*.
            requests.HTTPError: On transport-level failures.
        """
        login_payload = {
            "questionnaire": {},
            "login": {
                "password": self.password,
                "areaCode": "US",
                "appRevision": APP_VERSION,
                "cellphoneType": "PythonScript",
                "systemType": "11",
                "email": self.email,
                "platform": PLATFORM,
            },
            # The login response lists the account's bound devices of these
            # types (see ``devices``).
            "bindingList": {
                "deviceTypes": LOGIN_DEVICE_TYPES,
            },
        }

        encrypted_body = encrypt_request(login_payload)
        result = self._post(ENDPOINTS["login"], encrypted_body, auth=False)
        _check_response(result, "Login")

        user_data = decrypt_response(result["data"])

        if self.debug:
            print(f"  Decrypted login: {json.dumps(user_data, indent=2)[:500]}")

        login_info = user_data.get("login", {})
        self.token = login_info.get("token")
        self.user_id = login_info.get("id")
        self.user_info = login_info

        if not self.token:
            raise RenphoAPIError("Login", None, "No token in login response")

        if expected_user_id is not None and str(self.user_id) != str(expected_user_id):
            actual = self.user_id
            self.token = self.user_id = self.user_info = None
            raise RenphoAuthError(
                "Login",
                None,
                f"logged in as user {actual}, expected {expected_user_id}",
            )

        self.devices = []
        binding = user_data.get("bindingList")
        if isinstance(binding, dict):
            for connection in ("bluetooth", "wifi"):
                for device in binding.get(connection) or []:
                    if isinstance(device, dict):
                        self.devices.append({**device, "connection": connection})

        if self.session_file:
            self.save_session()

        return user_data

    def get_device_info(self) -> dict:
        """Get device info including scale table names and record counts.

        Returns:
            Decrypted device info dict (contains ``scale`` list among others).

        Raises:
            RenphoAPIError: On API-level failure.
        """
        # An empty ``data`` field means no devices; callers index into the
        # result, so hand back an empty dict rather than None.
        data = self._post_empty(ENDPOINTS["device_info"], "GetDeviceInfo") or {}

        # ``userIds`` has been seen as a list of ints, a list of strings and a
        # bare scalar. Hand callers a list every time.
        if isinstance(data, dict):
            for scale in data.get("scale") or []:
                if isinstance(scale, dict) and "userIds" in scale:
                    scale["userIds"] = self._normalize_user_ids(scale["userIds"])

        if self.debug:
            print(f"  Device info: {json.dumps(data, indent=2)[:500]}")

        return data

    @staticmethod
    def _normalize_user_ids(value) -> list:
        """Coerce a ``userIds`` field to a list, dropping null entries."""
        if value is None:
            return []
        if isinstance(value, (list, tuple, set)):
            return [v for v in value if v is not None]
        return [value]

    @classmethod
    def _tables_listing(cls, scales: list, user_id) -> list[str]:
        """Names of the scale tables in *scales* whose ``userIds`` include *user_id*.

        IDs arrive as both int and str, so they are compared as strings.
        """
        tables: list[str] = []
        for scale in scales:
            table = scale.get("tableName") if isinstance(scale, dict) else None
            if not table or table in tables:
                continue
            if any(str(u) == str(user_id) for u in cls._normalize_user_ids(scale.get("userIds"))):
                tables.append(table)
        return tables

    def _fetch_table(
        self, table: str, user_id, *, scale_count=None, composition_count=None
    ) -> list[tuple[str, dict]]:
        """*user_id*'s rows in *table* as ``(store, row)`` pairs.

        Body composition and legacy scale rows are separate stores that share
        table names. With per-store counts (from :meth:`get_data_counts`), each
        store that holds rows is read, as the app does. Without counts, or when
        both are 0, the body composition endpoint is tried first and the
        legacy one when that comes back empty: some accounts keep every row in
        the legacy store.
        """
        if not scale_count and not composition_count:
            rows = self.get_body_composition_measurements(table, user_id)
            if rows:
                return [("composition", r) for r in rows]
            return [("scale", r) for r in self.get_measurements(table, user_id)]
        pairs: list[tuple[str, dict]] = []
        if composition_count:
            pairs += [("composition", r) for r in self.get_body_composition_measurements(table, user_id)]
        if scale_count:
            pairs += [("scale", r) for r in self.get_measurements(table, user_id)]
        return pairs

    @staticmethod
    def _take_new(records: list[dict], seen: set) -> list[dict]:
        """Return the records in *records* not already in *seen*, and record them.

        Pagination loops use this to stop when the server keeps answering with
        a page it already sent, which would otherwise loop forever. Records are
        keyed by ``id``, or by their full content when they have none.
        """
        new = []
        for r in records:
            rid = r.get("id") if isinstance(r, dict) else None
            key = ("id", str(rid)) if rid is not None else (
                "raw", json.dumps(r, sort_keys=True, default=str)
            )
            if key not in seen:
                seen.add(key)
                new.append(r)
        return new

    def get_family_members(self) -> list[dict]:
        """Get the family members (sub-users) linked to the logged-in account.

        The logged-in user is not part of the list — their profile is in
        :attr:`user_info`. Each entry is a full profile dict; ``id`` matches the
        ``userIds`` reported per scale by :meth:`get_device_info` and
        ``accountName`` holds the display name.

        Raises:
            RenphoAPIError: On API-level failure.
        """
        data = self._post_empty(ENDPOINTS["family"], "GetFamilyMembers")
        return data if isinstance(data, list) else []

    def get_measurements(
        self,
        table_name: str,
        user_id,
        total_count: int | None = None,
        *,
        page_size: int = 50,
    ) -> list[dict]:
        """Fetch measurements from a specific scale table with pagination.

        Args:
            table_name: Dynamic table name from :meth:`get_device_info`.
            user_id: The user ID to query for.
            total_count: Total records available (from device info). Pass None
                when it is not known — pagination then runs until the server
                stops returning full pages.
            page_size: Records per page (default 50).

        Returns:
            List of measurement dicts.
        """
        all_measurements: list[dict] = []
        seen: set = set()
        page = 1

        while total_count is None or len(all_measurements) < total_count:
            request_data = {
                "pageNum": page,
                "pageSize": page_size,
                "userIds": [str(user_id)],
                "tableName": table_name,
            }

            if self.debug:
                print(f"  Page {page} (got {len(all_measurements)} so far)...")

            encrypted_body = encrypt_request(request_data)
            result = self._post(ENDPOINTS["measurements"], encrypted_body)
            _check_response(result, f"Measurements page {page}")

            if not result.get("data"):
                break

            page_data = decrypt_response(result["data"])

            if self.debug:
                if isinstance(page_data, list):
                    print(f"  Got {len(page_data)} records")
                else:
                    print(f"  Response type: {type(page_data)}")

            records = self._extract_records(page_data)
            if records is None:
                break

            new = self._take_new(records, seen)
            if not new:
                break  # the server repeated a page; stop instead of looping
            all_measurements.extend(new)
            # Without a total to bound the loop, a short page is the only
            # signal that the last one has been read.
            if total_count is None and len(records) < page_size:
                break
            page += 1

        return all_measurements

    def get_body_composition_measurements(
        self, table_name: str, user_id, *, page_size: int = 50
    ) -> list[dict]:
        """Fetch body composition measurements using the newer API endpoint.

        Body composition scales (those with impedance sensors) store data under
        ``queryBodyCompositionMeasureData`` rather than ``queryAllMeasureDataList``.
        The server-side count in device info is often reported as 0 for these
        scales even when data exists, so this method paginates until the server
        returns an empty page rather than relying on a total count.

        Args:
            table_name: Dynamic table name from :meth:`get_device_info`.
            user_id: The user ID to query for.
            page_size: Records per page (default 50).

        Returns:
            List of measurement dicts.
        """
        all_measurements: list[dict] = []
        seen: set = set()
        page = 1

        while True:
            request_data = {
                "pageNum": page,
                "pageSize": page_size,
                "userIds": [str(user_id)],
                "tableName": table_name,
            }

            if self.debug:
                print(f"  Page {page} (got {len(all_measurements)} so far)...")

            encrypted_body = encrypt_request(request_data)
            result = self._post(
                ENDPOINTS["body_composition_measurements"], encrypted_body
            )
            _check_response(result, f"BodyCompositionMeasurements page {page}")

            if not result.get("data"):
                break

            page_data = decrypt_response(result["data"])

            if self.debug:
                if isinstance(page_data, list):
                    print(f"  Got {len(page_data)} records")
                else:
                    print(f"  Response type: {type(page_data)}")

            records = self._extract_records(page_data)
            if not records:
                break

            new = self._take_new(records, seen)
            if not new:
                break  # the server repeated a page; stop instead of looping
            all_measurements.extend(new)
            if len(records) < page_size:
                break
            page += 1

        return all_measurements

    @staticmethod
    def measurement_table_for(user_id) -> str | None:
        """The shard table holding *user_id*'s measurements, or None if underivable.

        Measurements are sharded across
        :data:`~renpho.constants.MEASUREMENT_TABLE_SHARDS` tables by
        ``user_id % 24``, so the table can be computed rather than searched for.
        """
        try:
            return f"measurements_info_{int(user_id) % MEASUREMENT_TABLE_SHARDS}"
        except (TypeError, ValueError):
            return None

    def _table_has_records(self, table: str, user_id) -> bool:
        """True if *table* holds at least one record for *user_id*."""
        encrypted_body = encrypt_request({
            "pageNum": 1,
            "pageSize": 1,
            "userIds": [str(user_id)],
            "tableName": table,
        })
        # Not every account answers on the body composition endpoint — some
        # return an empty list there while the legacy endpoint has the rows —
        # so a miss on the first is not proof the table is empty.
        for endpoint in ("body_composition_measurements", "measurements"):
            # A table that does not exist is an expected miss, not an error,
            # and neither is one probe timing out: keep going rather than
            # aborting the whole sweep.
            try:
                result = self._post(ENDPOINTS[endpoint], encrypted_body)
            except requests.exceptions.RequestException as e:
                if self.debug:
                    print(f"  Probe {table} via {endpoint} failed ({e}), skipping")
                continue
            if not result.get("data"):
                continue
            if self._extract_records(decrypt_response(result["data"])):
                return True
        return False

    def discover_user_tables(self, user_id, *, tables: list | None = None) -> list[str]:
        """Find the measurement tables holding data for *user_id*.

        The server only reports the table for the logged-in user via
        ``device/count``, so for any other linked account the table has to be
        located here.

        The shard is derivable — ``measurements_info_<user_id % 24>`` — so by
        default that table is checked first and the remaining shards are only
        swept if it comes back empty. Pass *tables* to check an explicit list
        instead; :meth:`get_all_measurements` seeds it with the table names
        ``device/count`` actually reported, which are authoritative.

        Args:
            user_id: The user ID to look for.
            tables: Candidate table names. Defaults to the computed shard first,
                then the remaining shards.

        Returns:
            List of table names that contain at least one record for ``user_id``.
        """
        if tables is None:
            candidates = list(MEASUREMENT_TABLE_NAMES)
            shard = self.measurement_table_for(user_id)
            if shard in candidates:
                # cheap path: the computed shard is almost always the only hit
                candidates.remove(shard)
                candidates.insert(0, shard)
                if self._table_has_records(shard, user_id):
                    return [shard]
                candidates = candidates[1:]
        else:
            candidates = list(tables)

        found = [t for t in candidates if self._table_has_records(t, user_id)]
        if not found and self.debug:
            print(
                f"  No table held data for user {user_id} "
                f"(checked {len(candidates)}). If this account definitely has "
                f"measurements, pass tables=[...] explicitly."
            )
        return found

    def get_girth_measurements(self, *, page_size: int = 100) -> list[dict]:
        """Fetch body girth (tape-measure) measurements.

        Girth data comes from Renpho smart tape measures (e.g. the R-Y002) and
        lives under a separate endpoint from scale data
        (``RenphoHealth/renpho/girth/queryAllGirthsDataList``). The
        authenticated user is identified by the request headers, so unlike the
        scale endpoints this call needs no table name or user id. Paginates
        until the server returns an empty page.

        Each record contains ``*Value``/``*Unit`` pairs for neck, shoulder,
        chest, waist, abdomen and hip, plus overall and left/right arm, thigh
        and calf, a computed ``whrValue`` (waist-to-hip ratio) and up to five
        user-defined ``custom`` slots. Unmeasured fields are returned as ``0``.

        Calls :meth:`login` first if no token is set.

        Args:
            page_size: Records per page (default 100).

        Returns:
            List of girth measurement dicts sorted by timestamp (newest first).
        """
        self._ensure_session()

        all_measurements: list[dict] = []
        seen: set = set()
        page = 1

        while True:
            request_data = {"pageNum": page, "pageSize": page_size}

            if self.debug:
                print(f"  Girth page {page} (got {len(all_measurements)} so far)...")

            encrypted_body = encrypt_request(request_data)
            result = self._post(ENDPOINTS["girth_measurements"], encrypted_body)
            _check_response(result, f"GirthMeasurements page {page}")

            if not result.get("data"):
                break

            page_data = decrypt_response(result["data"])
            records = self._extract_records(page_data)
            if not records:
                break

            new = self._take_new(records, seen)
            if not new:
                break  # the server repeated a page; stop instead of looping
            all_measurements.extend(new)
            if len(records) < page_size:
                break
            page += 1

        all_measurements.sort(
            key=lambda m: m.get("timeStamp", 0) or 0,
            reverse=True,
        )
        return all_measurements

    def get_all_measurements(
        self,
        extra_user_ids: list | None = None,
        *,
        device_info: dict | None = None,
        profile_user_id=None,
    ) -> list[dict]:
        """Fetch all measurements for one person, plus any *extra_user_ids*.

        The person is the logged-in user unless *profile_user_id* names someone
        else. The server filters every table by the user id in the query, so a
        scale shared with family members only returns the rows of the person
        asked for; their rows carry that id in ``bUserId``.

        Each table :meth:`get_device_info` lists for the person is read, from
        the body composition endpoint first and the legacy one if that comes
        back empty. The device count is not used to decide, because it is
        unreliable for body composition scales (often 0).

        Calls :meth:`login` first if no token is set.

        Args:
            extra_user_ids: More people to include, e.g. family members
                (``[m["id"] for m in client.get_family_members()]``) or another
                account on the same email (such as one left over from a Google
                SSO migration). Tables that device info lists for an id are used
                directly; otherwise they are located with
                :meth:`discover_user_tables`.
            device_info: A result of :meth:`get_device_info` to reuse instead
                of fetching it again.
            profile_user_id: Fetch this person instead of the logged-in user,
                e.g. a family member's ``id`` from :meth:`get_family_members`.

        Returns:
            Measurement dicts sorted newest first, deduped by ``(table, id)``
            (row ids are only unique within a table).
        """
        self._ensure_session()

        if device_info is None:
            device_info = self.get_data_counts(names=["scale", "compositionScale"])
        scales = device_info.get("scale") or []
        # Per-store row counts are only usable when device_info came from
        # get_data_counts(); device/count has no compositionScale list.
        composition = device_info.get("compositionScale")
        if composition is None:
            scale_counts = composition_counts = {}
        else:
            scale_counts = {s.get("tableName"): s.get("count") or 0 for s in scales if isinstance(s, dict)}
            composition_counts = {s.get("tableName"): s.get("count") or 0 for s in composition if isinstance(s, dict)}

        primary = self.user_id if profile_user_id is None else profile_user_id

        fetched: set = set()
        done: set = set()
        all_measurements: list[dict] = []

        for uid in [primary, *(extra_user_ids or [])]:
            if uid is None or str(uid) in done:
                continue
            done.add(str(uid))

            tables = self._tables_listing(scales, uid)
            if composition:
                tables += [t for t in self._tables_listing(composition, uid) if t not in tables]
            if not tables:
                if uid is primary:
                    # Not on any scale: try the shard their id maps to, without
                    # sweeping all 24 tables for someone who may have no data.
                    shard = self.measurement_table_for(uid)
                    tables = [shard] if shard else []
                else:
                    tables = self.discover_user_tables(uid)

            for table in tables:
                pairs = self._fetch_table(
                    table, uid,
                    scale_count=scale_counts.get(table),
                    composition_count=composition_counts.get(table),
                )
                for store, m in pairs:
                    rid = m.get("id")
                    if rid is not None:
                        # The two stores number their rows independently.
                        key = (store, table, str(rid))
                        if key in fetched:
                            continue
                        fetched.add(key)
                    all_measurements.append(m)

        all_measurements.sort(
            key=lambda m: m.get("timeStamp", 0) or 0,
            reverse=True,
        )
        return all_measurements

    # ----- counts and experimental reads -----

    def _query(self, endpoint: str, payload, context: str):
        """POST *payload* to ``ENDPOINTS[endpoint]`` and return the decrypted ``data``."""
        self._ensure_session()
        result = self._post(ENDPOINTS[endpoint], encrypt_request(payload))
        _check_response(result, context)
        return decrypt_response(result["data"]) if result.get("data") else None

    def get_data_counts(self, names: list[str] | None = None) -> dict:
        """How much data the account holds, per data type (``device/countV2``).

        Returns the ``scale`` and ``compositionScale`` table lists (each entry
        ``{"tableName", "count", "userIds"}``, counts per table across all its
        users; ``compositionScale`` is the body composition store) plus totals
        such as ``girth``, ``rope``, ``stepCount``, ``treadmill`` and goal counts.

        This is what the Renpho app uses in place of ``device/count``. The
        server only includes ``compositionScale`` when it is asked for by name,
        so with no *names* this makes two requests and merges them. Pass
        *names* (e.g. ``["scale", "compositionScale"]``) for a single request
        limited to those keys.
        """
        def fetch(payload):
            data = self._query("data_counts", payload, "GetDataCounts")
            return data if isinstance(data, dict) else {}

        if names is not None:
            data = fetch({"names": list(names)})
        else:
            data = fetch({})
            data.update(fetch({"names": ["scale", "compositionScale"]}))
        for key in ("scale", "compositionScale"):
            for table in data.get(key) or []:
                if isinstance(table, dict) and "userIds" in table:
                    table["userIds"] = self._normalize_user_ids(table["userIds"])
        return data

    def get_measurement_count(self) -> int:
        """The logged-in user's total number of scale measurements (one request).

        Much cheaper than fetching everything, so it works as a "has anything
        new arrived?" check before calling :meth:`get_all_measurements`.
        """
        rows = self._query("measurement_count", {}, "GetMeasurementCount") or []
        for row in rows if isinstance(rows, list) else []:
            if isinstance(row, dict) and str(row.get("userId")) == str(self.user_id):
                return int(row.get("count") or 0)
        return 0

    def get_unassigned_measurements(self, *, page_size: int = 20) -> dict:
        """Experimental: weigh-ins the scale could not attribute to a profile.

        Returns the server's raw page: ``{"total", "list": [{"measurements",
        "unknownMeasurements"}], ...}``. The endpoint answers on a live account,
        but one with no unassigned weigh-ins, so the record fields are
        unconfirmed.
        """
        self._ensure_session()
        data = self._query(
            "unassigned_measurements",
            {"userId": int(self.user_id), "pageSize": page_size, "unknown": True, "getAll": 0},
            "GetUnassignedMeasurements",
        )
        return data if isinstance(data, dict) else {}

    def get_third_party_measurements(self, *, page_size: int = 100) -> list[dict]:
        """Experimental: measurements imported from other apps (e.g. Fitbit,
        Health Connect, Samsung Health), all pages. Record fields unconfirmed."""
        self._ensure_session()
        records: list[dict] = []
        seen: set = set()
        page = 1
        while True:
            data = self._query(
                "third_party_measurements",
                {"userId": int(self.user_id), "pageSize": str(page_size), "pageNum": page},
                f"GetThirdPartyMeasurements page {page}",
            )
            rows = self._extract_records(data) or []
            new = self._take_new(rows, seen)
            if not new:
                break
            records.extend(new)
            if len(rows) < page_size:
                break
            page += 1
        return records

    def get_third_party_sources(self) -> list[dict]:
        """Experimental: the third-party data sources linked to the account."""
        self._ensure_session()
        data = self._query("third_party_sources", {"userId": int(self.user_id)}, "GetThirdPartySources")
        return data if isinstance(data, list) else []

    def get_goals(self) -> dict:
        """Experimental: goals set in the app, as ``{"scale": [...], "girth": [...]}``.

        Scale goals come from ``queryGoalRecordsV2`` and tape-measure goals
        from ``queryGirthsGoals`` (which covers every profile on the account).
        Record fields are unconfirmed on a live account.
        """
        scale = self._query("scale_goals", {}, "GetScaleGoals")
        girth = self._query("girth_goals", {}, "GetGirthGoals")
        return {
            "scale": scale if isinstance(scale, list) else [],
            "girth": girth if isinstance(girth, list) else [],
        }

    # ----- friends (read another account's data) -----
    #
    # Renpho keeps one active session per account, so logging in as your main
    # account signs the phone app out. Instead, log in as a second account that
    # the main account has accepted as a friend, and read the main account's
    # data through these endpoints. See the README and issue #14.

    @staticmethod
    def local_utc_offset_hours() -> int:
        """This machine's UTC offset in whole hours, the friend endpoints' default."""
        return int(time.localtime().tm_gmtoff // 3600)

    def _friend_post(self, endpoint: str, payload: dict, context: str, time_zone: int):
        """POST to a friend endpoint and return the decrypted ``data`` (or None).

        ``measure/has`` and ``measure/trendV2`` reject requests without a
        ``timeZone`` header in signed form (``+0``, ``+2``, ``-5``). The other
        friend endpoints accept it, so it is always sent.
        """
        self._ensure_session()
        result = self._post(
            endpoint,
            encrypt_request(payload),
            extra_headers={"timeZone": f"{time_zone:+d}"},
        )
        _check_response(result, context)
        if not result.get("data"):
            return None
        return decrypt_response(result["data"])

    def get_friends(self, *, page_size: int = 50) -> list[dict]:
        """List the accounts that have accepted this account as a friend.

        Each entry includes ``userId``, ``accountName``, ``email`` and
        ``createTime``. Pass ``userId`` to the other ``get_friend_*`` methods.

        Calls :meth:`login` first if no token is set.
        """
        self._ensure_session()
        data = self._friend_post(
            ENDPOINTS["friends"],
            {"userId": str(self.user_id), "pageNum": 1, "pageSize": page_size},
            "GetFriends",
            self.local_utc_offset_hours(),
        )
        return self._extract_records(data) or []

    def get_friend_measure_days(self, friend_id, *, time_zone: int | None = None):
        """Days on which *friend_id* weighed in, as returned by the server (raw)."""
        tz = self.local_utc_offset_hours() if time_zone is None else time_zone
        return self._friend_post(
            ENDPOINTS["friend_measure_days"],
            {"rhFriendIds": str(friend_id), "timeZone": tz},
            "GetFriendMeasureDays",
            tz,
        )

    def get_friend_summary(self, friend_id, param: str = "weight") -> dict | None:
        """Summary statistics for one parameter of *friend_id* (raw dict)."""
        return self._friend_post(
            ENDPOINTS["friend_summary"],
            {"rhFriendId": str(friend_id), "param": param},
            "GetFriendSummary",
            self.local_utc_offset_hours(),
        )

    def get_friend_trend(
        self,
        friend_id,
        param: str = "weight",
        *,
        time_type: str = "MONTH",
        end_time: int = 0,
        time_zone: int | None = None,
    ) -> list[dict]:
        """Daily points for one parameter of *friend_id*.

        Args:
            friend_id: ``userId`` from :meth:`get_friends`.
            param: One of :data:`~renpho.constants.FRIEND_TREND_PARAMS`.
            time_type: Window granularity, e.g. ``"WEEK"`` or ``"MONTH"``.
            end_time: End of the window in unix seconds; ``0`` means now. Move
                it back to page through older data.
            time_zone: UTC offset in whole hours used to group points into
                days. Defaults to this machine's offset.

        Returns:
            List of ``{"groupDay", "timeStamp", "value", ...}`` dicts, one per
            day with a measurement (the last weigh-in of that day).
        """
        tz = self.local_utc_offset_hours() if time_zone is None else time_zone
        data = self._friend_post(
            ENDPOINTS["friend_trend"],
            {
                "rhFriendId": str(friend_id),
                "timeZone": tz,
                "param": param,
                "sourceDataType": "",
                "timeType": time_type,
                "endTime": end_time,
            },
            f"GetFriendTrend({param})",
            tz,
        )
        if isinstance(data, dict) and isinstance(data.get("list"), list):
            return data["list"]
        return data if isinstance(data, list) else []

    def get_friend_measurements(
        self,
        friend_id,
        *,
        params: tuple[str, ...] | list[str] = FRIEND_TREND_PARAMS,
        time_type: str = "MONTH",
        end_time: int = 0,
        time_zone: int | None = None,
    ) -> list[dict]:
        """One record per day for *friend_id*, merged across *params*.

        Calls :meth:`get_friend_trend` once per parameter and merges the points
        by day into ``{"day", "timeStamp", "weight", "bodyfat", ...}``. Body
        composition values appear only on days the scale measured them. Zero and
        missing values are dropped.

        Limits of the friend endpoints: one value per day, no segmental or girth
        data, and one call covers a limited window (move *end_time* back for
        older data).

        Returns:
            List of daily records sorted newest first.
        """
        tz = self.local_utc_offset_hours() if time_zone is None else time_zone
        days: dict = {}
        for param in params:
            points = self.get_friend_trend(
                friend_id, param,
                time_type=time_type, end_time=end_time, time_zone=tz,
            )
            for point in points:
                day = point.get("groupDay")
                value = point.get("value")
                if not day or not isinstance(value, (int, float)) or value <= 0:
                    continue
                record = days.setdefault(
                    day, {"day": day, "timeStamp": point.get("timeStamp")}
                )
                record[param] = value
        return sorted(
            days.values(), key=lambda r: r.get("timeStamp") or 0, reverse=True
        )

    # ----- tape measure (body girth) writes -----

    def _girth_write_headers(
        self, time_zone: str, zone_id: str, device_id: str, platform: str
    ) -> dict[str, str]:
        """The fuller header set the app sends on girth WRITE calls.

        The upload endpoint returns HTTP 400 (``Missing request header
        'timeZone'``) unless these are present; the read endpoints do not need
        them. ``time_zone`` is the short form (e.g. ``"-5"``), NOT ``"-5:00"``.

        *platform* defaults to the captured iOS value rather than the
        library-wide ``PLATFORM`` — see
        :data:`~renpho.constants.GIRTH_WRITE_PLATFORM` for why.
        """
        return {
            "userid": str(self.user_id),
            "platform": platform,
            "timezone": time_zone,
            "zoneid": zone_id,
            "appversion": APP_VERSION,
            "systemversion": SYSTEM_VERSION,
            "language": "en",
            "languagecode": "en",
            "area": "US",
            "userarea": "US",
            "phone": "python-client",
            "devid": device_id,
        }

    def upload_girth_measurements(
        self,
        records: list[dict],
        *,
        time_zone: str = "+0",
        zone_id: str = "UTC",
        device_id: str = "renpho-api-python",
        platform: str = GIRTH_WRITE_PLATFORM,
    ) -> list[dict]:
        """Upload (append) girth records via ``uploadGirthsDataV2``.

        Build *records* with :func:`renpho.girth.build_girth_record`. The
        endpoint only **adds** — there is no in-place replace, so re-uploading an
        existing date creates a second entry on the server.

        The server does not recalculate ``whrValue`` (waist-to-hip ratio) for
        records written outside the app, so uploaded entries have no WHR.

        Calls :meth:`login` first if no token is set.

        Args:
            records: List of records from :func:`renpho.girth.build_girth_record`.
            time_zone: Short-form offset header (e.g. ``"-5"``, NOT ``"-5:00"``).
            zone_id: IANA zone id header (e.g. ``"America/New_York"``).
            device_id: Device identifier header value.
            platform: ``platform`` header. Defaults to the captured iOS value,
                the only one verified against a live account — see
                :data:`~renpho.constants.GIRTH_WRITE_PLATFORM`.

        Returns:
            The server acknowledgements (a list of ``{id, timeStamp}`` dicts).

        Raises:
            RenphoAPIError: On API-level failure.
        """
        self._ensure_session()

        encrypted_body = encrypt_request(records)
        headers = self._girth_write_headers(time_zone, zone_id, device_id, platform)
        result = self._post(
            ENDPOINTS["girth_upload"], encrypted_body, extra_headers=headers
        )
        _check_response(result, "UploadGirths")

        if not result.get("data"):
            return []
        return decrypt_response(result["data"])

    @staticmethod
    def _extract_records(page_data) -> list[dict] | None:
        """Extract measurement records from a page response."""
        if isinstance(page_data, list):
            return page_data if page_data else None

        if isinstance(page_data, dict):
            for key in ("list", "data", "records", "measurements"):
                if key in page_data and isinstance(page_data[key], list):
                    return page_data[key] if page_data[key] else None

            if "weight" in page_data or "neckValue" in page_data:
                return [page_data]

        return None
