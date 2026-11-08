"""Fonts: bundled Roboto by default, or any Google Fonts family (downloaded + cached)."""

from __future__ import annotations

import re

from . import paths
from .log import log

WEIGHTS = {300: "light", 400: "regular", 700: "bold"}


def roboto() -> dict | None:
    fonts = {
        "bold": paths.BUNDLED_FONTS / "Roboto-Bold.ttf",
        "regular": paths.BUNDLED_FONTS / "Roboto-Regular.ttf",
        "light": paths.BUNDLED_FONTS / "Roboto-Light.ttf",
    }
    if all(p.exists() for p in fonts.values()):
        return {k: str(v) for k, v in fonts.items()}
    log("⚠ Bundled Roboto fonts missing; using system monospace")
    return None


def _download_google_font(family: str) -> dict | None:
    import requests

    safe = re.sub(r"[^a-z0-9]+", "_", family.lower()).strip("_")
    paths.FONTS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    cached = {key: paths.FONTS_CACHE_DIR / f"{safe}_{key}.ttf" for key in WEIGHTS.values()}
    if all(p.exists() for p in cached.values()):
        log(f"✓ Using cached font {family}")
        return {k: str(v) for k, v in cached.items()}

    # A bare user agent makes Google serve TrueType (.ttf), which matplotlib reads
    # directly (it can't read .woff2).
    resp = requests.get(
        "https://fonts.googleapis.com/css2",
        params={"family": f"{family}:wght@300;400;700"},
        headers={"User-Agent": "MapPosterStudio"},
        timeout=15,
    )
    if resp.status_code == 400:
        # Family may not offer all three weights; ask for whatever exists.
        resp = requests.get(
            "https://fonts.googleapis.com/css2",
            params={"family": family},
            headers={"User-Agent": "MapPosterStudio"},
            timeout=15,
        )
    resp.raise_for_status()

    url_by_weight: dict[int, str] = {}
    for block in re.split(r"@font-face\s*\{", resp.text)[1:]:
        w = re.search(r"font-weight:\s*(\d+)", block)
        u = re.search(r"url\((https://[^)]+)\)", block)
        if w and u:
            # Several unicode-range blocks per weight: keep the first (latin-ext is
            # usually last; any one file covers the whole family for TTF output).
            url_by_weight.setdefault(int(w.group(1)), u.group(1))
    if not url_by_weight:
        return None

    files: dict[str, str] = {}
    for weight, key in WEIGHTS.items():
        best = min(url_by_weight, key=lambda x: abs(x - weight))
        dest = cached[key]
        if not dest.exists():
            log(f"  Downloading {family} {key} ({best})...")
            r = requests.get(url_by_weight[best], timeout=30)
            r.raise_for_status()
            dest.write_bytes(r.content)
        files[key] = str(dest)
    return files


def font_files(path: str) -> dict | None:
    """Your own font: one .ttf/.otf used for every weight, or a folder whose file
    names contain Bold / Light / Regular."""
    from pathlib import Path
    p = Path(path)
    if p.is_file():
        return {"bold": str(p), "regular": str(p), "light": str(p)}
    if p.is_dir():
        files = sorted([*p.glob("*.ttf"), *p.glob("*.otf")])
        if not files:
            return None

        def pick(*words):
            for w in words:
                for f in files:
                    if w in f.stem.lower():
                        return str(f)
            return None
        regular = pick("regular", "book", "roman") or str(files[0])
        return {"regular": regular, "bold": pick("bold", "black", "heavy") or regular,
                "light": pick("light", "thin") or regular}
    return None


def load_fonts(family: str | None = None, font_file: str | None = None) -> dict | None:
    if font_file:
        f = font_files(font_file)
        if f:
            log(f"✓ Using your font {font_file}")
            return f
        log(f"⚠ No usable font at {font_file}")
    if family and family.strip().lower() != "roboto":
        try:
            log(f"Loading Google Font: {family}")
            f = _download_google_font(family.strip())
            if f:
                log(f"✓ Font '{family}' loaded")
                return f
        except Exception as e:  # network, bad name, ...
            log(f"⚠ Could not load Google Font '{family}': {e}")
        log("⚠ Falling back to Roboto")
    return roboto()
