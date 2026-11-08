"""Command line interface. Every flag from the original maptoposter is supported."""

from __future__ import annotations

import argparse

from . import __version__, paths, themes
import sys

from .units import parse_distance
from .log import log

EXAMPLES = """
Examples:
  MapPosterStudio -c "Phoenix" -C "USA" -t noir -d 12mi
  MapPosterStudio -c "Phoenix" -C "USA" -d 25mi --all-themes --pbf data\\arizona-latest.osm.pbf
  MapPosterStudio -c "Tokyo" -C "Japan" -dc "東京" -dC "日本" --font-family "Noto Sans JP" -t japanese_ink
  MapPosterStudio -c "New York" -C "USA" -lat 40.776676 -long -73.971321 -t noir -d 4mi
  MapPosterStudio -c "Paris" -C "France" -d 18000 --legacy-distance   (same framing as the original script; meters)
  MapPosterStudio --download-pbf north-america/us/arizona
  MapPosterStudio -c Phoenix -C USA -d 2mi -t noir --shape heart --marker "33.4484,-112.0740,Home,heart"
  MapPosterStudio -c "Sedona" -C USA -t forest --gpx hike.gpx --fit-route --border thin
  MapPosterStudio -c Phoenix -C USA -d 9mi --layers water,parks,waterways,railways --tagline "THE VALLEY OF THE SUN"
  MapPosterStudio -c "South Mountain" -C "Phoenix, AZ" -lat 33.335 -long -112.045 -d 2.5 --terrain both -t terracotta
  MapPosterStudio -c Phoenix -C USA -d 8 --labels roads,places --layers water,parks,places --scale-bar --north-arrow
  MapPosterStudio -c Phoenix -C USA -d 4 --highlight "Encanto, Phoenix, AZ" --highlight-mode focus
  MapPosterStudio -c Sedona -C USA --gpx hike.gpx --fit-route --elevation-profile --terrain hillshade
  MapPosterStudio -c Phoenix -C USA -d 3 --shape heart --photo us.jpg --qr https://photos.example/album
  MapPosterStudio -C USA --set "Phoenix, USA" --set "Tucson, USA" --set "Flagstaff, USA" -t noir
  MapPosterStudio -c Phoenix -C USA --zoom-series 1,4,12 -t blueprint
  MapPosterStudio -c Phoenix -C USA -d 6 --bleed 0.125 --crop-marks -f pdf --icc FOGRA39.icc
  MapPosterStudio -c Phoenix -C USA -t noir --border thin --save-preset "My look"   then  --preset "My look"
  MapPosterStudio --batch batch_example.csv
  MapPosterStudio --list-themes
  MapPosterStudio                 (no arguments: opens the window)

Distance (-d) is the real distance from the center to the nearest edge of the poster,
  in miles: 5, 5mi, 2.5mi, 800ft. Other units work too: 8km, 5000m.
  The original script's -d (meters) covered about a quarter of that; use --legacy-distance
  to get identical framing, with -d in meters as before.
  ~1 mi     a neighborhood / old town        ~2-3 mi   a downtown
  ~5-8 mi   a whole city                     ~12-25 mi a metro area (use --pbf)

Sizes (-W/-H, inches, max 36):  12x16 (default)  8.3x11.7 (A4)  11.7x16.5 (A3)
  18x24  24x36  3.6x3.6 at 300 dpi = 1080x1080 px  6.4x3.6 = 1920x1080 desktop
"""


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="MapPosterStudio",
        description="Generate minimalist map posters for any city.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=EXAMPLES,
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--city", "-c", help="City name (used for geocoding and the poster)")
    p.add_argument("--country", "-C", help="Country name")
    p.add_argument("--latitude", "-lat", dest="latitude",
                   help="Override center latitude (decimal or DMS, use with --longitude)")
    p.add_argument("--longitude", "-long", dest="longitude",
                   help="Override center longitude")
    p.add_argument("--country-label", dest="country_label",
                   help="Override the country text on the poster")
    p.add_argument("--theme", "-t", default="terracotta", help="Theme name (default: terracotta)")
    p.add_argument("--themes", nargs="+", metavar="NAME",
                   help="Several themes at once, e.g. --themes noir blueprint sunset")
    p.add_argument("--all-themes", "--All-themes", dest="all_themes", action="store_true",
                   help="Generate a poster for every theme (data is downloaded once)")
    p.add_argument("--distance", "-d", default="3",
                   help="Center to nearest edge, in miles (default: 3). Accepts 5, 2.5mi, "
                        "800ft, 8km, 5000m")
    p.add_argument("--legacy-distance", action="store_true",
                   help="Interpret -d like the original script (covers ~1/4 of the value)")
    p.add_argument("--width", "-W", type=float, default=12, help="Width in inches (max 36, default 12)")
    p.add_argument("--height", "-H", type=float, default=16, help="Height in inches (max 36, default 16)")
    p.add_argument("--list-themes", action="store_true", help="List available themes")
    p.add_argument("--display-city", "-dc", help="Display name for the city (e.g. native script)")
    p.add_argument("--display-country", "-dC", help="Display name for the country")
    p.add_argument("--font-family", help='Google Fonts family, e.g. "Noto Sans JP" (default: Roboto)')
    p.add_argument("--format", "-f", default="png", choices=["png", "svg", "pdf"],
                   help="Output format (default: png)")
    # New in this rewrite
    p.add_argument("--dpi", type=int, default=300, help="PNG resolution (default 300)")
    p.add_argument("--road-scale", type=float, default=1.0,
                   help="Multiply all road widths (e.g. 0.6 for big areas, 1.5 for small)")
    p.add_argument("--no-text", action="store_true", help="Map only, no city/country text")
    p.add_argument("--no-coords", action="store_true", help="Hide the coordinates line")
    p.add_argument("--no-gradient", action="store_true", help="Disable the top/bottom fade")
    p.add_argument("--pbf", help="Read map data from a local .osm.pbf file instead of the internet")
    p.add_argument("--download-pbf", metavar="REGION",
                   help="Download a Geofabrik extract into data/ "
                        "(e.g. north-america/us/arizona) and exit")
    p.add_argument("--output-dir", "-o", help="Where to save posters (default: posters/)")

    g = p.add_argument_group("map layers")
    g.add_argument("--layers", type=lambda s: [x.strip() for x in s.split(",") if x.strip()],
                   help="Comma list of layers to draw: water,parks,coastline,waterways,washes,"
                        "trails,railways,airports,buildings,places (default: as set in layers.json)")
    g.add_argument("--road-width", dest="road_scale_alias", type=float,
                   help=argparse.SUPPRESS)
    g.add_argument("--no-auto-roads", action="store_true",
                   help="Fixed road widths instead of scaling them with the area")

    g = p.add_argument_group("layout")
    g.add_argument("--text-position", choices=["bottom", "top"], default="bottom")
    g.add_argument("--title-style", choices=["spaced", "caps", "normal"], default="spaced",
                   help="S P A C E D capitals (default), CAPS, or as typed")
    g.add_argument("--letter-spacing", type=int, default=2,
                   help="Spaces between letters for the spaced style (default 2)")
    g.add_argument("--tagline", default="", help='Extra line under the coordinates, e.g. "EST. 1881"')
    g.add_argument("--border", choices=["none", "thin", "thick", "double"], default="none")
    g.add_argument("--shape", choices=["rect", "circle", "heart", "boundary"], default="rect",
                   help="Map shape; boundary = the city's outline from OpenStreetMap")
    g.add_argument("--boundary-file", help="Use this GeoJSON/GPKG/SHP outline for --shape boundary")
    g.add_argument("--bleed", type=float, default=0.0,
                   help="Print bleed in inches added on each side (0.125 is standard)")

    g = p.add_argument_group("markers and routes")
    g.add_argument("--marker", action="append", default=[], metavar='"LAT,LON[,LABEL][,ICON]"',
                   help="Add a marker; icon = pin, heart, star or dot. Repeatable.")
    g.add_argument("--gpx", action="append", default=[], metavar="FILE",
                   help="Draw a GPX track/route. Repeatable.")
    g.add_argument("--fit-route", action="store_true",
                   help="Center and size the poster to fit the GPX routes")
    g.add_argument("--route-width", type=float, default=2.2)

    g = p.add_argument_group("terrain")
    g.add_argument("--terrain", choices=["none", "hillshade", "contours", "both"], default="none",
                   help="Shaded relief and/or contour lines from free elevation data")
    g.add_argument("--contour-interval", type=float, metavar="FT",
                   help="Feet between contour lines (default: automatic)")
    g.add_argument("--terrain-strength", type=float, default=1.0,
                   help="0.3 = subtle … 1.5 = strong (default 1)")
    g.add_argument("--download-terrain", action="store_true",
                   help="Cache elevation for the poster area (all zooms) for offline use, then exit")

    g = p.add_argument_group("labels, highlight and map details")
    g.add_argument("--labels", type=lambda s: [x.strip() for x in s.split(",") if x.strip()],
                   default=[], help="Comma list: roads,places,parks (places needs the places layer)")
    g.add_argument("--label-size", type=float, default=1.0, help="Label size multiplier")
    g.add_argument("--highlight", metavar="PLACE",
                   help='Color one area, e.g. "Encanto, Phoenix, AZ" (outline from OpenStreetMap)')
    g.add_argument("--highlight-file", help="Highlight an outline from GeoJSON/GPKG/SHP instead")
    g.add_argument("--highlight-mode", choices=["fill", "focus"], default="fill",
                   help="fill = tint the area; focus = fade everything else")
    g.add_argument("--highlight-label", default="", help="Text on the highlighted area")
    g.add_argument("--scale-bar", action="store_true", help="Scale bar in miles")
    g.add_argument("--north-arrow", action="store_true")
    g.add_argument("--grid", action="store_true", help="Latitude/longitude grid with labels")
    g.add_argument("--elevation-profile", action="store_true",
                   help="Elevation chart of the GPX route under the map")

    g = p.add_argument_group("photo, QR code and fonts")
    g.add_argument("--photo", metavar="FILE",
                   help="Photo: fills the shape for --shape circle/heart, else a round corner badge")
    g.add_argument("--photo-corner", choices=["top-left", "top-right", "bottom-left",
                                              "bottom-right"], default="top-right")
    g.add_argument("--qr", metavar="TEXT_OR_URL", default="", help="Add a QR code, e.g. a photo album link")
    g.add_argument("--qr-corner", choices=["top-left", "top-right", "bottom-left",
                                           "bottom-right"], default="top-left")
    g.add_argument("--font-file", metavar="PATH",
                   help="Your own .ttf/.otf (or a folder with Regular/Bold/Light files)")

    g = p.add_argument_group("print")
    g.add_argument("--crop-marks", action="store_true",
                   help="Add crop marks outside the bleed (use with --bleed 0.125)")
    g.add_argument("--icc", metavar="PROFILE",
                   help="Also save a CMYK TIFF using your print shop's .icc profile")

    g = p.add_argument_group("sets and presets")
    g.add_argument("--set", dest="set_places", action="append", default=[], metavar='"CITY, COUNTRY"',
                   help="Side-by-side set of places in one image. Repeat for each place.")
    g.add_argument("--zoom-series", metavar="MILES",
                   help='One place at several radii side by side, e.g. "1,4,12"')
    g.add_argument("--preset", help="Start from a saved look (your options still win)")
    g.add_argument("--save-preset", metavar="NAME", help="Save this run's look as a preset")
    g.add_argument("--list-presets", action="store_true")

    g = p.add_argument_group("workflow")
    g.add_argument("--batch", metavar="CSV",
                   help="Make every poster listed in a CSV (see batch_example.csv)")
    g.add_argument("--preview", action="store_true",
                   help="Quick low-resolution preview of the first theme (cache/preview/)")
    g.add_argument("--mockup", choices=["black", "white", "oak"],
                   help="Also save a framed-on-a-wall mockup image for each PNG")
    p.add_argument("--no-cache", action="store_true", help="Ignore cached map data")
    p.add_argument("--gui", action="store_true", help="Open the window")
    p.add_argument("--debug", action="store_true", help="Show full error tracebacks")
    return p


