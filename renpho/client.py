"""Renpho API client for fetching scale measurements."""

import json
import sys

import requests

from .constants import (
    API_BASE_URL,
    APP_VERSION,
    BODY_WEIGHT_SCALES,
    ENDPOINTS,
    PLATFORM,
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


def _check_response(result: dict, context: str = "API call") -> None:
    """Raise :class:`RenphoAPIError` if the response indicates failure."""
    code = result.get("code")
    msg = result.get("msg", "")
    if msg.lower() == "success" or code in SUCCESS_CODES:
        return
    raise RenphoAPIError(context, code, msg)


class RenphoClient:
    """Client for the Renpho cloud API.

    Example::

        client = RenphoClient("user@example.com", "password")
        client.login()
        measurements = client.get_all_measurements()
        for m in measurements:
            print(m["weight"], m.get("bodyfat"))
    """

    def __init__(self, email: str, password: str, *, debug: bool = False):
        self.email = email
        self.password = password
        self.debug = debug
        self.token: str | None = None
        self.user_id: int | str | None = None
        self.user_info: dict | None = None
        self._session = requests.Session()

    # ----- internal helpers -----

    def _post(
        self,
        endpoint: str,
        body: dict,
        *,
        auth: bool = True,
        extra_headers: dict[str, str] | None = None,
    ) -> dict:
        """Make an encrypted POST request to the Renpho API.

        Args:
            endpoint: Endpoint path (from :data:`~renpho.constants.ENDPOINTS`).
            body: Already-encrypted request body (``{"encryptData": ...}``).
            auth: Attach the standard auth headers (token/userId/...).
            extra_headers: Additional headers merged on top of the auth headers.
                Some endpoints (e.g. the girth upload) require a fuller header
                set than the default reads.
        """
        url = f"{API_BASE_URL}/{endpoint}"
        headers: dict[str, str] = {}
        if auth and self.token:
            headers["token"] = self.token
            headers["userId"] = str(self.user_id)
            headers["appVersion"] = APP_VERSION
            headers["platform"] = PLATFORM
        if extra_headers:
            headers.update(extra_headers)

        if self.debug:
            print(f"  POST {url}")
            if auth and self.token:
                print(f"  Headers: token={self.token[:20]}..., userId={self.user_id}")

        resp = self._session.post(url, json=body, headers=headers)

        if self.debug:
            print(f"  Status: {resp.status_code}")
            print(f"  Response: {resp.text[:300]}")

        resp.raise_for_status()
        return resp.json()

    # ----- public API -----

    def login(self) -> dict:
        """Authenticate and store the session token.

        Returns the full decrypted login response (includes user profile).

        Raises:
            RenphoAPIError: If the API rejects the credentials.
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
            "bindingList": {
                "deviceTypes": BODY_WEIGHT_SCALES,
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

        return user_data

    def get_device_info(self) -> dict:
        """Get device info including scale table names and record counts.

        Returns:
            Decrypted device info dict (contains ``scale`` list among others).

        Raises:
            RenphoAPIError: On API-level failure.
        """
        for attempt, body_fn in enumerate([encrypt_empty_bytes, encrypt_empty_object]):
            encrypted_body = body_fn()
            try:
                result = self._post(ENDPOINTS["device_info"], encrypted_body)
                break
            except requests.exceptions.HTTPError as e:
                if attempt == 0:
                    if self.debug:
                        print(
                            f"  Attempt 1 failed ({e}), retrying with empty object..."
                        )
                    continue
                raise

        _check_response(result, "GetDeviceInfo")
        data = decrypt_response(result["data"])

        if self.debug:
            print(f"  Device info: {json.dumps(data, indent=2)[:500]}")

        return data

    def get_measurements(
        self, table_name: str, user_id, total_count: int, *, page_size: int = 50
    ) -> list[dict]:
        """Fetch measurements from a specific scale table with pagination.

        Args:
            table_name: Dynamic table name from :meth:`get_device_info`.
            user_id: The user ID to query for.
            total_count: Total records available (from device info).
            page_size: Records per page (default 50).

        Returns:
            List of measurement dicts.
        """
        all_measurements: list[dict] = []
        page = 1

        while len(all_measurements) < total_count:
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

            all_measurements.extend(records)
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

            all_measurements.extend(records)
            if len(records) < page_size:
                break
            page += 1

        return all_measurements

    def get_all_measurements(self) -> list[dict]:
        """High-level helper: fetch device info then pull all measurements.

        Tries the body composition endpoint first (used by impedance scales).
        Falls back to the basic measurements endpoint for weight-only scales.
        The server-side count in device info is unreliable for body composition
        scales (often reports 0), so this method always attempts a fetch.

        Calls :meth:`login` first if no token is set.

        Returns:
            List of measurement dicts sorted by timestamp (newest first).
        """
        if not self.token:
            self.login()

        device_info = self.get_device_info()
        scales = device_info.get("scale", [])

        all_measurements: list[dict] = []
        for scale in scales:
            table_name = scale.get("tableName")
            count = scale.get("count", 0)
            user_ids = scale.get("userIds", [])

            if not table_name:
                continue

            uid = self.user_id
            if user_ids and uid not in user_ids:
                uid = user_ids[0]

            # Try body composition endpoint first; it handles both newer
            # impedance scales and cases where count is incorrectly zero.
            measurements = self.get_body_composition_measurements(table_name, uid)
            if not measurements and count > 0:
                measurements = self.get_measurements(table_name, uid, count)

            all_measurements.extend(measurements)

        all_measurements.sort(
            key=lambda m: m.get("timeStamp", 0) or 0,
            reverse=True,
        )
        return all_measurements

    # ----- tape measure (body girth) -----

    def get_girths(self, *, page_size: int = 100, page_num: int = 1) -> list[dict]:
        """Fetch Smart Tape Measure (body girth) records.

        Returns the raw girth records, one per measurement session, newest first
        as returned by the server. Use :func:`renpho.girth.normalize_girth` to
        reduce a record to the sites that were actually measured. All
        circumferences are in centimetres.

        Calls :meth:`login` first if no token is set.

        Args:
            page_size: Records per page (the app uses 100).
            page_num: 1-based page number.

        Returns:
            List of raw girth record dicts.

        Raises:
            RenphoAPIError: On API-level failure.
        """
        if not self.token:
            self.login()

        body = encrypt_request({"pageSize": str(page_size), "pageNum": str(page_num)})
        result = self._post(ENDPOINTS["girth_list"], body)
        _check_response(result, "GetGirths")

        if not result.get("data"):
            return []

        data = decrypt_response(result["data"])
        if isinstance(data, list):
            return data
        return self._extract_records(data) or []

    def _girth_write_headers(
        self, time_zone: str, zone_id: str, device_id: str
    ) -> dict[str, str]:
        """The fuller header set the app sends on girth WRITE calls.

        The upload endpoint returns HTTP 400 (``Missing request header
        'timeZone'``) unless these are present; the read endpoints do not need
        them. ``time_zone`` is the short form (e.g. ``"-5"``), NOT ``"-5:00"``.
        """
        return {
            "userid": str(self.user_id),
            "platform": "ios",
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

    def upload_girths(
        self,
        records: list[dict],
        *,
        time_zone: str = "+0",
        zone_id: str = "UTC",
        device_id: str = "renpho-api-python",
    ) -> list[dict]:
        """Upload (append) girth records via ``uploadGirthsDataV2``.

        Build *records* with :func:`renpho.girth.build_girth_record`. The
        endpoint only **adds** — there is no in-place replace, so re-uploading an
        existing date creates a second entry on the server.

        Calls :meth:`login` first if no token is set.

        Args:
            records: List of records from :func:`renpho.girth.build_girth_record`.
            time_zone: Short-form offset header (e.g. ``"-5"``, NOT ``"-5:00"``).
            zone_id: IANA zone id header (e.g. ``"America/New_York"``).
            device_id: Device identifier header value.

        Returns:
            The server acknowledgements (a list of ``{id, timeStamp}`` dicts).

        Raises:
            RenphoAPIError: On API-level failure.
        """
        if not self.token:
            self.login()

        encrypted_body = encrypt_request(records)
        headers = self._girth_write_headers(time_zone, zone_id, device_id)
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

            if "weight" in page_data:
                return [page_data]

        return None
