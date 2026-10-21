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
from fishbaseball._core.acquire import (
    acquire_manifest,
    download_partitions,
    download_table,
    table_entry,
)
from fishbaseball._core.cache import Cache
from fishbaseball._core.frames import to_backend
from fishbaseball._core.manifest import is_partitioned
from fishbaseball.sources import REGISTRY

_INFO_SCHEMA = {
    "source": pl.Utf8,
    "version": pl.Utf8,
    "table": pl.Utf8,
    "bytes": pl.Int64,
    "partitions": pl.Int64,
    "last_checked": pl.Datetime(time_zone="UTC"),
    "next_check": pl.Datetime(time_zone="UTC"),
}


def info() -> Any:
    """One row per cached (source, version, table): how big it is on disk (and, for a table
    published in per-season partitions, how many of those partition files are cached —
    `partitions`, else `None`), when that source's
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
    source: str = "lahman",
    tables: list[str] | None = None,
    version: str | None = None,
    seasons: Any = None,
) -> None:
    """Download `tables` (default: every table in the source's manifest) for `version`
    (default: the newest supported release), so a later `load()` needs no network.

    `seasons` (one season, or a list / `range`; default: every published season) applies to
    tables published in per-season partitions, i.e. Retrosheet's `plays`, `batting`,
    `pitching`, `fielding` and `team_stats`; whole-file tables are always fetched in full.
    The default for Retrosheet is therefore everything, about 1 GB; name `tables` and
    `seasons` to take less."""
    if source not in REGISTRY:
        raise ValueError(f"unknown source {source!r}; known sources: {sorted(REGISTRY)}")
    spec = REGISTRY[source]
    cache = Cache()
    client = get_client()
    offline = config.get("offline")
    manifest, resolved = acquire_manifest(spec, cache, client, version=version)
    for table in tables or sorted(manifest["tables"]):
        entry = table_entry(manifest, spec, table)
        if is_partitioned(entry):
            download_partitions(
                spec, table, entry, resolved, seasons, cache, client, offline=offline
            )
        else:
            download_table(spec, table, entry, resolved, cache, client, offline=offline)
