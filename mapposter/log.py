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


class Cancelled(Exception):
    """Raised when the user cancels a run from the GUI."""
