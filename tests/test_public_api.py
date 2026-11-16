"""Public API contract: removing or renaming any of these is a breaking change.

Adding to the API is fine. If a test here fails because something was removed
on purpose, that change needs a major version bump and a release note.
"""

import inspect

import renpho
from renpho import RenphoClient

EXPORTS = {
    "__version__",
    "RenphoClient",
    "RenphoAPIError",
    "format_measurement",
    "format_timestamp",
    "save_csv",
    "save_json",
    "build_girth_record",
    "format_girth",
    "girth_date",
    "normalize_girth",
}

# method name -> keyword arguments callers rely on
CLIENT_METHODS = {
    "__init__": {"email", "password", "debug", "timeout"},
    "login": {"expected_user_id"},
    "get_device_info": set(),
    "get_family_members": set(),
    "get_measurements": {"table_name", "user_id", "total_count", "page_size"},
    "get_body_composition_measurements": {"table_name", "user_id", "page_size"},
    "get_all_measurements": {"extra_user_ids", "device_info", "profile_user_id"},
    "measurement_table_for": {"user_id"},
    "discover_user_tables": {"user_id", "tables"},
    "get_girth_measurements": {"page_size"},
    "upload_girth_measurements": {"records", "time_zone", "zone_id", "device_id", "platform"},
    "get_friends": {"page_size"},
    "get_friend_measure_days": {"friend_id", "time_zone"},
    "get_friend_summary": {"friend_id", "param"},
    "get_friend_trend": {"friend_id", "param", "time_type", "end_time", "time_zone"},
    "get_friend_measurements": {"friend_id", "params", "time_type", "end_time", "time_zone"},
    "local_utc_offset_hours": set(),
}


def test_package_exports():
    missing = EXPORTS - set(renpho.__all__)
    assert not missing, f"removed from renpho.__all__: {sorted(missing)}"
    for name in EXPORTS:
        assert hasattr(renpho, name), name


def test_version_is_a_string():
    assert isinstance(renpho.__version__, str) and renpho.__version__


def test_client_methods_and_arguments():
    for name, kwargs in CLIENT_METHODS.items():
        method = getattr(RenphoClient, name, None)
        assert callable(method), f"RenphoClient.{name} was removed"
        params = set(inspect.signature(method).parameters)
        missing = kwargs - params
        assert not missing, f"RenphoClient.{name} lost arguments: {sorted(missing)}"


def test_api_error_attributes():
    err = renpho.RenphoAPIError("Login", -114, "Decryption failed")
    assert (err.context, err.code, err.msg) == ("Login", -114, "Decryption failed")
