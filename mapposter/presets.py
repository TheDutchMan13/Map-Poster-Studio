"""Saved looks: every poster setting except the place itself, stored as JSON in presets/."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, fields

from . import paths
from .log import log

# Settings that describe WHERE, not HOW: never stored in a preset.
PLACE_FIELDS = {"city", "country", "latitude", "longitude", "display_city",
                "display_country", "country_label", "markers", "gpx", "highlight",
                "highlight_file", "highlight_label", "set_places", "preview",
                "boundary_file", "photo", "qr"}


def _file(name: str):
    safe = re.sub(r"[^\w -]+", "_", name.strip()).strip() or "preset"
    return paths.PRESETS_DIR / f"{safe}.json"


def list_presets() -> list[str]:
    if not paths.PRESETS_DIR.exists():
        return []
    return sorted(p.stem for p in paths.PRESETS_DIR.glob("*.json"))


def save_preset(name: str, job) -> None:
    data = {k: v for k, v in asdict(job).items() if k not in PLACE_FIELDS}
    paths.PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    _file(name).write_text(json.dumps(data, indent=2), encoding="utf-8")
    log(f"✓ Saved preset '{name}'")


def load_preset(name: str) -> dict:
    f = _file(name)
    if not f.exists():
        raise ValueError(f"Preset '{name}' not found. Saved presets: "
                         f"{', '.join(list_presets()) or 'none'}")
    data = json.loads(f.read_text(encoding="utf-8"))
    from .core import Job
    known = {f.name for f in fields(Job)}
    return {k: v for k, v in data.items() if k in known and k not in PLACE_FIELDS}


def delete_preset(name: str) -> None:
    f = _file(name)
    if f.exists():
        f.unlink()
