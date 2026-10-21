"""Retrosheet play-by-play and box-score data: `tables()`, `load()`, `version()`,
`releases()`, and one function per table (`plays`, `game_info`, `batting`, ...).

    import fishbaseball as fb

    fb.retrosheet.plays(2024, team="PIT")                    # every Pirates play of 2024
    fb.retrosheet.plays(1956, game_id="NYA195610080", game_type=None)   # Larsen's perfect game
    fb.retrosheet.batting(1927, player_id="ruthb101")        # one row per game Ruth batted in
    fb.retrosheet.plays(range(2015, 2025), lazy=True)        # a polars LazyFrame, nothing loaded

Data comes from `fishbaseball-data`'s published releases (see that repo's README for the
pipeline). The five large tables (`plays`, `batting`, `pitching`, `fielding`, `team_stats`)
are published as one Parquet file per season; the package downloads only the seasons you ask
for, verifies each, and keeps them in a content-addressed cache shared by every release, so a
later release that re-publishes one season re-downloads just that season. `game_info` and
`all_players` are single files.

Three conventions hold for every function here:

* **`seasons` is required for the five partitioned tables**, unless you pass
  `all_seasons=True` (everything, eagerly) or `lazy=True` (a polars `LazyFrame`; with no
  `seasons`, every season). Loading all of `plays` eagerly is ~17 million rows by ~180
  columns, so an accidental full load is a clear `ValueError`, not a frozen notebook. For
  multi-season work, prefer `lazy=True` with `columns=[...]` and polars expressions.
* **`stattype`** (stat tables) defaults to `"value"`, Retrosheet's best estimate of each
  figure; `"official"` and others are available, or `None` for all of them.
* **`game_type`** defaults to `"regular"` (regular season only); pass `None` for every game
  type, or a list such as `["regular", "worldseries"]`. Two 1933 games with no recorded game
  type are therefore excluded by default.

Player ids are Retrosheet's (`ruthb101`) and returned as-is; Lahman's `people.retro_id` joins
them to Lahman's `player_id`.

    The information used here was obtained free of charge from and is copyrighted by
    Retrosheet. Interested parties may contact Retrosheet at "www.retrosheet.org".

Every import here that isn't part of the public surface is aliased with a leading underscore,
so `dir(fishbaseball.retrosheet)` shows only real, usable names.
"""

from __future__ import annotations

from dataclasses import dataclass as _dataclass
from datetime import datetime as _datetime
from datetime import timezone as _timezone
from typing import Any as _Any

import polars as _pl

from fishbaseball import config as _config
from fishbaseball._client import get_client as _get_client
from fishbaseball._core.acquire import Acquired as _Acquired
from fishbaseball._core.acquire import acquire_manifest as _acquire_manifest
from fishbaseball._core.acquire import acquire_pointer as _acquire_pointer
from fishbaseball._core.acquire import download_partitions as _download_partitions
from fishbaseball._core.acquire import download_table as _download_table
from fishbaseball._core.acquire import table_entry as _table_entry
from fishbaseball._core.cache import Cache as _Cache
from fishbaseball._core.frames import filter_values as _filter_values
from fishbaseball._core.frames import render as _render
from fishbaseball._core.frames import scan_files as _scan_files
from fishbaseball._core.frames import select_columns as _select_columns
from fishbaseball._core.frames import to_backend as _to_backend
from fishbaseball._core.manifest import is_partitioned as _is_partitioned
from fishbaseball._core.provenance import PartitionProvenance, Provenance
from fishbaseball._core.provenance import build_partitioned_provenance as _build_partitioned
from fishbaseball._core.provenance import build_provenance as _build_provenance
from fishbaseball.retrosheet._source import SOURCE as _SOURCE


def tables() -> list[str]:
    """Every table name valid for `load()`, from the currently resolved release's manifest —
    so a table added upstream shows up here without a fishbaseball release."""
    manifest, _ = _acquire_manifest(_SOURCE, _Cache(), _get_client())
    return sorted(manifest["tables"])


