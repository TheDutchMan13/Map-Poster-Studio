"""Draws the poster. Pure matplotlib (no pyplot), so it is safe to call from a GUI thread."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .geometry import heart_path, ocean_polygons, pin_path, shape_polygon
from .log import log
from .sources import MapData, view_half_extents

# road class -> (theme color key, line width in points, draw order)
ROAD_CLASSES = {
    "motorway": ("road_motorway", 1.2, 6),
    "primary": ("road_primary", 1.0, 5),
    "secondary": ("road_secondary", 0.8, 4),
    "tertiary": ("road_tertiary", 0.6, 3),
    "residential": ("road_residential", 0.4, 2),
    "default": ("road_default", 0.4, 1),
}

_HIGHWAY_TO_CLASS = {
    "motorway": "motorway", "motorway_link": "motorway",
    "trunk": "primary", "trunk_link": "primary",
    "primary": "primary", "primary_link": "primary",
    "secondary": "secondary", "secondary_link": "secondary",
    "tertiary": "tertiary", "tertiary_link": "tertiary",
    "residential": "residential", "living_street": "residential",
    "unclassified": "residential",
}

# polygon layer -> (theme color key, zorder)
POLY_LAYERS = {
    "water": ("water", 0.5),
    "parks": ("parks", 0.8),
    "airports": ("airports", 0.85),
    "buildings": ("buildings", 0.9),
}
# line layer -> (theme color key, width pt, zorder)
LINE_LAYERS = {
    "washes": ("washes", 0.45, 1.45),
    "waterways": ("waterway", 0.7, 1.5),
    "trails": ("trails", 0.4, 1.95),
    "railways": ("railway", 0.6, 2.35),
}
DASHED = {"trails": (0, (3, 2)), "washes": (0, (5, 2))}
TRAIL_HIGHWAYS = {"path", "track", "bridleway"}

SHAPES = ("rect", "circle", "heart", "boundary")
BORDERS = ("none", "thin", "thick", "double")
TITLE_STYLES = ("spaced", "caps", "normal")


@dataclass
class PosterOptions:
    city: str
    country: str
    lat: float
    lon: float
    radius_m: float
    width: float = 12.0
    height: float = 16.0
    display_city: str | None = None
    display_country: str | None = None
    country_label: str | None = None
    fonts: dict | None = None
    fmt: str = "png"
    dpi: int = 300
    road_scale: float = 1.0
    auto_roads: bool = True
    classic: bool = False             # True = draw exactly like the original maptoposter
    show_text: bool = True
    show_coords: bool = True
    show_gradient: bool = True
    # layout
    text_position: str = "bottom"      # bottom | top
    title_style: str = "spaced"        # spaced | caps | normal
    letter_spacing: int = 2            # spaces between letters for "spaced"
    tagline: str = ""
    border: str = "none"               # none | thin | thick | double
    shape: str = "rect"                # rect | circle | heart | boundary
    boundary: object = None            # shapely polygon (lat/lon) for shape="boundary"
    bleed: float = 0.0                 # inches added on every side for print
    # overlays
    markers: list = field(default_factory=list)      # list[Marker]
    routes: list = field(default_factory=list)       # list[np.ndarray (lon, lat, ele)]
    route_width: float = 2.2
    elevation_profile: bool = False
    # terrain
    terrain: str = "none"              # none | hillshade | contours | both
    contour_interval_ft: float | None = None
    terrain_strength: float = 1.0
    data_bbox: tuple | None = None     # lat/lon box of the fetched data (for elevation)
    # labels / highlight / map furniture
    labels: list = field(default_factory=list)       # roads, places, parks
    label_scale: float = 1.0
    highlight: object = None           # shapely polygon (lat/lon)
    highlight_mode: str = "fill"       # fill | focus
    highlight_label: str = ""
    scale_bar: bool = False
    north_arrow: bool = False
    grid: bool = False
    # photo / QR
    photo: str | None = None
    photo_corner: str = "top-right"
    qr: str = ""
    qr_corner: str = "top-left"
    # print
    crop_marks: bool = False
    check_cancel: object = None


def is_latin_script(text: str) -> bool:
    """True if >80% of letters are Latin (then we upper-case and letter-space)."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return True
    return sum(ord(c) < 0x250 for c in letters) / len(letters) > 0.8


