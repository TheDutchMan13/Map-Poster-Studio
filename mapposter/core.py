"""One entry point used by both the CLI and the GUI."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field, fields
from datetime import datetime
from pathlib import Path

from . import fonts as fontmod
from . import geocode, paths, sources, themes
from .geometry import Marker, parse_marker, read_gpx, routes_extent
from .log import log
from .render import PosterOptions, render_poster
from .units import M_PER_MI, fmt_miles, parse_distance
from .sources import bbox_for, view_half_extents

MAX_INCHES = 36.0
PREVIEW_DPI = 100   # about screen size for a 12x16 poster; thin lines still show
PREVIEW_MAX_PX = 1800


def preview_dpi(width: float, height: float) -> int:
    """Preview resolution: 100 dpi, but never more than ~1800 px on the long side."""
    return max(30, min(PREVIEW_DPI, int(PREVIEW_MAX_PX / max(width, height, 1))))


@dataclass
class Job:
    city: str
    country: str
    themes: list[str] = field(default_factory=lambda: ["terracotta"])
    distance_m: float = 3 * M_PER_MI   # true radius in METERS: center -> nearest poster edge
    legacy_distance: bool = False      # interpret distance like the original script
    width: float = 12.0
    height: float = 16.0
    latitude: str | float | None = None
    longitude: str | float | None = None
    country_label: str | None = None
    display_city: str | None = None
    display_country: str | None = None
    font_family: str | None = None
    fmt: str = "png"
    dpi: int = 300
    road_scale: float = 1.0
    auto_roads: bool = True
    classic: bool = False              # draw exactly like the original maptoposter
    show_text: bool = True
    show_coords: bool = True
    show_gradient: bool = True
    pbf: str | None = None
    output_dir: str | None = None
    use_cache: bool = True
    # layers (None = defaults from layers.json)
    layers: list[str] | None = None
    # layout
    text_position: str = "bottom"
    title_style: str = "spaced"
    letter_spacing: int = 2
    tagline: str = ""
    border: str = "none"
    shape: str = "rect"
    boundary_file: str | None = None
    bleed: float = 0.0
    # overlays
    markers: list = field(default_factory=list)   # Marker or "lat, lon, label, icon"
    gpx: list = field(default_factory=list)       # paths to .gpx files
    fit_route: bool = False
    route_width: float = 2.2
    elevation_profile: bool = False
    # terrain
    terrain: str = "none"                         # none | hillshade | contours | both
    contour_interval_ft: float | None = None
    terrain_strength: float = 1.0
    # labels, highlight, map furniture
    labels: list = field(default_factory=list)    # roads, places, parks
    label_scale: float = 1.0
    highlight: str | None = None                  # place name, e.g. "Encanto, Phoenix"
    highlight_file: str | None = None
    highlight_mode: str = "fill"                  # fill | focus
    highlight_label: str = ""
    scale_bar: bool = False
    north_arrow: bool = False
    grid: bool = False
    # photo, QR, fonts
    photo: str | None = None
    photo_corner: str = "top-right"
    qr: str = ""
    qr_corner: str = "top-left"
    font_file: str | None = None
    # print
    crop_marks: bool = False
    icc: str | None = None                        # CMYK .icc/.icm profile -> extra .tif
    # sets
    set_places: list = field(default_factory=list)   # ["Tempe, USA", "Mesa, USA", ...]
    zoom_series: list = field(default_factory=list)  # radii in METERS
    set_gap: float = 0.4                              # inches between panels
    # extras
    mockup: str | None = None                     # None | black | white | oak
    preview: bool = False


def slug(text: str) -> str:
    s = re.sub(r"[^\w]+", "_", text.strip().lower(), flags=re.UNICODE).strip("_")
    return s or "poster"


def output_filename(out_dir: Path, city: str, theme: str, fmt: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    p = out_dir / f"{slug(city)}_{theme}_{ts}.{fmt}"
    n = 2
    while p.exists():  # all-themes runs can land in the same second
        p = out_dir / f"{slug(city)}_{theme}_{ts}_{n}.{fmt}"
        n += 1
    return p


def _markers(job: Job) -> list[Marker]:
    out = []
    for m in job.markers or []:
        if isinstance(m, Marker):
            out.append(m)
        elif isinstance(m, dict):
            out.append(Marker(**m))
        elif str(m).strip():
            out.append(parse_marker(str(m)))
    return out


def to_cmyk(png: Path, icc: str) -> Path:
    """Convert a finished PNG to a CMYK TIFF using the print shop's ICC profile."""
    from PIL import Image, ImageCms
    Image.MAX_IMAGE_PIXELS = None
    im = Image.open(png).convert("RGB")
    srgb = ImageCms.createProfile("sRGB")
    dst = ImageCms.getOpenProfile(icc)
    out = ImageCms.profileToProfile(im, srgb, dst, renderingIntent=1, outputMode="CMYK")
    tif = png.with_suffix(".cmyk.tif")
    dpi = im.info.get("dpi", (300, 300))
    out.save(tif, compression="tiff_lzw", dpi=dpi, icc_profile=dst.tobytes())
    log(f"✓ CMYK TIFF {tif.name}")
    return tif


