"""The "Studio" look from the design mockup: a terracotta, paper-coloured
version of the Sun Valley ttk theme, serif type, the palette for the parts drawn
by hand, line icons, and the hand-drawn controls (rail items, pill buttons,
switches, scrolling panel)."""

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
RECOLOR_VERSION = "5"

# Two complete looks. Light: cream paper everywhere. Dark: charcoal everywhere.
# "field" must match the text-box fill of the ttk theme (hint text sits on it).
PALETTES = {
    "light": {
        # settings panel
        "panel": "#f4efe7", "card": "#fbf8f3", "text": "#33231e", "muted": "#74675f",
        "line": "#e0d6ca", "field": "#fdfdfd", "sel": "#ecd3c6",
        "accent": "#b85d3b", "accent_hover": "#a3502f", "on_accent": "#ffffff",
        "accent_line": "#b85d3b",
        # preview stage and its zoom bar
        "stage": "#d6d2cc", "placeholder": "#a59a91",
        "bar": "#fffdf9", "bar_fg": "#33231e", "bar_hov": "#efe7dc", "bar_line": "#e0d6ca",
        # frame: top bar, rail, bottom bar
        "rail": "#ebe4da", "c_text": "#33231e", "c_muted": "#74675f", "c_line": "#d5cbbf",
        "hover": "#dfd6cb", "c_outline": "#9c8f86",
    },
    "dark": {
        "panel": "#262427", "card": "#302e31", "text": "#f0eae2", "muted": "#ada59d",
        "line": "#403c3f", "field": "#292929", "sel": "#5c3b2d",
        "accent": "#b85d3b", "accent_hover": "#c96c48", "on_accent": "#ffffff",
        "accent_line": "#d4805e",
        "stage": "#353230", "placeholder": "#6f6862",
        "bar": "#2b292a", "bar_fg": "#f0eae2", "bar_hov": "#3b3839", "bar_line": "#48433f",
        "rail": "#1b1c1f", "c_text": "#f2ece4", "c_muted": "#a8a29b", "c_line": "#34363a",
        "hover": "#2c2e32", "c_outline": "#cfc8bf",
    },
}

SERIF = "Georgia" if _WIN else "DejaVu Serif"


def font(size: int, bold: bool = False):
    if _WIN:
        return ("Segoe UI Semibold" if bold else "Segoe UI", size)
    return ("DejaVu Sans", size - 1, "bold") if bold else ("DejaVu Sans", size - 1)


def serif(size: int, bold: bool = False):
    s = size if _WIN else size - 1
    return (SERIF, s, "bold") if bold else (SERIF, s)


# ------------------------------------------------------------ amber theme
def _amber(r: int, g: int, b: int, light: bool) -> tuple[int, int, int] | None:
    """Blue accent colour -> amber, or None when the colour is not an accent blue."""
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    if not (0.48 < h < 0.68 and s > 0.35 and 0.12 < l < 0.95):
        return None
    l2 = l * 0.80 if light else l
    rr, gg, bb = colorsys.hls_to_rgb(17 / 360, l2, min(1.0, s * 0.82))
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
    text = re.sub(r"#([0-9a-fA-F]{6})\b", sub, text)
    if light:   # paper-coloured panel instead of the stock near-white
        text = text.replace('"#fafafa"', '"%s"' % PALETTES["light"]["panel"])
    else:       # warm charcoal instead of the stock near-black
        text = text.replace('-bg      "#1c1c1c"', '-bg      "%s"' % PALETTES["dark"]["panel"])
    return text


def is_light(color: str) -> bool:
    """True when a #rrggbb colour is light enough to need dark text on it."""
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return (0.299 * r + 0.587 * g + 0.114 * b) > 150


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
    """Load the terracotta ttk theme in the light or dark variant and the Studio
    styles; returns the palette."""
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
        _serif_fonts(root)
    if root._studio_loaded == "sv":
        style.theme_use("sun-valley-dark" if dark else "sun-valley-light")
    else:
        style.theme_use("clam")

    style.configure(".", background=pal["panel"])
    style.configure("Muted.TLabel", foreground=pal["muted"])
    style.configure("Title.TLabel", font=serif(19), foreground=pal["text"])
    style.configure("Sub.TLabel", foreground=pal["muted"])
    style.configure("Group.TLabel", font=serif(12, True), foreground=pal["text"])
    style.configure("Stage.TFrame", background=pal["stage"])
    style.configure("Rail.TFrame", background=pal["rail"])
    return pal


