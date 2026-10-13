"""Tests for renpho.export — formatting and file export."""

import json
from pathlib import Path

from renpho.export import format_measurement, format_timestamp, save_csv, save_json


def test_format_timestamp_seconds():
    # 2024-01-15 12:00:00 UTC
    assert "2024" in format_timestamp(1705320000)


def test_format_timestamp_milliseconds():
    # Should auto-detect and convert ms to s
    result = format_timestamp(1705320000000)
    assert "2024" in result


def test_format_timestamp_none():
    assert format_timestamp(None) == "unknown"


def test_format_measurement_basic():
    m = {"timeStamp": 1705320000, "weight": 75.5, "bmi": 23.1}
    result = format_measurement(m)
    assert "75.5" in result
    assert "23.1" in result
    assert "Weight" in result
    assert "BMI" in result


def test_format_measurement_skips_zero():
    m = {"timeStamp": 1705320000, "weight": 75.5, "bodyfat": 0}
    result = format_measurement(m)
    assert "Body Fat" not in result


def test_format_measurement_shows_user_name():
    m = {"timeStamp": 1705320000, "weight": 75.5, "userName": "Kid"}
    assert "User: Kid" in format_measurement(m)


def test_save_json(tmp_path):
    data = [{"weight": 70}, {"weight": 71}]
    filepath = tmp_path / "out" / "data.json"
    result = save_json(data, filepath)
    assert result == filepath
    assert filepath.exists()
    loaded = json.loads(filepath.read_text())
    assert loaded == data


def test_save_csv(tmp_path):
    measurements = [
        {"timeStamp": 1000, "weight": 70.5, "bmi": 22},
        {"timeStamp": 2000, "weight": 71.0, "bmi": 22.5},
    ]
    filepath = tmp_path / "data.csv"
    result = save_csv(measurements, filepath)
    assert result == filepath
    lines = filepath.read_text().strip().split("\n")
    assert len(lines) == 3  # header + 2 rows
    assert "timeStamp" in lines[0]
    assert "weight" in lines[0]


def test_save_csv_empty(tmp_path):
    filepath = tmp_path / "empty.csv"
    assert save_csv([], filepath) is None
    assert not filepath.exists()


def test_save_csv_creates_parents(tmp_path):
    measurements = [{"weight": 70}]
    filepath = tmp_path / "nested" / "dir" / "data.csv"
    save_csv(measurements, filepath)
    assert filepath.exists()
