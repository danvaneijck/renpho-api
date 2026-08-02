"""Constants and configuration for the Renpho API."""

# API connection
API_BASE_URL = "https://cloud.renpho.com"
ENCRYPTION_KEY = "ed*wijdi$h6fe3ew"  # 16-byte AES-128 key
APP_VERSION = "6.6.0"
PLATFORM = "android"
SYSTEM_VERSION = "11"  # systemversion header value (mirrors the login systemType)

# API endpoints (from RenphoApiEndpoints.cs)
ENDPOINTS = {
    "login": "renpho-aggregation/user/login",
    "token_time": "RenphoHealth/app/sync/getTokenTime",
    "device_info": "renpho-aggregation/device/count",
    "family": "RenphoHealth/centerUser/queryFamilyMemberList",
    "measurements": "RenphoHealth/scale/queryAllMeasureDataList",
    "body_composition_measurements": "RenphoHealth/scale/queryBodyCompositionMeasureData",
    # Smart Tape Measure (body girth) endpoints
    "girth_measurements": "RenphoHealth/renpho/girth/queryAllGirthsDataList",
    "girth_upload": "RenphoHealth/renpho/girth/uploadGirthsDataV2",
}

# Body composition scales are believed to shard measurements across 16 tables.
# Server-side discovery only reports the table for the logged-in user, so the
# only way to find data belonging to other linked accounts is to probe.
#
# INFERRED, NOT DOCUMENTED: the 16-table range and the ``measurements_info_<hex>``
# naming come from observed accounts, so an account whose tables are named
# differently would probe empty. ``get_all_measurements()`` therefore probes the
# table names ``device/count`` actually reported before falling back to these,
# and ``discover_user_tables(..., tables=[...])`` takes an explicit list.
MEASUREMENT_TABLE_NAMES = [f"measurements_info_{i:X}" for i in range(16)]

# Body weight scale device types
BODY_WEIGHT_SCALES = [
    "01", "02", "03", "04", "05", "06", "07", "08", "09", "0A",
    "0B", "0C", "0D", "0E", "0F", "10", "11", "12", "13", "14",
]

# Measurement display metadata: (api_key, label, unit)
METRICS = [
    ("weight", "Weight", "kg"),
    ("bmi", "BMI", ""),
    ("bodyfat", "Body Fat", "%"),
    ("water", "Body Water", "%"),
    ("muscle", "Muscle Mass", "%"),
    ("bone", "Bone Mass", "%"),
    ("bmr", "BMR", "kcal/day"),
    ("visfat", "Visceral Fat", "level"),
    ("subfat", "Subcutaneous Fat", "%"),
    ("protein", "Protein", "%"),
    ("bodyage", "Body Age", "years"),
    ("sinew", "Lean Body Mass", "kg"),
    ("fatFreeWeight", "Fat Free Weight", "kg"),
    ("heartRate", "Heart Rate", "bpm"),
    ("cardiacIndex", "Cardiac Index", ""),
    ("bodyShape", "Body Shape", ""),
]

# Girth (smart tape-measure) metric metadata: (api_key, label, unit)
# Body circumference data from Renpho smart tape measures (e.g. R-Y002) is
# stored separately from scale data, under the girth_measurements endpoint.
# Values are circumferences; the paired ``*Unit`` field encodes cm (0) vs inch.
GIRTH_METRICS = [
    ("neckValue", "Neck", "cm"),
    ("shoulderValue", "Shoulder", "cm"),
    ("chestValue", "Chest", "cm"),
    ("waistValue", "Waist", "cm"),
    ("abdomenValue", "Abdomen", "cm"),
    ("hipValue", "Hip", "cm"),
    ("armValue", "Arm", "cm"),
    ("leftArmValue", "Left Arm", "cm"),
    ("rightArmValue", "Right Arm", "cm"),
    ("thighValue", "Thigh", "cm"),
    ("leftThighValue", "Left Thigh", "cm"),
    ("rightThighValue", "Right Thigh", "cm"),
    ("calfValue", "Calf", "cm"),
    ("leftCalfValue", "Left Calf", "cm"),
    ("rightCalfValue", "Right Calf", "cm"),
    ("whrValue", "Waist-to-Hip Ratio", ""),
    ("customValue", "Custom", "cm"),
    ("customValue1", "Custom 1", "cm"),
    ("customValue2", "Custom 2", "cm"),
    ("customValue3", "Custom 3", "cm"),
    ("customValue4", "Custom 4", "cm"),
    ("customValue5", "Custom 5", "cm"),
]

# Tape-measure girth sites: (api_field, site, unit). All circumferences are in
# centimetres (the record's ``*Unit: 0`` confirms cm). "arm" = upper arm.
#
# A tape measure records either a single overall value (``armValue``) or the
# bilateral pair (``leftArmValue``/``rightArmValue``) — whichever is unused
# stays 0. Both forms are listed so a read never silently drops a site and
# a write can target either.
GIRTH_SITES = [
    ("neckValue", "neck", "cm"),
    ("shoulderValue", "shoulder", "cm"),
    ("chestValue", "chest", "cm"),
    ("waistValue", "waist", "cm"),
    ("hipValue", "hip", "cm"),
    ("abdomenValue", "abdomen", "cm"),
    ("armValue", "arm", "cm"),
    ("leftArmValue", "left_arm", "cm"),
    ("rightArmValue", "right_arm", "cm"),
    ("thighValue", "thigh", "cm"),
    ("leftThighValue", "left_thigh", "cm"),
    ("rightThighValue", "right_thigh", "cm"),
    ("calfValue", "calf", "cm"),
    ("leftCalfValue", "left_calf", "cm"),
    ("rightCalfValue", "right_calf", "cm"),
]

# --- girth write provenance tags ---
#
# The girth WRITE endpoint was reverse-engineered from the iOS app, and these
# iOS-flavoured values are the only combination confirmed to be accepted by a
# live account. That is the sole reason they differ from the library-wide
# ``PLATFORM`` ("android") used everywhere else — not a considered choice about
# what a Python client should claim to be.
#
# They are the *defaults*, not fixed values: pass ``platform`` to
# :meth:`~renpho.RenphoClient.upload_girth_measurements` and ``platform`` /
# ``data_source`` to :func:`~renpho.girth.build_girth_record` to override. If you
# confirm the endpoint accepts other values, please open an issue and we can
# align these with ``PLATFORM``.
#
# Note the header set also sends ``systemversion`` = SYSTEM_VERSION ("11", taken
# from the Android login payload) alongside a platform of "ios". That mismatch is
# what the captured traffic looked like; the server evidently does not mind.
GIRTH_WRITE_PLATFORM = "ios"  # `platform` request header on the upload call
GIRTH_RECORD_PLATFORM = "IOS"  # `platform` field inside the record (upper-case)
GIRTH_RECORD_DATA_SOURCE = "Health"  # `dataSource` field inside the record

# Every ``*Value`` field the upload endpoint expects (each paired with a matching
# ``*Unit``). The writer defaults all of them to "0" and fills the measured sites.
GIRTH_VALUE_FIELDS = [
    "neckValue", "shoulderValue", "chestValue", "waistValue", "hipValue",
    "abdomenValue", "armValue", "leftArmValue", "rightArmValue",
    "thighValue", "leftThighValue", "rightThighValue",
    "calfValue", "leftCalfValue", "rightCalfValue",
]

# Success codes returned by the API
SUCCESS_CODES = {0, "0", 101, "101", 200, "200", 20000, "20000"}
