"""Terrain: elevation from the free AWS Terrain Tiles (Terrarium PNGs), cached on
disk so a second poster of the same area needs no internet.

Data: Mapzen / AWS Open Data Terrain Tiles, built from SRTM, USGS 3DEP, GMTED,
ETOPO1 and others. Attribution is printed on posters that use it.
"""

from __future__ import annotations

import io
import math
from pathlib import Path

import numpy as np

from . import paths
from .log import log

TILE_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
ATTRIBUTION = "Elevation: AWS Terrain Tiles (USGS 3DEP, SRTM)"
FT_PER_M = 3.28084


def _deg2tile(lat, lon, z):
    n = 2 ** z
    x = (lon + 180) / 360 * n
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return x, y


def _tile(z, x, y, check_cancel):
    import requests
    from PIL import Image

    f = paths.CACHE_DIR / "terrain" / str(z) / str(x) / f"{y}.png"
    if not f.exists():
        check_cancel()
        r = requests.get(TILE_URL.format(z=z, x=x, y=y), timeout=30,
                         headers={"User-Agent": "MapPosterStudio/1.0"})
        if r.status_code == 404:
            return np.zeros((256, 256), dtype=np.float32)  # open ocean / no data
        r.raise_for_status()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(r.content)
    a = np.asarray(Image.open(io.BytesIO(f.read_bytes())).convert("RGB"), dtype=np.float32)
    return a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768


class DEM:
    """Mosaic of elevation tiles covering a lat/lon box. Elevations in meters."""

    def __init__(self, west, south, east, north, meters_per_px, check_cancel=lambda: None,
                 max_tiles=120):
        lat_c = (south + north) / 2
        z = math.ceil(math.log2(156543.03 * math.cos(math.radians(lat_c)) / max(meters_per_px, 1)))
        z = min(max(z, 4), 14)
        while True:
            x0, y0 = _deg2tile(north, west, z)
            x1, y1 = _deg2tile(south, east, z)
            nx, ny = int(x1) - int(x0) + 1, int(y1) - int(y0) + 1
            if nx * ny <= max_tiles or z <= 4:
                break
            z -= 1
        self.z, self.tx0, self.ty0 = z, int(x0), int(y0)
        cached = sum((paths.CACHE_DIR / "terrain" / str(z) / str(self.tx0 + i) /
                      f"{self.ty0 + j}.png").exists() for i in range(nx) for j in range(ny))
        log(f"Elevation: {nx * ny} tiles at zoom {z} "
            f"({cached} cached{', downloading the rest' if cached < nx * ny else ''})")
        rows = []
        for j in range(ny):
            rows.append(np.hstack([_tile(z, self.tx0 + i, self.ty0 + j, check_cancel)
                                   for i in range(nx)]))
        self.elev = np.vstack(rows)

    def sample(self, lons, lats):
        """Bilinear elevation (m) at lon/lat arrays."""
        lons, lats = np.asarray(lons, float), np.asarray(lats, float)
        n = 2 ** self.z
        px = ((lons + 180) / 360 * n - self.tx0) * 256 - 0.5
        lat_r = np.radians(lats)
        py = ((1 - np.arcsinh(np.tan(lat_r)) / math.pi) / 2 * n - self.ty0) * 256 - 0.5
        h, w = self.elev.shape
        px = np.clip(px, 0, w - 1.001)
        py = np.clip(py, 0, h - 1.001)
        x0, y0 = np.floor(px).astype(int), np.floor(py).astype(int)
        fx, fy = px - x0, py - y0
        e = self.elev
        return ((e[y0, x0] * (1 - fx) + e[y0, x0 + 1] * fx) * (1 - fy)
                + (e[y0 + 1, x0] * (1 - fx) + e[y0 + 1, x0 + 1] * fx) * fy)


def grid_for_view(dem: DEM, transformer_inv, x0, x1, y0, y1, nx: int):
    """Resample the DEM onto a regular grid in the poster's projected coordinates."""
    ny = max(int(nx * (y1 - y0) / (x1 - x0)), 2)
    xs = np.linspace(x0, x1, nx)
    ys = np.linspace(y0, y1, ny)
    X, Y = np.meshgrid(xs, ys)
    lon, lat = transformer_inv.transform(X, Y)
    return xs, ys, dem.sample(lon, lat).astype(np.float32)


def smooth(z, px: int):
    """Box blur (separable, edge-padded) to take the noise out of flat ground."""
    if px < 1:
        return z
    k = np.ones(2 * px + 1) / (2 * px + 1)
    z = np.pad(z, px, mode="edge")
    z = np.apply_along_axis(lambda r: np.convolve(r, k, "same"), 1, z)
    z = np.apply_along_axis(lambda c: np.convolve(c, k, "same"), 0, z)
    return z[px:-px, px:-px]


def hillshade(z, cell_m, azimuth=315.0, altitude=45.0, exaggeration=2.0):
    """0..1 shading (1 = lit). Rows go south->north."""
    dzdy, dzdx = np.gradient(z * exaggeration, cell_m)
    slope = np.pi / 2 - np.arctan(np.hypot(dzdx, dzdy))
    aspect = np.arctan2(-dzdx, dzdy)
    az, alt = np.radians(360 - azimuth + 90), np.radians(altitude)
    shaded = (np.sin(alt) * np.sin(slope)
              + np.cos(alt) * np.cos(slope) * np.cos(az - aspect))
    return np.clip(shaded, 0, 1)


def nice_interval_ft(zmin_m, zmax_m, target=16):
    span = max((zmax_m - zmin_m) * FT_PER_M, 1)
    raw = span / target
    for step in (10, 20, 25, 40, 50, 100, 200, 250, 500, 1000):
        if step >= raw:
            return step
    return 2000


def prefetch(west, south, east, north, zooms=(8, 9, 10, 11, 12), check_cancel=lambda: None):
    """Download every tile for an area so terrain works offline later."""
    total = 0
    for z in zooms:
        x0, y0 = _deg2tile(north, west, z)
        x1, y1 = _deg2tile(south, east, z)
        tiles = [(int(x), int(y)) for x in range(int(x0), int(x1) + 1)
                 for y in range(int(y0), int(y1) + 1)]
        log(f"  zoom {z}: {len(tiles)} tiles")
        for i, (x, y) in enumerate(tiles):
            _tile(z, x, y, check_cancel)
            if i % 200 == 199:
                log(f"    {i + 1}/{len(tiles)}")
        total += len(tiles)
    log(f"✓ Terrain cached: {total} tiles in {Path(paths.CACHE_DIR) / 'terrain'}")
    return total
