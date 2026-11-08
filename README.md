# Map Poster Studio

Minimalist city map posters from OpenStreetMap data, as a Windows app with a
window and a full command line. A from-scratch rewrite of
[originalankur/maptoposter](https://github.com/originalankur/maptoposter) that
keeps all of its features and adds a GUI, local data files and more.

## Build the exe

1. Install Python 3.11+ (python.org) if you don't have it.
2. Double-click **`build.bat`**. The first run takes a few minutes.
3. Your app is in **`dist\MapPosterStudio\`**. Copy that whole folder wherever
   you want; `MapPosterStudio.exe` is inside.

To run without building: run `build.bat` once (it sets up `.venv`), then use
`run_from_source.bat`.

**Installer:** double-click **`build_installer.bat`**. It builds the exe if
needed and installs Inno Setup through winget if it's missing. It then makes
`dist\MapPosterStudio-Setup-<version>.exe`, a normal Windows installer with a
Start menu entry, an optional desktop shortcut and an uninstaller. It installs
for your user only, with no admin prompt. Uninstalling removes downloaded
caches but keeps your posters, themes and presets.

## Use it

**Double-click `MapPosterStudio.exe`** to open the window. Fill in the city,
pick a radius, choose themes (Ctrl/Shift-click, or **All**) and click
**Generate posters**. The latest poster shows in the preview; click it to open
the file.

**From PowerShell** you get the command line:

```powershell
.\MapPosterStudio.exe -c "Phoenix" -C "USA" -t noir -d 6mi
.\MapPosterStudio.exe -c "Phoenix" -C "USA" -d 25mi --all-themes --pbf data\arizona-latest.osm.pbf
.\MapPosterStudio.exe --help
```

### Big areas (Phoenix at 25 miles and up)

The online OpenStreetMap servers (Overpass) are slow and can time out on huge
areas. Use a local extract instead:

1. In the window, leave Geofabrik on `north-america/us/arizona` and click
   **Download** (about 300 MB). From the command line:
   `--download-pbf north-america/us/arizona`.
2. Choose **Local .pbf file**. It's selected automatically after the download.

The whole state is then read from your disk, with no rate limits. Map data is
also cached, so every theme and every smaller poster of the same spot reuses
it.

## Features

**Everything from the original**

| Original flag | Here |
|---|---|
| `-c/--city`, `-C/--country` | same |
| `-lat/--latitude`, `-long/--longitude` | same (decimal or DMS like `33°26'53"N`) |
| `--country-label` | same |
| `-t/--theme`, `--all-themes`, `--list-themes` | same, plus `--themes a b c` |
| `-d/--distance` | real **miles** from the center to the poster edge (`6`, `2.5mi`, `800ft`; `8km` also works); `--legacy-distance` for the original framing (meters) |
| `-W/-H` | same, max raised to 36 in (for 24×36 posters) |
| `-dc/--display-city`, `-dC/--display-country` | same (non-Latin names aren't letter-spaced) |
| `--font-family` (Google Fonts) | same, cached in `fonts/` |
| `-f/--format png/svg/pdf` | same |
| all 17 themes, road hierarchy, fades, OSM attribution | same |
| geocoding cache, data cache | same, plus reuse of larger cached areas |

**Map**

* Layers: lakes, parks, the **ocean** (built from OSM coastlines), **rivers and
  canals**, **railways**, **airports** and **buildings**. Each can be switched on
  or off (`--layers`), and their OSM tags are set in `layers.json`.
* Local `.pbf` extracts (`--pbf`, `--download-pbf`) for big or offline posters
* Road widths scale with the area automatically (`--no-auto-roads` to turn off,
  `--road-scale` to adjust)
* Map shapes: rectangle, **circle**, **heart** or the **city's real outline**
  (`--shape`, `--boundary-file`)

**Markers and routes**

* `--marker "lat, lon, label, icon"` with a pin, heart, star or dot.
  Repeatable. In the window, right-click the map picker to drop one.
* `--gpx track.gpx` draws hikes, runs or road trips. `--fit-route` centers and
  sizes the poster on the route.

**Text and frame**

* Text at the top or bottom, title style (`spaced` / `caps` / `normal`),
  `--letter-spacing`, `--tagline "EST. 1881"`
* `--border thin | thick | double`
* `--no-text`, `--no-coords`, `--no-gradient`

**Output**

* Presets for prints (8×10 to 24×36, A4 to A2), Instagram, phone and desktop
  wallpapers (1080p, 4K) and a watch face
* `--bleed 0.125` adds print-shop bleed. `--dpi` sets the resolution. Output
  size is exact (12×16 in at 300 dpi = 3600×4800 px).
* **Layered SVG**: streets, water, text and so on are separate layers in
  Inkscape, or groups in Illustrator.
* `--mockup black | white | oak` adds a framed-on-a-wall image for each poster.

**Terrain**

* `--terrain hillshade | contours | both`. Elevation comes from the free AWS
  Terrain Tiles (USGS 3DEP and SRTM) and is cached in `cache\terrain`.
* `--contour-interval 50` sets the feet between contour lines (automatic by
  default). `--terrain-strength` makes the effect subtler or stronger.
* `--download-terrain`, or **Details → Save terrain for offline use**, saves
  every zoom level for the area so it works offline later.

**Labels, highlight and map details**

* `--labels roads,places,parks` adds street names, neighborhood names (turn on
  the `places` layer) and park names. Labels that would overlap, or run into
  the title, are skipped. `--label-size` changes their size.
* `--highlight "Encanto, Phoenix, AZ"` tints one area, using its outline from
  OpenStreetMap or from `--highlight-file`. `--highlight-mode focus` fades
  everything else instead. `--highlight-label` puts text on the area.
* `--scale-bar` (in miles or feet), `--north-arrow` and `--grid` (a
  latitude/longitude grid)
* New layers: **washes and streams** and **trails**, both drawn dashed

**Routes**

* `--elevation-profile` adds a chart of the GPX route under the map, with
  distance in miles, the elevation range in feet and total climb. It uses the
  GPX file's elevations, or the terrain data when the file has none.

**Photo, QR code and fonts**

* `--photo us.jpg`: with a circle or heart shape, the photo fills the shape and
  the map surrounds it. Otherwise the photo is a round badge in a corner
  (`--photo-corner`).
* `--qr https://…` adds a QR code (`--qr-corner`). It's drawn in the theme's
  text and background colors, so pick a theme with good contrast for scanning.
* `--font-file MyFont.ttf` uses your own font: one file for every weight, or
  a folder with Regular, Bold and Light files.

**Print shop**

* `--bleed 0.125 --crop-marks -f pdf` gives a print-ready PDF with crop marks.
* `--icc profile.icc` also saves a CMYK TIFF converted with your print shop's
  color profile (ask them for theirs, e.g. FOGRA39 or US Web Coated SWOP).

**Sets and presets**

* `--set "Phoenix, USA" --set "Tucson, USA" …` puts several places side by
  side in one image.
* `--zoom-series 1,4,12` shows one place at several radii, in miles.
* **Presets** save a whole look (theme, layers, text, size, terrain and so on)
  without the place. Use `--save-preset "My look"` and later
  `--preset "My look"`, or the Preset bar in the window. Anything you type on
  the command line overrides the preset.

**Workflow**

* The window has tabs for every option, a live preview, **dark mode**, and
  remembers your settings.
* **Quick preview** (`--preview`) does a fast low-resolution render before the
  full one.
* **Theme editor**: a color picker for every element, with an instant
  sample-town preview. Save under a new name to make a new theme.
* **Pick on map**: click a map to set the center, with the poster area shown as
  a box.
* **Batch** (`--batch file.csv`, or the button) makes many posters in one go.
  See `batch_example.csv`.
* Data is downloaded once for all themes.

### Batch CSV

One poster job per row. Columns are optional except `city`:
`city, country, themes, distance_mi, width, height, format, dpi, lat, lon,
tagline, markers, gpx, shape, border, mockup, text_position, title_style,
display_city, display_country, font_family, layers, bleed, terrain, labels,
highlight, scale_bar, north_arrow, photo, qr, zoom_series` (and any other
setting by its name).
Separate several themes, markers or layers in one cell with `;`. Use
`themes = all` for every theme. Anything not in the CSV comes from the window
or your command-line options.

### About distance

Everything is in miles. `-d` is the real distance from the center to the nearest
edge of the poster. Bare numbers are miles (`-d 6`); you can also write units
(`2.5mi`, `800ft`, `8km`, `5000m`). In the window the radius box is in miles.
In a batch CSV the column is `distance_mi` (cells can also carry a unit, and an
older `distance_km` column still works).

The original script's `-d` was in meters and covered only about a quarter of its
value: `-d 18000` showed roughly 2.8 miles from the center to the side edges.
To match an original poster, use `--legacy-distance` (then `-d` is in meters as
before) or divide its number by 4.

| Radius | Covers |
|---|---|
| 1 mi | a neighborhood or old town |
| 2–3 mi | a downtown |
| 5–8 mi | a whole city |
| 12–25 mi | a metro area (use a .pbf) |

## The window

- **Theme gallery** with swatch tiles. Click to pick, double-click to edit, and type in *Search* (Ctrl+F) to filter.
- **Recent posters** strip under the preview; click one to show it.
- **Preview zoom:** Fit, −, +, 100%, mouse wheel to zoom, drag to move, double-click to open the file.
- **Undo / Redo** (Ctrl+Z / Ctrl+Y) for every setting change.
- **Live preview:** tick the box and a quick preview redraws a moment after you change something.
- **Colour picker** in the theme editor with a colour square, hue bar, hex and RGB entry. The sample poster updates while you drag.
- **Tooltips** on every option; hover for a second.
- **Keyboard shortcuts:** Ctrl+G generate, Ctrl+P quick preview, Esc cancel, Ctrl+S save a look, Ctrl+O posters folder, Ctrl+1…6 tabs, Ctrl+D dark mode, F1 list.
- The window remembers its size, position and open tab.

## Customize

Everything you'd edit lives next to the exe (or the project folder):

* Themes: use **Map → Edit / new…** in the window, or edit `themes\*.json`
  by hand. Keys: `bg, text, gradient_color, water, parks, road_motorway,
  road_primary, road_secondary, road_tertiary, road_residential, road_default`.
  Optional keys: `ocean, waterway, railway, buildings, airports, marker,
  route, border`. Any you leave out are worked out from the others.
* `layers.json`: which OSM tags make up each layer, and which layers are on by default.
* Source code in `mapposter\`:
  * `render.py`: drawing (layout, fonts, line widths, road classes)
  * `geometry.py`: ocean, shapes, markers and GPX
  * `extras.py`: boundaries, mockups, batch and the sample town
  * `decor.py`: terrain drawing, labels, highlight, scale bar, grid, profile,
    photo, QR code and crop marks
  * `terrain.py`: elevation tiles
  * `presets.py`: saved looks
  * `sources.py`: data (online and .pbf)
  * `gui.py`: the window
  * `cli.py`: the command line
  * `core.py`: ties them together

Run `build.bat` again after changing code.

## Folders created on first run

`themes/`, `posters/`, `presets/`, `cache/`, `fonts/`, `data/`, `layers.json`, `settings.json`

## License

GPL-3.0-or-later © 2026 Hans De Kryger (see `LICENSE`). Based on maptoposter by
Ankur Gupta, which is MIT-licensed; its notice is kept in
`THIRD_PARTY_LICENSE_maptoposter.txt`. The bundled Roboto fonts are under the
Apache License 2.0. Map data © OpenStreetMap contributors (ODbL), and the
attribution is printed on every poster. Elevation data comes from the AWS Terrain
Tiles (credited on posters that use it).
