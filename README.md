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

The library will probe every measurement table for that user ID, fetch
matching records, and dedupe by record `id` so you get a single combined
timeline.

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
### Girth (tape-measure) data

Body circumference measurements from Renpho smart tape measures (e.g. the
R-Y002) are stored separately from scale data and are fetched with a dedicated
method:

```python
from renpho import RenphoClient, save_json, save_csv

client = RenphoClient("user@example.com", "password")

girth = client.get_girth_measurements()  # logs in automatically if needed

for g in girth:
    print(g["waistValue"], g["hipValue"], g.get("chestValue"))

save_json(girth, "girth.json")
save_csv(girth, "girth.csv")
```

The `renpho` CLI also fetches girth data automatically, saving it to
`girth.json` / `girth.csv` alongside the scale exports.

### Error handling

```python
from renpho import RenphoClient, RenphoAPIError

client = RenphoClient("user@example.com", "wrong_password")
try:
    client.login()
except RenphoAPIError as e:
    print(f"API error: {e}")
```

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
│   ├── constants.py      # API endpoints, device types, metrics
│   ├── crypto.py         # AES encryption/decryption
│   └── export.py         # JSON/CSV export helpers
├── tests/                # Unit tests
└── .github/workflows/    # CI + PyPI release automation
```
