# renpho-api

[![PyPI](https://img.shields.io/pypi/v/renpho-api)](https://pypi.org/project/renpho-api/)
[![CI](https://github.com/danvaneijck/renpho-api/actions/workflows/ci.yml/badge.svg)](https://github.com/danvaneijck/renpho-api/actions/workflows/ci.yml)
[![Python](https://img.shields.io/pypi/pyversions/renpho-api)](https://pypi.org/project/renpho-api/)

Unofficial Python client for the Renpho Health API. Pull body composition measurements from Renpho smart scales programmatically.

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
from renpho import RenphoClient, normalize_girth, format_girth

client = RenphoClient("user@example.com", "password")
client.login()

girths = client.get_girths()  # raw records, newest first

for record in girths[:5]:
    print(format_girth(record))

# Or reduce a record to just the sites that were measured (zeros omitted):
latest = normalize_girth(girths[0])
# -> {"date": "2024-06-27", "waist": 90.0, "left_arm": 33.0, "hip": 100.0, "whr": 0.9, ...}
```

`normalize_girth()` returns the local measurement `date` (from `timeStamp` +
`timeZone`), each measured site in cm, and `whr` (waist/hip ratio) when present.
A site that was not measured comes back as `0.0` and is omitted rather than
reported as a real zero.

**Site names** returned by `normalize_girth()` / accepted by
`build_girth_record()`: `neck`, `shoulder`, `chest`, `waist`, `hip`, `abdomen`,
`left_arm` / `right_arm` (upper arm), `left_thigh` / `right_thigh`,
`left_calf` / `right_calf`.

### Writing girths (backfill)

`upload_girths()` appends historical measurements (useful for backfilling the
app's history graph). The endpoint only **adds** — there is no in-place
replace, so re-uploading an existing date creates a second entry.

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

acks = client.upload_girths(
    [record],
    time_zone="-5",                    # short form, NOT "-5:00"
    zone_id="America/New_York",
)
# acks -> [{"id": <server id>, "timeStamp": 1719500400}]
```

> **Note:** the upload endpoint returns HTTP 400 (`Missing request header
> 'timeZone'`) unless the fuller app header set is sent. `upload_girths()`
> handles that for you — just pass `time_zone` (short form) and `zone_id`.

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
