"""Helpers for the Renpho Smart Tape Measure (body girth) data.

The tape measure stores circumference measurements (waist, hip, arms, thighs,
etc.) under the ``RenphoHealth/renpho/girth/*`` endpoints — separate from the
smart-scale body-composition data. All circumferences are stored in centimetres
(a record's ``*Unit: 0`` means cm).

Everything here is a pure transform — no network access. Use
:meth:`renpho.RenphoClient.get_girths` and
:meth:`renpho.RenphoClient.upload_girths` for the API calls.
"""

import datetime

from .constants import GIRTH_SITES, GIRTH_VALUE_FIELDS

# site name (e.g. "waist") -> raw api field (e.g. "waistValue")
_SITE_TO_FIELD = {site: api_field for api_field, site, _unit in GIRTH_SITES}


def _to_float(value):
    """Best-effort float conversion; ``None`` if the value is missing/garbage."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _tz_offset_seconds(time_zone) -> int:
    """Parse a Renpho ``timeZone`` string (e.g. ``"-5:00"`` or ``"-5"``) to seconds."""
    text = str(time_zone or "").strip()
    if not text:
        return 0
    sign = -1 if text.startswith("-") else 1
    text = text.lstrip("+-")
    try:
        if ":" in text:
            hours, minutes = text.split(":", 1)
            return sign * (int(hours) * 3600 + int(float(minutes)) * 60)
        return sign * int(float(text) * 3600)
    except ValueError:
        return 0


def girth_date(record: dict) -> str | None:
    """Local ``YYYY-MM-DD`` for a record from its ``timeStamp`` + ``timeZone``.

    Returns ``None`` if the record has no usable timestamp.
    """
    ts = _to_float(record.get("timeStamp"))
    if ts is None:
        return None
    moment = datetime.datetime.fromtimestamp(
        int(ts) + _tz_offset_seconds(record.get("timeZone", "")),
        tz=datetime.timezone.utc,
    )
    return moment.strftime("%Y-%m-%d")


def normalize_girth(record: dict) -> dict:
    """Reduce a raw girth record to the sites that were actually measured.

    A site that was not measured comes back as ``0.0``; those are omitted rather
    than reported as a real zero measurement.

    Returns:
        A dict with ``date`` (local, from ``timeStamp`` + ``timeZone``), each
        measured site name mapped to its value in cm, and ``whr`` (waist/hip
        ratio) when present.
    """
    out: dict = {}
    date = girth_date(record)
    if date:
        out["date"] = date
    for api_field, site, _unit in GIRTH_SITES:
        value = _to_float(record.get(api_field))
        if value and value > 0:
            out[site] = round(value, 1)
    whr = _to_float(record.get("whrValue"))
    if whr and whr > 0:
        out["whr"] = round(whr, 3)
    return out


def build_girth_record(
    values: dict,
    *,
    user_id,
    timestamp: int,
    time_zone: str = "+0:00",
    mac: str = "",
    scale_name: str = "",
    firmware_version: str = "",
) -> dict:
    """Build one ``uploadGirthsDataV2`` record from clean ``{site: cm}`` values.

    Every ``*Value``/``*Unit`` pair is sent as a string; sites that are not
    provided default to ``"0"``/``"0"`` (``*Unit: 0`` = cm). Keys of *values* are
    the site names from :data:`~renpho.constants.GIRTH_SITES` (``"waist"``,
    ``"left_arm"``, ...); unknown keys and non-positive values are ignored.

    Args:
        values: Mapping of site name -> circumference in cm.
        user_id: The account user id (from ``client.user_id``).
        timestamp: Measurement time as epoch **seconds**.
        time_zone: Offset string stored on the record (e.g. ``"-5:00"``).
        mac: Device MAC, if known (optional metadata).
        scale_name: Device model name, if known (optional metadata).
        firmware_version: Device firmware, if known (optional metadata).

    Returns:
        A record dict ready to pass (inside a list) to
        :meth:`renpho.RenphoClient.upload_girths`.
    """
    record = {
        "mac": mac,
        "scaleName": scale_name,
        "platform": "IOS",
        "dataSource": "Health",
        "firmwareVersion": firmware_version,
        "internalModel": "",
        "custom": "",
        "measureUnit": "1",
        "timeZone": time_zone,
        "timeStamp": str(int(timestamp)),
        "userId": str(user_id),
    }
    for field in GIRTH_VALUE_FIELDS:
        record[field] = "0"
        record[field.replace("Value", "Unit")] = "0"  # 0 = cm
    for site, value in values.items():
        field = _SITE_TO_FIELD.get(site)
        if field is None:
            continue
        number = _to_float(value)
        if number and number > 0:
            record[field] = str(round(number, 2))
    return record


def format_girth(record: dict) -> str:
    """Return a human-readable string for a single girth record."""
    normalized = normalize_girth(record)
    lines = [f"  Date: {normalized.get('date', 'unknown')}"]
    for _api_field, site, unit in GIRTH_SITES:
        if site in normalized:
            label = site.replace("_", " ").title()
            lines.append(f"  {label:<14} {normalized[site]} {unit}")
    if "whr" in normalized:
        lines.append(f"  {'WHR':<14} {normalized['whr']}")
    return "\n".join(lines)
