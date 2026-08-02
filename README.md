# renpho-api

[![PyPI](https://img.shields.io/pypi/v/renpho-api)](https://pypi.org/project/renpho-api/)
[![CI](https://github.com/danvaneijck/renpho-api/actions/workflows/ci.yml/badge.svg)](https://github.com/danvaneijck/renpho-api/actions/workflows/ci.yml)
[![Python](https://img.shields.io/pypi/pyversions/renpho-api)](https://pypi.org/project/renpho-api/)

Unofficial Python client for the Renpho Health API. Pull body composition measurements from Renpho smart scales and measuring tapes programmatically.

Based on reverse-engineering from [RenphoGarminSync-CLI](https://github.com/forkerer/RenphoGarminSync-CLI).

## Installation

```bash
pip install renpho-api
```

For `.env` file support (recommended for CLI usage):

```bash
pip install "renpho-api[dotenv]"
```

## CLI Usage

1. Create a `.env` file (or export the variables):

```
RENPHO_EMAIL=your@email.com
RENPHO_PASSWORD=your_plain_text_password
```

2. Run the CLI:

```bash
renpho
```

This will log in, discover your scales, fetch all measurements, print the 5 most recent, and save everything to `renpho_data/` as JSON and CSV.

### Environment variables

| Variable | Required | Description |
| --- | --- | --- |
| `RENPHO_EMAIL` | Yes | Your Renpho account email |
| `RENPHO_PASSWORD` | Yes | Your Renpho account password |
| `RENPHO_DEBUG` | No | Set to `1` to print API request/response details |
| `RENPHO_OUTPUT_DIR` | No | Output directory (default: `renpho_data`) |

## Library Usage

```python
from renpho import RenphoClient

client = RenphoClient("user@example.com", "password")
client.login()

# Fetch all measurements in one call
measurements = client.get_all_measurements()

for m in measurements:
    print(m["weight"], m.get("bodyfat"), m.get("muscle"))
```

### Step-by-step control

```python
from renpho import RenphoClient, save_json, save_csv

client = RenphoClient("user@example.com", "password")
client.login()

# Get device/scale info
device_info = client.get_device_info()
scales = device_info["scale"]

# Fetch from a specific scale table
# Use get_body_composition_measurements() for scales with impedance sensors
# (body fat, muscle, etc.) — the server-side count is unreliable for these.
# Fall back to get_measurements() for weight-only scales.
table = scales[0]
measurements = client.get_body_composition_measurements(
    table_name=table["tableName"],
    user_id=client.user_id,
)
if not measurements:
    measurements = client.get_measurements(
        table_name=table["tableName"],
        user_id=client.user_id,
        total_count=table["count"],
    )

# Export
save_json(measurements, "my_data.json")
save_csv(measurements, "my_data.csv")
```

### Multiple Renpho accounts on one email

Some users end up with **two Renpho accounts under the same email** — for
example after the Google SSO migration created an orphan account, or after
re-registering. Each account has its own user ID and its own measurement
table, so the default `get_all_measurements()` will only return data from
the account you log in to.

If you know the other account's user ID, pass it in:

```python
measurements = client.get_all_measurements(
    extra_user_ids=["5975813831868809088"],
)
```

The library locates that user's rows, fetches them, and dedupes by
`(table, id)` so you get a single combined timeline.

**How the lookup works.** Measurements are sharded across 24 tables,
`measurements_info_0` through `measurements_info_23`, and a user's rows live in
`measurements_info_<user_id % 24>`. `device/count` only names the table for the
account you logged in to, so any other account's table is computed instead:

```python
RenphoClient.measurement_table_for(6000380382810832768)
# -> 'measurements_info_16'
```

That's normally a single lookup; only if the computed shard comes back empty
does the library sweep the remaining 23. Each check tries the body-composition
endpoint and then the legacy one, because some accounts answer empty on the
former while holding all their rows on the latter.

**How to find your other user ID:**

Unfortunately there is no first-party API endpoint that lists "all
accounts associated with this email" — Renpho treats accounts as
independent even when emails collide. Options:

1. **Renpho support** — email them and ask for your user ID(s) on file
2. **Inspect the iOS / Android app** — sign in to the other account in
   the official app and look in Settings / Account / Help → Feedback
   pages (the user ID is sometimes visible there)
3. **Capture network traffic** — proxy the official app through
   mitmproxy, sign in, and look at any request body containing
   `userId` (decrypt with the published AES-128 key — see the
   reverse-engineering write-up linked at the top of this README)

Once you have the ID, save it alongside your credentials and you won't
need to discover it again.

### Error handling

```python
from renpho import RenphoClient, RenphoAPIError

client = RenphoClient("user@example.com", "wrong_password")
try:
    client.login()
except RenphoAPIError as e:
    print(f"API error: {e}")
```

## Smart Tape Measure (body girth)

The Renpho Smart Tape Measure stores circumference measurements (waist, hip,
arms, thighs, etc.) under a separate set of endpoints from the smart scale. The
same login/token works for both. All circumferences are in **centimetres**.

### Reading girths

```python
from renpho import RenphoClient, format_girth, normalize_girth, save_csv, save_json

client = RenphoClient("user@example.com", "password")

# Paginates through everything, newest first; logs in automatically if needed.
girths = client.get_girth_measurements()

for record in girths[:5]:
    print(format_girth(record))

save_json(girths, "girth.json")
save_csv(girths, "girth.csv")

# Or reduce a record to just the sites that were measured (zeros omitted):
latest = normalize_girth(girths[0])
# -> {"date": "2024-06-27", "waist": 90.0, "left_arm": 33.0, "hip": 100.0, "whr": 0.9, ...}
```

Records come back as raw API dicts (same convention as the scale methods) — see
[Girth metrics](#girth-metrics) for the field names.

`normalize_girth()` returns the local measurement `date` (from `timeStamp` +
`timeZone`), each measured site in cm, and `whr` (waist/hip ratio) when present.
A site that was not measured comes back as `0.0` and is omitted rather than
reported as a real zero.

**Site names** returned by `normalize_girth()` / accepted by
`build_girth_record()`: `neck`, `shoulder`, `chest`, `waist`, `hip`, `abdomen`,
`arm` / `left_arm` / `right_arm` (upper arm), `thigh` / `left_thigh` /
`right_thigh`, `calf` / `left_calf` / `right_calf`. A tape measure records
either the overall site or the left/right pair — whichever is unused stays `0`.

The `renpho` CLI also fetches girth data automatically, saving it to
`girth.json` / `girth.csv` alongside the scale exports.

### Writing girths (backfill)

`upload_girth_measurements()` appends historical measurements (useful for
backfilling the app's history graph). The endpoint only **adds** — there is no
in-place replace, so re-uploading an existing date creates a second entry.

```python
from renpho import RenphoClient, build_girth_record

client = RenphoClient("user@example.com", "password")
client.login()

record = build_girth_record(
    {"waist": 90.0, "left_arm": 33.0, "right_arm": 33.5},
    user_id=client.user_id,
    timestamp=1719500400,        # epoch seconds for the measurement
    time_zone="-5:00",
)

acks = client.upload_girth_measurements(
    [record],
    time_zone="-5",                    # short form, NOT "-5:00"
    zone_id="America/New_York",
)
# acks -> [{"id": <server id>, "timeStamp": 1719500400}]
```

> **Notes:**
>
> - The upload endpoint returns HTTP 400 (`Missing request header 'timeZone'`)
>   unless the fuller app header set is sent. `upload_girth_measurements()`
>   handles that for you — just pass `time_zone` (short form) and `zone_id`.
> - The server does not recalculate `whrValue` (waist-to-hip ratio) for records
>   written outside the app, so uploaded entries have no WHR.

The write path was reverse-engineered from the iOS app, so it tags uploads as
`platform: ios` / `dataSource: Health` — the only combination confirmed against a
live account, and the reason it differs from the `android` platform the rest of
the library sends. Both are overridable if you'd rather not claim iOS:

```python
record = build_girth_record(
    {"waist": 90.0},
    user_id=client.user_id,
    timestamp=1719500400,
    platform="ANDROID",        # record tag; default "IOS"
    data_source="python",      # record tag; default "Health"
)

client.upload_girth_measurements([record], platform="android")  # header; default "ios"
```

If you confirm the endpoint accepts other values, please open an issue and we
can change the defaults.

## Available Metrics

Each measurement dict can contain these fields (availability depends on your scale model):

| Key | Description | Unit |
| --- | --- | --- |
| `weight` | Weight | kg |
| `bmi` | BMI | |
| `bodyfat` | Body Fat | % |
| `water` | Body Water | % |
| `muscle` | Muscle Mass | % |
| `bone` | Bone Mass | % |
| `bmr` | Basal Metabolic Rate | kcal/day |
| `visfat` | Visceral Fat | level |
| `subfat` | Subcutaneous Fat | % |
| `protein` | Protein | % |
| `bodyage` | Body Age | years |
| `sinew` | Lean Body Mass | kg |
| `fatFreeWeight` | Fat Free Weight | kg |
| `heartRate` | Heart Rate | bpm |
| `cardiacIndex` | Cardiac Index | |
| `bodyShape` | Body Shape | |

### Girth metrics

Records from `get_girth_measurements()` contain these fields (each with a
paired `*Unit`, where `0` = cm). Unmeasured fields are returned as `0`.

| Key | Description | Unit |
| --- | --- | --- |
| `neckValue` | Neck | cm |
| `shoulderValue` | Shoulder | cm |
| `chestValue` | Chest | cm |
| `waistValue` | Waist | cm |
| `abdomenValue` | Abdomen | cm |
| `hipValue` | Hip | cm |
| `armValue` / `leftArmValue` / `rightArmValue` | Arm | cm |
| `thighValue` / `leftThighValue` / `rightThighValue` | Thigh | cm |
| `calfValue` / `leftCalfValue` / `rightCalfValue` | Calf | cm |
| `whrValue` | Waist-to-hip ratio | |
| `customValue`, `customValue1`…`customValue5` | User-defined measurements | cm |

## Project Structure

```
renpho-api/
├── pyproject.toml        # Package config & dependencies
├── README.md
├── renpho/
│   ├── __init__.py       # Public API exports
│   ├── client.py         # RenphoClient class
│   ├── cli.py            # CLI entry point
│   ├── constants.py      # API endpoints, device types, metrics, girth sites
│   ├── crypto.py         # AES encryption/decryption
│   ├── export.py         # JSON/CSV export helpers
│   └── girth.py          # Smart Tape Measure (body girth) helpers
├── tests/                # Unit tests
└── .github/workflows/    # CI + PyPI release automation
```
