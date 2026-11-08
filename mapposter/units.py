"""Distances. The app talks in miles; everything internal is meters."""

from __future__ import annotations

import re

M_PER_MI = 1609.344
M_PER_FT = 0.3048
SQMI_PER_SQM = 1 / (M_PER_MI ** 2)

_UNITS = {"mi": M_PER_MI, "mile": M_PER_MI, "miles": M_PER_MI,
          "ft": M_PER_FT, "feet": M_PER_FT,
          "km": 1000.0, "m": 1.0}


def parse_distance(text, bare: str = "mi") -> float:
    """'5', '5mi', '2.5 miles', '800ft', '8km', '5000m' -> meters.
    A number with no unit counts as `bare` (miles by default)."""
    m = re.fullmatch(r"\s*(\d*\.?\d+)\s*([a-z]*)\s*", str(text).lower())
    if not m or (m.group(2) and m.group(2) not in _UNITS):
        raise ValueError(f"bad distance '{text}' (try 5, 5mi, 800ft, or 8km)")
    return float(m.group(1)) * _UNITS[m.group(2) or bare]


def fmt_miles(meters: float) -> str:
    mi = meters / M_PER_MI
    return f"{mi:.2f} mi" if mi < 1 else f"{mi:g} mi" if mi == round(mi, 1) else f"{mi:.1f} mi"
