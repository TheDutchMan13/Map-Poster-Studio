"""Extra drawing: terrain, labels, highlight, scale bar, north arrow, grid,
elevation profile, photo, QR code and print crop marks."""

from __future__ import annotations

import math

import numpy as np

from .log import log
from .units import M_PER_MI

FT_PER_M = 3.28084


# ----------------------------------------------------------------- terrain

def draw_terrain(ax, P, view, theme, mode, data_bbox, interval_ft, strength, rs,
                 clip_targets, check_cancel=lambda: None):
    """mode: hillshade | contours | both. Returns True if drawn."""
    import matplotlib.colors as mcolors
    from pyproj import Transformer
    from . import terrain

    x0, x1, y0, y1 = view
    nx = 900
    try:
        w, s, e, n = data_bbox
        dem = terrain.DEM(w, s, e, n, (x1 - x0) / nx, check_cancel)
    except Exception as ex:
        log(f"⚠ Terrain skipped: {ex}")
        return False
    inv = Transformer.from_crs(P.crs, "EPSG:4326", always_xy=True)
    xs, ys, z = terrain.grid_for_view(dem, inv, x0, x1, y0, y1, nx)
    cell = (x1 - x0) / (nx - 1)
    zmin, zmax = float(np.nanmin(z)), float(np.nanmax(z))
    log(f"  elevation {zmin * FT_PER_M:,.0f}–{zmax * FT_PER_M:,.0f} ft")

    if mode in ("hillshade", "both"):
        hs = terrain.hillshade(z, cell)
        shadow = 1 - hs
        shadow = np.clip((shadow - 0.25) / 0.75, 0, 1) * strength * 0.75
        rgba = np.zeros(z.shape + (4,))
        rgba[..., :3] = mcolors.to_rgb(theme["hillshade"])
        rgba[..., 3] = shadow
        im = ax.imshow(rgba, extent=[x0, x1, y0, y1], origin="lower", zorder=0.95,
                       interpolation="bilinear")
        im.set_gid("hillshade")
        clip_targets.append(im)

    if mode in ("contours", "both") and zmax - zmin > 3:
        step_ft = interval_ft or terrain.nice_interval_ft(zmin, zmax)
        # smoother lines: more blur where the ground is flat relative to the step
        relief_ft = (zmax - zmin) * FT_PER_M
        blur = 2 if relief_ft > 600 else 4 if relief_ft > 150 else 6
        z_ft = terrain.smooth(z, blur) * FT_PER_M
        start = math.floor(z_ft.min() / step_ft) * step_ft
        levels = np.arange(start, z_ft.max() + step_ft, step_ft)
        major = levels[(np.round(levels / step_ft) % 5) == 0]
        minor = np.setdiff1d(levels, major)
        color = theme["contours"]
        for lv, lw, gid in ((minor, 0.35, "contours-minor"), (major, 0.7, "contours-major")):
            if len(lv) == 0:
                continue
            cs = ax.contour(xs, ys, z_ft, levels=lv, colors=color,
                            linewidths=lw * max(rs, 0.5) * strength ** 0.5, zorder=0.97)
            cs.set_gid(gid)
            clip_targets.append(cs)
        log(f"  contours every {step_ft:g} ft (bold every {step_ft * 5:g} ft)")
    return True


# ------------------------------------------------------------------ labels

