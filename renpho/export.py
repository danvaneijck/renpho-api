"""Helpers for formatting, displaying, and exporting Renpho measurements."""

import datetime
import json
from pathlib import Path

from .constants import GIRTH_METRICS, METRICS


def format_timestamp(ts) -> str:
    """Convert a Renpho timestamp (seconds or milliseconds) to a readable string."""
    if ts is None:
        return "unknown"
    ts = int(ts)
    if ts > 1e12:
        ts = ts // 1000
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def format_measurement(m: dict) -> str:
    """Return a human-readable string for a single measurement."""
    ts = m.get("timeStamp") or m.get("time_stamp")
    local = m.get("localCreatedAt", "")
    scale = m.get("scaleName", "")

    lines = [f"  Date: {format_timestamp(ts)}"]
    if local:
        lines.append(f"  Local time: {local}")
    if scale:
        lines.append(f"  Scale: {scale}")

    for key, label, unit in METRICS:
        value = m.get(key)
        if value is not None and value != 0 and value != 0.0:
            unit_str = f" {unit}" if unit else ""
            lines.append(f"  {label:<22} {value}{unit_str}")

    return "\n".join(lines)


def format_girth(m: dict) -> str:
    """Return a human-readable string for a single girth (tape-measure) record."""
    ts = m.get("timeStamp") or m.get("time_stamp")
    device = m.get("scaleName", "")

    lines = [f"  Date: {format_timestamp(ts)}"]
    if device:
        lines.append(f"  Device: {device}")

    for key, label, unit in GIRTH_METRICS:
        value = m.get(key)
        if value is not None and value != 0 and value != 0.0:
            unit_str = f" {unit}" if unit else ""
            lines.append(f"  {label:<22} {value}{unit_str}")

    return "\n".join(lines)


def save_json(data, filepath: str | Path) -> Path:
    """Write *data* as pretty-printed JSON.

    Parent directories are created automatically.

    Returns:
        The resolved :class:`~pathlib.Path` that was written.
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2, default=str)
    return filepath


def save_csv(measurements: list[dict], filepath: str | Path) -> Path | None:
    """Write measurements to a CSV file.

    Columns are ordered with the most useful metrics first, followed by any
    remaining keys in alphabetical order.

    Returns:
        The resolved :class:`~pathlib.Path` that was written, or ``None`` if
        *measurements* is empty.
    """
    if not measurements:
        return None

    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    priority = [
        "timeStamp", "localCreatedAt",
        *(key for key, _, _ in METRICS),
        "scaleName", "height", "gender",
    ]

    all_keys: set[str] = set()
    for m in measurements:
        all_keys.update(m.keys())

    columns = [k for k in priority if k in all_keys]
    columns += sorted(k for k in all_keys if k not in columns)

    with open(filepath, "w") as f:
        f.write(",".join(columns) + "\n")
        for m in measurements:
            row = []
            for k in columns:
                val = m.get(k, "")
                val_str = str(val).replace(",", ";") if val is not None else ""
                row.append(val_str)
            f.write(",".join(row) + "\n")

    return filepath
