"""Where things live.

Bundled resources (default themes, Roboto fonts) ship inside the package / exe.
User-editable folders live next to the exe (or the project root when run from
source), so themes can be added or edited without rebuilding:

    themes/      your theme JSON files (defaults copied here on first run)
    posters/     generated posters
    cache/       geocoding + downloaded map data
    fonts/       downloaded Google Fonts
    data/        local .osm.pbf extracts
    layers.json  which OSM tags count as water / parks
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)

if FROZEN:
    APP_DIR = Path(sys.executable).resolve().parent
    RESOURCES = Path(getattr(sys, "_MEIPASS", APP_DIR)) / "mapposter" / "resources"
else:
    APP_DIR = Path(__file__).resolve().parent.parent
    RESOURCES = Path(__file__).resolve().parent / "resources"

APP_DIR = Path(os.environ.get("MAPPOSTER_HOME", APP_DIR))

THEMES_DIR = APP_DIR / "themes"
POSTERS_DIR = APP_DIR / "posters"
PRESETS_DIR = APP_DIR / "presets"
CACHE_DIR = Path(os.environ.get("CACHE_DIR", APP_DIR / "cache"))
FONTS_CACHE_DIR = APP_DIR / "fonts"
DATA_DIR = APP_DIR / "data"
LAYERS_FILE = APP_DIR / "layers.json"

BUNDLED_THEMES = RESOURCES / "themes"
BUNDLED_FONTS = RESOURCES / "fonts"

LAYERS_VERSION = 4
_OLD_PLACE_VALUES = ["suburb", "neighbourhood", "quarter", "town", "village", "hamlet"]

# kind: "polygon" (filled), "line" (stroked), "point" (labels only) or
# "coastline" (turned into ocean fill).
# enabled: default on/off (the window and --layers can override per poster).
DEFAULT_LAYERS = {
    "_comment": "OSM tags for each map layer. Edit to taste: tag values can be a string, "
                "a list, or true (any value). Colors come from the theme.",
    "_version": LAYERS_VERSION,
    "water": {"kind": "polygon", "enabled": True,
              "tags": {"natural": ["water", "bay", "strait"], "waterway": "riverbank",
                       "water": True}},
    "parks": {"kind": "polygon", "enabled": True,
              "tags": {"leisure": ["park", "garden", "golf_course", "nature_reserve"],
                       "landuse": ["grass", "recreation_ground", "forest", "meadow"]}},
    "coastline": {"kind": "coastline", "enabled": True,
                  "tags": {"natural": "coastline"}},
    "waterways": {"kind": "line", "enabled": True,
                  "tags": {"waterway": ["river", "canal"]}},
    "washes": {"kind": "line", "enabled": False,
               "tags": {"waterway": ["stream", "wash", "arroyo", "dry_stream"]}},
    "trails": {"kind": "line", "enabled": False,
               "tags": {"highway": ["path", "track", "bridleway"]}},
    "railways": {"kind": "line", "enabled": False,
                 "tags": {"railway": ["rail", "light_rail", "subway", "tram",
                                      "narrow_gauge", "monorail"]}},
    "airports": {"kind": "polygon", "enabled": False,
                 "tags": {"aeroway": ["aerodrome", "runway", "taxiway", "apron"]}},
    "buildings": {"kind": "polygon", "enabled": False,
                  "tags": {"building": True}},
    "places": {"kind": "point", "enabled": False,
               "tags": {"place": ["city", "town", "suburb", "village", "quarter",
                                  "neighbourhood", "hamlet"]}},
}

LAYER_ORDER = ["coastline", "water", "parks", "airports", "buildings", "waterways",
               "washes", "trails", "railways", "places"]


def ensure_dirs() -> None:
    """Create user folders and seed themes / layers on first run."""
    for d in (THEMES_DIR, POSTERS_DIR, CACHE_DIR, FONTS_CACHE_DIR, DATA_DIR, PRESETS_DIR):
        d.mkdir(parents=True, exist_ok=True)
    # Copy any bundled theme the user doesn't have yet (never overwrite edits).
    if BUNDLED_THEMES.exists():
        for src in BUNDLED_THEMES.glob("*.json"):
            dst = THEMES_DIR / src.name
            if not dst.exists():
                shutil.copy2(src, dst)
    if not LAYERS_FILE.exists():
        LAYERS_FILE.write_text(json.dumps(DEFAULT_LAYERS, indent=2), encoding="utf-8")


def _strip(d: dict) -> dict:
    return {k: v for k, v in d.items() if not k.startswith("_")}


def load_layers() -> dict:
    """All layer definitions: {name: {"kind", "enabled", "tags"}}."""
    try:
        data = json.loads(LAYERS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _strip(DEFAULT_LAYERS)
    if data.get("_version") != LAYERS_VERSION:
        # Older file: add the new layers, keep the user's own edits.
        new = json.loads(json.dumps(DEFAULT_LAYERS))
        for name, spec in data.items():
            if name.startswith("_") or not isinstance(spec, dict):
                continue
            if "tags" not in spec:          # version 1: {"water": {tag spec}}
                if name in new:
                    new[name]["tags"] = spec
            elif name == "waterways" and data.get("_version") == 2:
                continue                    # streams moved to the new "washes" layer
            elif (name == "places" and spec.get("tags", {}).get("place") == _OLD_PLACE_VALUES):
                new[name]["enabled"] = spec.get("enabled", False)   # untouched old default:
                continue                                           # take the new list (adds city)
            else:
                new[name] = spec
        try:
            LAYERS_FILE.write_text(json.dumps(new, indent=2), encoding="utf-8")
        except OSError:
            pass
        data = new
    return _strip(data)


def default_enabled_layers() -> list[str]:
    return [n for n, d in load_layers().items() if d.get("enabled")]