@_dataclass
class _Loaded:
    """What `_load_raw` found: a lazy frame over the table's cached file(s) and the facts
    `_finish` needs to project, render and describe it."""

    lf: _pl.LazyFrame
    manifest: dict[str, _Any]
    columns: list[str]
    acquired: list[_Acquired]
    partitioned: bool


def _load_raw(
    table: str,
    *,
    seasons: _Any = None,
    all_seasons: bool = False,
    lazy: bool = False,
    version: str | None = None,
    refresh: bool = False,
    offline: bool | None = None,
) -> _Loaded:
    """`load()`'s work up to (not including) column projection and backend conversion, shared
    with the per-table functions in `_tables.py` so they can filter in polars first —
    converting to the configured backend, then filtering with polars-only expressions, would
    break the pandas backend."""
    if lazy and _config.get("backend") != "polars":
        _render(_pl.LazyFrame(), lazy=True, backend=_config.get("backend"))  # raises ValueError
    if seasons is not None and all_seasons:
        raise ValueError("pass either seasons=... or all_seasons=True, not both")

    cache, client = _Cache(), _get_client()
    resolved_offline = _config.get("offline") if offline is None else offline
    manifest, resolved = _acquire_manifest(
        _SOURCE, cache, client, version=version, refresh=refresh, offline=offline
    )
    entry = _table_entry(manifest, _SOURCE, table)
    columns = list(entry["columns"])

    if not _is_partitioned(entry):
        acquired = _download_table(
            _SOURCE, table, entry, resolved, cache, client, offline=resolved_offline
        )
        lf = _pl.scan_parquet(acquired.path)
        if seasons is not None:
            lf = _filter_values(lf, entry["season_column"], seasons)
        return _Loaded(lf, manifest, columns, [acquired], partitioned=False)

    if seasons is None and not (all_seasons or lazy):
        raise ValueError(
            f"{table!r} is published one Parquet file per season, so `seasons` is required "
            f"(e.g. {table}(2024)); pass all_seasons=True to load every season eagerly, or "
            "lazy=True for a polars LazyFrame over all of them without loading it"
        )
    acquired_list = _download_partitions(
        _SOURCE, table, entry, resolved, seasons, cache, client, offline=resolved_offline
    )
    lf = _scan_files(a.path for a in acquired_list)
    return _Loaded(lf, manifest, columns, acquired_list, partitioned=True)


def _finish(
    loaded: _Loaded,
    table: str,
    *,
    columns: _Any,
    lazy: bool,
    return_provenance: bool,
    lf: _pl.LazyFrame | None = None,
) -> _Any:
    """Project `columns`, render (collect, or keep lazy) and attach provenance if asked."""
    projected = _select_columns(loaded.lf if lf is None else lf, columns, known=loaded.columns)
    out = _render(projected, lazy=lazy, backend=_config.get("backend"))
    if not return_provenance:
        return out
    if loaded.partitioned:
        return out, _build_partitioned(_SOURCE.name, table, loaded.manifest, loaded.acquired)
    return out, _build_provenance(_SOURCE.name, table, loaded.manifest, loaded.acquired[0])


