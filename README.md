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
