"""Small reusable window pieces: tooltips, a colour picker with hex entry, and a
zoomable, draggable poster preview."""

from __future__ import annotations

import colorsys
import re
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

_WIN = sys.platform.startswith("win")
_HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")


# ------------------------------------------------------------------ tooltips
class Tooltip:
    """Shows a short explanation after the pointer rests on a widget."""

    def __init__(self, widget: tk.Misc, text: str, delay: int = 550) -> None:
        self.widget, self.text, self.delay = widget, text, delay
        self._after = None
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._enter, add="+")
        widget.bind("<Leave>", self._leave, add="+")
        widget.bind("<ButtonPress>", self._leave, add="+")

    def _enter(self, _e=None) -> None:
        self._cancel()
        self._after = self.widget.after(self.delay, self._show)

    def _leave(self, _e=None) -> None:
        self._cancel()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None

    def _cancel(self) -> None:
        if self._after is not None:
            try:
                self.widget.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None

    def _show(self) -> None:
        self._after = None
        if self._tip is not None or not self.widget.winfo_exists():
            return
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        x = self.widget.winfo_rootx() + 14
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        tip.wm_geometry(f"+{x}+{y}")
        tk.Label(tip, text=self.text, justify="left", wraplength=340, padx=9, pady=6,
                 bg="#2b2b2b", fg="#f4f4f4", relief="solid", borderwidth=1,
                 font=("Segoe UI", 9) if _WIN else None).pack()
        self._tip = tip


# -------------------------------------------------------------- colour picker
def _norm(hexs: str) -> str:
    m = _HEX.match((hexs or "").strip())
    return "#" + m.group(1).lower() if m else "#000000"