def run(job: Job, check_cancel=lambda: None, on_output=lambda p: None) -> list[Path]:
    if job.set_places or job.zoom_series:
        return run_set(job, check_cancel, on_output)
    paths.ensure_dirs()
    t0 = time.time()

    for attr in ("width", "height"):
        v = getattr(job, attr)
        if v > MAX_INCHES:
            log(f"⚠ {attr.capitalize()} {v} exceeds max {MAX_INCHES:g} in; using {MAX_INCHES:g}")
            setattr(job, attr, MAX_INCHES)
        if v <= 0:
            raise ValueError(f"{attr} must be positive")

    available = themes.available_themes()
    missing = [t for t in job.themes if t not in available]
    if missing:
        raise ValueError(f"Theme(s) not found: {', '.join(missing)}. "
                         f"Available: {', '.join(available)}")
    if job.preview:
        job.themes = job.themes[:1]

    # ----- overlays first (a route can decide the center and size)
    routes = []
    for g in job.gpx or []:
        routes += read_gpx(g)
    markers = _markers(job)

    radius = job.distance_m / 4 if job.legacy_distance else job.distance_m

    if job.fit_route and routes:
        lat, lon, radius = routes_extent(routes, job.width, job.height)
        log(f"✓ Fitted to route: center {lat:.5f}, {lon:.5f}, radius {fmt_miles(radius)}")
    elif job.latitude not in (None, "") and job.longitude not in (None, ""):
        lat = geocode.parse_coordinate(job.latitude)
        lon = geocode.parse_coordinate(job.longitude)
        log(f"✓ Coordinates: {lat:.5f}, {lon:.5f}")
    else:
        lat, lon = geocode.get_coordinates(job.city, job.country)
    log(f"Area: {fmt_miles(radius)} from center to nearest edge"
        + (f" (legacy -d {job.distance_m:g} m)" if job.legacy_distance else ""))
    check_cancel()

    boundary = None
    if job.shape == "boundary":
        from .extras import city_boundary
        boundary = city_boundary(job.city, job.country, job.boundary_file)
    highlight = None
    if job.highlight or job.highlight_file:
        from .extras import place_polygon
        highlight = place_polygon(job.highlight or "", job.highlight_file)

    font_files = fontmod.load_fonts(job.font_family, job.font_file)

    # Data covers the whole sheet incl. bleed, and is fetched ONCE for every theme.
    hx, hy = view_half_extents(radius, job.width, job.height)
    grow_x = (job.width + 2 * job.bleed) / job.width
    grow_y = (job.height + 2 * job.bleed) / job.height
    shift = 0.08 * 2 * hy if job.shape in ("circle", "heart", "boundary") else 0
    bbox = bbox_for(lat, lon, hx * grow_x, hy * grow_y + shift)
    layers = job.layers
    if "places" in (job.labels or []):   # place labels need the place-name data
        layers = list(layers if layers is not None else paths.default_enabled_layers())
        if "places" not in layers:
            layers.append("places")
    data = sources.get_map_data(lat, lon, radius, job.width, job.height,
                                pbf=job.pbf or None, use_cache=job.use_cache,
                                check_cancel=check_cancel, enabled=layers, bbox=bbox,
                                allow_empty=job.terrain != "none")
    check_cancel()

    if job.preview:
        out_dir = paths.CACHE_DIR / "preview"
    else:
        out_dir = Path(job.output_dir) if job.output_dir else paths.POSTERS_DIR
    outputs = []
    for i, name in enumerate(job.themes, 1):
        check_cancel()
        theme = themes.load_theme(name)
        log(f"\n[{i}/{len(job.themes)}] {theme.get('name', name)}")
        opts = PosterOptions(
            city=job.city, country=job.country, lat=lat, lon=lon, radius_m=radius,
            width=job.width, height=job.height,
            display_city=job.display_city or None,
            display_country=job.display_country or None,
            country_label=job.country_label or None,
            fonts=font_files,
            fmt="png" if job.preview else job.fmt,
            dpi=preview_dpi(job.width, job.height) if job.preview else job.dpi,
            road_scale=job.road_scale, auto_roads=job.auto_roads, classic=job.classic,
            show_text=job.show_text, show_coords=job.show_coords,
            show_gradient=job.show_gradient,
            text_position=job.text_position, title_style=job.title_style,
            letter_spacing=job.letter_spacing, tagline=job.tagline or "",
            border=job.border, shape=job.shape, boundary=boundary,
            bleed=0 if job.preview else job.bleed,
            markers=markers, routes=routes, route_width=job.route_width,
            elevation_profile=job.elevation_profile,
            terrain=job.terrain, contour_interval_ft=job.contour_interval_ft,
            terrain_strength=job.terrain_strength, data_bbox=bbox,
            labels=job.labels or [], label_scale=job.label_scale,
            highlight=highlight, highlight_mode=job.highlight_mode,
            highlight_label=job.highlight_label or "",
            scale_bar=job.scale_bar, north_arrow=job.north_arrow, grid=job.grid,
            photo=job.photo or None, photo_corner=job.photo_corner,
            qr=job.qr or "", qr_corner=job.qr_corner,
            crop_marks=False if job.preview else job.crop_marks,
            check_cancel=check_cancel,
        )
        out = output_filename(out_dir, job.city, name, opts.fmt)
        if job.preview:
            out = out_dir / "preview.png"
        out = render_poster(data, theme, opts, out)
        outputs.append(out)
        if job.icc and not job.preview and out.suffix == ".png":
            to_cmyk(out, job.icc)
        if job.mockup and not job.preview and out.suffix == ".png":
            from .extras import make_mockup
            make_mockup(out, job.mockup)
        on_output(out)

    log(f"\n✓ Done: {len(outputs)} {'preview' if job.preview else 'poster(s)'} "
        f"in {time.time() - t0:,.0f}s → {out_dir}")
    return outputs


