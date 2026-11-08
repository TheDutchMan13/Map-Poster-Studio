"""City → coordinates via Nominatim, cached on disk so repeat runs never hit the API."""

from __future__ import annotations

import json
import time

from . import paths
from .log import log

_CACHE = paths.CACHE_DIR / "geocode.json"


def _load() -> dict:
    try:
        return json.loads(_CACHE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save(data: dict) -> None:
    _CACHE.parent.mkdir(parents=True, exist_ok=True)
    _CACHE.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")


def get_coordinates(city: str, country: str) -> tuple[float, float]:
    key = f"{city.strip().lower()}|{country.strip().lower()}"
    cache = _load()
    if key in cache:
        lat, lon = cache[key]["lat"], cache[key]["lon"]
        log(f"✓ Using cached coordinates for {city}, {country}: {lat:.5f}, {lon:.5f}")
        return lat, lon

    from geopy.geocoders import Nominatim

    log("Looking up coordinates...")
    geolocator = Nominatim(user_agent="MapPosterStudio/1.0", timeout=15)
    time.sleep(1)  # Nominatim usage policy: max 1 request/second
    try:
        loc = geolocator.geocode(f"{city}, {country}")
    except Exception as e:
        raise ValueError(f"Geocoding failed for {city}, {country}: {e}") from e
    if not loc:
        raise ValueError(f"Could not find coordinates for {city}, {country}")

    log(f"✓ Found: {getattr(loc, 'address', '')}")
    log(f"✓ Coordinates: {loc.latitude:.5f}, {loc.longitude:.5f}")
    cache[key] = {"lat": loc.latitude, "lon": loc.longitude,
                  "address": getattr(loc, "address", "")}
    _save(cache)
    return loc.latitude, loc.longitude


def parse_coordinate(value: str | float) -> float:
    """Accept 33.45, '33.45', '33°26′53″N', '112.07 W', etc."""
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except ValueError:
        from lat_lon_parser import parse
        return float(parse(value))
