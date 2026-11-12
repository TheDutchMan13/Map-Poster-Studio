"""Tiny logging hook so the CLI prints and the GUI can capture the same messages."""

from __future__ import annotations

from typing import Callable

_sink: Callable[[str], None] = print


def set_sink(fn: Callable[[str], None]) -> None:
    global _sink
    _sink = fn


def log(msg: str = "") -> None:
    try:
        _sink(msg)
    except UnicodeEncodeError:  # old Windows consoles
        _sink(msg.encode("ascii", "replace").decode("ascii"))


# ---- progress (0..1 for the whole run). The GUI shows it as a percentage.
_progress: Callable[[float], None] = lambda f: None
_span = (0.0, 1.0)   # this step covers [start, start + width] of the whole run


def set_progress_sink(fn: Callable[[float], None] | None) -> None:
    global _progress
    _progress = fn or (lambda f: None)


def progress_span(start: float, width: float) -> None:
    """Map the next step()s (0..1) onto this part of the whole run."""
    global _span
    _span = (start, width)


def step(frac: float) -> None:
    """Report how far the current step is (0..1)."""
    try:
        _progress(min(max(_span[0] + _span[1] * frac, 0.0), 1.0))
    except Exception:
        pass


class Cancelled(Exception):
    """Raised when the user cancels a run from the GUI."""