def format_coords(lat: float, lon: float) -> str:
    ns = "N" if lat >= 0 else "S"
    ew = "E" if lon >= 0 else "W"
    return f"{abs(lat):.4f}° {ns} / {abs(lon):.4f}° {ew}"


def style_title(text: str, style: str, spacing: int) -> str:
    if not is_latin_script(text):
        return text
    if style == "normal":
        return text
    if style == "caps":
        return text.upper()
    return (" " * max(spacing, 0)).join(text.upper())


def auto_road_factor(radius_m: float, width: float, height: float) -> float:
    """Thinner lines for big areas / small prints, thicker for close-ups."""
    f = (5000.0 / max(radius_m, 100)) ** 0.35
    f = min(max(f, 0.35), 1.8)
    return f * (min(width, height) / 12.0) ** 0.5


# City-scale road widths (pt). Blended with ROAD_CLASSES widths by map_detail():
# close-ups keep the original look, wide areas get a clear hierarchy in which
# driveways, parking aisles and footways become fine texture instead of haze.
CITY_WIDTHS = {"motorway": 1.7, "primary": 1.15, "secondary": 0.85,
               "tertiary": 0.55, "residential": 0.36, "default": 0.24}

# Minimum contrast ratio (WCAG formula) against the background. Only colors below
# the floor are nudged, toward the theme's own text color, so good themes are untouched.
CONTRAST_FLOOR = {"road_motorway": 4.5, "road_primary": 3.2, "road_secondary": 2.3,
                  "road_tertiary": 1.7, "water": 1.2, "parks": 1.12}

# Protected areas bigger than this share of the view AND this size are skipped: at
# city scale a national monument is a flat block, not a park.
GIANT_PARK_SHARE = 0.05
GIANT_PARK_MIN_M2 = 400e6


def map_detail(radius_m: float) -> float:
    """0 at <= 3 km (original look) .. 1 at >= 15 km (city scale)."""
    import math
    d = (math.log(max(radius_m, 1)) - math.log(3000)) / (math.log(15000) - math.log(3000))
    return min(max(d, 0.0), 1.0)


def _rel_lum(c) -> float:
    from matplotlib.colors import to_rgb
    r, g, b = [(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4) for x in to_rgb(c)]
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b) -> float:
    la, lb = sorted((_rel_lum(a), _rel_lum(b)))
    return (lb + 0.05) / (la + 0.05)


def _lift(color, bg, toward, floor):
    """Blend color toward `toward` just enough to reach the contrast floor."""
    from .themes import mix
    if contrast(color, bg) >= floor:
        return color
    if contrast(toward, bg) < floor:   # text itself too weak: use black / white
        toward = "#000000" if _rel_lum(bg) > 0.18 else "#FFFFFF"
    lo, hi = 0.0, 1.0
    for _ in range(18):
        mid = (lo + hi) / 2
        if contrast(mix(color, toward, mid), bg) >= floor:
            hi = mid
        else:
            lo = mid
    return mix(color, toward, hi)


def tuned_theme(theme: dict, detail: float) -> dict:
    """Print-quality color adjustments, computed from the theme itself."""
    from .themes import mix
    t = dict(theme)
    bg = t["bg"]
    for key, floor in CONTRAST_FLOOR.items():
        t[key] = _lift(t[key], bg, t["text"], floor)
    # keep the hierarchy readable: minor roads always sit below residential streets
    minor = mix(bg, t["road_residential"], 0.75)
    t["road_default"] = mix(t["road_default"], minor, detail)
    t["road_residential"] = mix(t["road_residential"], bg, 0.1 * detail)
    return t


def road_width(cls: str, detail: float) -> float:
    base = ROAD_CLASSES[cls][1]
    return base + (CITY_WIDTHS[cls] - base) * detail


# ------------------------------------------------------------------ layers

class _Projector:
    def __init__(self, lat, lon):
        import geopandas as gpd
        from shapely.geometry import Point

        center = gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326")
        self.crs = center.estimate_utm_crs()
        self.cx, self.cy = center.to_crs(self.crs).iloc[0].coords[0]
        from pyproj import Transformer
        self._t = Transformer.from_crs("EPSG:4326", self.crs, always_xy=True)

    def gdf(self, g):
        return g.to_crs(self.crs) if g is not None and len(g) else None

    def xy(self, lon, lat):
        return self._t.transform(lon, lat)

    def geom(self, geom):
        from shapely.ops import transform
        return transform(self._t.transform, geom)


