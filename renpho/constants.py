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
    "girth_list": "RenphoHealth/renpho/girth/queryAllGirthsDataList",
    "girth_upload": "RenphoHealth/renpho/girth/uploadGirthsDataV2",
}

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

# Tape-measure girth sites: (api_field, site, unit). All circumferences are in
# centimetres (the record's ``*Unit: 0`` confirms cm). "arm" = upper arm. The
# bilateral sites populate ``left*``/``right*``; the single ``armValue`` /
# ``thighValue`` / ``calfValue`` field stays 0 when the bilateral pair is used.
GIRTH_SITES = [
    ("neckValue", "neck", "cm"),
    ("shoulderValue", "shoulder", "cm"),
    ("chestValue", "chest", "cm"),
    ("waistValue", "waist", "cm"),
    ("hipValue", "hip", "cm"),
    ("abdomenValue", "abdomen", "cm"),
    ("leftArmValue", "left_arm", "cm"),
    ("rightArmValue", "right_arm", "cm"),
    ("leftThighValue", "left_thigh", "cm"),
    ("rightThighValue", "right_thigh", "cm"),
    ("leftCalfValue", "left_calf", "cm"),
    ("rightCalfValue", "right_calf", "cm"),
]

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