# -------------------------------------------------------------------- batch

def _coerce(job_kw: dict) -> dict:
    """Convert CSV text values to the Job field types."""
    types = {f.name: f.type for f in fields(Job)}
    out = {}
    for k, v in job_kw.items():
        if k == "distance_mi":
            out["distance_m"] = parse_distance(v, bare="mi")
            continue
        if k == "distance_km":  # older CSVs
            out["distance_m"] = parse_distance(v, bare="km")
            continue
        if k not in types:
            log(f"  (ignoring unknown column '{k}')")
            continue
        t = str(types[k])
        if k == "zoom_series":
            out[k] = [parse_distance(x, bare="mi") for x in v.split(";") if x.strip()]
            continue
        if k in ("themes", "markers", "gpx", "layers", "labels", "set_places"):
            out[k] = [x.strip() for x in v.split(";") if x.strip()]
        elif "bool" in t:
            out[k] = v.lower() in ("1", "true", "yes", "y", "on")
        elif t.startswith("float"):
            out[k] = float(v)
        elif t.startswith("int"):
            out[k] = int(float(v))
        else:
            out[k] = v
    return out


def run_batch(csv_path, base: Job | None = None, check_cancel=lambda: None,
              on_output=lambda p: None) -> list[Path]:
    from dataclasses import asdict, replace
    from .extras import read_batch

    rows = read_batch(csv_path)
    log(f"Batch: {len(rows)} poster job(s) from {Path(csv_path).name}")
    outputs, failed = [], 0
    for i, row in enumerate(rows, 1):
        check_cancel()
        log(f"\n===== [{i}/{len(rows)}] {row.get('city')} =====")
        try:
            kw = _coerce(row)
            job = replace(base, **kw) if base else Job(**{**{"country": ""}, **kw})
            if kw.get("themes") == ["all"]:
                job.themes = themes.available_themes()
            # fresh mutable defaults per job
            job = Job(**{**asdict(job)})
            outputs += run(job, check_cancel, on_output)
        except Exception as e:
            from .log import Cancelled
            if isinstance(e, Cancelled):
                raise
            failed += 1
            log(f"✗ Row {i} failed: {e}")
    log(f"\nBatch finished: {len(outputs)} poster(s), {failed} failed row(s).")
    return outputs