def draw_labels(fig, ax, tax, data, P, theme, kinds, fp, scale, label_scale, view,
                avoid_frac, mask=None):
    """Street, place and park names, skipping any that would overlap."""
    import matplotlib.patheffects as pe
    import shapely
    from shapely.ops import linemerge

    x0, x1, y0, y1 = view
    vw = x1 - x0
    renderer = fig.canvas.get_renderer()
    placed = []
    trim = tax.get_window_extent(renderer)
    lo, hi = avoid_frac  # keep clear of the text block (trim fractions)
    halo = [pe.withStroke(linewidth=2.2 * scale, foreground=theme["bg"])]
    color = theme["labels"]
    count = 0

    def try_place(t):
        nonlocal count
        bb = t.get_window_extent(renderer).expanded(1.15, 1.3)
        if (bb.x0 < trim.x0 + 4 or bb.x1 > trim.x1 - 4 or bb.y0 < trim.y0 + 4
                or bb.y1 > trim.y1 - 4):
            t.remove()
            return False
        fy0 = (bb.y0 - trim.y0) / trim.height
        fy1 = (bb.y1 - trim.y0) / trim.height
        if fy1 > lo and fy0 < hi:
            t.remove()
            return False
        if any(bb.overlaps(o) for o in placed):
            t.remove()
            return False
        placed.append(bb)
        count += 1
        return True

    def inside(pt):
        return mask is None or mask.contains(pt)

    # places first (most important), then parks, then streets
    if "places" in kinds and data.layer("places") is not None:
        g = P.gdf(data.layer("places"))
        for geom, name in zip(g.geometry.values, g["name"].values):
            if not name or not inside(geom):
                continue
            label = " ".join(str(name).upper()) if len(name) < 14 else str(name).upper()
            t = ax.text(geom.x, geom.y, label, ha="center", va="center", color=color,
                        alpha=0.85, fontproperties=fp("regular", 7.5 * scale * label_scale),
                        zorder=11.5, path_effects=halo)
            t.set_gid("labels-places")
            try_place(t)

    if "parks" in kinds and data.layer("parks") is not None:
        g = P.gdf(data.layer("parks"))
        min_area = vw * (y1 - y0) * 0.0015
        g = g[g["name"].notna() & (g.geometry.area > min_area)]
        g = g.iloc[np.argsort(-g.geometry.area.values)]
        for geom, name in zip(g.geometry.values[:80], g["name"].values[:80]):
            pt = geom.representative_point()
            if not inside(pt):
                continue
            t = ax.text(pt.x, pt.y, str(name), ha="center", va="center",
                        color=theme["labels"], alpha=0.75, style="italic",
                        fontproperties=fp("light", 6 * scale * label_scale), zorder=11.4,
                        path_effects=halo)
            t.set_gid("labels-parks")
            try_place(t)

    if "roads" in kinds and data.roads is not None and len(data.roads):
        r = data.roads
        major = ["motorway", "trunk", "primary", "secondary"]
        if vw < 12000:
            major.append("tertiary")
        if vw < 4000:
            major += ["residential", "unclassified"]
        r = r[r["name"].notna() & r["highway"].isin(major)]
        if len(r):
            r = P.gdf(r)
            rank = {k: i for i, k in enumerate(major)}
            groups = []
            for name, sub in r.groupby("name"):
                best = min(rank.get(h, 9) for h in sub["highway"].values)
                merged = linemerge(shapely.MultiLineString(
                    [p for gm in sub.geometry.values for p in shapely.get_parts(gm)
                     if p.geom_type == "LineString"]))
                for piece in shapely.get_parts(merged):
                    piece = piece.intersection(shapely.box(x0, y0, x1, y1))
                    for part in shapely.get_parts(piece):
                        if part.geom_type == "LineString" and part.length > vw * 0.12:
                            groups.append((best, -part.length, name, part))
            groups.sort(key=lambda g: (g[0], g[1]))
            size = {0: 7, 1: 7, 2: 6.5, 3: 6}
            for best, _, name, line in groups[:400]:
                n_labels = max(1, int(line.length / (vw * 0.55)))
                for k in range(n_labels):
                    d = line.length * (k + 0.5) / n_labels
                    a = line.interpolate(max(d - vw * 0.01, 0))
                    b2 = line.interpolate(min(d + vw * 0.01, line.length))
                    mid = line.interpolate(d)
                    if not inside(mid):
                        continue
                    ang = math.degrees(math.atan2(b2.y - a.y, b2.x - a.x))
                    if ang > 90:
                        ang -= 180
                    elif ang < -90:
                        ang += 180
                    t = ax.text(mid.x, mid.y, str(name), rotation=ang, rotation_mode="anchor",
                                ha="center", va="center", color=color,
                                fontproperties=fp("regular",
                                                  size.get(best, 5.5) * scale * label_scale),
                                zorder=11.3, path_effects=halo)
                    t.set_gid("labels-roads")
                    try_place(t)
    log(f"  {count} labels placed")


# --------------------------------------------------------------- highlight

