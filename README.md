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

1. Create a `.env` file (copy `.env.example`, or export the variables):

```ini
RENPHO_EMAIL=your@email.com
RENPHO_PASSWORD=your_plain_text_password
```

2. Run the CLI:

```bash
renpho            # or, from a source checkout: python -m renpho
```

This will log in, discover your scales, fetch all measurements, print the 5 most
recent, and save everything to `renpho_data/` as JSON and CSV. If the account has
a smart tape measure it also writes `girth.json` / `girth.csv`; accounts without
one simply report no girth records.

The CLI exports measurements for you and every family member on the account.
Each row is tagged with a `userName` field, and the family profiles are saved to
`family_members.json`. Session tokens and password fields are never written to
these files.

Set `RENPHO_SESSION_FILE` to reuse the login between runs: the CLI then logs in
only when the saved session has been ended by another login (see
[Sessions](#sessions-reusing-a-login)). A run that reuses a session doesn't know
your display name, so your own rows have no `userName` that time.

### Environment variables

| Variable | Required | Description |
| --- | --- | --- |
| `RENPHO_EMAIL` | Yes | Your Renpho account email |
| `RENPHO_PASSWORD` | Yes | Your Renpho account password |
| `RENPHO_DEBUG` | No | Set to `1` to print API request/response details |
| `RENPHO_OUTPUT_DIR` | No | Output directory (default: `renpho_data`) |
| `RENPHO_FRIEND_ID` | No | Read this friend's daily data instead of your own (see [Reading through a friend account](#reading-through-a-friend-account)) |
| `RENPHO_SESSION_FILE` | No | Save the session here and reuse it on the next run (e.g. `~/.config/renpho/session.json`) |

## Library Usage

```python
from renpho import RenphoClient

client = RenphoClient("user@example.com", "password")
client.login()

# All of your measurements, newest first. Family members who share the scale
# are not included (see "Family members" below).
measurements = client.get_all_measurements()

for m in measurements:
    print(m["weight"], m.get("bodyfat"), m.get("muscle"))

import renpho
print(renpho.__version__)
```

### Step-by-step control

```python
from renpho import RenphoClient, save_json, save_csv

client = RenphoClient("user@example.com", "password")
client.login()

# Get device/scale info
device_info = client.get_device_info()
scales = device_info["scale"]

# Fetch your rows from a scale table that lists you. The server only returns
# rows for the user id you pass, even on a table shared with family members.
# Use get_body_composition_measurements() for scales with impedance sensors
# (body fat, muscle, etc.) and fall back to get_measurements() when it comes
# back empty. Don't pass the table's "count" as a total: it counts every
# person on that table.
table = next(s for s in scales if str(client.user_id) in map(str, s["userIds"]))
measurements = client.get_body_composition_measurements(
    table_name=table["tableName"],
    user_id=client.user_id,
)
if not measurements:
    measurements = client.get_measurements(
        table_name=table["tableName"],
        user_id=client.user_id,
    )

# Export
save_json(measurements, "my_data.json")
save_csv(measurements, "my_data.csv")
```

### Family members (sub-users)

Profiles added under your account in the app (e.g. family members sharing a
scale) can be listed with `get_family_members()`. The logged-in user is not part
of that list; their own profile is in `client.user_info`.

```python
names = {str(client.user_id): client.user_info["accountName"]}
for member in client.get_family_members():
    names[str(member["id"])] = member["accountName"]

# {'5981614576857776000': 'Alice', '5991064042346217344': 'Bob'}
```

Each entry is a full profile dict. Its `id` matches the `userIds` listed per
scale in `get_device_info()` and the `bUserId` field on measurement records.
Compare IDs as strings, since they arrive as both `int` and `str`.

To fetch a family member's measurements, pass their `id`:

```python
family = client.get_family_members()

# One person instead of you:
kid = client.get_all_measurements(profile_user_id=family[0]["id"])

# You plus everyone; bUserId says whose each row is:
everyone = client.get_all_measurements(extra_user_ids=[m["id"] for m in family])
```

### Reading through a friend account

Renpho allows one active session per account, so logging in with your main
account signs the phone app out. To sync without that, read your data through
Renpho's friends feature from a second account:

1. Create a second Renpho account with an email and password. An account
   created with "Sign in with Google" or Apple has no password and can't log in
   through the API.
2. In the Renpho app, add the second account as a friend of your main account
   and accept the request.
3. Log in as the second account and read your main account's data:

```python
client = RenphoClient("second@example.com", "password")
friend = client.get_friends()[0]          # {"userId", "accountName", ...}

days = client.get_friend_measurements(friend["userId"])
# [{"day": "2026-11-02", "timeStamp": ..., "weight": 79.5, "bodyfat": 20.1, ...}, ...]
```

With the CLI, set `RENPHO_FRIEND_ID` to the friend's `userId`. It writes
`friend_daily.json` and `friend_daily.csv` instead of the usual files.

`get_friend_trend(friend_id, param)` returns the daily points for a single
parameter, and `get_friend_summary()` and `get_friend_measure_days()` return
the server's raw responses.

Limits of the friend endpoints:

- One value per day (the last weigh-in that day).
- Body composition values only on days the scale measured them.
- One call covers a limited window. For older data, move `end_time` (unix
  seconds) back.
- No segmental or girth data.
- Days are grouped by a whole-hour UTC offset, by default this machine's
  (`time_zone=` to override).

This approach was worked out in
[#14](https://github.com/danvaneijck/renpho-api/issues/14), with a reference
implementation at
[DawidKrynski/renpho-friends](https://github.com/DawidKrynski/renpho-friends).

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

A password login can land on either account. If you know which one you want,
pass its ID to `login()`. On a mismatch the session is cleared and
`RenphoAPIError` is raised, so nothing reads the wrong account's data:

```python
client.login(expected_user_id="5975813831868809088")
```

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

### Sessions: reusing a login

Two facts, checked on a live account in November 2026, shape how to use the API:

- **One session per account.** Any login ends every other session on the
  account, on any platform. Logging in from a script signs the phone app out,
  and logging back in on the phone ends the script's session. (Sending
  `platform: "web"` does not get around this.)
- **Tokens last 90 days.** Until another login ends it, a session can be
  reused for months.

So a script that runs often should keep its session instead of logging in each
time:

```python
client = RenphoClient("user@example.com", "password",
                      session_file="~/.config/renpho/session.json")
measurements = client.get_all_measurements()  # logs in only if no usable saved session
```

The file is written with mode `0600` and holds the session token, not the
password. Treat it like a password anyway: it grants access to the account
until it expires.

When another login has ended the saved session, calls raise
`RenphoSessionError`. Pass `auto_relogin=True` to log in again and retry once
instead. That login signs the phone app out again, which is why it is off by
default. To avoid that conflict entirely, read your data from a second account
(see [Reading through a friend account](#reading-through-a-friend-account)),
which then only needs to log in once every 90 days.

Lower-level pieces: `client.token_expires_at` (unix seconds, from the token),
`client.get_token_info()` (asks the server; raises `RenphoSessionError` if the
session is dead), and `export_session()` / `import_session()` /
`save_session()` / `load_session()`.

### Devices and data counts

After `login()`, `client.devices` lists the scales and other devices bound to
the account, each with `deviceModel`, `deviceName`, `deviceType`, `mac`,
`firmwareVersion` and a `connection` of `"bluetooth"` or `"wifi"`.

```python
client.get_measurement_count()   # 31: your total, in one cheap request
client.get_data_counts()         # tables per store, plus girth/rope/treadmill/step/goal totals
```

`get_measurement_count()` is a cheap "has anything new arrived?" check before a
full fetch. `get_data_counts()` is what the Renpho app uses in place of
`get_device_info()`: it lists each measurement table for both the legacy scale
store (`scale`) and the body composition store (`compositionScale`), and
`get_all_measurements()` uses those counts to read only the stores that hold
rows.

### Experimental endpoints

These were found in the Renpho Health app (7.11.6) and answer on a live
account, but that account had none of this data, so the fields of individual
records are unconfirmed. They return the server's data as-is.

| Method | Returns |
| --- | --- |
| `get_unassigned_measurements()` | Weigh-ins the scale couldn't attribute to a profile |
| `get_third_party_measurements()` | Measurements imported from other apps (Fitbit, Health Connect, Samsung Health) |
| `get_third_party_sources()` | The third-party sources linked to the account |
| `get_goals()` | `{"scale": [...], "girth": [...]}` goals set in the app |

If you have this kind of data, an issue with the (redacted) record shapes would
help firm these up.

[docs/endpoints.md](docs/endpoints.md) lists every endpoint the Renpho app
uses (366 paths), with request payloads, error codes and what has been
verified for each.

### Error handling

Every API error is a `RenphoAPIError` (with `.code`, `.msg`, `.context`).
Specific cases have subclasses:

| Exception | When |
| --- | --- |
| `RenphoAuthError` | Wrong password or unknown email (codes 104, 106, 20001), or `login(expected_user_id=...)` landed on another account |
| `RenphoSessionError` | The session expired or another login replaced it (401/403) |
| `RenphoRateLimitError` | Too many requests (429) |

```python
from renpho import RenphoAPIError, RenphoAuthError, RenphoClient, RenphoSessionError

client = RenphoClient("user@example.com", "password")
try:
    measurements = client.get_all_measurements()
except RenphoAuthError:
    print("Check the email and password")
except RenphoSessionError:
    print("Signed out by another login; log in again")
except RenphoAPIError as e:
    print(f"API error: {e}")
```

Requests time out after 10 s to connect and 30 s to read by default. Pass
`RenphoClient(..., timeout=60)` (or a `(connect, read)` pair) to change that.

### Troubleshooting login

- **`code=-114` ("Decryption failed …").** Renpho's gateway changed in October
  2026 and now needs an `appVersion` header on the login request. Upgrade to
  `renpho-api>=0.2.1`. `APP_VERSION` must stay below `8.0.0`, because the
  bundled AES key only works for app versions before 8.0.0.
- **`code=104` ("wrong user name or password") with a correct password.**
  Upgrade to 0.2.1 first. If it persists, check whether the account signs in
  with Google or Apple (next point), and if not, report it in
  [#10](https://github.com/danvaneijck/renpho-api/issues/10).
- **Your account signs in with Google or Apple.** These accounts have no
  password, so they cannot log in through the API.
- **The phone app logs you out after a sync.** Renpho allows one active
  session per account, so every `login()` ends the app's session. Reuse the
  session between runs to log in far less often (see
  [Sessions](#sessions-reusing-a-login)), or read your data from a second
  account so the phone is never signed out (see
  [Reading through a friend account](#reading-through-a-friend-account)).

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

```text
renpho-api/
├── pyproject.toml        # Package config & dependencies
├── README.md
├── renpho/
│   ├── __init__.py       # Public API exports
│   ├── __main__.py       # python -m renpho
│   ├── client.py         # RenphoClient class
│   ├── cli.py            # CLI entry point
│   ├── constants.py      # API endpoints, device types, metrics, girth sites
│   ├── crypto.py         # AES encryption/decryption
│   ├── export.py         # JSON/CSV export helpers
│   ├── girth.py          # Smart Tape Measure (body girth) helpers
│   └── py.typed          # Marks the package as typed for type checkers
├── docs/endpoints.md     # Every known API endpoint: payloads, codes, status
├── tests/                # Unit tests (network access is blocked)
├── Makefile              # make test / make lint / make check
└── .github/workflows/    # CI (ruff + tests) and PyPI release automation
```
