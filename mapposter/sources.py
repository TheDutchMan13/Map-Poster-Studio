"""Map data: roads, water and parks for a rectangle around a point.

Two sources produce the same result:
  * online  - OpenStreetMap via the Overpass API (OSMnx), like the original
  * pbf     - a local .osm.pbf extract (e.g. Geofabrik's arizona-latest.osm.pbf).
              No rate limits, no timeouts, works offline; best for big radii.

Results are cached on disk. A cached area that fully contains a new request is
reused, so e.g. a 25 mile pull also serves every smaller poster of the same spot.
"""

from __future__ import annotations

import hashlib
import json
import math
import pickle
import time
from dataclasses import dataclass
from pathlib import Path

from . import paths
from .log import log

# Same exclusions OSMnx applies for network_type="all".
EXCLUDED_HIGHWAYS = {
    "abandoned", "construction", "no", "planned", "platform", "proposed",
    "raceway", "razed", "disused", "demolished", "dismantled",
}

M_PER_DEG = 111_320.0


CACHE_VERSION = 4   # 4: place labels keep their place=* class


@dataclass
class MapData:
    roads: object        # GeoDataFrame: geometry (lines), highway (str)
    layers: dict         # name -> GeoDataFrame (polygons or lines, per layer kind)
    bbox: tuple          # (west, south, east, north) actually covered

    def __getstate__(self):  # drawing caches never go into the disk cache
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    def layer(self, name):
        g = self.layers.get(name)
        return g if g is not None and len(g) else None


# ----------------------------------------------------------------- geometry

def _area(b) -> float:
    return max(b[2] - b[0], 0) * max(b[3] - b[1], 0)


def clip_to_bbox(data: MapData, bbox) -> MapData:
    """Drop features entirely outside bbox (lon/lat). A cached 40 km area then serves
    a 3 mile poster at 3 mile speed instead of drawing 40 km of hidden streets."""
    import shapely

    def sub(g):
        if g is None or len(g) == 0:
            return g
        b = shapely.bounds(g.geometry.values)
        keep = ((b[:, 0] <= bbox[2]) & (b[:, 2] >= bbox[0])
                & (b[:, 1] <= bbox[3]) & (b[:, 3] >= bbox[1]))
        return g if keep.all() else g[keep].reset_index(drop=True)

    return MapData(sub(data.roads), {k: sub(v) for k, v in data.layers.items()}, tuple(bbox))


# A .pbf scan costs about the same whatever the box, so the first read of a place
# covers at least this far from the center. Later posters of the same metro (other
# spots, smaller radius, other shape) then come straight from the cache.
MIN_PBF_READ_M = 25000


def pbf_read_box(bbox):
    w, s_, e, n = square_bbox(bbox)
    cx, cy = (w + e) / 2, (s_ + n) / 2
    half = max((n - s_) / 2, MIN_PBF_READ_M / M_PER_DEG)          # latitude degrees
    k = math.cos(math.radians(cy))
    return (cx - half / k, cy - half, cx + half / k, cy + half)


def square_bbox(bbox):
    """Smallest lon/lat box around bbox's center that is square on the ground, so a
    portrait and a landscape poster of the same spot share one .pbf read."""
    w, s, e, n = bbox
    cx, cy = (w + e) / 2, (s + n) / 2
    k = math.cos(math.radians(cy))
    half = max((e - w) / 2 * k, (n - s) / 2)          # in latitude degrees
    return (cx - half / k, cy - half, cx + half / k, cy + half)


def view_half_extents(radius_m: float, width: float, height: float) -> tuple[float, float]:
    """Half width / half height in meters. radius = center to nearest edge."""
    if width >= height:
        return radius_m * width / height, radius_m
    return radius_m, radius_m * height / width


def bbox_for(lat: float, lon: float, half_x: float, half_y: float,
             margin: float = 1.03) -> tuple[float, float, float, float]:
    dlat = half_y * margin / M_PER_DEG
    dlon = half_x * margin / (M_PER_DEG * math.cos(math.radians(lat)))
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


