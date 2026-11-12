"""'New version available' check against the GitHub releases of this project.

At most one request a day (the answer is remembered in update_check.json), a
short timeout, and any failure is silent: being offline must never get in the way.
"""

from __future__ import annotations

import json
import re
import time

from . import __version__, paths

REPO = "TheDutchMan13/Map-Poster-Studio"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
STATE = paths.APP_DIR / "update_check.json"
EVERY_S = 24 * 3600


def _parse(v: str) -> tuple:
    nums = re.findall(r"\d+", v or "")
    return tuple(int(n) for n in nums[:3]) or (0,)


def is_newer(latest: str, current: str = __version__) -> bool:
    return _parse(latest) > _parse(current)


def _fetch(timeout: float) -> dict | None:
    import urllib.request
    req = urllib.request.Request(API, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"MapPosterStudio/{__version__}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    if data.get("draft") or data.get("prerelease"):
        return None
    return {"tag": data.get("tag_name", ""), "url": data.get("html_url") or RELEASES_PAGE}


def check(force: bool = False, timeout: float = 6.0) -> dict | None:
    """Return {"tag", "url"} when a newer release exists, else None. Never raises."""
    try:
        state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    except Exception:
        state = {}
    latest = state.get("latest")
    if force or time.time() - state.get("checked", 0) > EVERY_S:
        try:
            latest = _fetch(timeout)
            STATE.parent.mkdir(parents=True, exist_ok=True)
            STATE.write_text(json.dumps({"checked": time.time(), "latest": latest}),
                             encoding="utf-8")
        except Exception:
            return None      # offline, rate-limited, GitHub down: say nothing
    if latest and is_newer(latest.get("tag", "")):
        return latest
    return None
