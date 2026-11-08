"""Desktop window (Tkinter). Everything the CLI can do, plus previews, a theme
editor and a click-on-a-map picker."""

from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from . import __version__, paths, themes
from .log import Cancelled, set_sink
from .uikit import ColorPicker, PreviewCanvas, Tooltip
from .units import M_PER_MI

SETTINGS = paths.APP_DIR / "settings.json"

AREA_PRESETS = {
    "Neighborhood (1 mi)": 1,
    "Downtown (2.5 mi)": 2.5,
    "City (6 mi)": 6,
    "Metro (15 mi)": 15,
    "Big metro (25 mi)": 25,
}
SIZE_PRESETS = {
    "Poster 12 × 16 in (default)": (12, 16),
    "Poster 18 × 24 in": (18, 24),
    "Poster 24 × 36 in": (24, 36),
    "Print 8 × 10 in": (8, 10),
    "Print 11 × 14 in": (11, 14),
    "Print 16 × 20 in": (16, 20),
    "A4 (8.3 × 11.7)": (8.3, 11.7),
    "A3 (11.7 × 16.5)": (11.7, 16.5),
    "A2 (16.5 × 23.4)": (16.5, 23.4),
    "Landscape 16 × 12": (16, 12),
    "Square 1080 px (3.6 × 3.6)": (3.6, 3.6),
    "Instagram post 1080 × 1350": (3.6, 4.5),
    "Phone wallpaper 1080 × 2400": (3.6, 8.0),
    "Desktop 1920 × 1080": (6.4, 3.6),
    "Desktop 4K 3840 × 2160": (12.8, 7.2),
    "Watch face 450 × 450": (1.5, 1.5),
}
LAYER_LABELS = {
    "water": "Lakes & water", "parks": "Parks & green", "coastline": "Ocean (coastline)",
    "waterways": "Rivers & canals", "railways": "Railways", "airports": "Airports",
    "buildings": "Buildings", "washes": "Washes & streams", "trails": "Trails",
    "places": "Neighborhoods (names)",
}
CORNERS = ["top-left", "top-right", "bottom-left", "bottom-right"]
DEFAULTS = {
    "city": "Phoenix", "country": "USA", "lat": "", "lon": "",
    "display_city": "", "display_country": "", "country_label": "",
    "distance_mi": "6", "source": "online", "pbf": "",
    "width": "12", "height": "16", "fmt": "png", "dpi": "300", "bleed": "0",
    "font": "", "road_scale": "1.0", "auto_roads": True,
    "show_text": True, "show_coords": True, "show_gradient": True,
    "themes": ["terracotta"], "region": "north-america/us/arizona",
    "text_position": "bottom", "title_style": "spaced", "letter_spacing": "2",
    "tagline": "", "border": "none", "shape": "rect", "boundary_file": "",
    "markers": "", "gpx": [], "fit_route": False, "route_width": "2.2",
    "mockup": "none", "output_dir": "", "layers": None,
    "terrain": "none", "contour_interval": "", "terrain_strength": "1.0",
    "label_roads": False, "label_places": False, "label_parks": False, "label_scale": "1.0",
    "highlight": "", "highlight_file": "", "highlight_mode": "fill", "highlight_label": "",
    "scale_bar": False, "north_arrow": False, "grid": False, "elevation_profile": False,
    "photo": "", "photo_corner": "top-right", "qr": "", "qr_corner": "top-left",
    "font_file": "", "crop_marks": False, "icc": "", "set_places": "", "zoom_series": "",
    "dark": False, "geometry": "", "tab": 0, "live_preview": False,
}

TIPS = {
    "city": "The place to put on the poster. Looked up online unless you type Lat / Lon.",
    "country": "Helps the lookup find the right city, e.g. USA.",
    "lat": "Latitude of the poster centre. Fill both Lat and Lon to skip the city lookup.",
    "lon": "Longitude of the poster centre (negative = west).",
    "display_city": "Text printed as the title, if different from the city you looked up.",
    "display_country": "Text printed under the title, if different from the country.",
    "country_label": "Line printed under the city name, e.g. ARIZONA, USA.",
    "distance_mi": "Miles from the centre to the nearest poster edge. Bigger = more of the region.",
    "source": "Online downloads data from OpenStreetMap. A local .pbf file is faster for big areas.",
    "pbf": "A downloaded OpenStreetMap extract (.pbf). Used when Source is Local .pbf file.",
    "region": "Geofabrik region path to download, e.g. north-america/us/arizona.",
    "width": "Poster width in inches.", "height": "Poster height in inches.",
    "fmt": "File type. PNG for images, PDF or SVG for print and editing.",
    "dpi": "Print sharpness. 300 for print, 100 for quick tests.",
    "bleed": "Extra inches around the poster for printers to trim.",
    "font": "A Google Fonts family name, e.g. Lora. Leave empty for Roboto.",
    "road_scale": "Makes all roads thicker (above 1) or thinner (below 1).",
    "auto_roads": "Adjusts road thickness to the poster size and map area automatically.",
    "show_text": "Print the title block on the poster.",
    "show_coords": "Print the latitude and longitude under the title.",
    "show_gradient": "Fade the map into the background at the top and bottom edges.",
    "text_position": "Where the title block sits.",
    "title_style": "How the title is written: spaced capitals, plain, and so on.",
    "letter_spacing": "Extra space between title letters.",
    "tagline": "An extra line of text, e.g. a date or a short quote.",
    "border": "Frame style around the poster.", "shape": "Crop the map into a circle or heart.",
    "boundary_file": "A GeoJSON outline; only the area inside is drawn.",
    "fit_route": "Zoom the poster to fit your GPX route.",
    "route_width": "Line thickness of GPX routes.",
    "mockup": "Also save a picture of the poster in a frame on a wall.",
    "output_dir": "Where finished posters are saved. Empty = the posters folder.",
    "terrain": "Shaded hills, contour lines, or both, from elevation data.",
    "contour_interval": "Feet between contour lines. Empty = chosen automatically.",
    "terrain_strength": "How strong the hill shading looks.",
    "label_roads": "Print street names along the roads.",
    "label_places": "Print neighborhood names.", "label_parks": "Print park names.",
    "label_scale": "Size of all map labels.",
    "highlight": "Place name to highlight, e.g. Encanto, Phoenix, AZ.",
    "highlight_file": "A GeoJSON outline to highlight instead of a place name.",
    "highlight_mode": "Fill tints the area; focus fades everything else.",
    "highlight_label": "Text printed on the highlighted area.",
    "scale_bar": "Draw a distance bar in miles.", "north_arrow": "Draw a compass arrow.",
    "grid": "Draw latitude and longitude grid lines.",
    "elevation_profile": "Add an elevation chart under the map (needs a GPX route).",
    "photo": "A picture placed in the heart or circle, or as a corner badge.",
    "photo_corner": "Corner for the photo badge.",
    "qr": "A web link or text made into a QR code on the poster.",
    "qr_corner": "Corner for the QR code.",
    "font_file": "A .ttf or .otf file (or a folder of them) to use instead of Roboto.",
    "crop_marks": "Add printer crop marks outside the poster edge.",
    "icc": "A CMYK colour profile (.icc) for a print-ready CMYK TIFF.",
    "zoom_series": "Several radii in miles, e.g. 1, 3, 10: one poster with all zoom levels side by side.",
}
BUTTON_TIPS = {
    "Generate posters": "Make the posters for every selected theme (Ctrl+G).",
    "Quick preview": "A fast, low-resolution version to check the look (Ctrl+P).",
    "Batch from CSV…": "Make many posters from a spreadsheet file.",
    "Cancel": "Stop after the current step (Esc).",
    "Posters folder": "Open the folder with finished posters (Ctrl+O).",
    "Save as…": "Save these settings as a named look (Ctrl+S).",
    "Delete": "Delete the selected saved look.",
    "Pick on map…": "Click the place on a map instead of typing a name.",
    "Download": "Download the Geofabrik extract for this region.",
    "Select all": "Select every theme.", "All": "Select every theme.",
    "None": "Deselect every theme.", "Reload": "Re-read the theme files.",
    "Edit / new…": "Edit the selected theme, or save it under a new name.",
    "Folder": "Open the themes folder.",
    "Undo": "Go back one change (Ctrl+Z).", "Redo": "Redo the change you undid (Ctrl+Y).",
    "Shortcuts": "Show keyboard shortcuts (F1).",
}
SHORTCUTS = (
    ("Ctrl+G", "Generate posters"), ("Ctrl+P", "Quick preview"), ("Esc", "Cancel the running job"),
    ("Ctrl+S", "Save these settings as a look"), ("Ctrl+O", "Open the posters folder"),
    ("Ctrl+Z / Ctrl+Y", "Undo / redo a change"), ("Ctrl+1 … 6", "Jump to a tab"),
    ("Ctrl+D", "Dark mode on / off"), ("Ctrl+F", "Search themes"), ("F1", "This list"),
    ("Mouse wheel", "Zoom the preview"), ("Drag", "Move the zoomed preview"),
    ("Double-click", "Open the poster file"),
)


def open_path(p: Path) -> None:
    p = Path(p)
    if sys.platform.startswith("win"):
        os.startfile(p)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", p])
    else:
        subprocess.Popen(["xdg-open", p])


