"""Constants and configuration for the Renpho API."""

# API connection
API_BASE_URL = "https://cloud.renpho.com"
ENCRYPTION_KEY = "ed*wijdi$h6fe3ew"  # 16-byte AES-128 key
APP_VERSION = "6.6.0"
PLATFORM = "android"

# API endpoints (from RenphoApiEndpoints.cs)
ENDPOINTS = {
    "login": "renpho-aggregation/user/login",
    "token_time": "RenphoHealth/app/sync/getTokenTime",
    "device_info": "renpho-aggregation/device/count",
    "family": "RenphoHealth/centerUser/queryFamilyMemberList",
    "measurements": "RenphoHealth/scale/queryAllMeasureDataList",
    "body_composition_measurements": "RenphoHealth/scale/queryBodyCompositionMeasureData",
    "body_composition_scale_count": "RenphoHealth/scale/bodyCompositionScaleCount",
    "girth_measurements": "RenphoHealth/renpho/girth/queryAllGirthsDataList",
}

# Body composition scales shard measurements across 16 tables. Server-side
# discovery only reports the table for the logged-in user, so the only way
# to find data belonging to other linked accounts is to probe each suffix.
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
]

# Success codes returned by the API
SUCCESS_CODES = {0, "0", 101, "101", 200, "200", 20000, "20000"}