# ---------------------------------------------------------------- poster sets

def run_set(job: Job, check_cancel=lambda: None, on_output=lambda p: None) -> list[Path]:
    """Several panels side by side in one image, per theme:
    set_places = different places, zoom_series = one place at several radii."""
    import tempfile
    from dataclasses import asdict
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = None
    panels = []
    if job.set_places:
        for entry in job.set_places:
            parts = [p.strip() for p in str(entry).split(",") if p.strip()]
            city = parts[0]
            country = ", ".join(parts[1:]) or job.country
            panels.append(dict(city=city, country=country, latitude=None, longitude=None,
                               display_city=None, display_country=None))
    else:
        for r in job.zoom_series:
            panels.append(dict(distance_m=float(r), legacy_distance=False))
    log(f"Poster set: {len(panels)} panels × {len(job.themes)} theme(s)")

    out_dir = Path(job.output_dir) if job.output_dir else paths.POSTERS_DIR
    if job.preview:
        out_dir = paths.CACHE_DIR / "preview"
    tmp = Path(tempfile.mkdtemp(prefix="mps_set_"))
    results = []
    for theme_name in (job.themes[:1] if job.preview else job.themes):
        imgs = []
        for i, change in enumerate(panels, 1):
            check_cancel()
            log(f"\n=== panel {i}/{len(panels)} ===")
            kw = asdict(job)
            kw.update(change)
            kw.update(themes=[theme_name], fmt="png", output_dir=str(tmp), mockup=None,
                      icc=None, crop_marks=False, bleed=0.0, set_places=[], zoom_series=[],
                      preview=False,
                      dpi=preview_dpi(job.width, job.height) if job.preview else job.dpi)
            sub = Job(**kw)
            imgs += run(sub, check_cancel)
        bg = themes.load_theme(theme_name)["bg"]
        ims = [Image.open(p).convert("RGB") for p in imgs]
        dpi = preview_dpi(job.width, job.height) if job.preview else job.dpi
        gap = int(job.set_gap * dpi)
        Wt = sum(im.width for im in ims) + gap * (len(ims) + 1)
        Ht = max(im.height for im in ims) + 2 * gap
        sheet = Image.new("RGB", (Wt, Ht), bg)
        x = gap
        for im in ims:
            sheet.paste(im, (x, gap))
            x += im.width + gap
        kind = "set" if job.set_places else "zoom"
        name = slug(job.city or panels[0].get("city", "poster"))
        if job.preview:
            out = out_dir / "preview.png"
            out.parent.mkdir(parents=True, exist_ok=True)
            sheet.save(out)
        else:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            ext = "pdf" if job.fmt == "pdf" else "png"
            out = out_dir / f"{name}_{kind}_{theme_name}_{ts}.{ext}"
            out.parent.mkdir(parents=True, exist_ok=True)
            sheet.save(out, dpi=(dpi, dpi), **({"resolution": dpi} if ext == "pdf" else {}))
            if job.mockup and ext == "png":
                from .extras import make_mockup
                make_mockup(out, job.mockup)
        log(f"✓ Saved {out}")
        results.append(out)
        on_output(out)
    for p in tmp.glob("*"):
        try:
            p.unlink()
        except OSError:
            pass
    return results