def list_themes() -> None:
    rows = themes.describe_themes()
    if not rows:
        print(f"No themes found in {paths.THEMES_DIR}")
        return
    print(f"\nThemes in {paths.THEMES_DIR}:\n" + "-" * 60)
    for key, name, desc in rows:
        print(f"  {key}\n    {name}")
        if desc:
            print(f"    {desc}")
        print()


def main(argv: list[str] | None = None) -> int:
    paths.ensure_dirs()
    args = build_parser().parse_args(argv)

    if args.gui:
        from .gui import main as gui_main
        gui_main()
        return 0
    if args.list_themes:
        list_themes()
        return 0
    if args.list_presets:
        from .presets import list_presets
        names = list_presets()
        print("\n".join(names) if names else f"No presets yet ({paths.PRESETS_DIR})")
        return 0
    if args.download_pbf:
        from .download import download_pbf
        try:
            download_pbf(args.download_pbf)
            return 0
        except Exception as e:
            log(f"✗ Download failed: {e}")
            return 1
    from .core import Job, run, run_batch

    try:
        # --legacy-distance keeps the original script's meaning: bare numbers are meters.
        distance_m = parse_distance(args.distance, bare="m" if args.legacy_distance else "mi")
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    try:
        zoom_series = ([parse_distance(x) for x in args.zoom_series.split(",") if x.strip()]
                       if args.zoom_series else [])
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    parser = build_parser()

    def apply_preset(job):
        """Preset values fill in every option you didn't type yourself."""
        if not args.preset:
            return job
        from .presets import load_preset
        preset = load_preset(args.preset)
        given = {a.lstrip("-").split("=")[0] for a in (argv if argv is not None else sys.argv[1:])
                 if a.startswith("-")}
        # job field -> the flags that set it
        flags = {f.dest: set(f.option_strings) for f in parser._actions}
        field_flags = {
            "fmt": flags["format"], "distance_m": flags["distance"],
            "show_text": flags["no_text"], "show_coords": flags["no_coords"],
            "show_gradient": flags["no_gradient"], "auto_roads": flags["no_auto_roads"],
            "themes": flags["theme"] | flags["themes"] | flags["all_themes"],
            "label_scale": flags["label_size"], "contour_interval_ft": flags["contour_interval"],
            "road_scale": flags["road_scale"] | flags["road_scale_alias"],
        }
        for k, v in preset.items():
            opts = field_flags.get(k) or flags.get(k, set())
            if not ({o.lstrip("-") for o in opts} & given):
                setattr(job, k, v)
        log(f"✓ Using preset '{args.preset}'")
        return job

    def build_job(city, country, chosen):
        return apply_preset(Job(
            city=city, country=country, themes=chosen,
            distance_m=distance_m, legacy_distance=args.legacy_distance,
            width=args.width, height=args.height,
            latitude=args.latitude, longitude=args.longitude,
            country_label=args.country_label, display_city=args.display_city,
            display_country=args.display_country, font_family=args.font_family,
            fmt=args.format, dpi=args.dpi,
            road_scale=args.road_scale_alias or args.road_scale,
            auto_roads=not args.no_auto_roads,
            show_text=not args.no_text, show_coords=not args.no_coords,
            show_gradient=not args.no_gradient, pbf=args.pbf,
            output_dir=args.output_dir, use_cache=not args.no_cache,
            layers=args.layers, text_position=args.text_position,
            title_style=args.title_style, letter_spacing=args.letter_spacing,
            tagline=args.tagline, border=args.border, shape=args.shape,
            boundary_file=args.boundary_file, bleed=args.bleed,
            markers=args.marker, gpx=args.gpx, fit_route=args.fit_route,
            route_width=args.route_width, mockup=args.mockup, preview=args.preview,
            elevation_profile=args.elevation_profile, terrain=args.terrain,
            contour_interval_ft=args.contour_interval, terrain_strength=args.terrain_strength,
            labels=args.labels, label_scale=args.label_size, highlight=args.highlight,
            highlight_file=args.highlight_file, highlight_mode=args.highlight_mode,
            highlight_label=args.highlight_label, scale_bar=args.scale_bar,
            north_arrow=args.north_arrow, grid=args.grid, photo=args.photo,
            photo_corner=args.photo_corner, qr=args.qr, qr_corner=args.qr_corner,
            font_file=args.font_file, crop_marks=args.crop_marks, icc=args.icc,
            set_places=args.set_places, zoom_series=zoom_series,
        ))

    if args.batch:
        print("=" * 50 + f"\nMap Poster Studio {__version__} - batch\n" + "=" * 50)
        try:
            # Command-line options act as defaults for every CSV row.
            run_batch(args.batch, base=build_job(args.city or "", args.country or "",
                                                 [args.theme]))
            return 0
        except KeyboardInterrupt:
            log("\nCancelled.")
            return 130

    if args.download_terrain:
        from . import geocode, terrain
        from .sources import bbox_for, view_half_extents
        if args.latitude and args.longitude:
            lat, lon = geocode.parse_coordinate(args.latitude), geocode.parse_coordinate(args.longitude)
        elif args.city and args.country:
            lat, lon = geocode.get_coordinates(args.city, args.country)
        else:
            print("Error: give --city/--country or --latitude/--longitude")
            return 1
        r = distance_m / 4 if args.legacy_distance else distance_m
        w, s_, e, n = bbox_for(lat, lon, *view_half_extents(r, args.width, args.height), margin=1.2)
        terrain.prefetch(w, s_, e, n)
        return 0

    if (args.set_places or zoom_series) and not args.city:
        args.city = args.set_places[0].split(",")[0] if args.set_places else None
        args.country = args.country or ""
    if not args.city or not args.country:
        print("Error: --city and --country are required.\n")
        build_parser().print_help()
        return 1

    if args.all_themes:
        chosen = themes.available_themes()
    elif args.themes:
        chosen = args.themes
    else:
        chosen = [args.theme]

    job = build_job(args.city, args.country, chosen)
    if args.save_preset:
        from .presets import save_preset
        save_preset(args.save_preset, job)
    print("=" * 50 + f"\nMap Poster Studio {__version__}\n" + "=" * 50)
    try:
        run(job)
        return 0
    except KeyboardInterrupt:
        log("\nCancelled.")
        return 130
    except Exception as e:
        log(f"\n✗ Error: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        return 1
