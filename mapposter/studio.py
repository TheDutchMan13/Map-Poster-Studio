"""The "Studio" look: an amber version of the Sun Valley ttk theme, the colour
palette for the parts drawn by hand, the icons on the left rail, and a few
small widgets (rail button, scrolling panel)."""

from __future__ import annotations

import colorsys
import re
import shutil
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from . import paths

_WIN = sys.platform.startswith("win")
RECOLOR_VERSION = "2"

# Hand-drawn parts of the window. "panel" matches the ttk theme background.
PALETTES = {
    "dark": {
        "rail": "#0e0f11", "stage": "#0b0c0e", "panel": "#1c1c1c", "line": "#2c2e34",
        "text": "#eceef2", "muted": "#a3a8b2", "accent": "#f2b84b", "on_accent": "#17130a",
        "accent_line": "#f2b84b", "hover": "#24262b", "active": "#2b2d33",
        "placeholder": "#34363d", "field": "#292929",
    },
    "light": {
        "rail": "#eceef1", "stage": "#dfe2e7", "panel": "#fafafa", "line": "#d6d9df",
        "text": "#1d1f23", "muted": "#555b65", "accent": "#a86c06", "on_accent": "#ffffff",
        "accent_line": "#b5770c", "hover": "#e0e3e8", "active": "#d5d9df",
        "placeholder": "#b9bec7", "field": "#fdfdfd",
    },
}


def font(size: int, bold: bool = False):
    if _WIN:
        return ("Segoe UI Semibold" if bold else "Segoe UI", size)
    return ("DejaVu Sans", size - 1, "bold") if bold else ("DejaVu Sans", size - 1)


# ------------------------------------------------------------ amber theme
def _amber(r: int, g: int, b: int, light: bool) -> tuple[int, int, int] | None:
    """Blue accent colour -> amber, or None when the colour is not an accent blue."""
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    if not (0.48 < h < 0.68 and s > 0.35 and 0.12 < l < 0.95):
        return None
    l2 = l * 0.80 if light else l
    rr, gg, bb = colorsys.hls_to_rgb(40 / 360, l2, min(1.0, s * 0.95))
    return round(rr * 255), round(gg * 255), round(bb * 255)


def _recolor_png(src: Path, dst: Path, light: bool) -> None:
    from PIL import Image
    with Image.open(src) as im:
        im = im.convert("RGBA")
        px = im.load()
        cache: dict = {}
        for y in range(im.height):
            for x in range(im.width):
                r, g, b, a = px[x, y]
                if a == 0:
                    continue
                key = (r, g, b)
                if key not in cache:
                    cache[key] = _amber(r, g, b, light)
                new = cache[key]
                if new:
                    px[x, y] = (*new, a)
        im.save(dst)


def _recolor_tcl(text: str, light: bool) -> str:
    def sub(m):
        c = m.group(1)
        new = _amber(int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), light)
        return m.group(0) if new is None else "#%02x%02x%02x" % new
    return re.sub(r"#([0-9a-fA-F]{6})\b", sub, text)


def build_theme() -> Path | None:
    """Make (once) an amber copy of the Sun Valley theme in the cache folder and
    return its sv.tcl, or None if sv_ttk is not installed."""
    try:
        import sv_ttk
    except ImportError:
        return None
    src = Path(sv_ttk.__file__).parent
    dst = paths.CACHE_DIR / "studio_theme"
    stamp = dst / "stamp.txt"
    want = f"{RECOLOR_VERSION}|{(src / 'theme' / 'dark.tcl').stat().st_size}"
    if stamp.exists() and stamp.read_text(encoding="utf-8") == want:
        return dst / "sv.tcl"
    shutil.rmtree(dst, ignore_errors=True)
    (dst / "theme").mkdir(parents=True, exist_ok=True)
    shutil.copy2(src / "sv.tcl", dst / "sv.tcl")
    for f in (src / "theme").iterdir():
        light = "light" in f.name
        if f.suffix == ".png":
            _recolor_png(f, dst / "theme" / f.name, light)
        elif f.name in ("dark.tcl", "light.tcl"):
            (dst / "theme" / f.name).write_text(
                _recolor_tcl(f.read_text(encoding="utf-8"), light), encoding="utf-8")
        else:
            shutil.copy2(f, dst / "theme" / f.name)
    stamp.write_text(want, encoding="utf-8")
    return dst / "sv.tcl"


def use_theme(root: tk.Tk, dark: bool) -> dict:
    """Switch the ttk theme and the extra Studio styles; returns the palette."""
    pal = PALETTES["dark" if dark else "light"]
    style = ttk.Style(root)
    if not getattr(root, "_studio_loaded", None):
        tcl = None
        try:
            tcl = build_theme()
        except Exception:  # recolouring is cosmetic; fall back to stock colours
            tcl = None
        try:
            if tcl:
                root.tk.call("source", str(tcl))
            else:
                import sv_ttk
                sv_ttk._load_theme(style)  # noqa: SLF001
            root._studio_loaded = "sv"
        except Exception:
            root._studio_loaded = "clam"
    if root._studio_loaded == "sv":
        style.theme_use("sun-valley-dark" if dark else "sun-valley-light")
    else:
        style.theme_use("clam")

    style.configure("Muted.TLabel", foreground=pal["muted"])
    style.configure("Title.TLabel", font=font(15, True))
    style.configure("Sub.TLabel", foreground=pal["muted"])
    style.configure("Group.TLabel", foreground=pal["muted"], font=font(8, True))
    style.configure("Head.TLabel", font=font(12, True))
    style.configure("Meta.TLabel", foreground=pal["muted"])
    style.configure("Stage.TFrame", background=pal["stage"])
    style.configure("Rail.TFrame", background=pal["rail"])
    return pal