class ColorPicker(tk.Toplevel):
    """Colour square + hue bar + hex and RGB entry. `on_change(hex)` fires live while
    you drag; Cancel puts the original colour back. The chosen colour ends up in .result."""

    SV = 220

    def __init__(self, parent, initial: str, title: str = "Pick a colour", on_change=None) -> None:
        super().__init__(parent)
        self.title(title)
        self.transient(parent.winfo_toplevel())
        self.resizable(False, False)
        self.result: str | None = None
        self.initial = _norm(initial)
        self.on_change = on_change
        r, g, b = (int(self.initial[i:i + 2], 16) / 255 for i in (1, 3, 5))
        self.h, self.s, self.v = colorsys.rgb_to_hsv(r, g, b)
        self._busy = False

        body = ttk.Frame(self, padding=10)
        body.pack()
        self.sv_canvas = tk.Canvas(body, width=self.SV, height=self.SV, highlightthickness=1,
                                   highlightbackground="#888", cursor="crosshair")
        self.sv_canvas.grid(row=0, column=0, rowspan=6)
        self.hue_canvas = tk.Canvas(body, width=26, height=self.SV, highlightthickness=1,
                                    highlightbackground="#888", cursor="sb_v_double_arrow")
        self.hue_canvas.grid(row=0, column=1, rowspan=6, padx=(10, 12))
        self._draw_hue_bar()

        right = ttk.Frame(body)
        right.grid(row=0, column=2, rowspan=6, sticky="n")
        sw = ttk.Frame(right)
        sw.pack(anchor="w")
        self.old_sw = tk.Label(sw, width=9, height=2, bg=self.initial, relief="solid", borderwidth=1)
        self.old_sw.pack(side="left")
        self.new_sw = tk.Label(sw, width=9, height=2, bg=self.initial, relief="solid", borderwidth=1)
        self.new_sw.pack(side="left")
        cap = ttk.Frame(right)
        cap.pack(anchor="w")
        ttk.Label(cap, text="  before", foreground="gray", width=11).pack(side="left")
        ttk.Label(cap, text="  now", foreground="gray").pack(side="left")

        self.hex_var = tk.StringVar(value=self.initial)
        hf = ttk.Frame(right)
        hf.pack(anchor="w", pady=(12, 4))
        ttk.Label(hf, text="Hex").pack(side="left", padx=(0, 8))
        he = ttk.Entry(hf, textvariable=self.hex_var, width=10)
        he.pack(side="left")
        he.bind("<KeyRelease>", self._hex_typed)
        he.bind("<Return>", lambda e: self._ok())

        self.rgb_vars = [tk.StringVar() for _ in range(3)]
        for name, var in zip("RGB", self.rgb_vars):
            rf = ttk.Frame(right)
            rf.pack(anchor="w", pady=2)
            ttk.Label(rf, text=name, width=3).pack(side="left")
            sp = ttk.Spinbox(rf, from_=0, to=255, width=5, textvariable=var, command=self._rgb_typed)
            sp.pack(side="left")
            sp.bind("<KeyRelease>", lambda e: self._rgb_typed())

        bb = ttk.Frame(right)
        bb.pack(anchor="w", pady=(16, 0))
        ttk.Button(bb, text="OK", command=self._ok).pack(side="left")
        ttk.Button(bb, text="Cancel", command=self._cancel).pack(side="left", padx=6)

        self.sv_canvas.bind("<Button-1>", self._sv_drag)
        self.sv_canvas.bind("<B1-Motion>", self._sv_drag)
        self.hue_canvas.bind("<Button-1>", self._hue_drag)
        self.hue_canvas.bind("<B1-Motion>", self._hue_drag)
        self.bind("<Escape>", lambda e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self._draw_sv()
        self._sync(notify=False)
        self.update_idletasks()
        px = parent.winfo_rootx() + 60
        py = parent.winfo_rooty() + 60
        self.geometry(f"+{px}+{py}")
        try:
            self.grab_set()
        except tk.TclError:
            pass
        he.focus_set()

    # ---- drawing
    def _draw_hue_bar(self) -> None:
        import numpy as np
        from PIL import Image, ImageTk
        n = self.SV
        h = np.linspace(0, 255, n, dtype=np.uint8)[:, None].repeat(24, axis=1)
        full = np.full_like(h, 255)
        img = Image.fromarray(np.dstack([h, full, full]), "HSV").convert("RGB")
        self._hue_img = ImageTk.PhotoImage(img)
        self.hue_canvas.create_image(2, 2, image=self._hue_img, anchor="nw")

    def _draw_sv(self) -> None:
        import numpy as np
        from PIL import Image, ImageTk
        n = self.SV
        sat = np.linspace(0, 255, n, dtype=np.uint8)[None, :].repeat(n, axis=0)
        val = np.linspace(255, 0, n, dtype=np.uint8)[:, None].repeat(n, axis=1)
        hue = np.full((n, n), int(self.h * 255), dtype=np.uint8)
        img = Image.fromarray(np.dstack([hue, sat, val]), "HSV").convert("RGB")
        self._sv_img = ImageTk.PhotoImage(img)
        self.sv_canvas.delete("all")
        self.sv_canvas.create_image(2, 2, image=self._sv_img, anchor="nw")
        x = 2 + self.s * (n - 1)
        y = 2 + (1 - self.v) * (n - 1)
        self.sv_canvas.create_oval(x - 7, y - 7, x + 7, y + 7, outline="#ffffff", width=2)
        self.sv_canvas.create_oval(x - 8, y - 8, x + 8, y + 8, outline="#000000", width=1)

    def _draw_hue_marker(self) -> None:
        self.hue_canvas.delete("mark")
        y = 2 + self.h * (self.SV - 1)
        self.hue_canvas.create_rectangle(0, y - 2, 28, y + 2, outline="#000", fill="#fff", tags="mark")

    # ---- state
    def _hex_now(self) -> str:
        r, g, b = colorsys.hsv_to_rgb(self.h, self.s, self.v)
        return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))

    def _sync(self, notify: bool = True, redraw_sv: bool = True) -> None:
        hexc = self._hex_now()
        self._busy = True
        self.hex_var.set(hexc)
        for i, var in enumerate(self.rgb_vars):
            var.set(str(int(hexc[1 + 2 * i:3 + 2 * i], 16)))
        self._busy = False
        self.new_sw.configure(bg=hexc)
        if redraw_sv:
            self._draw_sv()
        self._draw_hue_marker()
        if notify and self.on_change:
            self.on_change(hexc)

    def _set_from_hex(self, hexc: str) -> None:
        r, g, b = (int(hexc[i:i + 2], 16) / 255 for i in (1, 3, 5))
        self.h, self.s, self.v = colorsys.rgb_to_hsv(r, g, b)
        self._sync()

    # ---- events
    def _sv_drag(self, e) -> None:
        n = self.SV - 1
        self.s = min(1.0, max(0.0, (e.x - 2) / n))
        self.v = 1 - min(1.0, max(0.0, (e.y - 2) / n))
        self._sync(redraw_sv=True)

    def _hue_drag(self, e) -> None:
        self.h = min(1.0, max(0.0, (e.y - 2) / (self.SV - 1)))
        self._sync()

    def _hex_typed(self, _e=None) -> None:
        if self._busy:
            return
        m = _HEX.match(self.hex_var.get().strip())
        if m:
            self._set_from_hex("#" + m.group(1).lower())

    def _rgb_typed(self) -> None:
        if self._busy:
            return
        try:
            vals = [max(0, min(255, int(float(v.get())))) for v in self.rgb_vars]
        except ValueError:
            return
        self._set_from_hex("#%02x%02x%02x" % tuple(vals))

    def _ok(self) -> None:
        self.result = self._hex_now()
        self.grab_release()
        self.destroy()

    def _cancel(self) -> None:
        if self.on_change:
            self.on_change(self.initial)
        self.result = None
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()