def _contains(outer, inner) -> bool:
    return (outer[0] <= inner[0] and outer[1] <= inner[1]
            and outer[2] >= inner[2] and outer[3] >= inner[3])


def tags_match(tags, spec: dict) -> bool:
    """spec like {"natural": ["water","bay"], "waterway": "riverbank", "leisure": True}."""
    for key, want in spec.items():
        val = tags.get(key)
        if val is None:
            continue
        if want is True:
            return True
        if isinstance(want, str) and val == want:
            return True
        if isinstance(want, (list, tuple)) and val in want:
            return True
    return False


# -------------------------------------------------------------------- cache

_INDEX = paths.CACHE_DIR / "mapdata_index.json"

# The last results stay in memory, so repeated previews of the same area skip the
# disk read and keep their prepared drawing paths (see render._prepared).
_MEM: dict = {}
_MEM_MAX = 2


def _mem_get(key):
    v = _MEM.pop(key, None)
    if v is not None:
        _MEM[key] = v            # most recently used last
    return v


def _mem_put(key, data) -> None:
    _MEM.pop(key, None)
    _MEM[key] = data
    while len(_MEM) > _MEM_MAX:
        _MEM.pop(next(iter(_MEM)))


def clear_memory_cache() -> None:
    _MEM.clear()


def _layers_sig(layers: dict) -> str:
    blob = json.dumps({"v": CACHE_VERSION, "layers": layers}, sort_keys=True)
    return hashlib.sha1(blob.encode()).hexdigest()[:10]