# ----------------------------------------------------------------- icons
def draw_icon(c: tk.Canvas, kind: str, cx: float, cy: float, col: str, tag: str = "icon") -> None:
    """Simple line icons on a 24 px grid centred on (cx, cy)."""
    def P(x, y):
        return cx + (x - 12), cy + (y - 12)

    def line(*pts, w=1.8, **kw):
        flat = [v for p in pts for v in P(*p)]
        c.create_line(*flat, fill=col, width=w, capstyle="round", joinstyle="round", tags=tag, **kw)

    def oval(x0, y0, x1, y1, fill="", w=1.8):
        c.create_oval(*P(x0, y0), *P(x1, y1), outline=col, width=w, fill=fill, tags=tag)

    if kind == "place":
        line((12, 21), (6.6, 13.6), (5.6, 10), (6.6, 6.6), (9, 4.2), (12, 3.4), (15, 4.2),
             (17.4, 6.6), (18.4, 10), (17.4, 13.6), (12, 21), smooth=True)
        oval(9.5, 7.5, 14.5, 12.5)
    elif kind == "style":
        line((12, 3.5), (5.5, 6), (3.5, 12), (5.5, 18), (12, 20.5), (14.5, 19), (13.5, 16.5),
             (15, 15), (18, 15.5), (20.5, 12.5), (19, 7), (12, 3.5), smooth=True)
        for x, y in ((8, 10), (11.5, 7.5), (15.5, 9)):
            oval(x - 1.3, y - 1.3, x + 1.3, y + 1.3, fill=col, w=1)
    elif kind == "details":
        line((2.5, 19.5), (9, 8), (13, 14), (15.5, 10.5), (21.5, 19.5), (2.5, 19.5))
        line((7.5, 10.5), (9, 12), (10.5, 10.5), w=1.4)
    elif kind == "text":
        line((5, 5.5), (19, 5.5))
        line((12, 5.5), (12, 19.5))
        line((9, 19.5), (15, 19.5))
    elif kind == "overlays":
        line((12, 3.5), (21, 8.5), (12, 13.5), (3, 8.5), (12, 3.5))
        line((3, 12.5), (12, 17.5), (21, 12.5))
        line((3, 16.5), (12, 21.5), (21, 16.5))
    elif kind == "output":
        line((12, 15), (12, 3.5))
        line((7.5, 8), (12, 3.5), (16.5, 8))
        line((5, 13), (5, 20), (19, 20), (19, 13))
    elif kind == "moon":
        line((19, 14.5), (16, 16.5), (12.5, 17), (9, 15.5), (6.8, 12.5), (6.5, 9), (8, 5.8),
             (10.5, 4), (9.8, 7.5), (10.5, 11), (13, 13.5), (16, 14.8), (19, 14.5), smooth=True)
    elif kind == "sun":
        oval(8, 8, 16, 16)
        for a, b in (((12, 2.5), (12, 5)), ((12, 19), (12, 21.5)), ((2.5, 12), (5, 12)),
                     ((19, 12), (21.5, 12)), ((5.3, 5.3), (7, 7)), ((17, 17), (18.7, 18.7)),
                     ((5.3, 18.7), (7, 17)), ((17, 7), (18.7, 5.3))):
            line(a, b)
    elif kind == "keys":
        c.create_rectangle(*P(3, 6), *P(21, 18), outline=col, width=1.8, tags=tag)
        for x in (7, 10.5, 14, 17.5):
            oval(x - .7, 9.3, x + .7, 10.7, fill=col, w=1)
        line((8, 14.5), (16, 14.5))
    elif kind == "folder":
        line((3, 7), (3, 19), (21, 19), (21, 8.5), (11.5, 8.5), (9.5, 5.5), (3, 5.5), (3, 7))
    elif kind == "logo":
        # map pin over a little street grid
        line((5, 9), (19, 9), w=1.4)
        line((5, 15), (19, 15), w=1.4)
        line((9, 5), (9, 19), w=1.4)
        line((15, 5), (15, 19), w=1.4)