def _serif_fonts(root: tk.Tk) -> None:
    """Use the serif face for the whole window, like the design."""
    import tkinter.font as tkfont
    size = -14 if _WIN else -13
    for name in ("SunValleyBodyFont", "SunValleyBodyStrongFont", "SunValleyCaptionFont"):
        try:
            root.tk.call("font", "configure", name, "-family", SERIF,
                         "-size", -12 if "Caption" in name else size)
        except tk.TclError:
            pass
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        try:
            tkfont.nametofont(name).configure(family=SERIF, size=10 if _WIN else 9)
        except tk.TclError:
            pass


# ----------------------------------------------------------------- icons
def draw_icon(c: tk.Canvas, kind: str, cx: float, cy: float, col: str, tag: str = "icon",
              s: float = 1.0) -> None:
    """Simple line icons on a 24 px grid centred on (cx, cy), scaled by s."""
    def P(x, y):
        return cx + (x - 12) * s, cy + (y - 12) * s

    def line(*pts, w=1.7, **kw):
        flat = [v for p in pts for v in P(*p)]
        c.create_line(*flat, fill=col, width=w * s, capstyle="round", joinstyle="round",
                      tags=tag, **kw)

    def oval(x0, y0, x1, y1, fill="", w=1.7):
        c.create_oval(*P(x0, y0), *P(x1, y1), outline=col, width=w * s, fill=fill, tags=tag)

    if kind in ("place", "pin"):
        line((12, 21), (6.6, 13.6), (5.6, 10), (6.6, 6.6), (9, 4.2), (12, 3.4), (15, 4.2),
             (17.4, 6.6), (18.4, 10), (17.4, 13.6), (12, 21), smooth=True)
        oval(9.5, 7.5, 14.5, 12.5)
    elif kind == "logo":
        pts = [P(x, y) for x, y in ((12, 22), (6.2, 14), (5, 10), (6.2, 6), (9, 3.3), (12, 2.4),
                                    (15, 3.3), (17.8, 6), (19, 10), (17.8, 14), (12, 22))]
        c.create_polygon(*[v for p in pts for v in p], smooth=True, fill=col, outline="",
                         tags=tag)
        c.create_oval(*P(9.3, 7.3), *P(14.7, 12.7), fill=c.cget("bg"), outline="", tags=tag)
    elif kind == "style":           # stacked layers
        line((12, 3.5), (21, 8.5), (12, 13.5), (3, 8.5), (12, 3.5))
        line((3, 12.5), (12, 17.5), (21, 12.5))
        line((3, 16.5), (12, 21.5), (21, 16.5))
    elif kind == "details":         # sliders
        line((3, 7), (21, 7))
        line((3, 17), (21, 17))
        oval(6, 4.5, 11, 9.5, fill=c.cget("bg"))
        oval(13, 14.5, 18, 19.5, fill=c.cget("bg"))
    elif kind == "text":
        line((5.5, 5.5), (18.5, 5.5))
        line((5.5, 5.5), (5.5, 7.5))
        line((18.5, 5.5), (18.5, 7.5))
        line((12, 5.5), (12, 19.5))
        line((9.5, 19.5), (14.5, 19.5))
    elif kind == "overlays":        # route between two markers
        oval(3.5, 15.5, 8.5, 20.5)
        oval(15.5, 3.5, 20.5, 8.5)
        line((8, 16), (11, 13), (13, 11), (16, 8), dash=(2, 2))
    elif kind == "size":            # crop marks
        line((7, 2.5), (7, 17), (21.5, 17))
        line((2.5, 7), (17, 7), (17, 21.5))
    elif kind in ("output", "download"):
        line((12, 3.5), (12, 15))
        line((7.5, 10.5), (12, 15), (16.5, 10.5))
        line((4.5, 15.5), (4.5, 20), (19.5, 20), (19.5, 15.5))
    elif kind == "moon":
        line((19, 14.5), (16, 16.5), (12.5, 17), (9, 15.5), (6.8, 12.5), (6.5, 9), (8, 5.8),
             (10.5, 4), (9.8, 7.5), (10.5, 11), (13, 13.5), (16, 14.8), (19, 14.5), smooth=True)
    elif kind == "sun":
        oval(8.5, 8.5, 15.5, 15.5)
        for a, b in (((12, 2.5), (12, 5)), ((12, 19), (12, 21.5)), ((2.5, 12), (5, 12)),
                     ((19, 12), (21.5, 12)), ((5.3, 5.3), (7, 7)), ((17, 17), (18.7, 18.7)),
                     ((5.3, 18.7), (7, 17)), ((17, 7), (18.7, 5.3))):
            line(a, b)
    elif kind == "keys":
        c.create_rectangle(*P(3, 6), *P(21, 18), outline=col, width=1.7 * s, tags=tag)
        for x in (7, 10.5, 14, 17.5):
            oval(x - .7, 9.3, x + .7, 10.7, fill=col, w=1)
        line((8, 14.5), (16, 14.5))
    elif kind == "folder":
        line((3, 7), (3, 19), (21, 19), (21, 8.5), (11.5, 8.5), (9.5, 5.5), (3, 5.5), (3, 7))
    elif kind == "undo":
        line((9, 5), (4.5, 9.5), (9, 14))
        line((4.5, 9.5), (14, 9.5), (17, 10.3), (19, 12.5), (19.5, 15), (19, 17.5), (17, 19.3),
             (14, 20), (10, 20), smooth=True)
    elif kind == "redo":
        line((15, 5), (19.5, 9.5), (15, 14))
        line((19.5, 9.5), (10, 9.5), (7, 10.3), (5, 12.5), (4.5, 15), (5, 17.5), (7, 19.3),
             (10, 20), (14, 20), smooth=True)
    elif kind == "page":
        line((5.5, 3), (14.5, 3), (18.5, 7), (18.5, 21), (5.5, 21), (5.5, 3))
        line((14.5, 3), (14.5, 7), (18.5, 7))
    elif kind == "eye":
        line((2.5, 12), (6, 7.8), (12, 5.5), (18, 7.8), (21.5, 12), (18, 16.2), (12, 18.5),
             (6, 16.2), (2.5, 12), smooth=True)
        oval(9, 9, 15, 15)
    elif kind == "plus":
        line((12, 5), (12, 19))
        line((5, 12), (19, 12))
    elif kind == "minus":
        line((5, 12), (19, 12))
    elif kind == "fit":
        for (x, y), (dx, dy) in (((4, 4), (1, 1)), ((20, 4), (-1, 1)), ((4, 20), (1, -1)),
                                 ((20, 20), (-1, -1))):
            line((x, y + 5 * dy), (x, y), (x + 5 * dx, y))
    elif kind == "open":
        line((13, 4), (20, 4), (20, 11))
        line((20, 4), (11, 13))
        line((17, 14), (17, 20), (4, 20), (4, 7), (10, 7))
    elif kind == "log":
        for y in (6, 10, 14, 18):
            line((4, y), (20 if y != 18 else 14, y))


