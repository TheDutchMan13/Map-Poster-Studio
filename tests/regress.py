"""Theme regression test: renders a small saved map of downtown Phoenix in every
theme (plus a few option combinations) and compares each image with its saved
baseline in tests/baseline/. Needs no internet and no .pbf file.

    python tests/regress.py            check (exit code 1 if anything changed)
    python tests/regress.py --update   accept the current look as the new baseline
    python tests/regress.py -k noir    only cases whose name contains "noir"

Differences are written to tests/output/ as  <case>_diff.png  (before | after | diff).
run_tests.bat does the same from a double-click.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
# Keep the user's real settings, cache and themes folder out of the test.
os.environ.setdefault("MAPPOSTER_HOME", tempfile.mkdtemp(prefix="mps_test_"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")

FIXTURE = HERE / "fixtures" / "phoenix_downtown.gpkg"
BASELINE = HERE / "baseline"
OUTPUT = HERE / "output"

LAT, LON, RADIUS = 33.4484, -112.0740, 1500
W, H, DPI = 4.0, 5.0, 100

# A pixel counts as changed when a channel moves by more than `tol` (0-255); a case
# fails when more than `share` of its pixels changed. Map-only cases are strict:
# a 0.2 pt road-width change moves ~0.06% of pixels. Cases with text are looser,
# because fonts anti-alias slightly differently between machines.
STRICT = (8, 0.0002)
TEXT = (40, 0.006)


def load_fixture():
    import geopandas as gpd
    import pyogrio
    from mapposter.sources import MapData

    layers = {name: gpd.read_file(FIXTURE, layer=name)
              for name, _ in pyogrio.list_layers(FIXTURE)}
    roads = layers.pop("roads")
    b = roads.total_bounds
    return MapData(roads, layers, (b[0], b[1], b[2], b[3]))


def cases():
    from mapposter import themes
    nt = {"show_text": False}
    out = [(f"theme_{name}", name, dict(nt)) for name in themes.available_themes()]
    out += [
        ("classic_terracotta", "terracotta", {"classic": True, **nt}),
        ("cityscale_noir", "noir", {"_detail": 1.0, **nt}),
        ("cityscale_warm_beige", "warm_beige", {"_detail": 1.0, **nt}),
        ("cityscale_pastel_dream", "pastel_dream", {"_detail": 1.0, **nt}),
        ("text_terracotta", "terracotta", {}),
        ("text_noir", "noir", {}),
        ("labels_terracotta", "terracotta", {"labels": ["places", "parks", "roads"]}),
        ("top_text_border_blueprint", "blueprint",
         {"text_position": "top", "border": "double", "title_style": "caps"}),
        ("circle_ocean", "ocean", {"shape": "circle", "scale_bar": True,
                                   "north_arrow": True}),
    ]
    return out


def render(data, theme_name, extra, out: Path, fmt="png"):
    from mapposter import fonts, render as R, themes

    extra = dict(extra)
    detail = extra.pop("_detail", None)
    opts = R.PosterOptions(city="Phoenix", country="Arizona, USA", lat=LAT, lon=LON,
                           radius_m=RADIUS, width=W, height=H, dpi=DPI, fmt=fmt,
                           fonts=fonts.load_fonts(None, None), **extra)
    real = R.map_detail
    if detail is not None:      # pretend this is a city-scale map
        R.map_detail = lambda _r: detail
    try:
        return R.render_poster(data, themes.load_theme(theme_name), opts, out)
    finally:
        R.map_detail = real


def compare(a_path: Path, b_path: Path, diff_path: Path, tol: int, share: float):
    import numpy as np
    from PIL import Image

    a = Image.open(a_path).convert("RGB")
    b = Image.open(b_path).convert("RGB")
    if a.size != b.size:
        return 1.0, f"size {a.size} -> {b.size}"
    d = np.abs(np.asarray(a, dtype=np.int16) - np.asarray(b, dtype=np.int16)).max(axis=2)
    changed = float((d > tol).mean())
    if changed > share:
        vis = Image.fromarray(np.clip(d * 4, 0, 255).astype("uint8")).convert("RGB")
        sheet = Image.new("RGB", (a.width * 3 + 20, a.height), "white")
        for i, im in enumerate((a, b, vis)):
            sheet.paste(im, (i * (a.width + 10), 0))
        sheet.save(diff_path)
    return changed, ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--update", action="store_true", help="save current images as baseline")
    ap.add_argument("-k", default="", help="only run cases whose name contains this")
    args = ap.parse_args(argv)

    from mapposter import log as L, paths
    paths.ensure_dirs()
    L.set_sink(lambda m: None)

    BASELINE.mkdir(exist_ok=True)
    OUTPUT.mkdir(exist_ok=True)
    for f in OUTPUT.glob("*.png"):
        f.unlink()

    data = load_fixture()
    t0 = time.time()
    failed, new = [], []
    todo = [c for c in cases() if args.k in c[0]]
    for name, theme, extra in todo:
        out = OUTPUT / f"{name}.png"
        render(data, theme, extra, out)
        base = BASELINE / f"{name}.png"
        if args.update or not base.exists():
            if not base.exists():
                new.append(name)
            base.write_bytes(out.read_bytes())
            print(f"  saved     {name}")
            continue
        tol, share = STRICT if extra.get("show_text") is False else TEXT
        changed, why = compare(base, out, OUTPUT / f"{name}_diff.png", tol, share)
        ok = changed <= share
        print(f"  {'ok  ' if ok else 'FAIL'}      {name:34} {changed * 100:6.3f}% changed {why}")
        if not ok:
            failed.append(name)

    # Vector export smoke test: it must render and stay small.
    if not args.k or "pdf" in args.k:
        pdf = render(data, "terracotta", {}, OUTPUT / "export.pdf", fmt="pdf")
        size_kb = pdf.stat().st_size / 1024
        ok = 0 < size_kb < 4000
        print(f"  {'ok  ' if ok else 'FAIL'}      pdf export {size_kb:,.0f} KB")
        if not ok:
            failed.append("pdf_export")

    print(f"\n{len(todo)} cases in {time.time() - t0:.1f}s.", end=" ")
    if args.update:
        print("Baseline updated.")
        return 0
    if new:
        print(f"New baselines saved: {', '.join(new)}.", end=" ")
    if failed:
        print(f"\nCHANGED: {', '.join(failed)}\nLook at tests/output/*_diff.png "
              "(baseline | now | difference). If the change is intended, run "
              "with --update.")
        return 1
    print("All match the baseline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