def _lines_to_segments(geoms):
    """Lines/MultiLines -> list of (N,2) arrays for a LineCollection, fast."""
    import shapely

    parts = shapely.get_parts(np.asarray(geoms))
    if len(parts) == 0:
        return []
    coords, idx = shapely.get_coordinates(parts, return_index=True)
    cuts = np.flatnonzero(np.diff(idx)) + 1
    return np.split(coords, cuts)


def _lines_path(geoms):
    """Lines/MultiLines -> ONE compound matplotlib Path (MOVETO per line).
    Building 600k separate Path objects for a LineCollection costs far more than
    drawing them; a single path draws the same pixels."""
    from matplotlib.path import Path as MPath
    import shapely

    parts = shapely.get_parts(np.asarray(geoms))
    if len(parts) == 0:
        return None
    coords, idx = shapely.get_coordinates(parts, return_index=True)
    if len(coords) < 2:
        return None
    codes = np.full(len(coords), MPath.LINETO, dtype=MPath.code_type)
    codes[0] = MPath.MOVETO
    codes[np.flatnonzero(np.diff(idx)) + 1] = MPath.MOVETO
    return MPath(coords, codes)


def _poly_path(geoms):
    """Polygons -> one compound matplotlib Path (fast, holes respected)."""
    from matplotlib.path import Path as MPath
    import shapely

    polys = shapely.get_parts(np.asarray(geoms))
    polys = polys[shapely.get_type_id(polys) == 3] if len(polys) else polys
    if len(polys) == 0:
        return None
    nint = shapely.get_num_interior_rings(polys)
    owner = np.repeat(np.arange(len(polys)), nint)
    nth = np.arange(len(owner)) - np.repeat(np.cumsum(nint) - nint, nint)
    # exterior then holes, per polygon (same order as before)
    rings = np.empty(len(polys) + len(owner), dtype=object)
    order = np.argsort(np.r_[np.arange(len(polys)), owner], kind="stable")
    rings[:] = np.r_[shapely.get_exterior_ring(polys),
                     shapely.get_interior_ring(polys[owner], nth)][order]
    rings = rings[shapely.get_num_coordinates(rings) >= 4]
    if len(rings) == 0:
        return None
    coords, idx = shapely.get_coordinates(rings, return_index=True)
    starts = np.r_[0, np.flatnonzero(np.diff(idx)) + 1]
    ends = np.r_[starts[1:], len(coords)] - 1
    codes = np.full(len(coords), MPath.LINETO, dtype=MPath.code_type)
    codes[starts] = MPath.MOVETO
    codes[ends] = MPath.CLOSEPOLY
    return MPath(coords, codes)


def _add_polys(ax, path, color, zorder, gid, clip):
    from matplotlib.patches import PathPatch
    if path is None:
        return
    patch = PathPatch(path, facecolor=color, edgecolor="none", linewidth=0, zorder=zorder)
    patch.set_gid(gid)
    # add_artist, not add_patch: add_patch walks every vertex to update the data
    # limits (15 s at city scale), and our limits are fixed anyway.
    ax.add_artist(patch)
    clip.append(patch)


def _add_path_lines(ax, path, color, width, zorder, gid, clip):
    from matplotlib.patches import PathPatch
    if path is None:
        return
    patch = PathPatch(path, facecolor="none", edgecolor=color, linewidth=width,
                      capstyle="round", joinstyle="round", zorder=zorder)
    patch.set_gid(gid)
    ax.add_artist(patch)
    clip.append(patch)


def _add_lines(ax, segs, color, width, zorder, gid, clip, **kw):
    from matplotlib.collections import LineCollection
    if not segs:
        return
    lc = LineCollection(segs, colors=color, linewidths=width, capstyle="round",
                        joinstyle="round", zorder=zorder, **kw)
    lc.set_gid(gid)
    ax.add_collection(lc, autolim=False)
    clip.append(lc)