def rounded(c: tk.Canvas, x0, y0, x1, y1, r, fill="", outline="", width=1.0, tags=""):
    """A rounded rectangle on a canvas (smoothed polygon)."""
    r = max(0.0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
           x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    return c.create_polygon(pts, smooth=True, fill=fill, outline=outline,
                            width=width if outline else 0, tags=tags)


class _Clickable(tk.Canvas):
    """Base for the hand-drawn controls: hover, focus, click, keyboard."""

    def __init__(self, parent, command, w: int, h: int, bg: str) -> None:
        super().__init__(parent, width=w, height=h, highlightthickness=0, borderwidth=0,
                         cursor="hand2", takefocus=1, bg=bg)
        self.command, self.w, self.h = command, w, h
        self._hover = False
        self._enabled = True
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<ButtonRelease-1>", lambda e: self._fire())
        self.bind("<Return>", lambda e: self._fire())
        self.bind("<space>", lambda e: self._fire())
        self.bind("<FocusIn>", lambda e: self.draw())
        self.bind("<FocusOut>", lambda e: self.draw())

    def _fire(self) -> None:
        if self._enabled and self.command:
            self.command()

    def _set_hover(self, v: bool) -> None:
        self._hover = v
        self.draw()

    def _focused(self) -> bool:
        try:
            return self.focus_get() is self
        except (KeyError, tk.TclError):
            return False

    # ttk-like API so the rest of the window can treat these as buttons
    def configure(self, cnf=None, **kw):  # noqa: D401
        changed = False
        for k in ("text", "command", "state", "style"):
            if k in kw:
                v = kw.pop(k)
                if k == "text":
                    self.text = v
                elif k == "command":
                    self.command = v
                elif k == "state":
                    self._enabled = str(v) != "disabled"
                    super().configure(cursor="hand2" if self._enabled else "arrow")
                elif k == "style":
                    self.kind_style = "accent" if "Accent" in str(v) else "outline"
                changed = True
        out = super().configure(cnf, **kw) if (cnf or kw) else None
        if changed:
            self.draw()
        return out

    config = configure

    def draw(self) -> None:  # pragma: no cover - overridden
        pass


class NavButton(_Clickable):
    """A wide item on the left rail: icon and label; the active one is a filled
    terracotta pill."""

    def __init__(self, parent, kind: str, label: str, command, pal: dict,
                 w: int = 150, h: int = 46) -> None:
        self.kind, self.label, self.pal, self.active = kind, label, pal, False
        super().__init__(parent, command, w, h, pal["rail"])
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
        tk.Canvas.configure(self, bg=p["rail"])
        self.delete("all")
        if self.active:
            rounded(self, 6, 3, self.w - 6, self.h - 3, 8, fill=p["accent"])
        elif self._hover:
            rounded(self, 6, 3, self.w - 6, self.h - 3, 8, fill=p["hover"])
        if self._focused():
            rounded(self, 6, 3, self.w - 6, self.h - 3, 8,
                    outline=p["c_text"] if self.active else p["accent"], width=1.5)
        col = p["on_accent"] if self.active else (p["c_text"] if self._hover else p["c_muted"])
        tcol = p["on_accent"] if self.active else p["c_text"]
        if self.label:
            draw_icon(self, self.kind, 30, self.h / 2, col, s=0.92)
            self.create_text(56, self.h / 2, text=self.label, anchor="w", fill=tcol,
                             font=serif(12))
        else:
            draw_icon(self, self.kind, self.w / 2, self.h / 2, col, s=0.9)


# kept for compatibility (older code/tests import it)
RailButton = NavButton


class IconButton(_Clickable):
    """A borderless icon button for the dark bars (undo, redo, ...)."""

    def __init__(self, parent, kind: str, command, pal: dict, size: int = 36,
                 key_bg: str = "rail", key_fg: str = "c_text", key_hover: str = "hover") -> None:
        self.kind, self.pal = kind, pal
        self.keys = (key_bg, key_fg, key_hover)
        super().__init__(parent, command, size, size, pal[key_bg])
        self.draw()

    def set_palette(self, pal: dict) -> None:
        self.pal = pal
        self.draw()

    def draw(self) -> None:
        bgk, fgk, hk = self.keys
        p = self.pal
        tk.Canvas.configure(self, bg=p[bgk])
        self.delete("all")
        if self._enabled and (self._hover or self._focused()):
            rounded(self, 2, 2, self.w - 2, self.h - 2, 7, fill=p[hk])
        col = p[fgk] if self._enabled else p.get("c_line" if bgk == "rail" else "line", "#888")
        if self.kind in ("1:1",):
            self.create_text(self.w / 2, self.h / 2, text="1:1", fill=col, font=serif(10, True))
        else:
            draw_icon(self, self.kind, self.w / 2, self.h / 2, col, s=self.w / 40)


class PillButton(_Clickable):
    """The big rounded buttons in the bottom bar: filled terracotta (accent) or
    outlined, with an icon on the left."""

    def __init__(self, parent, text: str, icon: str, command, pal: dict, accent: bool,
                 w: int = 196, h: int = 46) -> None:
        self.text, self.icon, self.pal = text, icon, pal
        self.kind_style = "accent" if accent else "outline"
        super().__init__(parent, command, w, h, pal["rail"])
        self.draw()

    def set_palette(self, pal: dict) -> None:
        self.pal = pal
        self.draw()

    def draw(self) -> None:
        p = self.pal
        tk.Canvas.configure(self, bg=p["rail"])
        self.delete("all")
        acc = self.kind_style == "accent"
        on = self._enabled
        if acc:
            fill = p["accent_hover"] if (self._hover and on) else p["accent"]
            rounded(self, 1, 1, self.w - 1, self.h - 1, 9, fill=fill if on else p["c_line"])
            col = p["on_accent"]
        else:
            rounded(self, 1, 1, self.w - 1, self.h - 1, 9,
                    fill=p["hover"] if (self._hover and on) else p["rail"],
                    outline=p["c_outline"] if on else p["c_line"], width=1.3)
            col = p["c_text"] if on else p["c_muted"]
        if self._focused():
            rounded(self, 4, 4, self.w - 4, self.h - 4, 7, outline=col, width=1)
        tid = self.create_text(0, 0, text=self.text, fill=col, font=serif(12), anchor="w")
        x0, y0, x1, y1 = self.bbox(tid)
        tw = x1 - x0
        total = tw + (30 if self.icon else 0)
        left = (self.w - total) / 2
        if self.icon:
            draw_icon(self, self.icon, left + 11, self.h / 2, col, s=0.85)
            left += 30
        self.coords(tid, left, self.h / 2)


class ModeSwitch(_Clickable):
    """Sun · switch · moon, like the design's top-right toggle."""

    def __init__(self, parent, var: tk.BooleanVar, command, pal: dict) -> None:
        self.var, self.pal = var, pal
        super().__init__(parent, command, 112, 36, pal["rail"])
        self.draw()

    def set_palette(self, pal: dict) -> None:
        self.pal = pal
        self.draw()

    def draw(self) -> None:
        p = self.pal
        tk.Canvas.configure(self, bg=p["rail"])
        self.delete("all")
        dark = bool(self.var.get())
        draw_icon(self, "sun", 14, 18, p["c_text"] if not dark else p["c_muted"], s=0.8)
        rounded(self, 32, 7, 80, 29, 11, fill=p["hover"], outline=p["c_line"], width=1)
        kx = 69 if dark else 43
        self.create_oval(kx - 9, 9, kx + 9, 27, fill="#ffffff" if not dark else p["c_text"],
                         outline=p["c_outline"] if not dark else "", width=1)
        draw_icon(self, "moon", 98, 18, p["c_text"] if dark else p["c_muted"], s=0.8)
        if self._focused():
            rounded(self, 30, 5, 82, 31, 13, outline=p["accent"], width=1.5)


class MiniSwitch(_Clickable):
    """A small on/off switch with a label, for the dark bar (Live preview)."""

    def __init__(self, parent, text: str, var: tk.BooleanVar, command, pal: dict) -> None:
        self.text, self.var, self.pal = text, var, pal
        self._cmd = command
        super().__init__(parent, self._toggle, 84, 36, pal["rail"])
        var.trace_add("write", lambda *a: self.draw())
        self.draw()

    def _toggle(self) -> None:
        self.var.set(not self.var.get())
        if self._cmd:
            self._cmd()

    def set_palette(self, pal: dict) -> None:
        self.pal = pal
        self.draw()

    def draw(self) -> None:
        p = self.pal
        tk.Canvas.configure(self, bg=p["rail"])
        self.delete("all")
        on = bool(self.var.get())
        self.create_text(4, 18, text=self.text, anchor="w", fill=p["c_text"], font=serif(11))
        x0 = 44
        rounded(self, x0, 9, x0 + 34, 27, 9, fill=p["accent"] if on else p["hover"],
                outline="" if on else p["c_line"], width=1)
        kx = x0 + 25 if on else x0 + 9
        self.create_oval(kx - 6, 12, kx + 6, 24, fill="#ffffff" if on else p["c_muted"],
                         outline="")
        if self._focused():
            rounded(self, x0 - 2, 7, x0 + 36, 29, 11, outline=p["accent"], width=1.2)


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
