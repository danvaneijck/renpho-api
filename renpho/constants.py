"""Constants and configuration for the Renpho API."""

# API connection
API_BASE_URL = "https://cloud.renpho.com"
ENCRYPTION_KEY = "ed*wijdi$h6fe3ew"  # 16-byte AES-128 key

# APP_VERSION is not cosmetic: the gateway selects the payload decryption key
# from the ``appVersion`` request header. ENCRYPTION_KEY above is the key for
# app versions BELOW 8.0.0 — send 8.0.0 or newer (or omit the header) and the
# server tries a different key and fails with code -114, "Decryption failed,
# please check the parameters or key, or the data length is too long".
#
# Verified against a live account on 2026-10-22: 6.6.0, 6.9.9, 7.0.0 and 7.5.0
# all authenticate; 8.0.0, 8.5.0, 9.0.0 and 10.0.0 all return -114, as does
# sending no appVersion header at all.
#
# So do NOT bump this to match the current store version without also working
# out the newer key — that swap is what breaks login.
APP_VERSION = "6.6.0"
PLATFORM = "android"
SYSTEM_VERSION = "11"  # systemversion header value (mirrors the login systemType)

# Default per-request timeout in seconds, as ``(connect, read)``. Without one a
# stalled server hangs the caller forever, which for a scheduled sync means a
# job that never finishes and never reports an error.
REQUEST_TIMEOUT = (10, 30)

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
    # "Friends" endpoints: read another account's data after it has accepted a
    # friend request. See RenphoClient.get_friends() and issue #14.
    "friends": "RenphoHealth/app/friend/friendsList",
    "friend_measure_days": "RenphoHealth/app/friend/measure/has",
    "friend_summary": "RenphoHealth/app/friend/measure/model",
    "friend_trend": "RenphoHealth/app/friend/measure/trendV2",
    # Found in the Renpho Health 7.11.6 app and checked against a live account.
    "data_counts": "renpho-aggregation/device/countV2",
    "measurement_count": "RenphoHealth/scale/countAll",
    # Experimental: these answer on a live account, but it had no such data, so
    # the shape of individual records is unconfirmed.
    "unassigned_measurements": "RenphoHealth/va/scale/getDualModeMeasurementByMac",
    "third_party_measurements": "RenphoHealth/scale/queryThirdPartyMeasureData",
    "third_party_sources": "RenphoHealth/scale/getThirdPartyDatasource",
    "scale_goals": "RenphoHealth/scale/queryGoalRecordsV2",
    "girth_goals": "RenphoHealth/renpho/girth/queryGirthsGoals",
}

# ``param`` values accepted by the friend trend/summary endpoints. Each trendV2
# call returns one parameter, so a full daily record takes one call per entry.
FRIEND_TREND_PARAMS = (
    "weight", "bodyfat", "water", "muscle", "bone", "visfat", "bmr", "bmi",
)

# Measurements are sharded across 24 tables, ``measurements_info_0`` through
# ``measurements_info_23``, and a user's rows live in the shard given by
# ``user_id % 24``. ``device/count`` only reports the table for the logged-in
# user, so this is how you locate any other linked account's data.
#
# Verified against a live account: tables 0-23 all respond and 24+ do not, three
# separate user ids each resolved to exactly ``user_id % 24``, and the
# hex-suffixed names an earlier revision generated (``measurements_info_A`` …
# ``_F``) do not exist. The suffix is decimal, not hex.
MEASUREMENT_TABLE_SHARDS = 24
MEASUREMENT_TABLE_NAMES = [
    f"measurements_info_{i}" for i in range(MEASUREMENT_TABLE_SHARDS)
]

# Legacy two-digit body weight scale device types. Kept for compatibility; the
# login request now sends LOGIN_DEVICE_TYPES.
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

# Device type codes the Renpho Health app (7.11.6) sends in the login
# request's ``bindingList``. The login response lists the account's bound
# devices of these types.
LOGIN_DEVICE_TYPES = [
    "00001", "00002", "00003", "00006", "00007", "00008", "00009", "00010",
    "00011", "00012", "00015", "00016", "00024", "00025", "00026", "00027",
    "00029", "00032", "00033", "00034", "00035", "00036", "00051", "00054",
    "00038", "00044", "00046", "00048", "00023", "00042", "00043", "00057",
    "00045", "00047", "00049", "00050", "00053", "00055", "00059", "00052",
    "00058", "00061", "00062", "00063", "00064", "00065", "00067", "00060",
    "00076", "00070", "00072", "00073", "00071",
]

# Success codes returned by the API
SUCCESS_CODES = {0, "0", 101, "101", 200, "200", 20000, "20000"}

# Error codes mapped to specific exception types (compared as strings).
AUTH_ERROR_CODES = {"104", "106", "20001"}  # wrong password / unknown email
# 401/403: the token expired, or another login (the phone app, another script)
# replaced this session. Renpho allows one active session per account.
SESSION_ERROR_CODES = {"401", "403"}
RATE_LIMIT_CODES = {"429"}