def _simplify(geoms, tol, polygons=False):
    """Vector export: drop detail finer than half a printed pixel. Invisible on paper,
    but it is most of the file size of a city-scale PDF / SVG."""
    import shapely
    if not tol or len(geoms) == 0:
        return geoms
    b = shapely.bounds(geoms)
    big = np.maximum(b[:, 2] - b[:, 0], b[:, 3] - b[:, 1]) >= tol
    geoms = shapely.simplify(geoms[big], tol, preserve_topology=polygons)
    return geoms[~shapely.is_empty(geoms)]


def _prepared(data, P, view_area=None, tol=0.0):
    """Projected, theme-independent drawing paths, built once per data + projection
    and reused for every theme of an all-themes run."""
    import shapely
    key = (P.crs.to_string(), round(view_area or 0), round(tol, 2))
    store = data.__dict__.setdefault("_prep", {})
    if key in store:
        return store[key]
    store.clear()  # one projection at a time keeps memory flat
    prep = {"polys": {}, "lines": {}, "roads": {}}
    for name in POLY_LAYERS:
        g = data.layer(name)
        if g is not None:
            geoms = P.gdf(g).geometry.values
            if name == "parks" and view_area:
                big = shapely.area(geoms) > max(GIANT_PARK_SHARE * view_area, GIANT_PARK_MIN_M2)
                if big.any():
                    log(f"  (skipping {int(big.sum())} protected area(s) larger than "
                        f"{GIANT_PARK_SHARE:.0%} of the map)")
                    geoms = geoms[~big]
            prep["polys"][name] = _poly_path(_simplify(geoms, tol, polygons=True))
    for name in LINE_LAYERS:
        g = data.layer(name)
        if g is not None:
            geoms = _simplify(P.gdf(g).geometry.values, tol)
            prep["lines"][name] = (_lines_to_segments(geoms) if name in DASHED
                                   else _lines_path(geoms))
    roads = P.gdf(data.roads)
    if roads is not None and data.layer("trails") is not None:
        roads = roads[~roads["highway"].isin(TRAIL_HIGHWAYS)]
    if roads is not None:
        classes = roads["highway"].map(lambda v: _HIGHWAY_TO_CLASS.get(v, "default")).to_numpy()
        for cls in ROAD_CLASSES:
            prep["roads"][cls] = _lines_path(_simplify(roads.geometry.values[classes == cls], tol))
    store[key] = prep
    return prep


def _gradient(ax, color, where, extend=0.0, classic=False):
    """Fade on the trim axes. `extend` = extra fraction past the trim edge (bleed),
    filled solid so the fade still reaches the paper edge. The non-classic curve stays
    solid under the text block and eases out, so streets don't run through the title."""
    import matplotlib.colors as mcolors

    rgba = np.zeros((256, 4))
    rgba[:, :3] = mcolors.to_rgb(color)
    u = np.linspace(0, 1, 256)
    if classic:
        fade = 1 - u
    else:
        v = np.clip((u - 0.3) / 0.7, 0, 1)
        fade = 1 - v * v * (3 - 2 * v)
    if where == "bottom":
        rgba[:, 3] = fade
        y0, y1 = 0.0, 0.25
    else:
        rgba[:, 3] = fade[::-1]
        y0, y1 = 0.75, 1.0
    grad = np.linspace(0, 1, 256).reshape(-1, 1)
    im = ax.imshow(np.hstack((grad, grad)), extent=[0, 1, y0, y1], transform=ax.transAxes,
                   aspect="auto", cmap=mcolors.ListedColormap(rgba), zorder=10,
                   origin="lower", clip_on=False)
    im.set_gid(f"fade-{where}")
    if extend > 0:
        from matplotlib.patches import Rectangle
        y = -extend if where == "bottom" else 1.0
        r = Rectangle((-extend, y), 1 + 2 * extend, extend, transform=ax.transAxes,
                      facecolor=color, edgecolor="none", zorder=10, clip_on=False)
        r.set_gid(f"fade-{where}-bleed")
        ax.add_patch(r)


def _fp_factory(fonts):
    from matplotlib.font_manager import FontProperties

    def fp(weight, size):
        if fonts:
            return FontProperties(fname=fonts[weight], size=size)
        return FontProperties(family="monospace",
                              weight="bold" if weight == "bold" else "normal", size=size)
    return fp


# ------------------------------------------------------------------- poster

