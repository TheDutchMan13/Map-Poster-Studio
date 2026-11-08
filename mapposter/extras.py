"""Extras: city boundary lookup, wall mockups, batch CSV."""

from __future__ import annotations

import csv
import pickle
import re
from pathlib import Path

from . import paths
from .log import log


# ---------------------------------------------------------------- boundary

def city_boundary(city: str, country: str, boundary_file: str | None = None):
    """City outline as a shapely (Multi)Polygon in lat/lon, or None."""
    return place_polygon(f"{city}, {country}", boundary_file)


def place_polygon(query: str, file: str | None = None):
    """Outline of any named place ("Encanto, Phoenix, AZ") from OpenStreetMap via
    Nominatim, or from a GeoJSON / GPKG / SHP file. Lat/lon (Multi)Polygon or None."""
    import geopandas as gpd
    from shapely.ops import unary_union

    if file:
        g = gpd.read_file(file).to_crs("EPSG:4326")
        return unary_union(g.geometry.values)

    safe = re.sub(r"[^\w]+", "_", query.lower())
    cache = paths.CACHE_DIR / f"boundary_{safe}.pkl"
    if cache.exists():
        try:
            return pickle.loads(cache.read_bytes())
        except Exception:
            pass
    try:
        import osmnx as ox
        log(f"Looking up the outline of {query}...")
        g = ox.geocode_to_gdf(query)
        geom = g.geometry.iloc[0]
        if geom.geom_type not in ("Polygon", "MultiPolygon"):
            log(f"⚠ OpenStreetMap has no outline for {query}")
            return None
        cache.write_bytes(pickle.dumps(geom))
        return geom
    except Exception as e:
        log(f"⚠ Could not get the outline of {query}: {e}")
        return None


# ------------------------------------------------------------------ mockup

FRAMES = {
    "black": ("#1b1b1b", "#2a2a2a"),
    "white": ("#f4f4f2", "#dcdcd8"),
    "oak": ("#b98a57", "#8f6537"),
}


def make_mockup(poster: Path, frame: str = "black", wall: str = "#e8e3db") -> Path:
    """Framed poster on a wall, saved next to the poster as *_mockup.jpg."""
    from PIL import Image, ImageDraw, ImageFilter

    img = Image.open(poster).convert("RGB")
    W, H = 2400, 1800
    canvas = Image.new("RGB", (W, H), wall)

    # soft light falloff on the wall
    shade = Image.radial_gradient("L").resize((W, H)).point(lambda v: int(v * 0.28))
    canvas = Image.composite(Image.new("RGB", (W, H), "#000000"), canvas, shade)

    # poster size: fit inside 70% of the wall height / 60% width
    ph = int(H * 0.68)
    pw = int(ph * img.width / img.height)
    if pw > W * 0.6:
        pw = int(W * 0.6)
        ph = int(pw * img.height / img.width)
    mat = int(min(pw, ph) * 0.07)
    fw = int(min(pw, ph) * 0.035)
    outer_w, outer_h = pw + 2 * (mat + fw), ph + 2 * (mat + fw)
    x0, y0 = (W - outer_w) // 2, int((H - outer_h) * 0.42)

    # drop shadow
    sh = Image.new("L", (W, H), 0)
    ImageDraw.Draw(sh).rectangle([x0 + 18, y0 + 30, x0 + outer_w + 18, y0 + outer_h + 30],
                                 fill=150)
    sh = sh.filter(ImageFilter.GaussianBlur(28))
    canvas = Image.composite(Image.new("RGB", (W, H), "#3a3530"), canvas, sh)

    face, edge = FRAMES.get(frame, FRAMES["black"])
    d = ImageDraw.Draw(canvas)
    d.rectangle([x0, y0, x0 + outer_w, y0 + outer_h], fill=face, outline=edge, width=3)
    d.rectangle([x0 + fw, y0 + fw, x0 + outer_w - fw, y0 + outer_h - fw], fill="#fbfbf8")
    canvas.paste(img.resize((pw, ph), Image.LANCZOS), (x0 + fw + mat, y0 + fw + mat))
    # inner bevel line on the mat
    d.rectangle([x0 + fw + mat - 2, y0 + fw + mat - 2, x0 + fw + mat + pw + 1,
                 y0 + fw + mat + ph + 1], outline="#d8d6d0", width=2)

    out = poster.with_name(poster.stem + "_mockup.jpg")
    canvas.save(out, quality=92)
    log(f"✓ Mockup {out.name}")
    return out


