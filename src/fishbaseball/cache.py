"""`fb.cache`: inspect, clear and pre-warm the on-disk cache (`fishbaseball._core.cache.Cache`
underneath). Every function here re-resolves `config.get("cache_dir")` on each call, so a
`config.set(cache_dir=...)` in the same process takes effect immediately.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import polars as pl

from fishbaseball import config
from fishbaseball._client import get_client
from fishbaseball._core.acquire import acquire_manifest, acquire_table
from fishbaseball._core.cache import Cache
from fishbaseball._core.frames import to_backend
from fishbaseball.sources import REGISTRY

_INFO_SCHEMA = {
    "source": pl.Utf8,
    "version": pl.Utf8,
    "table": pl.Utf8,
    "bytes": pl.Int64,
    "last_checked": pl.Datetime(time_zone="UTC"),
    "next_check": pl.Datetime(time_zone="UTC"),
}


def info() -> Any:
    """One row per cached (source, version, table): how big it is on disk, when that source's
    release pointer was last checked, and when it's next due to be rechecked (`last_checked +
    fb.config.set(ttl=...)`; both `None` if that source has never been checked). Empty (but
    correctly shaped) if nothing has been loaded yet. Reads only the local cache — never makes
    a network call."""
    cache = Cache()
    ttl = timedelta(seconds=config.get("ttl"))
    rows = []
    for row in cache.info():
        meta = cache.get_metadata(row["source"]) or {}
        last_checked_raw = meta.get("last_checked")
        last_checked = datetime.fromisoformat(last_checked_raw) if last_checked_raw else None
        rows.append(
            {
                **row,
                "last_checked": last_checked,
                "next_check": last_checked + ttl if last_checked else None,
            }
        )
    df = pl.DataFrame(rows, schema=_INFO_SCHEMA) if rows else pl.DataFrame(schema=_INFO_SCHEMA)
    return to_backend(df, config.get("backend"))


def purge(source: str | None = None, version: str | None = None) -> None:
    """Delete cached data. With neither argument, clears the entire cache. With `source` only,
    clears everything for that source. With both, clears just that one cached release,
    leaving the rest of `source`'s cache (and its pointer/metadata) untouched."""
    Cache().purge(source, version=version)


def prefetch(
    source: str = "lahman", tables: list[str] | None = None, version: str | None = None
) -> None:
    """Download `tables` (default: every table in the source's manifest) for `version`
    (default: the newest supported release), so a later `load()` needs no network."""
    if source not in REGISTRY:
        raise ValueError(f"unknown source {source!r}; known sources: {sorted(REGISTRY)}")
    spec = REGISTRY[source]
    cache = Cache()
    client = get_client()
    manifest, _ = acquire_manifest(spec, cache, client, version=version)
    for table in tables or sorted(manifest["tables"]):
        acquire_table(spec, table, cache, client, version=version)