def draw_highlight(ax, geom_proj, theme, mode, view, scale, label, fp):
    import shapely
    from matplotlib.patches import PathPatch
    from .render import _poly_path

    polys = [geom_proj] if geom_proj.geom_type == "Polygon" else list(geom_proj.geoms)
    path = _poly_path(polys)
    if path is None:
        return
    if mode == "focus":
        x0, x1, y0, y1 = view
        outside = shapely.box(x0, y0, x1, y1).difference(geom_proj)
        op = _poly_path(list(shapely.get_parts(outside)))
        if op is not None:
            veil = PathPatch(op, facecolor=theme["bg"], edgecolor="none", alpha=0.62,
                             zorder=9.6)
            veil.set_gid("highlight-veil")
            ax.add_patch(veil)
    else:
        fill = PathPatch(path, facecolor=theme["highlight"], edgecolor="none", alpha=0.28,
                         zorder=1.9)
        fill.set_gid("highlight-fill")
        ax.add_patch(fill)
    edge = PathPatch(path, facecolor="none", edgecolor=theme["highlight"],
                     linewidth=1.6 * scale, zorder=9.65)
    edge.set_gid("highlight-outline")
    ax.add_patch(edge)
    if label:
        import matplotlib.patheffects as pe
        pt = geom_proj.representative_point()
        t = ax.text(pt.x, pt.y, label, ha="center", va="center", color=theme["text"],
                    fontproperties=fp("bold", 11 * scale), zorder=11.6,
                    path_effects=[pe.withStroke(linewidth=3 * scale, foreground=theme["bg"])])
        t.set_gid("highlight-label")


# --------------------------------------------------- scale bar / north / grid

def _nice(x):
    for v in (0.1, 0.2, 0.25, 0.5, 1, 2, 2.5, 5, 10, 20, 25, 50, 100):
        if v >= x:
            return v
    return 100


def draw_scale_bar(tax, theme, view_w_m, fp, scale, x=0.06, y=0.035):
    """Miles (or feet for tiny areas). Lives in trim-axes fractions."""
    from matplotlib.patches import Rectangle
    target_mi = view_w_m / M_PER_MI * 0.18
    if target_mi < 0.15:
        ft = _nice(target_mi * 5280 / 100) * 100
        length_m, label = ft / 3.28084, f"{ft:g} ft"
    else:
        mi = _nice(target_mi)
        length_m, label = mi * M_PER_MI, f"{mi:g} mi"
    frac = length_m / view_w_m
    c = theme["text"]
    hgt = 0.004
    for i in range(4):
        r = Rectangle((x + frac * i / 4, y), frac / 4, hgt, transform=tax.transAxes,
                      facecolor=c if i % 2 == 0 else "none", edgecolor=c,
                      linewidth=0.6 * scale, zorder=12)
        r.set_gid("scale-bar")
        tax.add_patch(r)
    for fx, txt in ((x, "0"), (x + frac, label)):
        t = tax.text(fx, y + hgt + 0.004, txt, transform=tax.transAxes, ha="center",
                     va="bottom", color=c, alpha=0.85, fontproperties=fp("regular", 6.5 * scale),
                     zorder=12)
        t.set_gid("scale-bar-text")
    return x + frac


def draw_north_arrow(tax, theme, fp, scale, x, y, aspect):
    from matplotlib.patches import Polygon
    c = theme["text"]
    s = 0.018
    sy = s * aspect
    left = Polygon([(x, y + sy), (x - s / 2, y - sy * 0.6), (x, y - sy * 0.2)],
                   closed=True, transform=tax.transAxes, facecolor=c, edgecolor=c,
                   linewidth=0.5 * scale, zorder=12)
    right = Polygon([(x, y + sy), (x + s / 2, y - sy * 0.6), (x, y - sy * 0.2)],
                    closed=True, transform=tax.transAxes, facecolor="none", edgecolor=c,
                    linewidth=0.5 * scale, zorder=12)
    for p in (left, right):
        p.set_gid("north-arrow")
        tax.add_patch(p)
    t = tax.text(x, y + sy + 0.004, "N", transform=tax.transAxes, ha="center", va="bottom",
                 color=c, fontproperties=fp("bold", 7 * scale), zorder=12)
    t.set_gid("north-arrow-n")