def render_poster(data: MapData, theme: dict, opts: PosterOptions, output: Path) -> Path:
    import matplotlib
    matplotlib.rcParams["agg.path.chunksize"] = 20000
    matplotlib.rcParams["svg.fonttype"] = "path"
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from matplotlib.patches import PathPatch, Rectangle
    import matplotlib.patheffects as pe
    import shapely

    log(f"Rendering '{theme.get('name', theme['_key'])}'...")
    P = _Projector(opts.lat, opts.lon)
    cx, cy = P.cx, P.cy

    w, h, b = opts.width, opts.height, max(opts.bleed, 0.0)
    slug = 0.3 if opts.crop_marks else 0.0
    W, H = w + 2 * b, h + 2 * b                  # printed sheet incl. bleed
    FW, FH = W + 2 * slug, H + 2 * slug          # file size incl. crop-mark margin
    fig = Figure(figsize=(FW, FH), facecolor="white" if slug else theme["bg"])
    FigureCanvasAgg(fig)
    ax = fig.add_axes((slug / FW, slug / FH, W / FW, H / FH))   # map: sheet incl. bleed
    ax.set_facecolor(theme["bg"])
    ax.set_axis_off()
    tax = fig.add_axes(((slug + b) / FW, (slug + b) / FH, w / FW, h / FH))  # trim area
    tax.set_axis_off()
    tax.set_xlim(0, 1)
    tax.set_ylim(0, 1)
    tax.patch.set_alpha(0)

    # View window in meters. Trim half-extents, grown to cover the bleed.
    hx, hy = view_half_extents(opts.radius_m, w, h)
    HX, HY = hx * W / w, hy * H / h
    shaped = opts.shape in ("circle", "heart", "boundary")
    # Shaped maps sit a bit off-center to leave room for the text block.
    f = 0.5
    if shaped and opts.show_text:
        f = 0.58 if opts.text_position == "bottom" else 0.42
    F = (b + f * h) / H
    x0, x1 = cx - HX, cx + HX
    y0 = cy - F * 2 * HY
    y1 = y0 + 2 * HY
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal", adjustable="box")
    view_box = shapely.box(x0, y0, x1, y1)

    clip_targets: list = []
    rs = opts.road_scale * (auto_road_factor(opts.radius_m, w, h) if opts.auto_roads else 1.0)
    detail = 0.0 if opts.classic else map_detail(opts.radius_m)
    if not opts.classic:
        theme = tuned_theme(theme, detail)

    # --- base layers
    coast = data.layer("coastline")
    if coast is not None:
        sea = ocean_polygons(P.gdf(coast).geometry.values, view_box)
        if sea:
            _add_polys(ax, _poly_path(sea), theme["ocean"], 0.4, "ocean", clip_targets)
    cancel = opts.check_cancel or (lambda: None)
    cancel()
    tol = 0.0
    if opts.fmt in ("pdf", "svg"):
        tol = 0.5 * (2 * HX) / (W * 300)   # half a 300 dpi pixel, in map meters
    prep = _prepared(data, P, None if opts.classic else (x1 - x0) * (y1 - y0), tol)
    cancel()
    for name, (ckey, z) in POLY_LAYERS.items():
        if name in prep["polys"]:
            _add_polys(ax, prep["polys"][name], theme[ckey], z, name, clip_targets)
    if opts.terrain != "none":
        from .decor import draw_terrain
        draw_terrain(ax, P, (x0, x1, y0, y1), theme, opts.terrain,
                     opts.data_bbox or data.bbox, opts.contour_interval_ft,
                     opts.terrain_strength, rs, clip_targets,
                     opts.check_cancel or (lambda: None))
    for name, (ckey, lw, z) in LINE_LAYERS.items():
        if name not in prep["lines"]:
            continue
        if name in DASHED:
            _add_lines(ax, prep["lines"][name], theme[ckey], lw * rs, z, name,
                       clip_targets, linestyles=DASHED[name])
        else:
            _add_path_lines(ax, prep["lines"][name], theme[ckey], lw * rs, z, name,
                            clip_targets)

    for cls, (ckey, lw, order) in sorted(ROAD_CLASSES.items(), key=lambda kv: kv[1][2]):
        if cls in prep["roads"]:
            _add_path_lines(ax, prep["roads"][cls], theme[ckey],
                            road_width(cls, detail) * rs, 2 + order / 10,
                            f"roads-{cls}", clip_targets)

    # --- overlays
    scale = min(w, h) / 12.0
    for i, route in enumerate(opts.routes):
        xs, ys = P.xy(route[:, 0], route[:, 1])
        xs, ys = np.asarray(xs), np.asarray(ys)
        (ln,) = ax.plot(xs, ys, color=theme["route"], linewidth=opts.route_width * scale,
                        solid_capstyle="round", solid_joinstyle="round", zorder=10.5)
        ln.set_gid(f"route-{i + 1}")
        clip_targets.append(ln)
        for (px, py) in ((xs[0], ys[0]), (xs[-1], ys[-1])):
            d = ax.scatter([px], [py], s=(opts.route_width * 3.2 * scale) ** 2,
                           color=theme["route"], zorder=10.6, linewidths=0)
            d.set_gid(f"route-{i + 1}-end")
            clip_targets.append(d)

    # --- shape mask
    mask = None
    if shaped:
        size = min(hx, hy * 0.8) * 0.9
        scx, scy = cx, cy
        boundary = P.geom(opts.boundary) if (opts.shape == "boundary" and opts.boundary) else None
        if opts.shape == "boundary" and boundary is None:
            log("⚠ No boundary available; drawing the full rectangle instead")
        mask = shape_polygon(opts.shape, scx, scy, size, boundary)
        if mask is not None:
            mpath = _poly_path([mask] if mask.geom_type == "Polygon" else list(mask.geoms))
            clip_patch = PathPatch(mpath, transform=ax.transData, facecolor="none",
                                   edgecolor="none")
            if opts.photo:
                # Photo fills the shape; the map surrounds it.
                from .decor import load_photo
                mx0, my0, mx1, my1 = mask.bounds
                img = load_photo(opts.photo, (mx1 - mx0) / (my1 - my0))
                pim = ax.imshow(img, extent=[mx0, mx1, my0, my1], zorder=10.2,
                                interpolation="bilinear")
                pim.set_gid("photo")
                pim.set_clip_path(clip_patch)
                ax.set_xlim(x0, x1)
                ax.set_ylim(y0, y1)
            else:
                for art in clip_targets:
                    art.set_clip_path(clip_patch)
            outline = PathPatch(mpath, facecolor="none", edgecolor=theme["text"],
                                linewidth=1.0 * scale, alpha=0.6, zorder=10.7)
            outline.set_gid("shape-outline")
            ax.add_patch(outline)

    if opts.highlight is not None:
        from .decor import draw_highlight
        draw_highlight(ax, P.geom(opts.highlight), theme, opts.highlight_mode,
                       (x0, x1, y0, y1), min(w, h) / 12.0, opts.highlight_label,
                       _fp_factory(opts.fonts))
    if opts.grid:
        from .decor import draw_grid
        draw_grid(ax, tax, P, theme, (x0, x1, y0, y1), _fp_factory(opts.fonts),
                  min(w, h) / 12.0)

    if opts.show_gradient and not shaped:
        ext_b = b / h
        _gradient(tax, theme["gradient_color"], "bottom", ext_b, opts.classic)
        _gradient(tax, theme["gradient_color"], "top", ext_b, opts.classic)

    # markers (above fades so they stay crisp)
    fp = _fp_factory(opts.fonts)

    icons = {"pin": pin_path(), "heart": heart_path(), "star": "*", "dot": "o"}
    halo = [pe.withStroke(linewidth=3 * scale, foreground=theme["bg"])]
    for i, m in enumerate(opts.markers):
        mx, my = P.xy(m.lon, m.lat)
        icon = icons.get(m.icon, icons["pin"])
        size = {"pin": 34, "heart": 24, "star": 26, "dot": 12}.get(m.icon, 30) * scale
        sc = ax.scatter([mx], [my], marker=icon, s=size ** 2, color=theme["marker"],
                        edgecolors=theme["bg"], linewidths=0.8 * scale, zorder=12)
        sc.set_gid(f"marker-{i + 1}")
        if m.label:
            dy = (size * 1.35 if m.icon == "pin" else size * 0.6)
            t = ax.annotate(m.label, (mx, my), xytext=(0, dy), textcoords="offset points",
                            ha="center", va="bottom", color=theme["text"],
                            fontproperties=fp("regular", 13 * scale), zorder=12,
                            path_effects=halo)
            t.set_gid(f"marker-{i + 1}-label")

    # --- text block
    text_color = theme["text"]
    if opts.show_text:
        city = opts.display_city or opts.city
        country = opts.display_country or opts.country_label or opts.country
        label = style_title(city, opts.title_style, opts.letter_spacing)
        # Same rule as the original: shrink only when the NAME is over 10 letters.
        main_size = 60 * scale
        if len(city) > 10:
            main_size = max(main_size * 10 / len(city), 10 * scale)

        if opts.text_position == "top":
            ys = {"city": 0.885, "line": 0.872, "country": 0.84, "coords": 0.812, "tag": 0.787}
        else:
            ys = {"city": 0.14, "line": 0.125, "country": 0.10, "coords": 0.07, "tag": 0.045}

        text_halo = None if opts.classic else [
            pe.withStroke(linewidth=3.5 * scale, foreground=theme["gradient_color"])]

        def put(y, s, weight, size, gid, alpha=1.0):
            t = tax.text(0.5, y, s, transform=tax.transAxes, color=text_color, ha="center",
                         alpha=alpha, fontproperties=fp(weight, size), zorder=11,
                         path_effects=text_halo)
            t.set_gid(gid)
            return t

        city_t = put(ys["city"], label, "bold", main_size, "text-city")
        # Never let the title run off the paper (long names, wide spacing, fonts).
        try:
            ext = city_t.get_window_extent(fig.canvas.get_renderer())
            avail = 0.9 * tax.get_window_extent().width
            if ext.width > avail:
                city_t.set_fontsize(main_size * avail / ext.width)
        except Exception:
            pass
        put(ys["country"], country.upper() if is_latin_script(country) else country,
            "light", 22 * scale, "text-country")
        if opts.show_coords:
            put(ys["coords"], format_coords(opts.lat, opts.lon), "regular", 14 * scale,
                "text-coords", 0.7)
        if opts.tagline:
            put(ys["tag"], opts.tagline, "light", 13 * scale, "text-tagline", 0.85)
        (div,) = tax.plot([0.4, 0.6], [ys["line"]] * 2, transform=tax.transAxes,
                          color=text_color, linewidth=1 * scale, zorder=11)
        div.set_gid("text-divider")

    aspect = w / h  # converts trim-x fractions into equal trim-y fractions
    if opts.text_position == "top":
        text_zone = (0.76, 1.0) if opts.show_text else (2, 2)
    else:
        text_zone = (0.0, 0.25) if opts.show_text else (-1, -1)
    if opts.elevation_profile and opts.routes:
        from .decor import draw_profile
        rect = (0.2, 0.215, 0.6, 0.05) if opts.text_position != "top" else (0.2, 0.69, 0.6, 0.05)
        lookup = None
        try:
            from .terrain import DEM
            pts = np.vstack([r[:, :2] for r in opts.routes])
            (lw_, ls_), (le_, ln_) = pts.min(0), pts.max(0)
            dem = DEM(lw_ - 0.01, ls_ - 0.01, le_ + 0.01, ln_ + 0.01, 30)
            lookup = dem.sample
        except Exception as e:
            log(f"  (no elevation data for the profile: {e})")
        draw_profile(fig, tax, opts.routes, theme, fp, scale, rect, lookup)
        if opts.text_position == "top":
            text_zone = (0.67, 1.0)
        else:
            text_zone = (0.0, 0.3)
    if opts.labels:
        from .decor import draw_labels
        draw_labels(fig, ax, tax, data, P, theme, set(opts.labels), fp, scale,
                    opts.label_scale, (x0, x1, y0, y1), text_zone, mask)
    if opts.scale_bar or opts.north_arrow:
        from .decor import draw_north_arrow, draw_scale_bar
        inset = 0.06 if opts.border != "none" else 0.045
        end = inset
        if opts.scale_bar:
            end = draw_scale_bar(tax, theme, 2 * hx, fp, scale, x=inset, y=0.03 + inset / 3)
        if opts.north_arrow:
            draw_north_arrow(tax, theme, fp, scale, end + 0.035, 0.03 + inset / 3, aspect)
    # corner items stay clear of the text block (and scale bar)
    lift = (text_zone[1] + 0.01) if text_zone[0] <= 0 else 0.07
    drop = (1 - text_zone[0] + 0.01) if text_zone[1] >= 1 and text_zone[0] < 1 else 0.0
    if opts.photo and mask is None:
        from .decor import draw_photo_badge, load_photo
        draw_photo_badge(fig, tax, load_photo(opts.photo, 1.0), theme, opts.photo_corner,
                         aspect, scale, lift, drop)
    if opts.qr:
        from .decor import draw_qr
        draw_qr(fig, tax, opts.qr, theme, opts.qr_corner, aspect, scale, w, lift, drop)

    # --- border
    if opts.border != "none":
        insets = {"thin": [(0.03, 1.0)], "thick": [(0.03, 4.0)],
                  "double": [(0.025, 1.0), (0.037, 0.6)]}[opts.border]
        for j, (inset, lw) in enumerate(insets):
            ins_y = inset * w / h
            r = Rectangle((inset, ins_y), 1 - 2 * inset, 1 - 2 * ins_y, transform=tax.transAxes,
                          facecolor="none", edgecolor=theme["border"], linewidth=lw * scale,
                          zorder=13)
            r.set_gid(f"border-{j + 1}")
            tax.add_patch(r)

    # OpenStreetMap data is ODbL: attribution stays on every poster.
    credit = "© OpenStreetMap contributors"
    if opts.terrain != "none" or (opts.elevation_profile and opts.routes):
        from .terrain import ATTRIBUTION
        credit += "  ·  " + ATTRIBUTION
    att = tax.text(0.98, 0.012 if opts.border == "none" else 0.045,
                   credit, transform=tax.transAxes,
                   color=text_color, alpha=0.5 if opts.classic else 0.72,
                   ha="right", va="bottom",
                   fontproperties=fp("light", 8), zorder=13)
    att.set_gid("text-attribution")

    if opts.crop_marks:
        from .decor import draw_crop_marks
        draw_crop_marks(fig, slug, b, w, h)

    cancel()
    log("  Saving…")
    output.parent.mkdir(parents=True, exist_ok=True)
    kw = dict(facecolor=fig.get_facecolor(), format=opts.fmt)
    if opts.fmt == "png":
        kw["dpi"] = opts.dpi
        # Tag the PNG as sRGB so print shops and photo apps don't guess the color space.
        icc = _srgb_icc()
        if icc:
            kw["pil_kwargs"] = {"icc_profile": icc, "dpi": (opts.dpi, opts.dpi)}
    fig.savefig(output, **kw)
    fig.clear()
    if opts.fmt == "svg":
        _svg_to_layers(output)
    log(f"✓ Saved {output}")
    return output