def _index_load() -> list:
    try:
        return json.loads(_INDEX.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []


def _cache_lookup(source_id: str, sig: str, bbox) -> MapData | None:
    best = None
    for entry in _index_load():
        if entry["source"] != source_id or entry["sig"] != sig:
            continue
        if not _contains(entry["bbox"], bbox):
            continue
        f = paths.CACHE_DIR / entry["file"]
        if not f.exists():
            continue
        area = (entry["bbox"][2] - entry["bbox"][0]) * (entry["bbox"][3] - entry["bbox"][1])
        if best is None or area < best[0]:
            best = (area, f)
    if best is None:
        return None
    try:
        with open(best[1], "rb") as fh:
            data = pickle.load(fh)
        log(f"✓ Using cached map data ({best[1].name})")
        return data
    except Exception as e:
        log(f"⚠ Cache read failed ({e}); downloading again")
        return None


def _cache_store(source_id: str, sig: str, data: MapData) -> None:
    try:
        paths.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        name = "map_" + hashlib.sha1(
            f"{source_id}{sig}{data.bbox}{time.time()}".encode()).hexdigest()[:16] + ".pkl"
        with open(paths.CACHE_DIR / name, "wb") as fh:
            pickle.dump(data, fh, protocol=pickle.HIGHEST_PROTOCOL)
        idx = _index_load()
        idx.append({"source": source_id, "sig": sig, "bbox": list(data.bbox), "file": name})
        _INDEX.write_text(json.dumps(idx, indent=1), encoding="utf-8")
    except Exception as e:
        log(f"⚠ Could not write cache: {e}")


# ------------------------------------------------------------------ helpers

def _empty_gdf():
    import geopandas as gpd
    return gpd.GeoDataFrame({"geometry": []}, geometry="geometry", crs="EPSG:4326")


def _first(v):
    if isinstance(v, (list, tuple)):
        return v[0] if v else "unclassified"
    return v if isinstance(v, str) else "unclassified"


POLY_TYPES = ["Polygon", "MultiPolygon"]
LINE_TYPES = ["LineString", "MultiLineString"]
POINT_TYPES = ["Point"]
KIND_TYPES = {"polygon": POLY_TYPES, "line": LINE_TYPES, "coastline": LINE_TYPES,
              "point": POINT_TYPES + POLY_TYPES}


def _keep(gdf, kind):
    """Keep geometries that fit the layer kind, plus name and the class tag."""
    import geopandas as gpd
    if gdf is None or len(gdf) == 0:
        return _empty_gdf()
    gdf = gdf[gdf.geometry.geom_type.isin(KIND_TYPES[kind])]
    out = gpd.GeoDataFrame(geometry=gdf.geometry.values, crs=gdf.crs)
    out["name"] = gdf["name"].values if "name" in gdf.columns else None
    if kind == "point":  # areas tagged place=* -> their center
        out["place"] = gdf["place"].values if "place" in gdf.columns else None
        out["geometry"] = out.geometry.representative_point()
        out = out[out["name"].notna()]
    return out.reset_index(drop=True)


# ------------------------------------------------------------------- online

def _fetch_online(bbox, layers: dict, check_cancel) -> MapData:
    import osmnx as ox

    ox.settings.use_cache = True
    ox.settings.cache_folder = str(paths.CACHE_DIR / "overpass")
    ox.settings.requests_timeout = 600
    ox.settings.log_console = False

    west, south, east, north = bbox
    area_sqmi = ((east - west) * M_PER_DEG * math.cos(math.radians((north + south) / 2))
                * (north - south) * M_PER_DEG) / 1609.344 ** 2
    log(f"Downloading OpenStreetMap data for ~{area_sqmi:,.0f} sq mi "
        "(large areas can take a long time)...")

    # (no "[i/n]" here: the window reads that pattern as theme progress)
    t_all = t0 = time.time()
    log(f"  Streets (1 of {len(layers) + 1})...")
    roads = ox.features_from_bbox(bbox, tags={"highway": True})
    check_cancel()
    roads = roads[roads.geometry.geom_type.isin(["LineString", "MultiLineString"])]
    cols = [c for c in ("highway", "area", "service", "name") if c in roads.columns]
    roads = roads[cols + ["geometry"]].copy()
    roads["highway"] = roads["highway"].map(_first)
    roads = roads[~roads["highway"].isin(EXCLUDED_HIGHWAYS)]
    if "area" in roads.columns:
        roads = roads[roads["area"] != "yes"]
    if "service" in roads.columns:
        roads = roads[roads["service"] != "private"]
    if "name" not in roads.columns:
        roads["name"] = None
    roads = roads[["highway", "name", "geometry"]].reset_index(drop=True)
    log(f"      {len(roads):,} street segments  ({time.time() - t0:.0f}s)")

    feats = {}
    total = len(layers) + 1
    for i, (name, spec) in enumerate(layers.items(), start=2):
        log(f"  {name.capitalize()} ({i} of {total})...")
        t0 = time.time()
        try:
            g = ox.features_from_bbox(bbox, tags=spec["tags"])
            feats[name] = _keep(g, spec["kind"])
        except Exception as e:  # osmnx raises when nothing matches
            log(f"      none found ({type(e).__name__})")
            feats[name] = _empty_gdf()
        log(f"      {len(feats[name]):,} features  ({time.time() - t0:.0f}s)")
        check_cancel()

    log(f"✓ Download finished in {time.time() - t_all:,.0f}s (saved to the cache)")
    return MapData(roads, feats, tuple(bbox))


# ---------------------------------------------------------------------- pbf

def _read_pbf(pbf: Path, bbox, layers: dict, check_cancel) -> MapData:
    import geopandas as gpd
    import osmium
    import shapely

    west, south, east, north = bbox
    # Loose box for the cheap node test (catches long ways that cross the edge).
    pad = 0.05
    lw, ls, le, ln = west - pad, south - pad, east + pad, north + pad

    keys = {"highway"}
    for spec in layers.values():
        keys.update(spec["tags"].keys())
    line_layers = {n: d for n, d in layers.items() if d["kind"] in ("line", "coastline")}
    poly_layers = {n: d for n, d in layers.items() if d["kind"] == "polygon"}
    point_layers = {n: d for n, d in layers.items() if d["kind"] == "point"}

    wkb = osmium.geom.WKBFactory()
    roads_wkb, roads_hw, roads_name = [], [], []
    feats = {name: [] for name in layers}
    names = {name: [] for name in layers}
    kinds = {name: [] for name in point_layers}     # place=* value, for label ranking

    size_mb = pbf.stat().st_size / 1e6
    log(f"Reading {pbf.name} ({size_mb:,.0f} MB) — a big extract takes a few minutes...")
    t0 = time.time()
    n = 0

    fp = (osmium.FileProcessor(str(pbf))
          .with_locations()
          .with_areas(osmium.filter.KeyFilter(*keys))
          .with_filter(osmium.filter.EntityFilter(
              (osmium.osm.WAY | osmium.osm.AREA | osmium.osm.NODE) if point_layers
              else (osmium.osm.WAY | osmium.osm.AREA)))
          .with_filter(osmium.filter.KeyFilter(*keys)))

    def inside(loc) -> bool:
        return loc.valid() and lw <= loc.lon <= le and ls <= loc.lat <= ln

    def line_wkb(way):
        """Way -> WKB line. Clipped extracts can miss some node locations:
        keep the runs of nodes we do have instead of dropping the whole way."""
        try:
            return wkb.create_linestring(way)
        except Exception:
            runs, cur = [], []
            for nd in way.nodes:
                loc = nd.location
                if loc.valid():
                    cur.append((loc.lon, loc.lat))
                elif cur:
                    runs.append(cur)
                    cur = []
            runs.append(cur)
            runs = [r for r in runs if len(r) >= 2]
            if not runs:
                return None
            g = (shapely.LineString(runs[0]) if len(runs) == 1
                 else shapely.MultiLineString(runs))
            return shapely.to_wkb(g)

    def any_inside(way) -> bool:
        nodes = way.nodes
        return (inside(nodes[0].location) or inside(nodes[-1].location)
                or inside(nodes[len(nodes) // 2].location)
                or any(inside(nodes[i].location) for i in range(0, len(nodes), 8)))

    for obj in fp:
        n += 1
        if n % 200_000 == 0:
            check_cancel()
            log(f"  ...{n:,} objects scanned ({time.time() - t0:,.0f}s)")
        tags = obj.tags
        if obj.is_way():
            nodes = obj.nodes
            if len(nodes) < 2:
                continue
            if not any_inside(obj):
                continue
            geom = None
            hw = tags.get("highway")
            if (hw is not None and hw not in EXCLUDED_HIGHWAYS
                    and tags.get("area") != "yes" and tags.get("service") != "private"):
                geom = line_wkb(obj)
                if geom is None:
                    continue
                roads_wkb.append(geom)
                roads_hw.append(hw)
                roads_name.append(tags.get("name"))
            for name, spec in line_layers.items():
                if tags_match(tags, spec["tags"]):
                    g = geom or line_wkb(obj)
                    if g is not None:
                        feats[name].append(g)
                        names[name].append(tags.get("name"))
        elif obj.is_area() and (poly_layers or point_layers):
            for name, spec in poly_layers.items():
                if tags_match(tags, spec["tags"]):
                    try:
                        feats[name].append(wkb.create_multipolygon(obj))
                        names[name].append(tags.get("name"))
                    except Exception:
                        pass
                    break
            for name, spec in point_layers.items():  # place areas -> label point
                if tags.get("name") and tags_match(tags, spec["tags"]):
                    try:
                        g = shapely.from_wkb(wkb.create_multipolygon(obj))
                        feats[name].append(shapely.to_wkb(g.representative_point()))
                        names[name].append(tags.get("name"))
                        kinds[name].append(tags.get("place"))
                    except Exception:
                        pass
        elif obj.is_node() and point_layers:
            if not tags.get("name") or not inside(obj.location):
                continue
            for name, spec in point_layers.items():
                if tags_match(tags, spec["tags"]):
                    feats[name].append(wkb.create_point(obj))
                    names[name].append(tags.get("name"))
                    kinds[name].append(tags.get("place"))

    log(f"✓ Scanned {n:,} objects in {time.time() - t0:,.0f}s")

    box = shapely.box(west, south, east, north)

    def to_gdf(wkbs, nm, hw=None, place=None):
        import numpy as np
        if not wkbs:
            return _empty_gdf()
        geoms = shapely.from_wkb(wkbs)
        keep = shapely.intersects(geoms, box)
        data = {"geometry": geoms[keep], "name": np.asarray(nm, dtype=object)[keep]}
        if hw is not None:
            data["highway"] = np.asarray(hw, dtype=object)[keep]
        if place is not None:
            data["place"] = np.asarray(place, dtype=object)[keep]
        return gpd.GeoDataFrame(data, geometry="geometry", crs="EPSG:4326")

    roads = to_gdf(roads_wkb, roads_name, roads_hw)
    out = {name: to_gdf(w, names[name], place=kinds.get(name)) for name, w in feats.items()}
    log(f"  {len(roads):,} streets in view; "
        + ", ".join(f"{len(g):,} {k}" for k, g in out.items()))
    return MapData(roads, out, tuple(bbox))


def pbf_bounds(pbf: Path):
    """(west, south, east, north) from the file header, or None."""
    try:
        import osmium
        box = osmium.io.Reader(str(pbf), osmium.osm.osm_entity_bits.NOTHING).header().box()
        if box.valid():
            return (box.bottom_left.lon, box.bottom_left.lat,
                    box.top_right.lon, box.top_right.lat)
    except Exception:
        pass
    return None


# --------------------------------------------------------------------- main

def get_map_data(lat: float, lon: float, radius_m: float, width: float, height: float,
                 pbf: str | Path | None = None, use_cache: bool = True,
                 check_cancel=lambda: None, enabled: list[str] | None = None,
                 bbox: tuple | None = None, allow_empty: bool = False) -> MapData:
    all_layers = paths.load_layers()
    if enabled is None:
        enabled = paths.default_enabled_layers()
    layers = {n: all_layers[n] for n in paths.LAYER_ORDER + list(all_layers)
              if n in all_layers and n in enabled}
    layers = dict(layers)
    sig = _layers_sig(layers)
    if bbox is None:
        hx, hy = view_half_extents(radius_m, width, height)
        bbox = bbox_for(lat, lon, hx, hy)
    if "buildings" in layers and radius_m > 8000:
        log("⚠ Buildings over a large area means millions of shapes: slow and memory-hungry.")

    if pbf:
        pbf = Path(pbf)
        if not pbf.exists():
            raise FileNotFoundError(f"PBF file not found: {pbf}")
        st = pbf.stat()
        source_id = f"pbf:{pbf.name}:{st.st_size}:{int(st.st_mtime)}"
        hb = pbf_bounds(pbf)
        if hb and not _contains(hb, bbox):
            log("⚠ The poster area extends past the edge of this extract; "
                "the outside will be blank.")
    else:
        source_id = "overpass"

    mem_key = (source_id, sig, tuple(round(v, 6) for v in bbox))
    if use_cache:
        hit = _mem_get(mem_key)
        if hit is not None:
            log("✓ Using map data already in memory")
            return hit
        cached = _cache_lookup(source_id, sig, bbox)
        if cached is not None:
            if _area(cached.bbox) > 1.1 * _area(bbox):
                cached = clip_to_bbox(cached, bbox)
            _mem_put(mem_key, cached)
            return cached

    # Reading a .pbf costs the same whatever the box, so read a square: the cache
    # then also serves the other orientation. Online stays exact (server load).
    read_box = pbf_read_box(bbox) if pbf else bbox
    data = (_read_pbf(pbf, read_box, layers, check_cancel) if pbf
            else _fetch_online(bbox, layers, check_cancel))
    if len(data.roads) == 0:
        if not allow_empty:
            raise RuntimeError("No streets found for this area. (Check the .pbf covers it, "
                               "or turn on terrain for a streets-free landscape poster.)")
        log("⚠ No streets in this area – drawing terrain and other layers only")
    if use_cache:
        _cache_store(source_id, sig, data)
    if read_box != bbox and _area(read_box) > 1.1 * _area(bbox):
        data = clip_to_bbox(data, bbox)
    if use_cache:
        _mem_put(mem_key, data)
    return data
