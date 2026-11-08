"""Geometry helpers: ocean from coastlines, shape masks, marker icons, GPX tracks."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .log import log


# ------------------------------------------------------------------- ocean

def ocean_polygons(coast_lines, view_box):
    """Turn OSM coastline lines (land on the LEFT, water on the RIGHT of the
    line direction) into sea polygons covering the view box. Returns a list of
    shapely Polygons (projected coordinates), possibly empty."""
    import shapely
    from shapely.ops import polygonize, unary_union

    if coast_lines is None or len(coast_lines) == 0:
        return []
    parts = shapely.get_parts(np.asarray(coast_lines))
    parts = [p for p in parts if p.geom_type == "LineString" and not p.is_empty]
    if not parts:
        return []
    merged = shapely.line_merge(shapely.MultiLineString(parts), directed=True)
    clipped = [g for g in shapely.get_parts(merged.intersection(view_box))
               if g.geom_type == "LineString" and g.length > 0]
    if not clipped:
        return []

    pieces = list(polygonize(unary_union(clipped + [view_box.boundary])))
    if len(pieces) < 2:
        # Coastline doesn't split the view (e.g. clipped extract): can't tell sides.
        return []

    coast_union = shapely.MultiLineString(clipped)
    tree = shapely.STRtree(clipped)
    sea = []
    for poly in pieces:
        if poly.boundary.intersection(coast_union).length <= 0:
            continue
        p = poly.representative_point()
        line = clipped[tree.nearest(p)]
        d = line.project(p)
        eps = min(1.0, line.length / 4)
        a = line.interpolate(max(d - eps, 0))
        b = line.interpolate(min(d + eps, line.length))
        cross = (b.x - a.x) * (p.y - a.y) - (b.y - a.y) * (p.x - a.x)
        if cross < 0:  # point is to the right of the coastline -> water
            sea.append(poly)
    return sea


# ------------------------------------------------------------------ shapes

def shape_polygon(shape: str, cx: float, cy: float, size: float, boundary=None):
    """Clip shape in projected coords. size = half-width of the shape."""
    import shapely

    if shape == "circle":
        return shapely.Point(cx, cy).buffer(size, quad_segs=64)
    if shape == "heart":
        t = np.linspace(0, 2 * math.pi, 400)
        x = 16 * np.sin(t) ** 3
        y = 13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t)
        y = y - (y.max() + y.min()) / 2
        s = size / 16
        return shapely.Polygon(np.column_stack([cx + x * s, cy + y * s]))
    if shape == "boundary" and boundary is not None:
        return boundary
    return None


def heart_path():
    from matplotlib.path import Path as MPath
    t = np.linspace(0, 2 * math.pi, 80)
    x = 16 * np.sin(t) ** 3
    y = 13 * np.cos(t) - 5 * np.cos(2 * t) - 2 * np.cos(3 * t) - np.cos(4 * t)
    v = np.column_stack([x, y - (y.max() + y.min()) / 2]) / 17
    return MPath(v, closed=True)


def pin_path():
    """Map pin with its tip at (0, 0)."""
    from matplotlib.path import Path as MPath
    t = np.linspace(-0.25 * math.pi, 1.25 * math.pi, 60)  # arc over the top
    r, cy = 0.55, 1.15
    arc = np.column_stack([r * np.cos(t), cy + r * np.sin(t)])
    outer = np.vstack([[0, 0], arc[::-1], [0, 0]])
    hole_t = np.linspace(0, 2 * math.pi, 30)
    hole = np.column_stack([0.22 * np.cos(hole_t), cy + 0.22 * np.sin(hole_t)])[::-1]
    verts = np.vstack([outer, hole])
    codes = ([MPath.MOVETO] + [MPath.LINETO] * (len(outer) - 2) + [MPath.CLOSEPOLY]
             + [MPath.MOVETO] + [MPath.LINETO] * (len(hole) - 2) + [MPath.CLOSEPOLY])
    return MPath(verts, codes)


# ----------------------------------------------------------------- markers

MARKER_ICONS = ("pin", "heart", "star", "dot")


@dataclass
class Marker:
    lat: float
    lon: float
    label: str = ""
    icon: str = "pin"


def parse_marker(text: str) -> Marker:
    """'33.45, -112.07, Our first home, heart'  (label and icon optional)."""
    from .geocode import parse_coordinate
    parts = [p.strip() for p in text.split(",")]
    if len(parts) < 2:
        raise ValueError(f"Marker needs at least 'lat, lon': {text!r}")
    icon = "pin"
    rest = parts[2:]
    if rest and rest[-1].lower() in MARKER_ICONS:
        icon = rest.pop().lower()
    return Marker(parse_coordinate(parts[0]), parse_coordinate(parts[1]),
                  ", ".join(rest), icon)


# --------------------------------------------------------------------- gpx

def read_gpx(path: str | Path) -> list[np.ndarray]:
    """Return a list of (N, 3) arrays of (lon, lat, elevation_m or NaN),
    one per track segment / route."""
    tree = ET.parse(str(path))
    out = []

    def local(tag):
        return tag.rsplit("}", 1)[-1]

    for el in tree.iter():
        name = local(el.tag)
        if name in ("trkseg", "rte"):
            pts = []
            for p in el:
                if local(p.tag) not in ("trkpt", "rtept"):
                    continue
                ele = next((c.text for c in p if local(c.tag) == "ele"), None)
                try:
                    ele = float(ele)
                except (TypeError, ValueError):
                    ele = float("nan")
                pts.append((float(p.get("lon")), float(p.get("lat")), ele))
            if len(pts) >= 2:
                out.append(np.asarray(pts))
    if not out:
        log(f"⚠ No track points found in {Path(path).name}")
    return out


def routes_extent(routes: list[np.ndarray], width: float, height: float, pad: float = 1.15):
    """Center (lat, lon) and radius (m) that fit all routes on the poster."""
    pts = np.vstack([r[:, :2] for r in routes])
    lon0, lat0 = pts.min(0)
    lon1, lat1 = pts.max(0)
    lat_c, lon_c = (lat0 + lat1) / 2, (lon0 + lon1) / 2
    half_x = (lon1 - lon0) / 2 * 111_320 * math.cos(math.radians(lat_c))
    half_y = (lat1 - lat0) / 2 * 111_320
    # radius is the half-extent of the poster's SHORT side
    if width >= height:
        r = max(half_x * height / width, half_y)
    else:
        r = max(half_x, half_y * width / height)
    # leave room for the text block at the bottom
    return lat_c, lon_c, max(r * pad * 1.25, 300)


def route_length_m(route: np.ndarray) -> np.ndarray:
    """Cumulative distance along a (lon, lat, ...) route in meters (haversine)."""
    lon, lat = np.radians(route[:, 0]), np.radians(route[:, 1])
    a = (np.sin(np.diff(lat) / 2) ** 2
         + np.cos(lat[:-1]) * np.cos(lat[1:]) * np.sin(np.diff(lon) / 2) ** 2)
    d = 2 * 6371008.8 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
    return np.concatenate([[0], np.cumsum(d)])