_SRGB = None


def _srgb_icc() -> bytes | None:
    global _SRGB
    if _SRGB is None:
        try:
            from PIL import ImageCms
            _SRGB = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        except Exception:
            _SRGB = b""
    return _SRGB or None


# ------------------------------------------------------------- layered svg

_LAYER_IDS = re.compile(
    r'<g id="((?:figure|axes)_\d+|ocean|water|parks|airports|buildings|waterways|railways|'
    r'washes|trails|hillshade|contours-\w+|labels-\w+|highlight-\w+|grid(?:-label)?|'
    r'scale-bar(?:-text)?|north-arrow(?:-n)?|elevation-profile(?:-text)?|photo|qr-code|'
    r'crop-marks|roads-\w+|route-\d+(?:-end)?|shape-outline|fade-\w+(?:-bleed)?|'
    r'marker-\d+(?:-label)?|text-\w+|border-\d+)"')


def _svg_to_layers(path: Path) -> None:
    """Mark matplotlib's named groups as Inkscape layers (Illustrator sees groups)."""
    s = path.read_text(encoding="utf-8")
    if "xmlns:inkscape" not in s:
        s = s.replace("<svg ", '<svg xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" ',
                      1)
    s = _LAYER_IDS.sub(lambda m: f'<g id="{m.group(1)}" inkscape:groupmode="layer" '
                                 f'inkscape:label="{m.group(1)}"', s)
    path.write_text(s, encoding="utf-8")