def _pil_thumb(path: Path, w: int, h: int):
    from PIL import Image, ImageTk
    with Image.open(path) as im:
        im.thumbnail((max(w, 50), max(h, 50)))
        return ImageTk.PhotoImage(im)


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        paths.ensure_dirs()
        self.title(f"Map Poster Studio {__version__}")
        self.geometry("1340x820")
        self.minsize(1040, 660)
        try:
            ico = paths.RESOURCES.parent.parent / "assets" / "icon.ico"
            if sys.platform.startswith("win") and ico.exists():
                self.iconbitmap(str(ico))
        except tk.TclError:
            pass

        self.q: queue.Queue = queue.Queue()
        self.cancel_evt = threading.Event()
        self.worker: threading.Thread | None = None
        self.preview_img = None
        self.last_output: Path | None = None

        self.s = dict(DEFAULTS)
        try:
            self.s.update(json.loads(SETTINGS.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            pass
        if "distance_km" in self.s:  # settings saved by version 1.0/1.1 were in km
            try:
                self.s["distance_mi"] = f"{float(self.s['distance_km']) * 1000 / M_PER_MI:.1f}"
            except ValueError:
                pass
            self.s.pop("distance_km")

        self._restore_geometry()
        self._t0 = 0.0
        self._run_label = ""
        self._step = ""
        self.recent_imgs: list = []
        self.tiles: dict = {}
        self._tcache: dict = {}
        self._ready = False
        self._restoring = False
        self._quiet = False
        self._live_run = False
        self._live_again = False
        self._settle_id = None
        self.undo: list[dict] = []
        self.redo: list[dict] = []
        self.v: dict = {}
        self._build()
        self._load_themes()
        self._apply_theme_mode()
        self._wire_changes()
        self._bind_shortcuts()
        self._attach_tips()
        try:
            self.nb.select(max(0, min(5, int(self.s.get("tab") or 0))))
        except (tk.TclError, ValueError):
            pass
        self._push_snapshot()
        self._update_undo_buttons()
        self._ready = True
        set_sink(lambda m: self.q.put(("log", m)))
        self.after(100, self._poll)
        self.after(300, self._place_divider)
        self.after(600, self._scan_recent)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _restore_geometry(self) -> None:
        """Reopen at the last size and position, if that spot is still on screen."""
        g = str(self.s.get("geometry") or "")
        m = re.fullmatch(r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", g)
        if not m:
            return
        w, h, x, y = map(int, m.groups())
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        if w >= 1040 and h >= 660 and -w + 120 < x < sw - 120 and 0 <= y < sh - 80:
            self.geometry(g)

    # ---------------------------------------------------------- helpers
    def var(self, key, kind=tk.StringVar):
        v = kind(value=self.s.get(key, DEFAULTS[key]))
        self.v[key] = v
        return v

    @staticmethod
    def row(parent, r, label, widget, hint=None):
        ttk.Label(parent, text=label).grid(row=r, column=0, sticky="w", pady=2, padx=(0, 6))
        widget.grid(row=r, column=1, sticky="ew", pady=2)
        if hint:
            ttk.Label(parent, text=hint, foreground="gray").grid(row=r + 1, column=1, sticky="w")
        return widget

    @staticmethod
    def frame(parent, text):
        f = ttk.LabelFrame(parent, text=text, padding=6)
        f.pack(fill="x", pady=(0, 6))
        f.columnconfigure(1, weight=1)
        return f

    # ------------------------------------------------------------ layout
    def _build(self) -> None:
        root = ttk.Frame(self, padding=8)
        root.pack(fill="both", expand=True)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        left = ttk.Frame(root, width=460)
        left.grid(row=0, column=0, sticky="ns", padx=(0, 8))
        left.rowconfigure(1, weight=1)

        pbox = ttk.Frame(left)
        pbox.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        pb = ttk.Frame(pbox)
        pb.pack(fill="x")
        ttk.Label(pb, text="Preset").pack(side="left")
        self.preset_var = tk.StringVar()
        self.preset_cb = ttk.Combobox(pb, textvariable=self.preset_var, width=16, state="readonly")
        self.preset_cb.pack(side="left", padx=4)
        self.preset_cb.bind("<<ComboboxSelected>>", lambda e: self._load_preset())
        ttk.Button(pb, text="Save as…", command=self._save_preset).pack(side="left")
        ttk.Button(pb, text="Delete", command=self._delete_preset).pack(side="left", padx=2)
        self.dark_var = tk.BooleanVar(value=bool(self.s.get("dark")))
        ttk.Checkbutton(pb, text="Dark mode", variable=self.dark_var,
                        command=self._apply_theme_mode).pack(side="right")
        pb2 = ttk.Frame(pbox)
        pb2.pack(fill="x", pady=(6, 0))
        self.undo_btn = ttk.Button(pb2, text="Undo", width=7, command=self._undo)
        self.undo_btn.pack(side="left")
        self.redo_btn = ttk.Button(pb2, text="Redo", width=7, command=self._redo)
        self.redo_btn.pack(side="left", padx=4)
        self.live_var = tk.BooleanVar(value=bool(self.s.get("live_preview")))
        live = ttk.Checkbutton(pb2, text="Live preview", variable=self.live_var,
                               command=self._live_toggled)
        live.pack(side="left", padx=(10, 0))
        Tooltip(live, "Redraws a quick preview a moment after you change something. "
                      "Works best with a local .pbf file or after the area is cached.")
        ttk.Button(pb2, text="Shortcuts", command=self._show_shortcuts).pack(side="right")
        self._refresh_presets()

        nb = self.nb = ttk.Notebook(left)
        nb.grid(row=1, column=0, sticky="nsew")
        tabs = {}
        for name in ("Place", "Map", "Details", "Text", "Overlays", "Output"):
            f = ttk.Frame(nb, padding=8)
            nb.add(f, text=name)
            tabs[name] = f

        self._tab_place(tabs["Place"])
        self._tab_map(tabs["Map"])
        self._tab_details(tabs["Details"])
        self._tab_text(tabs["Text"])
        self._tab_overlays(tabs["Overlays"])
        self._tab_output(tabs["Output"])

        btn = ttk.Frame(left, padding=(0, 6, 0, 0))
        btn.grid(row=2, column=0, sticky="ew")
        for i in range(3):
            btn.columnconfigure(i, weight=1)
        self.go_btn = ttk.Button(btn, text="Generate posters", command=self._generate,
                                 style="Accent.TButton")
        self.go_btn.grid(row=0, column=0, columnspan=2, sticky="ew", ipady=6)
        self.prev_btn = ttk.Button(btn, text="Quick preview", command=lambda: self._generate(True))
        self.prev_btn.grid(row=0, column=2, sticky="ew", padx=(6, 0), ipady=6)
        self.batch_btn = ttk.Button(btn, text="Batch from CSV…", command=self._batch)
        self.batch_btn.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self.cancel_btn = ttk.Button(btn, text="Cancel", command=self._cancel, state="disabled")
        self.cancel_btn.grid(row=1, column=1, sticky="ew", padx=6, pady=(6, 0))
        ttk.Button(btn, text="Posters folder", command=lambda: open_path(self._out_dir())).grid(
            row=1, column=2, sticky="ew", pady=(6, 0))

        right = ttk.Frame(root)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        self.pane = ttk.PanedWindow(right, orient="vertical")
        self.pane.grid(row=0, column=0, sticky="nsew")
        pv = ttk.LabelFrame(self.pane, text="Preview  ·  scroll to zoom, drag to move, double-click to open", padding=6)
        pv.columnconfigure(0, weight=1)
        pv.rowconfigure(0, weight=1)
        self.preview = PreviewCanvas(pv, on_open=lambda: self.last_output and open_path(self.last_output))
        self.preview.grid(row=0, column=0, sticky="nsew")
        self.preview.set_text("Your poster shows up here\n\n"
                              "Pick a place, then press Generate posters.\n"
                              "Quick preview makes a fast, low-resolution version first.")
        rc = ttk.Frame(pv)
        rc.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(rc, text="Recent posters", font=("Segoe UI", 10, "bold")
                  if sys.platform.startswith("win") else None).pack(anchor="w")
        self.recent_row = ttk.Frame(rc)
        self.recent_row.pack(anchor="w", fill="x", pady=(4, 0))

        lg = ttk.LabelFrame(self.pane, text="Log", padding=6)
        lg.columnconfigure(0, weight=1)
        lg.rowconfigure(0, weight=1)
        self.log = tk.Text(lg, height=5, wrap="word", state="disabled", relief="flat",
                           borderwidth=0, padx=6, pady=4,
                           font=("Consolas", 9) if sys.platform.startswith("win") else None)
        lsb = ttk.Scrollbar(lg, command=self.log.yview)
        self.log.configure(yscrollcommand=lsb.set)
        self.log.grid(row=0, column=0, sticky="nsew")
        lsb.grid(row=0, column=1, sticky="ns")
        self.pane.add(pv, weight=6)
        self.pane.add(lg, weight=1)

        self.status = ttk.Label(self, text="Ready", anchor="w", padding=(12, 4))
        self.status.pack(fill="x", side="bottom")
        self.progress = ttk.Progressbar(self, mode="indeterminate")

    # ----- tab: place
    def _tab_place(self, t) -> None:
        loc = self.frame(t, "Location")
        self.row(loc, 0, "City", ttk.Entry(loc, textvariable=self.var("city"), width=30))
        self.row(loc, 1, "Country", ttk.Entry(loc, textvariable=self.var("country")))
        ll = ttk.Frame(loc)
        ttk.Entry(ll, textvariable=self.var("lat"), width=11).pack(side="left", fill="x",
                                                                    expand=True)
        ttk.Entry(ll, textvariable=self.var("lon"), width=11).pack(side="left", fill="x",
                                                                    expand=True, padx=3)
        ttk.Button(ll, text="Pick on map…", command=self._map_picker).pack(side="left")
        self.row(loc, 2, "Lat / Lon", ll, "optional – overrides the city lookup")
        self.row(loc, 4, "Display city", ttk.Entry(loc, textvariable=self.var("display_city")))
        self.row(loc, 5, "Display country",
                 ttk.Entry(loc, textvariable=self.var("display_country")))
        self.row(loc, 6, "Country label", ttk.Entry(loc, textvariable=self.var("country_label")))

        area = self.frame(t, "Area")
        af = ttk.Frame(area)
        ttk.Entry(af, textvariable=self.var("distance_mi"), width=7).pack(side="left")
        ttk.Label(af, text="miles").pack(side="left", padx=(2, 6))
        preset = ttk.Combobox(af, values=list(AREA_PRESETS), state="readonly", width=22)
        preset.set("presets…")
        preset.bind("<<ComboboxSelected>>",
                    lambda e: self.v["distance_mi"].set(str(AREA_PRESETS[preset.get()])))
        preset.pack(side="left", fill="x", expand=True)
        self.row(area, 0, "Radius", af, "center → nearest poster edge")

        data = self.frame(t, "Map data")
        src = self.var("source")
        sf = ttk.Frame(data)
        ttk.Radiobutton(sf, text="Online (OSM)", value="online", variable=src).pack(side="left")
        ttk.Radiobutton(sf, text="Local .pbf file", value="pbf", variable=src).pack(
            side="left", padx=6)
        self.row(data, 0, "Source", sf)
        pf = ttk.Frame(data)
        ttk.Entry(pf, textvariable=self.var("pbf")).pack(side="left", fill="x", expand=True)
        ttk.Button(pf, text="…", width=3, command=self._browse_pbf).pack(side="left", padx=2)
        self.row(data, 1, "PBF file", pf)
        df = ttk.Frame(data)
        ttk.Entry(df, textvariable=self.var("region")).pack(side="left", fill="x", expand=True)
        ttk.Button(df, text="Download", command=self._download).pack(side="left", padx=2)
        self.row(data, 2, "Geofabrik", df, "e.g. north-america/us/arizona (≈300 MB)")

    # ----- tab: map
    def _tab_map(self, t) -> None:
        st = self.frame(t, "Themes")
        # The listbox is only the selection model (not shown); the swatch gallery drives it.
        self.theme_list = tk.Listbox(st, selectmode="extended", exportselection=False)
        sf = ttk.Frame(st)
        sf.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        ttk.Label(sf, text="Search").pack(side="left", padx=(0, 6))
        self.theme_filter = tk.StringVar()
        self.search_entry = ttk.Entry(sf, textvariable=self.theme_filter)
        self.search_entry.pack(side="left", fill="x", expand=True)
        Tooltip(self.search_entry, "Type part of a theme name to filter the swatches (Ctrl+F).")
        ttk.Button(sf, text="✕", width=3, command=lambda: self.theme_filter.set("")).pack(
            side="left", padx=(4, 0))
        self.theme_count = ttk.Label(sf, text="", foreground="gray")
        self.theme_count.pack(side="left", padx=(8, 0))
        self.theme_filter.trace_add("write", lambda *a: self._rebuild_gallery())
        gal = ttk.Frame(st)
        gal.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.gal_canvas = tk.Canvas(gal, height=190, highlightthickness=0, borderwidth=0)
        gsb = ttk.Scrollbar(gal, command=self.gal_canvas.yview)
        self.gal_canvas.configure(yscrollcommand=gsb.set)
        self.gal_canvas.pack(side="left", fill="both", expand=True)
        gsb.pack(side="left", fill="y")
        self.gal_inner = tk.Frame(self.gal_canvas, borderwidth=0)
        self.gal_canvas.create_window((0, 0), window=self.gal_inner, anchor="nw")
        self.gal_inner.bind("<Configure>", lambda e: self.gal_canvas.configure(
            scrollregion=self.gal_canvas.bbox("all")))
        self.gal_canvas.bind("<MouseWheel>", self._gal_wheel)
        bf = ttk.Frame(st)
        bf.grid(row=2, column=0, columnspan=2, sticky="ew", pady=4)
        for text, cmd in (("All", self._select_all),
                          ("None", lambda: (self.theme_list.selection_clear(0, "end"),
                                            self._show_swatch())),
                          ("Reload", self._load_themes), ("Edit / new…", self._edit_theme),
                          ("Folder", lambda: open_path(paths.THEMES_DIR))):
            ttk.Button(bf, text=text, command=cmd).pack(side="left", fill="x", expand=True)
        self.swatch = tk.Canvas(st, width=260, height=24, highlightthickness=0)
        self.swatch.grid(row=3, column=0, columnspan=2, sticky="w")
        self.theme_desc = ttk.Label(st, text="", foreground="gray", wraplength=360)
        self.theme_desc.grid(row=4, column=0, columnspan=2, sticky="w")

        ly = self.frame(t, "Layers")
        all_layers = paths.load_layers()
        enabled = self.s.get("layers")
        if enabled is None:
            enabled = paths.default_enabled_layers()
        self.layer_vars = {}
        for i, name in enumerate([n for n in paths.LAYER_ORDER if n in all_layers]
                                 + [n for n in all_layers if n not in paths.LAYER_ORDER]):
            v = tk.BooleanVar(value=name in enabled)
            self.layer_vars[name] = v
            ttk.Checkbutton(ly, text=LAYER_LABELS.get(name, name.capitalize()), variable=v).grid(
                row=i // 2, column=i % 2, sticky="w")
        ttk.Button(ly, text="Edit layer tags…", command=lambda: open_path(paths.LAYERS_FILE)).grid(
            row=10, column=0, sticky="w", pady=(4, 0))

        rd = self.frame(t, "Roads & shape")
        rf = ttk.Frame(rd)
        ttk.Entry(rf, textvariable=self.var("road_scale"), width=6).pack(side="left")
        ttk.Checkbutton(rf, text="auto-scale with area", variable=self.var(
            "auto_roads", tk.BooleanVar)).pack(side="left", padx=8)
        self.row(rd, 0, "Road width ×", rf)
        self.row(rd, 1, "Map shape", ttk.Combobox(rd, textvariable=self.var("shape"), state="readonly",
                                                  values=["rect", "circle", "heart", "boundary"]),
                 "boundary = the city's real outline")
        bf2 = ttk.Frame(rd)
        ttk.Entry(bf2, textvariable=self.var("boundary_file")).pack(side="left", fill="x",
                                                                    expand=True)
        ttk.Button(bf2, text="…", width=3, command=lambda: self._browse_into(
            "boundary_file", [("Shapes", "*.geojson *.json *.gpkg *.shp"), ("All", "*.*")])).pack(
            side="left", padx=2)
        self.row(rd, 3, "Outline file", bf2, "optional, for shape = boundary")

    # ----- tab: details (terrain, labels, highlight, map furniture)
    def _tab_details(self, t) -> None:
        tr = self.frame(t, "Terrain")
        self.row(tr, 0, "Show", ttk.Combobox(tr, textvariable=self.var("terrain"),
                                             values=["none", "hillshade", "contours", "both"],
                                             state="readonly"),
                 "shaded hills and/or contour lines")
        cf = ttk.Frame(tr)
        ttk.Entry(cf, textvariable=self.var("contour_interval"), width=6).pack(side="left")
        ttk.Label(cf, text="ft  (blank = auto)    strength").pack(side="left")
        ttk.Entry(cf, textvariable=self.var("terrain_strength"), width=5).pack(side="left",
                                                                              padx=3)
        self.row(tr, 2, "Contour every", cf)
        ttk.Button(tr, text="Save terrain for offline use", command=self._prefetch_terrain).grid(
            row=3, column=1, sticky="w", pady=(4, 0))

        lb = self.frame(t, "Labels")
        lf = ttk.Frame(lb)
        for key, text in (("label_roads", "Street names"), ("label_places", "Neighborhoods"),
                          ("label_parks", "Parks")):
            ttk.Checkbutton(lf, text=text, variable=self.var(key, tk.BooleanVar)).pack(
                side="left", padx=(0, 6))
        self.row(lb, 0, "Show", lf, "Neighborhoods also needs that layer on (Map tab)")
        self.row(lb, 2, "Size ×", ttk.Entry(lb, textvariable=self.var("label_scale"), width=6))

        hl = self.frame(t, "Highlight an area")
        self.row(hl, 0, "Place", ttk.Entry(hl, textvariable=self.var("highlight")),
                 "e.g. Encanto, Phoenix, AZ")
        hf = ttk.Frame(hl)
        ttk.Entry(hf, textvariable=self.var("highlight_file")).pack(side="left", fill="x",
                                                                    expand=True)
        ttk.Button(hf, text="…", width=3, command=lambda: self._browse_into(
            "highlight_file", [("Shapes", "*.geojson *.json *.gpkg *.shp"), ("All", "*.*")])).pack(
            side="left", padx=2)
        self.row(hl, 2, "or file", hf)
        mf = ttk.Frame(hl)
        ttk.Combobox(mf, textvariable=self.var("highlight_mode"), values=["fill", "focus"],
                     state="readonly", width=7).pack(side="left")
        ttk.Label(mf, text="  label").pack(side="left")
        ttk.Entry(mf, textvariable=self.var("highlight_label")).pack(side="left", fill="x",
                                                                     expand=True, padx=3)
        self.row(hl, 3, "Style", mf, "focus = fade everything else")

        fu = self.frame(t, "Map details")
        ff = ttk.Frame(fu)
        for key, text in (("scale_bar", "Scale bar (miles)"), ("north_arrow", "North arrow"),
                          ("grid", "Lat/lon grid")):
            ttk.Checkbutton(ff, text=text, variable=self.var(key, tk.BooleanVar)).pack(
                side="left", padx=(0, 6))
        self.row(fu, 0, "Show", ff)

    # ----- tab: text
    def _tab_text(self, t) -> None:
        tx = self.frame(t, "Text")
        cf = ttk.Frame(tx)
        for key, text in (("show_text", "Text"), ("show_coords", "Coordinates"),
                          ("show_gradient", "Fade")):
            ttk.Checkbutton(cf, text=text, variable=self.var(key, tk.BooleanVar)).pack(
                side="left", padx=(0, 6))
        self.row(tx, 0, "Show", cf)
        self.row(tx, 1, "Position", ttk.Combobox(tx, textvariable=self.var("text_position"),
                                                 values=["bottom", "top"], state="readonly"))
        self.row(tx, 2, "Title style", ttk.Combobox(tx, textvariable=self.var("title_style"),
                                                    values=["spaced", "caps", "normal"],
                                                    state="readonly"),
                 "S P A C E D,  CAPS,  or as typed")
        self.row(tx, 4, "Letter spacing", ttk.Spinbox(tx, from_=0, to=6, width=5,
                                                      textvariable=self.var("letter_spacing")))
        self.row(tx, 5, "Tagline", ttk.Entry(tx, textvariable=self.var("tagline")),
                 "e.g. EST. 1881 · Our first home")
        self.row(tx, 7, "Google font", ttk.Entry(tx, textvariable=self.var("font")),
                 "e.g. Playfair Display, Noto Sans JP (blank = Roboto)")

        fo = ttk.Frame(tx)
        ttk.Entry(fo, textvariable=self.var("font_file")).pack(side="left", fill="x", expand=True)
        ttk.Button(fo, text="…", width=3, command=lambda: self._browse_into(
            "font_file", [("Fonts", "*.ttf *.otf"), ("All", "*.*")])).pack(side="left", padx=2)
        self.row(tx, 9, "Your font file", fo, "overrides the Google font")

        fr = self.frame(t, "Frame")
        self.row(fr, 0, "Border", ttk.Combobox(fr, textvariable=self.var("border"),
                                               values=["none", "thin", "thick", "double"],
                                               state="readonly"))

        ph = self.frame(t, "Photo & QR code")
        pf = ttk.Frame(ph)
        ttk.Entry(pf, textvariable=self.var("photo")).pack(side="left", fill="x", expand=True)
        ttk.Button(pf, text="…", width=3, command=lambda: self._browse_into(
            "photo", [("Images", "*.jpg *.jpeg *.png *.webp *.heic"), ("All", "*.*")])).pack(
            side="left", padx=2)
        self.row(ph, 0, "Photo", pf, "fills a circle/heart shape, otherwise a corner badge")
        self.row(ph, 2, "Photo corner", ttk.Combobox(ph, textvariable=self.var("photo_corner"),
                                                     values=CORNERS, state="readonly"))
        self.row(ph, 3, "QR code", ttk.Entry(ph, textvariable=self.var("qr")),
                 "a link or any text, e.g. a photo album")
        self.row(ph, 5, "QR corner", ttk.Combobox(ph, textvariable=self.var("qr_corner"),
                                                  values=CORNERS, state="readonly"))

    # ----- tab: overlays
    def _tab_overlays(self, t) -> None:
        mk = self.frame(t, "Markers")
        ttk.Label(mk, text="One per line:  lat, lon, label, icon\n"
                           "icon = pin, heart, star or dot (label and icon optional)",
                  foreground="gray").grid(row=0, column=0, columnspan=2, sticky="w")
        self.markers_txt = tk.Text(mk, height=6, width=40, wrap="none")
        self.markers_txt.grid(row=1, column=0, columnspan=2, sticky="ew", pady=3)
        self.markers_txt.insert("1.0", self.s.get("markers", ""))
        ttk.Button(mk, text="Add by clicking the map…", command=self._map_picker).grid(
            row=2, column=0, sticky="w")

        rt = self.frame(t, "GPX routes")
        self.gpx_list = tk.Listbox(rt, height=4)
        self.gpx_list.grid(row=0, column=0, columnspan=2, sticky="ew")
        for g in self.s.get("gpx") or []:
            self.gpx_list.insert("end", g)
        gb = ttk.Frame(rt)
        gb.grid(row=1, column=0, columnspan=2, sticky="w", pady=3)
        ttk.Button(gb, text="Add GPX…", command=self._add_gpx).pack(side="left")
        ttk.Button(gb, text="Remove", command=lambda: [self.gpx_list.delete(i) for i in
                                                       reversed(self.gpx_list.curselection())]
                   ).pack(side="left", padx=4)
        ttk.Checkbutton(rt, text="Center and size the poster on the route",
                        variable=self.var("fit_route", tk.BooleanVar)).grid(
            row=2, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(rt, text="Elevation profile under the map",
                        variable=self.var("elevation_profile", tk.BooleanVar)).grid(
            row=3, column=0, columnspan=2, sticky="w")
        self.row(rt, 4, "Line width", ttk.Entry(rt, textvariable=self.var("route_width"), width=6))

    # ----- tab: output
    def _tab_output(self, t) -> None:
        size = self.frame(t, "Size")
        sp = ttk.Combobox(size, values=list(SIZE_PRESETS), state="readonly")
        sp.set("presets…")

        def pick_size(_e):
            w, h = SIZE_PRESETS[sp.get()]
            self.v["width"].set(str(w))
            self.v["height"].set(str(h))
        sp.bind("<<ComboboxSelected>>", pick_size)
        self.row(size, 0, "Preset", sp)
        wf = ttk.Frame(size)
        ttk.Entry(wf, textvariable=self.var("width"), width=6).pack(side="left")
        ttk.Label(wf, text=" × ").pack(side="left")
        ttk.Entry(wf, textvariable=self.var("height"), width=6).pack(side="left")
        ttk.Label(wf, text=" in (max 36)").pack(side="left")
        self.row(size, 1, "Width × height", wf, "pixel presets assume 300 DPI")
        self.row(size, 3, "Print bleed", ttk.Entry(size, textvariable=self.var("bleed"), width=6),
                 "inches per side; 0.125 is standard for print shops")

        of = self.frame(t, "File")
        ff = ttk.Frame(of)
        ttk.Combobox(ff, textvariable=self.var("fmt"), values=["png", "svg", "pdf"],
                     state="readonly", width=6).pack(side="left")
        ttk.Label(ff, text="  DPI").pack(side="left")
        ttk.Entry(ff, textvariable=self.var("dpi"), width=6).pack(side="left")
        self.row(of, 0, "Format", ff, "SVG keeps layers for Inkscape / Illustrator")
        self.row(of, 2, "Wall mockup", ttk.Combobox(of, textvariable=self.var("mockup"),
                                                    values=["none", "black", "white", "oak"],
                                                    state="readonly"),
                 "framed-on-a-wall image next to each PNG")
        od = ttk.Frame(of)
        ttk.Entry(od, textvariable=self.var("output_dir")).pack(side="left", fill="x",
                                                                expand=True)
        ttk.Button(od, text="…", width=3, command=self._browse_outdir).pack(side="left", padx=2)
        self.row(of, 4, "Save to", od, "blank = the posters folder")

        pr = self.frame(t, "Print shop")
        ttk.Checkbutton(pr, text="Crop marks (use with bleed)",
                        variable=self.var("crop_marks", tk.BooleanVar)).grid(
            row=0, column=0, columnspan=2, sticky="w")
        icf = ttk.Frame(pr)
        ttk.Entry(icf, textvariable=self.var("icc")).pack(side="left", fill="x", expand=True)
        ttk.Button(icf, text="…", width=3, command=lambda: self._browse_into(
            "icc", [("ICC profiles", "*.icc *.icm"), ("All", "*.*")])).pack(side="left", padx=2)
        self.row(pr, 1, "CMYK profile", icf, "adds a CMYK TIFF next to each PNG")

        st = self.frame(t, "Poster sets")
        self.row(st, 0, "Zoom series", ttk.Entry(st, textvariable=self.var("zoom_series")),
                 "radii in miles, e.g. 1, 4, 12 (one place, side by side)")
        ttk.Label(st, text="Places side by side (one “City, Country” per line):").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.set_txt = tk.Text(st, height=3, width=40)
        self.set_txt.grid(row=3, column=0, columnspan=2, sticky="ew")
        self.set_txt.insert("1.0", self.s.get("set_places", ""))

    # ------------------------------------------------------------ themes
    def _load_themes(self, select: str | None = None) -> None:
        self._tcache = {}
        prev = set(self.s.get("themes") or [])
        if self.theme_list.size():
            prev = {self.theme_list.get(i) for i in self.theme_list.curselection()}
        if select:
            prev.add(select)
        self.theme_list.delete(0, "end")
        for i, key in enumerate(themes.available_themes()):
            self.theme_list.insert("end", key)
            if key in prev:
                self.theme_list.selection_set(i)
        self._rebuild_gallery()
        self._show_swatch()

    def _select_all(self) -> None:
        self.theme_list.selection_set(0, "end")
        self._show_swatch()

    def _selected_themes(self) -> list[str]:
        return [self.theme_list.get(i) for i in self.theme_list.curselection()]

    TILE_W, TILE_H = 144, 86

    def _accent(self) -> str:
        return "#60cdff" if self.dark_var.get() else "#005fb8"

    def _gal_wheel(self, e) -> None:
        self.gal_canvas.yview_scroll(int(-e.delta / 120), "units")

    def _rebuild_gallery(self) -> None:
        for w in self.gal_inner.winfo_children():
            w.destroy()
        self.tiles = {}
        W, H = self.TILE_W, self.TILE_H
        needle = self.theme_filter.get().strip().lower() if hasattr(self, "theme_filter") else ""
        shown = 0
        for n in range(self.theme_list.size()):
            key = self.theme_list.get(n)
            try:
                t = self._tcache.get(key) or themes.load_theme(key)
                self._tcache[key] = t
            except Exception:
                continue
            if needle and needle not in key.lower() and needle not in str(t.get("name", "")).lower():
                continue
            n = shown
            shown += 1
            c = tk.Canvas(self.gal_inner, width=W, height=H, highlightthickness=0,
                          borderwidth=0, cursor="hand2", bg=t["bg"])
            c.grid(row=n // 3, column=n % 3, padx=4, pady=4)
            c.create_rectangle(0, H * 0.56, W, H * 0.78, fill=t.get("water", t["bg"]), outline="")
            c.create_rectangle(10, 9, 46, 28, fill=t.get("parks", t["bg"]), outline="")
            for pts, k, wd in (((0, 22, W, 50), "road_motorway", 3), ((26, 0, 90, H), "road_primary", 2.4),
                               ((0, 54, W, 30), "road_secondary", 1.8), ((58, 0, 108, H), "road_tertiary", 1.2),
                               ((0, 38, W, 44), "road_residential", 1)):
                c.create_line(*pts, fill=t.get(k, t["text"]), width=wd)
            c.create_rectangle(0, H - 20, W, H, fill=t["bg"], outline="")
            c.create_text(W // 2, H - 10, text=key.replace("_", " "), fill=t["text"],
                          font=("Segoe UI", 8, "bold") if sys.platform.startswith("win") else None)
            c.bind("<Button-1>", lambda e, k=key: self._toggle_theme(k))
            c.bind("<Double-Button-1>", lambda e, k=key: self._edit_theme_key(k))
            c.bind("<MouseWheel>", self._gal_wheel)
            Tooltip(c, f"{t.get('name', key)} - {t.get('description', '')}\n"
                       "Click to select or deselect. Double-click to edit.")
            self.tiles[key] = c
        self._mark_tiles()

    def _mark_tiles(self) -> None:
        sel = set(self._selected_themes())
        W, H = self.TILE_W, self.TILE_H
        acc = self._accent()
        for key, c in self.tiles.items():
            c.delete("sel")
            if key in sel:
                c.create_rectangle(1, 1, W - 2, H - 2, outline=acc, width=3, tags="sel")
                c.create_oval(W - 22, 6, W - 6, 22, fill=acc, outline="", tags="sel")
                c.create_text(W - 14, 14, text="✓", fill="#ffffff" if not self.dark_var.get()
                              else "#000000", font=("Segoe UI", 9, "bold")
                              if sys.platform.startswith("win") else None, tags="sel")

    def _toggle_theme(self, key: str) -> None:
        names = [self.theme_list.get(i) for i in range(self.theme_list.size())]
        if key not in names:
            return
        i = names.index(key)
        if self.theme_list.selection_includes(i):
            self.theme_list.selection_clear(i)
        else:
            self.theme_list.selection_set(i)
        self._show_swatch()

    def _edit_theme_key(self, key: str) -> None:
        names = [self.theme_list.get(i) for i in range(self.theme_list.size())]
        if key in names:
            self.theme_list.selection_set(names.index(key))
        self._show_swatch()
        self._edit_theme()

    def _show_swatch(self) -> None:
        self._mark_tiles()
        total = self.theme_list.size()
        self.theme_count.configure(
            text=f"{len(self.theme_list.curselection())} selected · {len(self.tiles)}/{total} shown")
        self._changed()
        self.swatch.delete("all")
        sel = self._selected_themes()
        if not sel:
            self.theme_desc.configure(text="Click themes to pick one or more. "
                                           "Double-click a theme to edit it.")
            return
        t = themes.load_theme(sel[-1])
        keys = ["bg", "water", "parks", "road_residential", "road_tertiary",
                "road_secondary", "road_primary", "road_motorway", "text", "marker"]
        for i, k in enumerate(keys):
            self.swatch.create_rectangle(i * 26, 2, i * 26 + 24, 22, fill=t[k], outline="#888")
        n = len(sel)
        self.theme_desc.configure(
            text=f"{t.get('name', sel[-1])} – {t.get('description', '')}"
                 + (f"\n({n} themes selected)" if n > 1 else ""))

    def _edit_theme(self) -> None:
        sel = self._selected_themes()
        ThemeEditor(self, sel[-1] if sel else "terracotta")

    # ----------------------------------------------------------- pickers
    def _browse_into(self, key, types) -> None:
        f = filedialog.askopenfilename(filetypes=types)
        if f:
            self.v[key].set(f)

    def _browse_pbf(self) -> None:
        f = filedialog.askopenfilename(
            title="Choose an OpenStreetMap extract", initialdir=paths.DATA_DIR,
            filetypes=[("OSM PBF", "*.osm.pbf *.pbf"), ("All files", "*.*")])
        if f:
            self.v["pbf"].set(f)
            self.v["source"].set("pbf")

    def _browse_outdir(self) -> None:
        d = filedialog.askdirectory(initialdir=self._out_dir())
        if d:
            self.v["output_dir"].set(d)

    def _add_gpx(self) -> None:
        for f in filedialog.askopenfilenames(filetypes=[("GPX", "*.gpx"), ("All", "*.*")]):
            self.gpx_list.insert("end", f)
            self._changed()

    def _out_dir(self) -> Path:
        d = self.v["output_dir"].get().strip()
        return Path(d) if d else paths.POSTERS_DIR

    def _map_picker(self) -> None:
        try:
            MapPicker(self)
        except ImportError:
            messagebox.showerror("Map picker", "The map widget (tkintermapview) is not installed.")

    def add_marker_line(self, lat, lon, label, icon) -> None:
        cur = self.markers_txt.get("1.0", "end").strip()
        line = f"{lat:.6f}, {lon:.6f}" + (f", {label}" if label else "") + f", {icon}"
        self.markers_txt.delete("1.0", "end")
        self.markers_txt.insert("1.0", (cur + "\n" if cur else "") + line)

    # ----------------------------------------------------------- actions
    def _collect(self) -> dict:
        s = {k: v.get() for k, v in self.v.items()}
        s["themes"] = self._selected_themes()
        s["layers"] = [n for n, v in self.layer_vars.items() if v.get()]
        s["markers"] = self.markers_txt.get("1.0", "end").strip()
        s["gpx"] = list(self.gpx_list.get(0, "end"))
        s["set_places"] = self.set_txt.get("1.0", "end").strip()
        s["dark"] = self.dark_var.get()
        s["geometry"] = self.geometry()
        s["tab"] = self.nb.index("current")
        s["live_preview"] = self.live_var.get()
        return s

    def _save_settings(self) -> None:
        try:
            SETTINGS.write_text(json.dumps(self._collect(), indent=1), encoding="utf-8")
        except OSError:
            pass

    def _start(self, target, label: str) -> None:
        if self.worker and self.worker.is_alive():
            return
        self.cancel_evt.clear()
        for b in (self.go_btn, self.prev_btn, self.batch_btn):
            b.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.status.configure(text=label)
        self._t0 = time.time()
        self._run_label = label
        self._step = ""
        self.progress.configure(mode="indeterminate", value=0)
        self.progress.pack(fill="x", side="bottom", before=self.status)
        self.progress.start(12)
        self.after(1000, self._tick)

        def check():
            if self.cancel_evt.is_set():
                raise Cancelled()

        def body():
            try:
                target(check)
                self.q.put(("done", None))
            except Cancelled:
                self.q.put(("log", "\nCancelled."))
                self.q.put(("done", None))
            except Exception as e:
                self.q.put(("error", str(e)))

        self.worker = threading.Thread(target=body, daemon=True)
        self.worker.start()

    def _build_job(self, s: dict, need_city=True):
        from .core import Job
        try:
            dist = float(s["distance_mi"]) * M_PER_MI
            w, h = float(s["width"]), float(s["height"])
            dpi = int(float(s["dpi"]))
            road_scale = float(s["road_scale"] or 1)
            bleed = float(s["bleed"] or 0)
            contour = float(s["contour_interval"]) if s["contour_interval"].strip() else None
            t_strength = float(s["terrain_strength"] or 1)
            l_scale = float(s["label_scale"] or 1)
            from .units import parse_distance
            zooms = [parse_distance(x) for x in s["zoom_series"].replace(";", ",").split(",")
                     if x.strip()]
            spacing = int(float(s["letter_spacing"] or 0))
            route_w = float(s["route_width"] or 2.2)
        except ValueError as e:
            self._err("Invalid number",
                      f"Check the numbers (radius, size, DPI, bleed, spacing, widths, "
                                 f"terrain, zoom series).\n\n{e}")
            return None
        pbf = s["pbf"].strip() if s["source"] == "pbf" else None
        if s["source"] == "pbf" and not pbf:
            self._warn("No file", "Choose a .pbf file or switch to Online.")
            return None
        return Job(
            city=s["city"].strip(), country=s["country"].strip(), themes=s["themes"],
            distance_m=dist, width=w, height=h,
            latitude=s["lat"].strip() or None, longitude=s["lon"].strip() or None,
            country_label=s["country_label"].strip() or None,
            display_city=s["display_city"].strip() or None,
            display_country=s["display_country"].strip() or None,
            font_family=s["font"].strip() or None, fmt=s["fmt"], dpi=dpi,
            road_scale=road_scale, auto_roads=s["auto_roads"],
            show_text=s["show_text"], show_coords=s["show_coords"],
            show_gradient=s["show_gradient"], pbf=pbf,
            output_dir=s["output_dir"].strip() or None,
            layers=s["layers"], text_position=s["text_position"],
            title_style=s["title_style"], letter_spacing=spacing,
            tagline=s["tagline"].strip(), border=s["border"], shape=s["shape"],
            boundary_file=s["boundary_file"].strip() or None, bleed=bleed,
            markers=[ln for ln in s["markers"].splitlines() if ln.strip()],
            gpx=s["gpx"], fit_route=s["fit_route"], route_width=route_w,
            mockup=None if s["mockup"] == "none" else s["mockup"],
            elevation_profile=s["elevation_profile"], terrain=s["terrain"],
            contour_interval_ft=contour, terrain_strength=t_strength,
            labels=[k for k in ("roads", "places", "parks") if s[f"label_{k}"]],
            label_scale=l_scale, highlight=s["highlight"].strip() or None,
            highlight_file=s["highlight_file"].strip() or None,
            highlight_mode=s["highlight_mode"], highlight_label=s["highlight_label"].strip(),
            scale_bar=s["scale_bar"], north_arrow=s["north_arrow"], grid=s["grid"],
            photo=s["photo"].strip() or None, photo_corner=s["photo_corner"],
            qr=s["qr"].strip(), qr_corner=s["qr_corner"],
            font_file=s["font_file"].strip() or None, crop_marks=s["crop_marks"],
            icc=s["icc"].strip() or None,
            set_places=[ln.strip() for ln in s["set_places"].splitlines() if ln.strip()],
            zoom_series=zooms,
        )

    def _warn(self, title: str, msg: str) -> None:
        if not self._quiet:
            messagebox.showwarning(title, msg)

    def _err(self, title: str, msg: str) -> None:
        if not self._quiet:
            messagebox.showerror(title, msg)

    def _ask(self, title: str, msg: str) -> bool:
        return False if self._quiet else messagebox.askyesno(title, msg)

    def _generate(self, preview: bool = False) -> None:
        s = self._collect()
        if not s["themes"]:
            self._warn("No theme", "Select at least one theme (Map tab).")
            return
        if not s["set_places"].strip() and (not s["city"].strip() or not s["country"].strip()):
            self._warn("Missing", "City and country are required (Place tab).")
            return
        job = self._build_job(s)
        if job is None:
            return
        job.preview = preview
        if job.distance_m > 20000 and not job.pbf and not job.fit_route:
            if not self._ask(
                    "Large area",
                    "Downloading this much from the online OSM servers can take a long time "
                    "and may time out.\n\nFor big areas, a local .pbf extract is much faster "
                    "(Place tab → Download).\n\nContinue online anyway?"):
                return
        self._save_settings()
        from .core import run

        def work(check):
            run(job, check_cancel=check, on_output=lambda p: self.q.put(("poster", p)))

        n = len(job.themes)
        self._start(work, "Rendering preview…" if preview else
                    f"Generating {n} poster{'s' if n > 1 else ''}…")

    def _batch(self) -> None:
        f = filedialog.askopenfilename(title="Batch CSV", initialdir=paths.APP_DIR,
                                       filetypes=[("CSV", "*.csv"), ("All", "*.*")])
        if not f:
            return
        s = self._collect()
        if not s["themes"]:
            s["themes"] = ["terracotta"]
        base = self._build_job(s)
        if base is None:
            return
        # rows set their own place; don't inherit the window's coordinates
        base.latitude = base.longitude = None
        self._save_settings()
        from .core import run_batch

        def work(check):
            run_batch(f, base=base, check_cancel=check,
                      on_output=lambda p: self.q.put(("poster", p)))

        self._start(work, f"Batch: {Path(f).name}…")

    def _download(self) -> None:
        region = self.v["region"].get().strip()
        if not region:
            return
        from .download import download_pbf

        def work(check):
            p = download_pbf(region, check_cancel=check)
            self.q.put(("pbf", p))

        self._start(work, f"Downloading {region}…")

    def _cancel(self) -> None:
        self.cancel_evt.set()
        self.status.configure(text="Cancelling after the current step…")

    # ----------------------------------------------------------- presets
    PRESET_TO_VAR = {
        "fmt": "fmt", "dpi": "dpi", "width": "width", "height": "height", "bleed": "bleed",
        "road_scale": "road_scale", "auto_roads": "auto_roads", "show_text": "show_text",
        "show_coords": "show_coords", "show_gradient": "show_gradient",
        "text_position": "text_position", "title_style": "title_style",
        "letter_spacing": "letter_spacing", "tagline": "tagline", "border": "border",
        "shape": "shape", "route_width": "route_width", "fit_route": "fit_route",
        "terrain": "terrain", "terrain_strength": "terrain_strength",
        "label_scale": "label_scale", "highlight_mode": "highlight_mode",
        "scale_bar": "scale_bar", "north_arrow": "north_arrow", "grid": "grid",
        "photo_corner": "photo_corner", "qr_corner": "qr_corner", "font_file": "font_file",
        "crop_marks": "crop_marks", "icc": "icc", "elevation_profile": "elevation_profile",
        "font_family": "font", "output_dir": "output_dir",
    }

    def _refresh_presets(self) -> None:
        from .presets import list_presets
        self.preset_cb.configure(values=list_presets())

    def _save_preset(self) -> None:
        name = simpledialog.askstring("Save preset", "Name for this look:", parent=self,
                                      initialvalue=self.preset_var.get())
        if not name:
            return
        s = self._collect()
        s["themes"] = s["themes"] or ["terracotta"]
        job = self._build_job(s)
        if job is None:
            return
        from .presets import save_preset
        save_preset(name, job)
        self._refresh_presets()
        self.preset_var.set(name)

    def _delete_preset(self) -> None:
        name = self.preset_var.get()
        if name and messagebox.askyesno("Delete preset", f"Delete '{name}'?"):
            from .presets import delete_preset
            delete_preset(name)
            self.preset_var.set("")
            self._refresh_presets()

    def _load_preset(self) -> None:
        from .presets import load_preset
        from .units import M_PER_MI
        try:
            p = load_preset(self.preset_var.get())
        except Exception as e:
            messagebox.showerror("Preset", str(e))
            return
        for k, key in self.PRESET_TO_VAR.items():
            if k in p and key in self.v:
                v = p[k]
                self.v[key].set("" if v is None else v)
        if "mockup" in p:
            self.v["mockup"].set(p["mockup"] or "none")
        if "distance_m" in p and not p.get("legacy_distance"):
            self.v["distance_mi"].set(f"{p['distance_m'] / M_PER_MI:g}")
        if p.get("contour_interval_ft"):
            self.v["contour_interval"].set(f"{p['contour_interval_ft']:g}")
        else:
            self.v["contour_interval"].set("")
        if "labels" in p:
            for k in ("roads", "places", "parks"):
                self.v[f"label_{k}"].set(k in (p["labels"] or []))
        if p.get("layers") is not None:
            for n, var in self.layer_vars.items():
                var.set(n in p["layers"])
        if p.get("themes"):
            self.theme_list.selection_clear(0, "end")
            for i in range(self.theme_list.size()):
                if self.theme_list.get(i) in p["themes"]:
                    self.theme_list.selection_set(i)
            self._show_swatch()
        if p.get("pbf"):
            self.v["pbf"].set(p["pbf"])
            self.v["source"].set("pbf")
        zs = p.get("zoom_series") or []
        self.v["zoom_series"].set(", ".join(f"{z / M_PER_MI:g}" for z in zs))
        self._append(f"✓ Loaded preset '{self.preset_var.get()}'")

    # ----------------------------------------------------------- terrain
    def _prefetch_terrain(self) -> None:
        s = self._collect()
        job = self._build_job({**s, "themes": s["themes"] or ["terracotta"]})
        if job is None:
            return
        from . import geocode, terrain
        from .sources import bbox_for, view_half_extents

        def work(check):
            if job.latitude and job.longitude:
                lat = geocode.parse_coordinate(job.latitude)
                lon = geocode.parse_coordinate(job.longitude)
            else:
                lat, lon = geocode.get_coordinates(job.city, job.country)
            w, so, e, n = bbox_for(lat, lon, *view_half_extents(job.distance_m, job.width,
                                                                job.height), margin=1.2)
            terrain.prefetch(w, so, e, n, check_cancel=check)

        self._start(work, "Saving terrain for offline use…")

    # --------------------------------------------------------- dark mode
    def _apply_theme_mode(self) -> None:
        dark = self.dark_var.get()
        try:
            import sv_ttk
            sv_ttk.set_theme("dark" if dark else "light")
        except Exception:
            style = ttk.Style(self)
            style.theme_use("clam")
        self._polish_fonts()
        bg = "#1c1c1c" if dark else "#fafafa"
        fg = "#e6e6e6" if dark else "#1c1c1c"
        for w in (self.log, self.markers_txt, self.set_txt, self.theme_list, self.gpx_list):
            try:
                w.configure(bg=bg, fg=fg, insertbackground=fg,
                            selectbackground="#2f6fbf" if dark else "#cfe1ff")
            except tk.TclError:
                pass
        self.preview.set_colors("#232323" if dark else "#ececec", fg)
        pbg = ttk.Style(self).lookup("TFrame", "background") or bg
        self.swatch.configure(bg=pbg)
        self.gal_canvas.configure(bg=pbg)
        self.gal_inner.configure(bg=pbg)
        self._mark_tiles()

    def _place_divider(self) -> None:
        try:
            h = self.pane.winfo_height()
            if h > 200:
                self.pane.sashpos(0, int(h * 0.84))
        except tk.TclError:
            pass

    def _polish_fonts(self) -> None:
        """Slightly larger text and bold section titles; Windows only (Segoe UI)."""
        if not sys.platform.startswith("win"):
            return
        import tkinter.font as tkfont
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
            try:
                tkfont.nametofont(name).configure(family="Segoe UI", size=10)
            except tk.TclError:
                pass
        st = ttk.Style(self)
        st.configure("TLabelframe.Label", font=("Segoe UI", 10, "bold"))
        st.configure("TNotebook.Tab", padding=(14, 6))

    # ----------------------------------------------------------- preview
    def _refresh_preview(self) -> None:
        p = self.last_output
        if not p or p.suffix.lower() != ".png" or not p.exists():
            return
        try:
            self.preview.set_image(p)
        except Exception as e:  # preview is a nicety, never fatal
            self.preview.set_text(f"(preview unavailable: {e})")

    # ------------------------------------------------- undo / redo / live preview
    def _wire_changes(self) -> None:
        for v in list(self.v.values()) + list(self.layer_vars.values()):
            v.trace_add("write", lambda *a: self._changed())
        for t in (self.markers_txt, self.set_txt):
            t.bind("<KeyRelease>", lambda e: self._changed(), add="+")

    def _changed(self) -> None:
        if not self._ready or self._restoring:
            return
        if self._settle_id:
            self.after_cancel(self._settle_id)
        self._settle_id = self.after(900, self._settled)

    def _snapshot(self) -> dict:
        snap = self._collect()
        for k in ("geometry", "tab", "dark", "live_preview"):
            snap.pop(k, None)
        return snap

    def _push_snapshot(self) -> None:
        snap = self._snapshot()
        if not self.undo or snap != self.undo[-1]:
            self.undo.append(snap)
            self.redo.clear()
            del self.undo[:-40]

    def _settled(self) -> None:
        self._settle_id = None
        self._push_snapshot()
        self._update_undo_buttons()
        if self.live_var.get():
            self._live_preview()

    def _flush(self) -> None:
        if self._settle_id:
            self.after_cancel(self._settle_id)
            self._settle_id = None
            self._push_snapshot()

    def _update_undo_buttons(self) -> None:
        self.undo_btn.configure(state="normal" if len(self.undo) > 1 else "disabled")
        self.redo_btn.configure(state="normal" if self.redo else "disabled")

    def _undo(self) -> None:
        self._flush()
        if len(self.undo) < 2:
            return
        self.redo.append(self.undo.pop())
        self._restore(self.undo[-1])

    def _redo(self) -> None:
        if not self.redo:
            return
        snap = self.redo.pop()
        self.undo.append(snap)
        self._restore(snap)

    def _restore(self, snap: dict) -> None:
        self._restoring = True
        try:
            for k, val in snap.items():
                if k in self.v:
                    try:
                        self.v[k].set(val)
                    except tk.TclError:
                        pass
            for n, var in self.layer_vars.items():
                var.set(n in (snap.get("layers") or []))
            want = set(snap.get("themes") or [])
            self.theme_list.selection_clear(0, "end")
            for i in range(self.theme_list.size()):
                if self.theme_list.get(i) in want:
                    self.theme_list.selection_set(i)
            for widget, key in ((self.markers_txt, "markers"), (self.set_txt, "set_places")):
                widget.delete("1.0", "end")
                widget.insert("1.0", snap.get(key, ""))
            self.gpx_list.delete(0, "end")
            for g in snap.get("gpx") or []:
                self.gpx_list.insert("end", g)
            self._show_swatch()
        finally:
            self._restoring = False
        self._update_undo_buttons()
        if self.live_var.get():
            self._live_preview()

    def _live_toggled(self) -> None:
        if self.live_var.get():
            self._live_preview()

    def _live_preview(self) -> None:
        """Quick preview without popups; skips quietly while the settings are incomplete."""
        if self.worker and self.worker.is_alive():
            self._live_again = True
            return
        self._quiet = True
        self._live_run = True
        try:
            self._generate(True)
        finally:
            self._quiet = False
        if not (self.worker and self.worker.is_alive()):
            self._live_run = False  # nothing started (settings incomplete)

    def _after_run(self) -> None:
        if self._live_again and self.live_var.get():
            self._live_again = False
            self.after(200, self._live_preview)
        else:
            self._live_again = False

    # ------------------------------------------------------ shortcuts & tips
    def _bind_shortcuts(self) -> None:
        def key(seq, fn):
            def handler(e):
                fn()
                return "break"
            self.bind_all(seq, handler)
            # Tk's text boxes use some of these keys themselves (Ctrl+D deletes a letter,
            # Ctrl+O opens a line...); take them over there too.
            for cls in ("TEntry", "Entry", "TCombobox", "TSpinbox", "Text"):
                self.bind_class(cls, seq, handler)

        key("<Control-g>", self._generate)
        key("<Control-p>", lambda: self._generate(True))
        key("<Control-s>", self._save_preset)
        key("<Control-o>", lambda: open_path(self._out_dir()))
        key("<Control-z>", self._undo)
        key("<Control-y>", self._redo)
        key("<Control-Z>", self._redo)
        key("<Control-d>", self._toggle_dark)
        key("<Control-f>", self._focus_search)
        key("<F1>", self._show_shortcuts)
        key("<Escape>", lambda: self._cancel() if self.worker and self.worker.is_alive() else None)
        for i in range(6):
            key(f"<Control-Key-{i + 1}>", lambda i=i: self.nb.select(i))

    def _toggle_dark(self) -> None:
        self.dark_var.set(not self.dark_var.get())
        self._apply_theme_mode()

    def _focus_search(self) -> None:
        self.nb.select(1)
        self.search_entry.focus_set()
        self.search_entry.selection_range(0, "end")

    def _show_shortcuts(self) -> None:
        messagebox.showinfo("Keyboard shortcuts", "\n".join(f"{k:<18}{d}" for k, d in SHORTCUTS))

    def _attach_tips(self) -> None:
        by_var = {str(v): k for k, v in self.v.items()}
        by_layer = {str(v): n for n, v in self.layer_vars.items()}

        def walk(w) -> None:
            for c in w.winfo_children():
                text = None
                try:
                    name = str(c.cget("textvariable"))
                    text = TIPS.get(by_var.get(name, ""))
                except tk.TclError:
                    pass
                if text is None:
                    try:
                        name = str(c.cget("variable"))
                        if name in by_var:
                            text = TIPS.get(by_var[name])
                        elif name in by_layer:
                            lbl = LAYER_LABELS.get(by_layer[name], by_layer[name])
                            text = f"Draw {lbl.lower()} on the map."
                    except tk.TclError:
                        pass
                if text is None:
                    try:
                        text = BUTTON_TIPS.get(str(c.cget("text")))
                    except tk.TclError:
                        pass
                if text and c.winfo_class() not in ("TFrame", "TLabelframe", "Frame"):
                    Tooltip(c, text)
                walk(c)

        walk(self)

    # ------------------------------------------------------ recent posters
    def _scan_recent(self) -> None:
        d = self._out_dir()

        def work():
            try:
                from PIL import Image
                files = sorted((p for p in d.glob("*.png") if p.is_file()),
                               key=lambda p: p.stat().st_mtime, reverse=True)[:8]
                tdir = paths.CACHE_DIR / "thumbs"
                tdir.mkdir(parents=True, exist_ok=True)
                out = []
                for p in files:
                    tp = tdir / f"{p.stem}_{int(p.stat().st_mtime)}.png"
                    if not tp.exists():
                        with Image.open(p) as im:
                            im.thumbnail((120, 160))
                            im.convert("RGB").save(tp)
                    out.append((p, tp))
                self.q.put(("recent", out))
            except Exception:
                pass  # the strip is a nicety

        threading.Thread(target=work, daemon=True).start()

    def _show_recent(self, items) -> None:
        for w in self.recent_row.winfo_children():
            w.destroy()
        self.recent_imgs = []
        if not items:
            ttk.Label(self.recent_row, text="Posters you make will show up here.",
                      foreground="gray").pack(anchor="w")
            return
        from PIL import ImageTk, Image
        for p, tp in items:
            try:
                with Image.open(tp) as im:
                    img = ImageTk.PhotoImage(im.copy())
            except Exception:
                continue
            self.recent_imgs.append(img)
            f = ttk.Frame(self.recent_row)
            f.pack(side="left", padx=(0, 10))
            lb = tk.Label(f, image=img, cursor="hand2", borderwidth=1, relief="solid")
            lb.pack()
            cap = p.stem if len(p.stem) <= 16 else p.stem[:15] + "…"
            ttk.Label(f, text=cap, foreground="gray",
                      font=("Segoe UI", 8) if sys.platform.startswith("win") else None).pack()
            for w in (lb, f):
                w.bind("<Button-1>", lambda e, q=p: self._open_recent(q))

    def _open_recent(self, p: Path) -> None:
        self.last_output = p
        self._refresh_preview()

    # -------------------------------------------------------------- loop
    def _tick(self) -> None:
        if self.worker and self.worker.is_alive():
            secs = int(time.time() - self._t0)
            step = f" · {self._step}" if self._step else ""
            self.status.configure(text=f"{self._run_label}{step} · {secs // 60}:{secs % 60:02d} elapsed")
            self.after(1000, self._tick)

    def _append(self, text: str) -> None:
        m = re.match(r"\s*(?:=+ )?\[(\d+)/(\d+)\]", text)
        if m and self.worker and self.worker.is_alive():
            i, n = int(m.group(1)), int(m.group(2))
            self._step = f"{i} of {n}"
            self.progress.stop()
            self.progress.configure(mode="determinate", maximum=max(n, 1), value=i - 1)
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _finish(self) -> None:
        self.progress.stop()
        self.progress.pack_forget()
        for b in (self.go_btn, self.prev_btn, self.batch_btn):
            b.configure(state="normal")
        self.cancel_btn.configure(state="disabled")

    def _poll(self) -> None:
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "log":
                    self._append(val)
                elif kind == "poster":
                    self.last_output = Path(val)
                    if self.last_output.suffix.lower() == ".png":
                        self._refresh_preview()
                    else:
                        self.preview.set_text(f"Saved {self.last_output.name}\n"
                                              "(double-click to open)")
                elif kind == "pbf":
                    self.v["pbf"].set(str(val))
                    self.v["source"].set("pbf")
                elif kind == "recent":
                    self._show_recent(val)
                elif kind == "done":
                    self._finish()
                    secs = int(time.time() - self._t0)
                    self.status.configure(text=f"Done in {secs // 60}:{secs % 60:02d}")
                    if not self._live_run:
                        self._scan_recent()
                    self._live_run = False
                    self._after_run()
                elif kind == "error":
                    self._finish()
                    self._append(f"\n✗ Error: {val}")
                    self.status.configure(text="Error – see log")
                    if not self._live_run:
                        messagebox.showerror("Error", val)
                    self._live_run = False
                    self._after_run()
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _on_close(self) -> None:
        self._save_settings()
        self.cancel_evt.set()
        self.destroy()


# ===================================================================== editor

class ThemeEditor(tk.Toplevel):
    """Color pickers for every theme key with an instant sample-town preview."""

    LABELS = {
        "bg": "Background", "text": "Text", "gradient_color": "Fade",
        "water": "Lakes & rivers", "ocean": "Ocean", "waterway": "Canals & streams",
        "parks": "Parks", "buildings": "Buildings", "airports": "Airports",
        "railway": "Railways", "road_motorway": "Motorways", "road_primary": "Primary roads",
        "road_secondary": "Secondary roads", "road_tertiary": "Tertiary roads",
        "road_residential": "Residential", "road_default": "Paths & other",
        "marker": "Markers", "route": "Routes", "border": "Border",
    }

    def __init__(self, app: App, key: str) -> None:
        super().__init__(app)
        self.app = app
        self.title("Theme editor")
        self.geometry("1040x700")
        self.transient(app)
        self.theme = themes.load_theme(key)
        self.key = key
        self._img = None
        self._pending = None
        self._sample = None

        left = ttk.Frame(self, padding=8)
        left.pack(side="left", fill="y")
        self.name_var = tk.StringVar(value=self.theme.get("name", key))
        self.desc_var = tk.StringVar(value=self.theme.get("description", ""))
        self.file_var = tk.StringVar(value=key)
        for r, (lbl, var) in enumerate((("Name", self.name_var), ("Description", self.desc_var),
                                        ("File name", self.file_var))):
            ttk.Label(left, text=lbl).grid(row=r, column=0, sticky="w")
            ttk.Entry(left, textvariable=var, width=40).grid(row=r, column=1, columnspan=2,
                                                             sticky="ew", pady=1)

        self.buttons = {}
        grid = ttk.Frame(left)
        grid.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        keys = list(themes.EDITABLE_KEYS)
        half = (len(keys) + 1) // 2
        for i, k in enumerate(keys):
            r, c = i % half, (i // half) * 3
            ttk.Label(grid, text=self.LABELS.get(k, k)).grid(row=r, column=c, sticky="w",
                                                             padx=(0 if c == 0 else 10, 4))
            b = tk.Button(grid, width=3, relief="groove", command=lambda k=k: self._pick(k))
            b.grid(row=r, column=c + 1, sticky="w", pady=1)
            hexl = ttk.Label(grid, text="", width=8, foreground="gray")
            hexl.grid(row=r, column=c + 2, sticky="w")
            self.buttons[k] = (b, hexl)
        bb = ttk.Frame(left)
        bb.grid(row=99, column=0, columnspan=3, pady=8, sticky="ew")
        ttk.Button(bb, text="Save", command=self._save).pack(side="left", fill="x", expand=True)
        ttk.Button(bb, text="Close", command=self.destroy).pack(side="left", padx=4)
        ttk.Label(left, text="Saving under a new file name\ncreates a new theme.",
                  foreground="gray").grid(row=100, column=0, columnspan=3, sticky="w")

        self.preview = tk.Label(self, text="Rendering preview…", anchor="center")
        self.preview.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        self._refresh_buttons()
        self.after(50, self._render)

    def _refresh_buttons(self) -> None:
        for k, (b, hexl) in self.buttons.items():
            c = self.theme.get(k, "#000000")
            b.configure(bg=c, activebackground=c)
            hexl.configure(text=c)

    def _pick(self, k: str) -> None:
        def live(hexc: str) -> None:
            self.theme[k] = hexc
            self._refresh_buttons()
            if self._pending:
                self.after_cancel(self._pending)
            self._pending = self.after(250, self._render)

        dlg = ColorPicker(self, self.theme.get(k, "#000000"), self.LABELS.get(k, k), on_change=live)
        self.wait_window(dlg)

    def _render(self) -> None:
        self._pending = None
        try:
            from .extras import sample_data
            from .fonts import roboto
            from .geometry import Marker
            from .render import PosterOptions, render_poster
            if self._sample is None:
                self._sample = sample_data()
            out = paths.CACHE_DIR / "preview" / "theme_editor.png"
            t = dict(self.theme)
            t["name"] = self.name_var.get()
            opts = PosterOptions("Sample", "Town", 0, 0, 1000, fonts=roboto(), dpi=45,
                                 markers=[Marker(0.0012, -0.0021, "Home", "pin")])
            from . import log as logmod
            old = logmod._sink
            logmod.set_sink(lambda m: None)
            try:
                render_poster(self._sample, t, opts, out)
            finally:
                logmod.set_sink(old)
            self._img = _pil_thumb(out, 480, 660)
            self.preview.configure(image=self._img, text="")
        except Exception as e:
            self.preview.configure(text=f"Preview failed: {e}", image="")

    def _save(self) -> None:
        import re
        key = re.sub(r"[^\w-]+", "_", self.file_var.get().strip().lower()).strip("_")
        if not key:
            messagebox.showwarning("File name", "Enter a file name.", parent=self)
            return
        if themes.theme_path(key).exists() and key != self.key:
            if not messagebox.askyesno("Overwrite?", f"Theme '{key}' exists. Replace it?",
                                       parent=self):
                return
        self.theme["name"] = self.name_var.get().strip() or key
        self.theme["description"] = self.desc_var.get().strip()
        themes.save_theme(key, self.theme)
        self.key = key
        self.app._load_themes(select=key)
        self.app._append(f"✓ Saved theme {themes.theme_path(key)}")


# ================================================================ map picker

TILE_SERVERS = {
    "OpenStreetMap": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    "CARTO light": "https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png",
    "CARTO dark": "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
}
TILE_UA = "MapPosterStudio/1.0 (desktop map poster app)"


def _patch_tile_requests() -> None:
    """tkintermapview sends a generic User-Agent that OSM's tile servers block.
    Send an identifying one instead (OSM tile usage policy)."""
    import requests
    import tkintermapview.map_widget as mw

    if getattr(mw, "_mps_patched", False):
        return

    class _Requests:
        def __getattr__(self, name):
            return getattr(requests, name)

        @staticmethod
        def get(url, **kw):
            headers = dict(kw.pop("headers", None) or {})
            headers["User-Agent"] = TILE_UA
            kw.setdefault("timeout", 20)
            return requests.get(url, headers=headers, **kw)

    mw.requests = _Requests()
    mw._mps_patched = True


class MapPicker(tk.Toplevel):
    """Click to set the poster center; right-click to drop a marker."""

    def __init__(self, app: App) -> None:
        import tkintermapview
        _patch_tile_requests()
        super().__init__(app)
        self.app = app
        self.title("Pick the center – left-click: center · right-click: add marker")
        self.geometry("980x720")
        self.transient(app)

        top = ttk.Frame(self, padding=6)
        top.pack(fill="x")
        self.search = tk.StringVar(value=f"{app.v['city'].get()}, {app.v['country'].get()}")
        e = ttk.Entry(top, textvariable=self.search, width=40)
        e.pack(side="left")
        e.bind("<Return>", lambda ev: self._go())
        ttk.Button(top, text="Search", command=self._go).pack(side="left", padx=4)
        self.style_var = tk.StringVar(value="OpenStreetMap")
        cb = ttk.Combobox(top, textvariable=self.style_var, values=list(TILE_SERVERS),
                          state="readonly", width=14)
        cb.pack(side="left", padx=4)
        ttk.Button(top, text="Use this center", command=self._use).pack(side="right")
        self.info = ttk.Label(top, text="")
        self.info.pack(side="left", padx=10)
        cb.bind("<<ComboboxSelected>>",
                lambda e: self.map.set_tile_server(TILE_SERVERS[self.style_var.get()]))

        self.map = tkintermapview.TkinterMapView(self, corner_radius=0)
        self.map.set_tile_server(TILE_SERVERS["OpenStreetMap"])
        self.map.pack(fill="both", expand=True)
        self.map.add_left_click_map_command(self._clicked)
        self.map.add_right_click_menu_command("Add marker here…", self._add_marker,
                                              pass_coords=True)
        self.center = None
        self.center_marker = None
        self.extent = None

        lat, lon = app.v["lat"].get().strip(), app.v["lon"].get().strip()
        try:
            from .geocode import parse_coordinate
            self._set_center(parse_coordinate(lat), parse_coordinate(lon), zoom=True)
        except Exception:
            self.after(200, self._go)

    def _go(self) -> None:
        try:
            ok = self.map.set_address(self.search.get())
            if ok:
                self.map.set_zoom(11)
        except Exception as e:
            self.info.configure(text=f"Search failed: {e}")

    def _clicked(self, coords) -> None:
        self._set_center(*coords)

    def _set_center(self, lat, lon, zoom=False) -> None:
        from .sources import M_PER_DEG, view_half_extents
        import math
        self.center = (lat, lon)
        if self.center_marker:
            self.center_marker.delete()
        self.center_marker = self.map.set_marker(lat, lon, text="center")
        if self.extent:
            self.extent.delete()
        try:
            r = float(self.app.v["distance_mi"].get()) * M_PER_MI
            w, h = float(self.app.v["width"].get()), float(self.app.v["height"].get())
            hx, hy = view_half_extents(r, w, h)
            dlat = hy / M_PER_DEG
            dlon = hx / (M_PER_DEG * math.cos(math.radians(lat)))
            self.extent = self.map.set_polygon(
                [(lat + dlat, lon - dlon), (lat + dlat, lon + dlon),
                 (lat - dlat, lon + dlon), (lat - dlat, lon - dlon)],
                outline_color="#d9480f", fill_color=None, border_width=2)
        except ValueError:
            pass
        self.info.configure(text=f"{lat:.5f}, {lon:.5f}  (orange box = poster area)")
        if zoom:
            self.map.set_position(lat, lon)
            self.map.set_zoom(11)

    def _add_marker(self, coords) -> None:
        lat, lon = coords
        label = simpledialog.askstring("Marker", "Label (optional):", parent=self) or ""
        icon = simpledialog.askstring("Marker", "Icon: pin, heart, star or dot", parent=self,
                                      initialvalue="pin") or "pin"
        icon = icon.strip().lower() if icon.strip().lower() in ("pin", "heart", "star",
                                                                 "dot") else "pin"
        self.app.add_marker_line(lat, lon, label.strip(), icon)
        self.map.set_marker(lat, lon, text=label or icon)

    def _use(self) -> None:
        if self.center:
            self.app.v["lat"].set(f"{self.center[0]:.6f}")
            self.app.v["lon"].set(f"{self.center[1]:.6f}")
        self.destroy()


def main() -> None:
    App().mainloop()