# ------------------------------------------------------------ poster preview
class PreviewCanvas(ttk.Frame):
    """Shows a poster image on a dark "stage". A floating bar has Fit / zoom /
    open; mouse-wheel zooms, drag pans, double-click opens the file. With no
    image it draws an outline of the poster shape with a hint inside."""

    MAX_SIDE = 6000   # very large posters are shrunk to this many pixels on a side
    MARGIN = 36       # space around the poster when it is fitted

    def __init__(self, parent, on_open=None) -> None:
        super().__init__(parent)
        self.on_open = on_open
        self.src = None
        self.zoom: float | None = None   # None = fit to window
        self._tk = None
        self._cache_key = None
        self._cache_img = None
        self._text = ""
        self._fg = "#202020"
        self._muted = "#808080"
        self._line = "#444444"
        self.aspect = 0.75               # width / height of the empty-state outline

        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.redraw())
        self.canvas.bind("<ButtonPress-1>", lambda e: self.canvas.scan_mark(e.x, e.y))
        self.canvas.bind("<B1-Motion>", lambda e: self.canvas.scan_dragto(e.x, e.y, gain=1))
        self.canvas.bind("<Double-Button-1>", lambda e: self._open())
        self.canvas.bind("<MouseWheel>", lambda e: self._step(1.25 if e.delta > 0 else 1 / 1.25))
        self.canvas.bind("<Button-4>", lambda e: self._step(1.25))
        self.canvas.bind("<Button-5>", lambda e: self._step(1 / 1.25))

        bar = self.bar = ttk.Frame(self, padding=4)
        for label, cmd, tip, wd in (("Fit", self.fit, "Show the whole poster", 4),
                                    ("−", lambda: self._step(1 / 1.5), "Zoom out", 3),
                                    ("+", lambda: self._step(1.5), "Zoom in", 3),
                                    ("100%", lambda: self.set_zoom(1.0), "Actual pixels", 5)):
            b = ttk.Button(bar, text=label, width=wd, command=cmd)
            b.pack(side="left", padx=2)
            Tooltip(b, tip)
        self.zoom_label = ttk.Label(bar, text="", width=9, anchor="center", style="Muted.TLabel")
        self.zoom_label.pack(side="left", padx=4)
        self.open_btn = ttk.Button(bar, text="Open file", command=self._open)
        self.open_btn.pack(side="left", padx=2)
        Tooltip(self.open_btn, "Open the poster file (double-click the poster does the same)")
        self._show_bar(False)

    def _show_bar(self, on: bool) -> None:
        if on:
            self.bar.place(relx=0.5, rely=1.0, y=-14, anchor="s")
        else:
            self.bar.place_forget()

    # ---- public
    def set_colors(self, bg: str, fg: str, muted: str | None = None, line: str | None = None) -> None:
        self.canvas.configure(bg=bg)
        self._fg = fg
        self._muted = muted or fg
        self._line = line or fg
        self.redraw()

    def set_aspect(self, aspect: float) -> None:
        self.aspect = max(0.2, min(5.0, aspect))
        if self.src is None:
            self.redraw()

    def set_text(self, text: str) -> None:
        self.src = None
        self._text = text
        self._cache_key = None
        self.zoom_label.configure(text="")
        self._show_bar(False)
        self.redraw()

    def set_image(self, path: Path) -> None:
        from PIL import Image
        with Image.open(path) as im:
            im = im.convert("RGB")
            if max(im.size) > self.MAX_SIDE:
                k = self.MAX_SIDE / max(im.size)
                im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))),
                               Image.Resampling.BILINEAR)
            self.src = im.copy()
        self.zoom = None
        self._cache_key = None
        self._show_bar(True)
        self.redraw()

    def fit(self) -> None:
        self.zoom = None
        self.redraw()

    def set_zoom(self, z: float) -> None:
        if self.src is None:
            return
        self.zoom = None if z <= self._fit_scale() * 1.001 else min(1.0, z)
        self.redraw(keep_center=True)

    # ---- internals
    def _open(self) -> None:
        if self.on_open:
            self.on_open()

    def _space(self) -> tuple[int, int]:
        cw, ch = max(self.canvas.winfo_width(), 50), max(self.canvas.winfo_height(), 50)
        return max(cw - 2 * self.MARGIN, 40), max(ch - 2 * self.MARGIN - 44, 40)

    def _fit_scale(self) -> float:
        if self.src is None:
            return 1.0
        aw, ah = self._space()
        return min(aw / self.src.width, ah / self.src.height, 1.0)

    def _scale(self) -> float:
        return self._fit_scale() if self.zoom is None else self.zoom

    def _step(self, factor: float) -> None:
        if self.src is None:
            return
        self.set_zoom(min(1.0, self._scale() * factor))

    def _placeholder(self, cw: int, ch: int) -> None:
        cv = self.canvas
        aw, ah = self._space()
        h = min(ah, aw / self.aspect, 560)
        w = h * self.aspect
        x0, y0 = (cw - w) / 2, (ch - 44 - h) / 2 + 8
        cv.create_rectangle(x0, y0, x0 + w, y0 + h, outline=self._line, width=2, dash=(6, 5))
        # a faint suggestion of streets and a title block
        for i in range(1, 4):
            y = y0 + h * 0.18 * i
            cv.create_line(x0 + w * .12, y, x0 + w * .88, y + h * .04, fill=self._line, width=1)
        for i in range(1, 4):
            x = x0 + w * 0.25 * i
            cv.create_line(x, y0 + h * .1, x - w * .05, y0 + h * .72, fill=self._line, width=1)
        cv.create_line(x0 + w * .3, y0 + h * .84, x0 + w * .7, y0 + h * .84, fill=self._line, width=3)
        cv.create_line(x0 + w * .4, y0 + h * .89, x0 + w * .6, y0 + h * .89, fill=self._line, width=1.5)
        bg = cv.cget("bg")
        cv.create_rectangle(x0 + w * .06, y0 + h * .33, x0 + w * .94, y0 + h * .55, fill=bg, outline="")
        lines = self._text.split("\n", 1)
        cv.create_text(cw / 2, y0 + h * .40, text=lines[0], fill=self._fg, justify="center",
                       font=("Segoe UI Semibold", 13) if _WIN else ("DejaVu Sans", 12, "bold"),
                       width=max(w - 30, 100))
        if len(lines) > 1:
            cv.create_text(cw / 2, y0 + h * .40 + 24, text=lines[1].strip(), fill=self._muted,
                           justify="center", anchor="n",
                           font=("Segoe UI", 10) if _WIN else ("DejaVu Sans", 9),
                           width=max(w - 40, 100))

    def redraw(self, keep_center: bool = False) -> None:
        cv = self.canvas
        cw, ch = max(cv.winfo_width(), 2), max(cv.winfo_height(), 2)
        fx = fy = 0.5
        if keep_center and self._cache_img is not None:
            x0, x1 = cv.xview()
            y0, y1 = cv.yview()
            fx, fy = (x0 + x1) / 2, (y0 + y1) / 2
        cv.delete("all")
        if self.src is None:
            cv.configure(scrollregion=(0, 0, cw, ch))
            self._placeholder(cw, ch)
            return
        from PIL import Image, ImageTk
        s = self._scale()
        size = (max(1, int(self.src.width * s)), max(1, int(self.src.height * s)))
        if self._cache_key != size:
            resample = Image.Resampling.BILINEAR if s < 1 else Image.Resampling.NEAREST
            self._cache_img = ImageTk.PhotoImage(self.src.resize(size, resample, reducing_gap=2.0)
                                                 if s < 1 else self.src.resize(size, resample))
            self._cache_key = size
        pad = 2 * self.MARGIN
        rw, rh = max(size[0] + pad, cw), max(size[1] + pad + 44, ch)
        cv.configure(scrollregion=(0, 0, rw, rh))
        cx, cy = rw // 2, (rh - 44) // 2
        hw, hh = size[0] / 2, size[1] / 2
        cv.create_rectangle(cx - hw - 1, cy - hh - 1, cx + hw + 1, cy + hh + 1,
                            outline=self._line, width=1)
        cv.create_image(cx, cy, image=self._cache_img, anchor="center")
        if rw > cw:
            cv.xview_moveto(max(0.0, min(1.0, fx - (cw / rw) / 2)))
        if rh > ch:
            cv.yview_moveto(max(0.0, min(1.0, fy - (ch / rh) / 2)))
        self.zoom_label.configure(text=("Fit · " if self.zoom is None else "") + f"{s * 100:.0f}%")