def draw_grid(ax, tax, P, theme, view, fp, scale):
    """Latitude / longitude graticule with edge labels."""
    from pyproj import Transformer
    x0, x1, y0, y1 = view
    inv = Transformer.from_crs(P.crs, "EPSG:4326", always_xy=True)
    lon0, lat0 = inv.transform(x0, y0)
    lon1, lat1 = inv.transform(x1, y1)
    span = max(lon1 - lon0, lat1 - lat0)
    step = next((v for v in (0.005, 0.01, 0.02, 0.025, 0.05, 0.1, 0.2, 0.25, 0.5, 1)
                 if span / v <= 8), 1.0)
    c = theme["text"]
    fwd = P._t
    ts = np.linspace(0, 1, 60)
    for lon in np.arange(math.ceil(lon0 / step) * step, lon1, step):
        xs, ys = fwd.transform(np.full_like(ts, lon), lat0 + (lat1 - lat0) * ts)
        (ln,) = ax.plot(xs, ys, color=c, alpha=0.18, linewidth=0.4 * scale, zorder=9.55)
        ln.set_gid("grid")
        fx = (xs[0] - x0) / (x1 - x0)
        if 0.03 < fx < 0.97:
            t = tax.text(fx, 0.995, f"{abs(lon):.3f}°{'W' if lon < 0 else 'E'}",
                         transform=tax.transAxes, ha="center", va="top", color=c, alpha=0.55,
                         fontproperties=fp("light", 5 * scale), zorder=12)
            t.set_gid("grid-label")
    for lat in np.arange(math.ceil(lat0 / step) * step, lat1, step):
        xs, ys = fwd.transform(lon0 + (lon1 - lon0) * ts, np.full_like(ts, lat))
        (ln,) = ax.plot(xs, ys, color=c, alpha=0.18, linewidth=0.4 * scale, zorder=9.55)
        ln.set_gid("grid")
        fy = (ys[0] - y0) / (y1 - y0)
        if 0.3 < fy < 0.97:
            t = tax.text(0.005, fy, f"{abs(lat):.3f}°{'N' if lat >= 0 else 'S'}",
                         transform=tax.transAxes, ha="left", va="center", rotation=90,
                         color=c, alpha=0.55, fontproperties=fp("light", 5 * scale), zorder=12)
            t.set_gid("grid-label")


# ------------------------------------------------------- elevation profile

