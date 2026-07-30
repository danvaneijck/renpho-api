"""Command-line interface for pulling Renpho scale data."""

import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from .client import RenphoAPIError, RenphoClient
from .export import format_girth, format_measurement, save_csv, save_json


def main(argv: list[str] | None = None) -> None:
    """Entry point for the ``renpho`` CLI command."""
    email = os.getenv("RENPHO_EMAIL", "")
    password = os.getenv("RENPHO_PASSWORD", "")
    debug = os.getenv("RENPHO_DEBUG", "").lower() in ("1", "true", "yes")
    output_dir = Path(os.getenv("RENPHO_OUTPUT_DIR", "renpho_data"))

    if not email or not password:
        print("Missing credentials!\n")
        print("Create a .env file with:")
        print("  RENPHO_EMAIL=your@email.com")
        print("  RENPHO_PASSWORD=your_plain_text_password")
        print("  RENPHO_DEBUG=1  # optional")
        sys.exit(1)

    client = RenphoClient(email, password, debug=debug)

    # Step 1: Login
    print(f"Logging in as {email}...")
    client.login()
    print(f"Logged in! User ID: {client.user_id}")

    # Step 2: Device info
    print("Getting device info...")
    device_info = client.get_device_info()

    if not device_info:
        print("Could not get device info")
        sys.exit(1)

    save_json(device_info, output_dir / "device_info.json")

    scales = device_info.get("scale", [])
    if not scales:
        print("No scales found in device info")
        print(f"  Device info keys: {list(device_info.keys())}")
        sys.exit(1)

    print(f"\nFound {len(scales)} scale table(s):")
    for i, scale in enumerate(scales):
        table = scale.get("tableName", "unknown")
        count = scale.get("count", 0)
        uids = scale.get("userIds", [])
        print(f"  [{i}] table={table}, records={count}, users={uids}")

    # Step 3: Fetch measurements
    all_measurements: list[dict] = []
    for scale in scales:
        table_name = scale.get("tableName")
        count = scale.get("count", 0)
        user_ids = scale.get("userIds", [])

        if not table_name or count == 0:
            continue

        uid = client.user_id
        if user_ids and uid not in user_ids:
            uid = user_ids[0]

        print(f"Fetching measurements (table: {table_name}, total: {count})...")
        measurements = client.get_measurements(table_name, uid, count)
        all_measurements.extend(measurements)

    if all_measurements:
        # Sort newest first
        all_measurements.sort(
            key=lambda m: m.get("timeStamp", 0) or 0,
            reverse=True,
        )

        print(f"\nTotal: {len(all_measurements)} measurement(s)")

        # Display most recent 5
        for i, m in enumerate(all_measurements[:5]):
            print(f"\n{'=' * 55}")
            print(f"  Measurement #{i + 1}")
            print(f"{'=' * 55}")
            print(format_measurement(m))

        if len(all_measurements) > 5:
            print(f"\n  ... and {len(all_measurements) - 5} more")

        # Save data
        save_json(all_measurements, output_dir / "measurements.json")
        save_csv(all_measurements, output_dir / "measurements.csv")
    else:
        print("\nNo scale measurements found.")
        print("  Try setting RENPHO_DEBUG=1 to see API responses.")

    # Step 4: Girth (tape-measure) data
    print("\nFetching girth (tape-measure) data...")
    try:
        girth = client.get_girth_measurements()
    except RenphoAPIError as e:
        print(f"  Girth fetch failed: {e}")
        girth = []

    if girth:
        print(f"Total: {len(girth)} girth record(s)")
        for i, g in enumerate(girth[:3]):
            print(f"\n{'=' * 55}")
            print(f"  Girth #{i + 1}")
            print(f"{'=' * 55}")
            print(format_girth(g))
        if len(girth) > 3:
            print(f"\n  ... and {len(girth) - 3} more")
        save_json(girth, output_dir / "girth.json")
        save_csv(girth, output_dir / "girth.csv")
    else:
        print("  No girth records found.")

    if client.user_info:
        save_json(client.user_info, output_dir / "user_profile.json")

    print(f"\nDone! Data saved to '{output_dir}/' folder.")