def load(
    table: str,
    *,
    seasons: _Any = None,
    columns: _Any = None,
    lazy: bool = False,
    all_seasons: bool = False,
    version: str | None = None,
    refresh: bool = False,
    offline: bool | None = None,
    return_provenance: bool = False,
) -> _Any:
    """A Retrosheet table, in the backend `fb.config.set(backend=...)` selects (default
    polars), with no filtering beyond `seasons`.

    Most tables also have a dedicated function (`fb.retrosheet.plays(...)`, ...) with
    convenient filters and sensible defaults (`game_type="regular"`, `stattype="value"`);
    `load()` is the general form: every row, every game type, every `stattype`.

    Args:
        table: a name from `tables()`, e.g. `"plays"`.
        seasons: one season, or any non-string iterable of seasons (a list, a `range`, a
            generator, ...). **Required** for the five partitioned tables (`plays`,
            `batting`, `pitching`, `fielding`, `team_stats`) unless `all_seasons` or `lazy`
            is set. Optional for `game_info` and `all_players`, where it filters on their
            season column. A season the release doesn't publish raises
            `DataNotAvailableError` naming the seasons it does.
        columns: keep only these columns, in this order (unknown names are a `ValueError`).
            Worth using on `plays`, which has ~180 columns: with `lazy=True` only these are
            ever read from disk.
        lazy: return a polars `LazyFrame` over the cached Parquet files instead of loading
            them; filter and aggregate with polars expressions, then `.collect()`. Needs the
            polars backend (`ValueError` with `backend="pandas"`). With no `seasons`, covers
            every season, which first downloads them all (about 1 GB for every table,
            about 600 MB for `plays` alone; cached afterwards).
        all_seasons: load every published season eagerly. Mutually exclusive with `seasons`.
        version: pin to an exact release date (`"2026-10-20"`) or an upstream version string.
            `None` (default) uses the newest release this version of fishbaseball can read.
        refresh: check for a newer release now, instead of waiting out the cache TTL
            (`fb.config.set(ttl=...)`).
        offline: `True` never touches the network — cached data only, or
            `DataNotAvailableError`. `None` (default) uses `fb.config.set(offline=...)`.
        return_provenance: if `True`, return `(result, Provenance)`. For a multi-season call
            there is one `Provenance` whose `partitions` lists every season used, its release
            tag and whether it came from the cache.

    Returns:
        A DataFrame (or `LazyFrame`, with `lazy=True`), or `(that, Provenance)`. A partition
        that can't be fetched or fails verification is served from the newest older cached
        release that has it, with a `StaleDataWarning` (`fb.config.set(strict=True)` raises
        instead); with no such copy, `DataNotAvailableError`.

    The information used here was obtained free of charge from and is copyrighted by
    Retrosheet. Interested parties may contact Retrosheet at "www.retrosheet.org".
    """
    loaded = _load_raw(
        table,
        seasons=seasons,
        all_seasons=all_seasons,
        lazy=lazy,
        version=version,
        refresh=refresh,
        offline=offline,
    )
    return _finish(loaded, table, columns=columns, lazy=lazy, return_provenance=return_provenance)


def version(*, refresh: bool = False) -> str:
    """The release tag `load()` would currently use, e.g. `"retrosheet-2026-10-20"`. Subject to
    the same cache/TTL behavior as `load()`; pass `refresh=True` to check for a newer one
    first."""
    _, resolved = _acquire_manifest(_SOURCE, _Cache(), _get_client(), refresh=refresh)
    return resolved.tag


def releases(*, refresh: bool = False) -> _Any:
    """Every known release, as a DataFrame with one row per release: `tag`, `version`,
    `schema_version`, `built_at` and `withdrawn`. Use `tag` or `version` with
    `load(..., version=...)` to pin to one. Respects `fb.config.set(offline=...)` and the
    usual TTL; pass `refresh=True` to check for new releases first."""
    now = _datetime.now(_timezone.utc)
    pointer = _acquire_pointer(
        _SOURCE,
        _Cache(),
        _get_client(),
        refresh=refresh,
        offline=_config.get("offline"),
        now=now,
    )
    rows = pointer.get("releases", [])
    schema = {
        "tag": _pl.Utf8,
        "version": _pl.Utf8,
        "schema_version": _pl.Int64,
        "built_at": _pl.Utf8,
        "withdrawn": _pl.Boolean,
    }
    df = _pl.DataFrame(rows, schema=schema) if rows else _pl.DataFrame(schema=schema)
    return _to_backend(df, _config.get("backend"))


from fishbaseball.retrosheet import _tables as _tables  # noqa: E402 - after _load_raw/_finish exist
from fishbaseball.retrosheet._tables import *  # noqa: E402, F403

__all__: list[str] = [
    "tables",
    "load",
    "version",
    "releases",
    "Provenance",
    "PartitionProvenance",
]
__all__.extend(_tables.__all__)
