"""The Lahman Baseball Database: `tables()`, `load()`, `version()` and `releases()`.

Data comes from `fishbaseball-data`'s published releases (see that repo's README for the
pipeline and license). This module is a thin, source-specific layer over `fishbaseball._core`:
it knows the source's name and repo (`lahman/_source.py`) and nothing else source-specific.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import polars as pl

from fishbaseball import config
from fishbaseball._client import get_client
from fishbaseball._core.acquire import acquire_manifest, acquire_pointer, acquire_table
from fishbaseball._core.cache import Cache
from fishbaseball._core.frames import filter_values, to_backend
from fishbaseball._core.provenance import Provenance, build_provenance
from fishbaseball.lahman._source import SOURCE


def tables() -> list[str]:
    """Every table name valid for `load()`, from the currently resolved release's manifest —
    so a table added upstream shows up here without a fishbaseball release."""
    manifest, _ = acquire_manifest(SOURCE, Cache(), get_client())
    return sorted(manifest["tables"])


def _load_raw(
    table: str,
    *,
    seasons: Any = None,
    version: str | None = None,
    refresh: bool = False,
    offline: bool | None = None,
) -> tuple[pl.DataFrame, dict[str, Any], Any]:
    """`load()`'s work up to (not including) backend conversion, shared with the per-table
    wrappers in `_tables.py` so they can apply their own filters in polars first — converting
    to the configured backend, then filtering with polars-only expressions, would break the
    pandas backend."""
    cache = Cache()
    acquired = acquire_table(
        SOURCE, table, cache, get_client(),
        version=version, refresh=refresh, offline=offline,
    )  # fmt: skip
    manifest = cache.read_json(cache.manifest_path(SOURCE.name, acquired.version))
    assert manifest is not None, f"manifest for {acquired.version} must be cached by acquire_table"
    entry = manifest["tables"][table]

    df = pl.read_parquet(acquired.path)
    if seasons is not None:
        season_column = entry.get("season_column")
        if season_column is None:
            raise ValueError(f"{table!r} has no season column; `seasons` doesn't apply to it")
        df = filter_values(df, season_column, seasons)
    return df, manifest, acquired


def _finish(
    df: pl.DataFrame, table: str, manifest: dict[str, Any], acquired: Any, return_provenance: bool
) -> Any:
    out = to_backend(df, config.get("backend"))
    if return_provenance:
        return out, build_provenance(SOURCE.name, table, manifest, acquired)
    return out


def load(
    table: str,
    *,
    seasons: Any = None,
    version: str | None = None,
    refresh: bool = False,
    offline: bool | None = None,
    return_provenance: bool = False,
) -> Any:
    """A Lahman table, in the backend `fb.config.set(backend=...)` selects (default polars).

    Args:
        table: a name from `tables()`, e.g. `"batting"`. Most tables also have a dedicated
            function (`fb.lahman.batting(...)`, etc.) with convenient built-in filters;
            `load()` is the general form that always works.
        seasons: filter to one season or a list of seasons, on the table's season column.
            `ValueError` if the table has no season column (e.g. `people`) and this is given.
        version: pin to an exact release date (`"2026-10-02"`) or a SABR version
            (`"2025"`, resolving to that version's newest release). `None` (default) uses the
            newest release this version of fishbaseball can read.
        refresh: check for a newer release now, instead of waiting out the cache TTL
            (`fb.config.set(ttl=...)`).
        offline: `True` never touches the network — cached data only, or `DataNotAvailableError`.
            `None` (default) uses `fb.config.set(offline=...)`, itself default `False`.
        return_provenance: if `True`, return `(df, Provenance)` instead of just `df`.

    Returns:
        The table as a DataFrame, or `(df, Provenance)` if `return_provenance=True`. If the
        resolved release can't be fetched or fails verification, the newest still-good cached
        release is served instead, with a `StaleDataWarning` (`fb.config.set(strict=True)`
        raises instead of warning).
    """
    df, manifest, acquired = _load_raw(
        table, seasons=seasons, version=version, refresh=refresh, offline=offline
    )
    return _finish(df, table, manifest, acquired, return_provenance)


def version(*, refresh: bool = False) -> str:
    """The release tag `load()` would currently use, e.g. `"lahman-2026-09-28"`. Subject to the
    same cache/TTL behavior as `load()`; pass `refresh=True` to check for a newer one first."""
    _, resolved = acquire_manifest(SOURCE, Cache(), get_client(), refresh=refresh)
    return resolved.tag


def releases(*, refresh: bool = False) -> Any:
    """Every known release, as a DataFrame with one row per release: `tag`, `version` (the
    upstream/SABR version), `schema_version`, `built_at` and `withdrawn`. Use `tag` or
    `version` with `load(..., version=...)` to pin to one. Respects `fb.config.set(offline=...)`
    and the usual TTL; pass `refresh=True` to check for new releases first."""
    now = datetime.now(timezone.utc)
    offline = config.get("offline")
    pointer = acquire_pointer(
        SOURCE, Cache(), get_client(), refresh=refresh, offline=offline, now=now
    )
    rows = pointer.get("releases", [])
    schema = {
        "tag": pl.Utf8,
        "version": pl.Utf8,
        "schema_version": pl.Int64,
        "built_at": pl.Utf8,
        "withdrawn": pl.Boolean,
    }
    df = pl.DataFrame(rows, schema=schema) if rows else pl.DataFrame(schema=schema)
    return to_backend(df, config.get("backend"))


from fishbaseball.lahman import _tables as _tables  # noqa: E402 - after _load_raw/_finish exist
from fishbaseball.lahman._tables import *  # noqa: E402, F403

__all__: list[str] = ["tables", "load", "version", "releases", "Provenance"]
__all__.extend(_tables.__all__)
