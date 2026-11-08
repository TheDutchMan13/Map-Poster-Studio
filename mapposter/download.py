"""Download an OpenStreetMap extract (.osm.pbf) from Geofabrik."""

from __future__ import annotations

import time
from pathlib import Path

from . import paths
from .log import log

GEOFABRIK = "https://download.geofabrik.de/{region}-latest.osm.pbf"
DEFAULT_REGION = "north-america/us/arizona"


def region_url(region: str) -> str:
    region = region.strip().strip("/")
    if region.startswith("http"):
        return region
    return GEOFABRIK.format(region=region)


def download_pbf(region: str = DEFAULT_REGION, check_cancel=lambda: None) -> Path:
    import requests

    url = region_url(region)
    paths.ensure_dirs()
    dest = paths.DATA_DIR / url.rsplit("/", 1)[-1]
    tmp = dest.with_suffix(dest.suffix + ".part")
    log(f"Downloading {url}")
    with requests.get(url, stream=True, timeout=60,
                      headers={"User-Agent": "MapPosterStudio/1.0"}) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        got, last = 0, 0.0
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(chunk_size=1 << 20):
                fh.write(chunk)
                got += len(chunk)
                if time.time() - last > 2:
                    check_cancel()
                    pct = f" ({got / total:.0%})" if total else ""
                    log(f"  {got / 1e6:,.0f} MB{pct}")
                    last = time.time()
    tmp.replace(dest)
    log(f"✓ Saved {dest} ({dest.stat().st_size / 1e6:,.0f} MB)")
    return dest
