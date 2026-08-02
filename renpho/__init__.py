"""renpho - Unofficial Python client for the Renpho Health API.

Pull body composition measurements from Renpho smart scales, and circumference
measurements from the Renpho Smart Tape Measure.

Quick start::

    from renpho import RenphoClient

    client = RenphoClient("user@example.com", "password")
    client.login()
    measurements = client.get_all_measurements()     # smart scale
    girths = client.get_girth_measurements()         # smart tape measure
"""

from .client import RenphoAPIError, RenphoClient
from .export import (
    format_girth,
    format_measurement,
    format_timestamp,
    save_csv,
    save_json,
)
from .girth import build_girth_record, girth_date, normalize_girth

__all__ = [
    "RenphoClient",
    "RenphoAPIError",
    "format_measurement",
    "format_timestamp",
    "save_csv",
    "save_json",
    # smart tape measure (body girth)
    "build_girth_record",
    "format_girth",
    "girth_date",
    "normalize_girth",
]