# ------------------------------------------------------------------- batch

_ALIASES = {
    "theme": "themes", "distance": "distance_mi", "radius": "distance_mi",
    "radius_mi": "distance_mi", "miles": "distance_mi", "radius_km": "distance_km", "lat": "latitude", "lon": "longitude", "long": "longitude",
    "format": "fmt", "font": "font_family", "marker": "markers",
}


def read_batch(csv_path: str | Path) -> list[dict]:
    """Rows of a CSV as dicts with normalized column names.
    Multiple themes / markers in one cell are separated by ';'."""
    rows = []
    with open(csv_path, newline="", encoding="utf-8-sig") as fh:
        for raw in csv.DictReader(fh):
            row = {}
            for k, v in raw.items():
                if k is None or v is None or not str(v).strip():
                    continue
                key = k.strip().lower().replace(" ", "_").replace("-", "_")
                row[_ALIASES.get(key, key)] = str(v).strip()
            if row.get("city"):
                rows.append(row)
    return rows


# --------------------------------------------------------- sample for editor

def sample_data():
    """A small made-up town (lat/lon near 0,0) for instant theme previews."""
    import geopandas as gpd
    import numpy as np
    import shapely
    from .sources import MapData

    rng = np.random.default_rng(7)
    d = 0.009  # ~0.6 mi
    lines, hw = [], []
    for i, v in enumerate(np.linspace(-d, d, 23)):
        cls = "primary" if i == 11 else ("tertiary" if i % 6 == 0 else "residential")
        jitter = rng.normal(0, 0.00015, 2)
        lines.append(shapely.LineString([(v + jitter[0], -d * 1.4), (v + jitter[1], d * 1.4)]))
        hw.append(cls)
    for i, v in enumerate(np.linspace(-d * 1.4, d * 1.4, 31)):
        cls = "secondary" if i == 15 else ("tertiary" if i % 7 == 0 else "residential")
        lines.append(shapely.LineString([(-d, v), (d, v + rng.normal(0, 0.0002))]))
        hw.append(cls)
    for _ in range(140):  # footpaths / service roads
        x, y = rng.uniform(-d, d), rng.uniform(-d * 1.4, d * 1.4)
        lines.append(shapely.LineString([(x, y), (x + rng.normal(0, 0.0008),
                                                  y + rng.normal(0, 0.0008))]))
        hw.append("footway")
    lines.append(shapely.LineString([(-d, -d * 1.2), (d, d * 0.9)]))
    hw.append("motorway")
    roads = gpd.GeoDataFrame({"highway": hw, "geometry": lines}, crs=4326)

    def gdf(geoms):
        return gpd.GeoDataFrame({"geometry": geoms}, crs=4326)

    t = np.linspace(-d * 1.5, d * 1.5, 80)  # a winding river
    river = shapely.LineString(np.column_stack([t * 0.7 + 0.002 * np.sin(t * 900), t])).buffer(
        0.0006)
    coast = shapely.LineString([(d * 1.5, d * 0.55), (d * 0.45, d * 0.75), (-d * 1.5, d * 0.95)])
    parks = [shapely.box(-0.006, -0.008, -0.003, -0.004), shapely.Point(0.004, -0.002).buffer(0.0015)]
    blds = [b for b in (shapely.box(x, y, x + 0.00035, y + 0.00025)
                        for x, y in rng.uniform(-d, d, (260, 2)) * [1, 1.3])
            if b.bounds[3] < d * 0.5 and not b.intersects(river)]
    rail = shapely.LineString([(-d, d * 0.2), (d, -d * 0.4)])
    canal = shapely.LineString([(-d, -d * 0.6), (d, -d * 0.5)])
    airport = shapely.box(0.005, -0.012, 0.009, -0.009)
    layers = {"water": gdf([river]), "parks": gdf(parks), "coastline": gdf([coast]),
              "buildings": gdf(blds), "railways": gdf([rail]), "waterways": gdf([canal]),
              "airports": gdf([airport])}
    return MapData(roads, layers, (-d, -d * 1.4, d, d * 1.4))