class RailButton(tk.Canvas):
    """A square button on the left rail: icon with a small caption, keyboard
    focusable, highlighted when it is the active section."""

    def __init__(self, parent, kind: str, label: str, command, pal: dict,
                 w: int = 68, h: int = 60) -> None:
        super().__init__(parent, width=w, height=h, highlightthickness=0, borderwidth=0,
                         cursor="hand2", takefocus=1)
        self.kind, self.label, self.command, self.pal = kind, label, command, pal
        self.w, self.h = w, h
        self.active = False
        self._hover = False
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<Button-1>", lambda e: self.command())
        self.bind("<Return>", lambda e: self.command())
        self.bind("<space>", lambda e: self.command())
        self.bind("<FocusIn>", lambda e: self.draw())
        self.bind("<FocusOut>", lambda e: self.draw())
        self.draw()

    def _set_hover(self, v: bool) -> None:
        self._hover = v
        self.draw()

    def set_active(self, v: bool) -> None:
        self.active = v
        self.draw()

    def set_palette(self, pal: dict) -> None:
        self.pal = pal
        self.draw()

    def set_kind(self, kind: str) -> None:
        self.kind = kind
        self.draw()

    def draw(self) -> None:
        p = self.pal
        self.configure(bg=p["rail"])
        self.delete("all")
        if self.active or self._hover:
            self._round(3, 2, self.w - 3, self.h - 2, 9,
                        p["active"] if self.active else p["hover"])
        if self.active:
            self.create_rectangle(0, 14, 3, self.h - 14, fill=p["accent_line"], outline="")
        try:
            focused = self.focus_get() is self
        except (KeyError, tk.TclError):
            focused = False
        if focused:
            self._round(3, 2, self.w - 3, self.h - 2, 9, "", outline=p["accent_line"])
        col = p["accent_line"] if self.active else (p["text"] if self._hover else p["muted"])
        has_label = bool(self.label)
        draw_icon(self, self.kind, self.w / 2, self.h / 2 - (8 if has_label else 0), col)
        if has_label:
            self.create_text(self.w / 2, self.h - 13, text=self.label, font=font(8),
                             fill=p["text"] if (self.active or self._hover) else p["muted"])

    def _round(self, x0, y0, x1, y1, r, fill, outline="") -> None:
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
               x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        self.create_polygon(pts, smooth=True, fill=fill, outline=outline,
                            width=1.5 if outline else 0)


class ScrollFrame(ttk.Frame):
    """A vertically scrolling area; put children in .inner. The scrollbar only
    shows when the content is taller than the space."""

    def __init__(self, parent, **kw) -> None:
        super().__init__(parent, **kw)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        self.sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self._sb_set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda e: self._update())
        self.canvas.bind("<Configure>", lambda e: (
            self.canvas.itemconfigure(self._win, width=e.width), self._update()))
        self.bind_all("<MouseWheel>", self._wheel, add="+")
        self.bind_all("<Button-4>", lambda e: self._wheel(e, -1), add="+")
        self.bind_all("<Button-5>", lambda e: self._wheel(e, 1), add="+")

    def _sb_set(self, a, b) -> None:
        if float(a) <= 0.0 and float(b) >= 1.0:
            self.sb.pack_forget()
        elif not self.sb.winfo_ismapped():
            self.sb.pack(side="right", fill="y", before=self.canvas)
        self.sb.set(a, b)

    def _update(self) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _inside(self, e) -> bool:
        try:
            w = self.winfo_containing(e.x_root, e.y_root)
        except (KeyError, tk.TclError):
            return False
        while w is not None:
            if w is self:
                return True
            if w.winfo_class() in ("TCombobox", "TSpinbox", "Text", "Listbox"):
                return False   # those scroll themselves
            w = w.master
        return False

    def _wheel(self, e, direction: int | None = None) -> None:
        if not self._inside(e):
            return
        if self.canvas.yview() == (0.0, 1.0):
            return
        step = direction if direction is not None else int(-e.delta / 120) or (-1 if e.delta > 0 else 1)
        self.canvas.yview_scroll(step * 2, "units")

    def to_top(self) -> None:
        self.canvas.yview_moveto(0)

    def set_bg(self, bg: str) -> None:
        self.canvas.configure(bg=bg)


class Placeholder:
    """Grey hint text shown inside an empty entry until it has focus."""

    _all: list = []

    def __init__(self, entry: ttk.Entry, var: tk.StringVar, text: str) -> None:
        self.entry, self.var = entry, var
        self.lbl = tk.Label(entry, text=text, anchor="w", borderwidth=0, padx=0, cursor="xterm")
        self.lbl.bind("<Button-1>", lambda e: entry.focus_set())
        entry.bind("<FocusIn>", lambda e: self.update(), add="+")
        entry.bind("<FocusOut>", lambda e: self.update(), add="+")
        var.trace_add("write", lambda *a: self.update())
        Placeholder._all.append(self)
        self.update()

    def set_palette(self, pal: dict) -> None:
        self.lbl.configure(bg=pal["field"], fg=pal["muted"], font=font(10))

    def update(self) -> None:
        try:
            focused = self.entry.focus_get() is self.entry
        except (KeyError, tk.TclError):
            focused = False
        if self.var.get() or focused:
            self.lbl.place_forget()
        else:
            self.lbl.place(x=11, rely=0.5, anchor="w")

    @classmethod
    def restyle(cls, pal: dict) -> None:
        for p in list(cls._all):
            try:
                p.set_palette(pal)
            except tk.TclError:
                cls._all.remove(p)