def draw_profile(fig, tax, routes, theme, fp, scale, rect, dem_lookup=None):
    """Elevation profile of all routes joined end to end. rect = trim fractions."""
    from .geometry import route_length_m
    dist, elev = [], []
    offset = 0.0
    for r in routes:
        d = route_length_m(r) + offset
        e = r[:, 2] if r.shape[1] > 2 else np.full(len(r), np.nan)
        if np.isnan(e).mean() > 0.2 and dem_lookup is not None:
            e = dem_lookup(r[:, 0], r[:, 1])
        dist.append(d)
        elev.append(e)
        offset = d[-1]
    d = np.concatenate(dist) / M_PER_MI
    e = np.concatenate(elev) * FT_PER_M
    ok = ~np.isnan(e)
    if ok.sum() < 2:
        log("⚠ No elevations for the profile (add <ele> to the GPX or turn on terrain)")
        return
    d, e = d[ok], e[ok]
    if len(e) > 25:  # light smoothing
        k = max(3, len(e) // 150)
        e = np.convolve(np.pad(e, k, mode="edge"), np.ones(2 * k + 1) / (2 * k + 1), "valid")
    tb = tax.get_position()
    fx, fy, fw, fh = rect
    pax = fig.add_axes((tb.x0 + fx * tb.width, tb.y0 + fy * tb.height,
                        fw * tb.width, fh * tb.height))
    pax.set_gid("elevation-profile")
    pax.patch.set_alpha(0)
    for sp in pax.spines.values():
        sp.set_visible(False)
    pax.set_xticks([])
    pax.set_yticks([])
    lo, hi = e.min(), e.max()
    span = max(hi - lo, 120.0)            # flat routes still read as a line, not a block
    mid = (hi + lo) / 2
    bottom = mid - span * 0.75
    pax.set_ylim(bottom, mid + span * 0.6)
    pax.set_xlim(d[0], d[-1])
    pax.fill_between(d, bottom, e, color=theme["route"], alpha=0.14, linewidth=0, zorder=1)
    pax.plot(d, e, color=theme["route"], linewidth=1.1 * scale, zorder=2)
    gain = np.clip(np.diff(e), 0, None).sum()
    txt = (f"{d[-1]:.1f} mi  ·  {lo:,.0f}–{hi:,.0f} ft  ·  ↑ {gain:,.0f} ft")
    t = pax.text(0.5, 1.04, txt, transform=pax.transAxes, ha="center", va="bottom",
                 color=theme["text"], alpha=0.75, fontproperties=fp("regular", 6.5 * scale))
    t.set_gid("elevation-profile-text")


# ------------------------------------------------------------- photo + QR

def load_photo(path, aspect_wh: float):
    """Center-crop a photo to the given width/height ratio; returns an RGB array."""
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    W, H = im.size
    if W / H > aspect_wh:
        nw = int(H * aspect_wh)
        im = im.crop(((W - nw) // 2, 0, (W - nw) // 2 + nw, H))
    else:
        nh = int(W / aspect_wh)
        im = im.crop((0, (H - nh) // 2, W, (H - nh) // 2 + nh))
    im.thumbnail((2400, 2400))
    return np.asarray(im)


CORNERS = ("top-left", "top-right", "bottom-left", "bottom-right")


def corner_rect(corner: str, size_w: float, aspect: float, margin=0.045, bottom_lift=0.0,
                top_drop=0.0):
    """(x, y, w, h) in trim fractions for a square of width size_w.
    bottom_lift / top_drop keep corner items clear of the text block."""
    size_h = size_w * aspect
    mx, my = margin, margin * aspect
    x = mx if "left" in corner else 1 - mx - size_w
    y = (1 - my - size_h - top_drop) if "top" in corner else my + bottom_lift
    return x, y, size_w, size_h


def draw_photo_badge(fig, tax, img, theme, corner, aspect, scale, lift=0.03, drop=0.0):
    from matplotlib.patches import Circle
    x, y, w, h = corner_rect(corner, 0.22, aspect, bottom_lift=lift, top_drop=drop)
    tb = tax.get_position()
    pax = fig.add_axes((tb.x0 + x * tb.width, tb.y0 + y * tb.height, w * tb.width,
                        h * tb.height))
    pax.set_axis_off()
    pax.set_gid("photo")
    im = pax.imshow(img, extent=[0, 1, 0, 1], zorder=1)
    circ = Circle((0.5, 0.5), 0.5, transform=pax.transAxes, facecolor="none")
    pax.add_patch(circ)
    im.set_clip_path(circ)
    ring = Circle((0.5, 0.5), 0.5, transform=pax.transAxes, facecolor="none",
                  edgecolor=theme["text"], linewidth=2.2 * scale, zorder=2)
    pax.add_patch(ring)


def draw_qr(fig, tax, text, theme, corner, aspect, scale, width_in, lift=0.03, drop=0.0):
    import matplotlib.colors as mcolors
    import qrcode
    qr = qrcode.QRCode(border=1, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(text)
    qr.make(fit=True)
    m = np.array(qr.get_matrix(), dtype=float)
    size_w = max(0.075, min(0.11, 1.1 * max(scale, 0.55) / width_in))
    x, y, w, h = corner_rect(corner, size_w, aspect, bottom_lift=lift, top_drop=drop)
    tb = tax.get_position()
    qax = fig.add_axes((tb.x0 + x * tb.width, tb.y0 + y * tb.height, w * tb.width,
                        h * tb.height))
    qax.set_axis_off()
    qax.set_gid("qr-code")
    # dark modules in the text color, light = background (needs contrast to scan)
    qax.imshow(m, cmap=mcolors.ListedColormap([theme["bg"], theme["text"]]),
               interpolation="nearest", extent=[0, 1, 0, 1])


# -------------------------------------------------------------- crop marks

def draw_crop_marks(fig, slug, bleed, w, h):
    """Thin black marks in the slug at the trim lines (all in inches)."""
    from matplotlib.lines import Line2D
    W, H = w + 2 * (bleed + slug), h + 2 * (bleed + slug)
    off = bleed + slug
    gap = bleed + 0.06
    length = slug - 0.06
    lines = []
    for tx in (off, off + w):
        for ty, sign in ((0, 1), (H, -1)):
            y_a, y_b = ty, ty + sign * length
            lines.append(((tx, tx), (y_a, y_b)))
    for ty in (off, off + h):
        for tx, sign in ((0, 1), (W, -1)):
            lines.append(((tx, tx + sign * length), (ty, ty)))
    del gap
    for xs, ys in lines:
        ln = Line2D([v / W for v in xs], [v / H for v in ys], transform=fig.transFigure,
                    color="black", linewidth=0.4, zorder=100)
        ln.set_gid("crop-marks")
        fig.add_artist(ln)
