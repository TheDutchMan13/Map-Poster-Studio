"""Theme loading. A theme is a JSON file of colors in the themes/ folder."""

from __future__ import annotations

import json
from pathlib import Path

from . import paths

REQUIRED_KEYS = (
    "bg", "text", "gradient_color", "water", "parks",
    "road_motorway", "road_primary", "road_secondary",
    "road_tertiary", "road_residential", "road_default",
)

FALLBACK = {
    "name": "Terracotta",
    "description": "Mediterranean warmth - burnt orange and clay tones on cream",
    "bg": "#F5EDE4",
    "text": "#8B4513",
    "gradient_color": "#F5EDE4",
    "water": "#A8C4C4",
    "parks": "#E8E0D0",
    "road_motorway": "#A0522D",
    "road_primary": "#B8653A",
    "road_secondary": "#C9846A",
    "road_tertiary": "#D9A08A",
    "road_residential": "#E5C4B0",
    "road_default": "#D9A08A",
}


# Optional colors for the extra layers. If a theme doesn't set them they are
# derived from its other colors, so all old themes keep working.
OPTIONAL_KEYS = ("ocean", "waterway", "washes", "trails", "railway", "buildings", "airports",
                 "marker", "route", "border", "highlight", "labels", "contours", "hillshade")

EDITABLE_KEYS = REQUIRED_KEYS + OPTIONAL_KEYS


def mix(c1: str, c2: str, t: float) -> str:
    """Blend two hex colors: t=0 -> c1, t=1 -> c2."""
    from matplotlib.colors import to_hex, to_rgb
    a, b = to_rgb(c1), to_rgb(c2)
    return to_hex(tuple(x + (y - x) * t for x, y in zip(a, b)))


def derived(theme: dict) -> dict:
    return {
        "ocean": theme["water"],
        "waterway": theme["water"],
        "railway": mix(theme["bg"], theme["text"], 0.45),
        "buildings": mix(theme["bg"], theme["road_residential"], 0.45),
        "airports": mix(theme["bg"], theme["road_default"], 0.35),
        "marker": theme["road_motorway"],
        "route": theme["text"],
        "border": theme["text"],
        "washes": mix(theme["bg"], theme["water"], 0.7),
        "trails": mix(theme["bg"], theme["road_tertiary"], 0.8),
        "highlight": theme["road_motorway"],
        "labels": mix(theme["text"], theme["bg"], 0.2),
        "contours": mix(theme["bg"], theme["text"], 0.42),
        "hillshade": _shadow(theme),
    }


def _luminance(c: str) -> float:
    from matplotlib.colors import to_rgb
    r, g, b = to_rgb(c)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _shadow(theme: dict) -> str:
    """Hill shadows: darker than the background; on near-black backgrounds use a
    faint light tone instead so the relief still shows."""
    if _luminance(theme["bg"]) < 0.1:
        return mix(theme["bg"], theme["text"], 0.45)
    return mix(theme["bg"], "#000000", 0.7)


def available_themes() -> list[str]:
    if not paths.THEMES_DIR.exists():
        return []
    return sorted(p.stem for p in paths.THEMES_DIR.glob("*.json"))


def theme_path(name: str) -> Path:
    return paths.THEMES_DIR / f"{name}.json"


def load_theme(name: str = "terracotta") -> dict:
    """Load a theme; missing keys are filled sensibly so partial themes work."""
    p = theme_path(name)
    if not p.exists():
        theme = dict(FALLBACK)
        theme.update(derived(theme))
        theme["_key"] = name
        return theme
    with open(p, encoding="utf-8") as f:
        theme = json.load(f)
    # Fill gaps so a hand-made theme with only a few colors still renders.
    theme.setdefault("gradient_color", theme.get("bg", FALLBACK["bg"]))
    theme.setdefault("road_default", theme.get("road_tertiary", FALLBACK["road_default"]))
    for k in REQUIRED_KEYS:
        theme.setdefault(k, FALLBACK[k])
    for k, v in derived(theme).items():
        theme.setdefault(k, v)
    theme.setdefault("name", name)
    theme["_key"] = name
    return theme


def describe_themes() -> list[tuple[str, str, str]]:
    out = []
    for key in available_themes():
        try:
            t = json.loads(theme_path(key).read_text(encoding="utf-8"))
            out.append((key, t.get("name", key), t.get("description", "")))
        except (OSError, json.JSONDecodeError):
            out.append((key, key, "(could not read file)"))
    return out


def save_theme(key: str, theme: dict) -> None:
    """Write a theme file (only its own keys, not internal ones)."""
    data = {k: v for k, v in theme.items() if not k.startswith("_")}
    paths.THEMES_DIR.mkdir(parents=True, exist_ok=True)
    theme_path(key).write_text(json.dumps(data, indent=2), encoding="utf-8")
