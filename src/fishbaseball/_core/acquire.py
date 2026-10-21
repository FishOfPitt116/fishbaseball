"""The refresh algorithm: given a source and a table, decide what to trust — cache, a fresh
download, or an older cached release — and return a verified local Parquet path.

Overview (see the design doc for the full decision table):
- A date pin (`"2026-10-02"`) never needs the pointer: the tag is computable directly, so an
  already-cached, checksum-verified copy is used with no network at all.
- A version pin (`"2025"`) is resolved from a cached pointer first, without touching the
  network; only an unresolvable pin (or `refresh=True`) triggers a pointer refresh.
- With no pin, the cached pointer is used as-is within its TTL; past it (or forced), a
  conditional GET checks for changes. A failed refresh falls back to the cached pointer with
  `StaleDataWarning` (`config.strict=True` raises instead); no cached pointer at all raises
  `DataNotAvailableError`.
- A table download that fails after the manifest resolved falls back to the newest other
  cached release that already has a verified copy of that table, again via `StaleDataWarning`
  (or raising in strict mode); with nothing to fall back to, it raises `DataNotAvailableError`.
"""

from __future__ import annotations

import difflib
import hashlib
import warnings
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl

from fishbaseball import config
from fishbaseball._compat import SUPPORTED_SCHEMAS
from fishbaseball._core.cache import Cache
from fishbaseball._core.manifest import (
    DATE_PIN,
    Resolved,
    describe_partitions,
    is_partitioned,
    normalize_partition_keys,
    partition_keys,
    resolve,
)
from fishbaseball.exceptions import (
    ChecksumError,
    DataNotAvailableError,
    FishbaseballWarning,
    IncompatibleDataError,
    SourceUnavailableError,
    StaleDataWarning,
)


@dataclass(frozen=True)
class SourceSpec:
    name: str  # "lahman"
    repo: str  # "FishOfPitt116/fishbaseball-data" — owns the GitHub Releases this reads


@dataclass(frozen=True)
class Acquired:
    path: Path
    version: str  # the release tag actually served (may differ from the resolved one on fallback)
    fetched_at: datetime
    from_cache: bool
    fallback_reason: str | None = None
    partition: str | None = None  # the season, for a file from a partitioned table


def release_url(repo: str, tag: str, filename: str) -> str:
    return f"https://github.com/{repo}/releases/download/{tag}/{filename}"


def pointer_url(spec: SourceSpec) -> str:
    return release_url(spec.repo, f"{spec.name}-latest", "latest.json")


def manifest_url(spec: SourceSpec, tag: str) -> str:
    return release_url(spec.repo, tag, "manifest.json")


def _warn_or_raise(warning: FishbaseballWarning) -> None:
    if config.get("strict"):
        raise warning
    warnings.warn(warning, stacklevel=3)


def _resolve_offline(offline: bool | None) -> bool:
    return config.get("offline") if offline is None else offline


def acquire_pointer(
    spec: SourceSpec, cache: Cache, client: Any, *, refresh: bool, offline: bool, now: datetime
) -> dict[str, Any]:
    """The pointer (`latest.json`), refreshed over the network per TTL/`refresh` policy."""
    cached = cache.read_json(cache.pointer_path(spec.name))
    if offline:
        if cached is None:
            raise DataNotAvailableError(f"{spec.name}: offline and no cached pointer")
        return cached
    if (
        not refresh
        and cached is not None
        and not cache.is_stale(spec.name, ttl=config.get("ttl"), now=now)
    ):
        return cached
    meta = cache.get_metadata(spec.name) or {}
    try:
        resp = client.get_json(pointer_url(spec), etag=meta.get("etag"))
    except SourceUnavailableError as e:
        if cached is None:
            raise DataNotAvailableError(
                f"{spec.name}: could not reach the source and nothing is cached"
            ) from e
        _warn_or_raise(
            StaleDataWarning(
                f"{spec.name}: could not check for updates ({e}); "
                f"using cached data from {meta.get('last_checked', 'an unknown time')}"
            )
        )
        return cached
    if resp.not_modified:
        cache.update_metadata(spec.name, last_checked=now.isoformat())
        return cached if cached is not None else {}
    cache.write_json_atomic(cache.pointer_path(spec.name), resp.json)
    cache.update_metadata(spec.name, etag=resp.etag, last_checked=now.isoformat())
    return resp.json


def _resolve_pin(
    spec: SourceSpec,
    pin: str,
    cache: Cache,
    client: Any,
    *,
    refresh: bool,
    offline: bool,
    now: datetime,
) -> Resolved:
    supported = SUPPORTED_SCHEMAS[spec.name]
    if DATE_PIN.match(pin):
        # The tag is computable without the pointer at all.
        tag = f"{spec.name}-{pin}"
        cached_pointer = cache.read_json(cache.pointer_path(spec.name))
        latest = cached_pointer.get("latest") if cached_pointer else None
        return Resolved(tag=tag, is_latest=(tag == latest), latest_tag=latest)

    cached_pointer = cache.read_json(cache.pointer_path(spec.name))
    if cached_pointer is not None and not refresh:
        try:
            return resolve(cached_pointer, supported, pin=pin)
        except ValueError:
            if offline:
                raise DataNotAvailableError(
                    f"{spec.name}: version {pin!r} isn't in the cached data, and offline=True"
                ) from None
    elif offline:
        raise DataNotAvailableError(
            f"{spec.name}: offline and no cached pointer to resolve version {pin!r}"
        )
    pointer = acquire_pointer(spec, cache, client, refresh=refresh, offline=offline, now=now)
    return resolve(pointer, supported, pin=pin)


def acquire_manifest(
    spec: SourceSpec,
    cache: Cache,
    client: Any,
    *,
    version: str | None = None,
    refresh: bool = False,
    offline: bool | None = None,
    now: datetime | None = None,
) -> tuple[dict[str, Any], Resolved]:
    """The manifest for the resolved release, plus how it was resolved."""
    now = now or datetime.now(timezone.utc)
    offline = _resolve_offline(offline)
    supported = SUPPORTED_SCHEMAS[spec.name]

    if version is not None:
        resolved = _resolve_pin(
            spec, version, cache, client, refresh=refresh, offline=offline, now=now
        )
    else:
        pointer = acquire_pointer(spec, cache, client, refresh=refresh, offline=offline, now=now)
        resolved = resolve(pointer, supported)
        if not resolved.is_latest:
            _warn_or_raise(
                StaleDataWarning(
                    f"{spec.name}: using {resolved.tag}, which is not the newest published "
                    f"release ({resolved.latest_tag}); this version of fishbaseball can't read "
                    "the newer schema yet"
                )
            )

    manifest = cache.read_json(cache.manifest_path(spec.name, resolved.tag))
    if manifest is None:
        if offline:
            raise DataNotAvailableError(f"{spec.name} {resolved.tag}: not cached and offline=True")
        try:
            resp = client.get_json(manifest_url(spec, resolved.tag))
        except SourceUnavailableError as e:
            raise DataNotAvailableError(
                f"{spec.name} {resolved.tag}: could not fetch manifest"
            ) from e
        manifest = resp.json
        cache.write_json_atomic(cache.manifest_path(spec.name, resolved.tag), manifest)
    return manifest, resolved


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _verify_table_schema(path: Path, columns: dict[str, str]) -> None:
    schema = pl.read_parquet_schema(path)
    actual = {c: str(t) for c, t in schema.items()}
    if actual != columns:
        raise IncompatibleDataError(
            f"{path.name}: columns {actual} don't match the manifest's {columns}"
        )


def _cached_and_verified(cache: Cache, source: str, tag: str, table: str, sha256: str) -> bool:
    path = cache.table_path(source, tag, table)
    return path.exists() and _sha256_file(path) == sha256


def _find_fallback(cache: Cache, spec: SourceSpec, table: str, exclude_tag: str) -> str | None:
    """The newest other cached release with a checksum-verified copy of `table`. Tags sort
    correctly as plain strings: `<source>-YYYY-MM-DD` sorts before its own `-2`, `-3`, ...
    same-day suffixes."""
    candidates = []
    for version_dir in cache.release_dirs(spec.name):
        tag = version_dir.name
        if tag == exclude_tag:
            continue
        manifest = cache.read_json(cache.manifest_path(spec.name, tag))
        entry = (manifest or {}).get("tables", {}).get(table)
        if entry and _cached_and_verified(cache, spec.name, tag, table, entry["sha256"]):
            candidates.append(tag)
    return max(candidates) if candidates else None


def _table_entry(manifest: dict[str, Any], spec: SourceSpec, table: str) -> dict[str, Any]:
    if table not in manifest["tables"]:
        close = difflib.get_close_matches(table, manifest["tables"], n=1)
        hint = f"; did you mean {close[0]!r}?" if close else ""
        raise ValueError(
            f"unknown table {table!r} for {spec.name}{hint} "
            f"known tables: {sorted(manifest['tables'])}"
        )
    return manifest["tables"][table]


def acquire_table(
    spec: SourceSpec,
    table: str,
    cache: Cache,
    client: Any,
    *,
    version: str | None = None,
    refresh: bool = False,
    offline: bool | None = None,
    now: datetime | None = None,
) -> Acquired:
    now = now or datetime.now(timezone.utc)
    offline = _resolve_offline(offline)
    manifest, resolved = acquire_manifest(
        spec, cache, client, version=version, refresh=refresh, offline=offline, now=now
    )
    entry = _table_entry(manifest, spec, table)
    if is_partitioned(entry):
        raise ValueError(
            f"{spec.name} {table!r} is published in per-season partitions; use acquire_partitions()"
        )
    path = cache.table_path(spec.name, resolved.tag, table)

    if _cached_and_verified(cache, spec.name, resolved.tag, table, entry["sha256"]):
        return Acquired(path=path, version=resolved.tag, fetched_at=_mtime(path), from_cache=True)
    if offline:
        raise DataNotAvailableError(
            f"{spec.name} {table} {resolved.tag}: not cached and offline=True"
        )
    try:
        client.download(entry["url"], path, sha256=entry["sha256"])
        _verify_table_schema(path, entry["columns"])
    except (SourceUnavailableError, ChecksumError, IncompatibleDataError) as e:
        fallback_tag = _find_fallback(cache, spec, table, exclude_tag=resolved.tag)
        if fallback_tag is None:
            raise DataNotAvailableError(
                f"{spec.name} {table} {resolved.tag}: could not fetch it, and no usable "
                "cached version exists"
            ) from e
        _warn_or_raise(StaleDataWarning(f"{spec.name} {table}: using cached {fallback_tag} ({e})"))
        fallback_path = cache.table_path(spec.name, fallback_tag, table)
        return Acquired(
            path=fallback_path,
            version=fallback_tag,
            fetched_at=_mtime(fallback_path),
            from_cache=True,
            fallback_reason=str(e),
        )
    return Acquired(path=path, version=resolved.tag, fetched_at=_mtime(path), from_cache=False)


def _mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


# ---- partitioned tables ---------------------------------------------------------------------

MAX_PARALLEL_DOWNLOADS = 4


def _object_ok(cache: Cache, source: str, partition: dict[str, Any]) -> bool:
    path = cache.object_path(source, partition["sha256"])
    return path.exists() and _sha256_file(path) == partition["sha256"]


def _find_partition_fallback(
    cache: Cache, spec: SourceSpec, table: str, key: str, exclude_tag: str
) -> tuple[str, Path] | None:
    """The newest other cached release that has a verified copy of this partition."""
    for version_dir in sorted(cache.release_dirs(spec.name), reverse=True):
        tag = version_dir.name
        if tag == exclude_tag:
            continue
        manifest = cache.read_json(cache.manifest_path(spec.name, tag))
        partition = (
            ((manifest or {}).get("tables", {}).get(table) or {}).get("partitions") or {}
        ).get(key)
        if partition and _object_ok(cache, spec.name, partition):
            return tag, cache.object_path(spec.name, partition["sha256"])
    return None


def _fetch_partition(
    client: Any, cache: Cache, spec: SourceSpec, partition: dict[str, Any], columns: dict[str, str]
) -> Exception | None:
    """Download one partition into the object store, verified (checksum, then columns). The
    error, if any, is returned rather than raised so a thread pool can collect all of them."""
    path = cache.object_path(spec.name, partition["sha256"])
    path.unlink(missing_ok=True)  # a stale or corrupt copy must not look verified
    try:
        client.download(partition["url"], path, sha256=partition["sha256"])
        _verify_table_schema(path, columns)
    except IncompatibleDataError as e:
        path.unlink(missing_ok=True)  # the store only ever holds verified files
        return e
    except (SourceUnavailableError, ChecksumError) as e:
        return e
    return None


def acquire_partitions(
    spec: SourceSpec,
    table: str,
    partitions: Any,
    cache: Cache,
    client: Any,
    *,
    version: str | None = None,
    refresh: bool = False,
    offline: bool | None = None,
    now: datetime | None = None,
) -> list[Acquired]:
    """Verified local Parquet files for the requested partitions (seasons) of a partitioned
    table, in the order requested (`partitions=None` means every partition).

    The release is resolved exactly as for `acquire_table`. Each partition is a file in the
    content-addressed object store (`Cache.object_path`): one whose bytes already match the
    manifest's SHA-256 is reused — even if it was downloaded for an older release that
    published the same partition — and the rest are downloaded, at most
    `MAX_PARALLEL_DOWNLOADS` at a time, and checked for SHA-256 and columns before being moved
    in. A partition that can't be fetched falls back to the newest other cached release's
    verified copy, with one `StaleDataWarning` naming every such partition (`strict` raises
    instead); with no such copy, `DataNotAvailableError`. Asking for a partition the release
    doesn't have raises `DataNotAvailableError` naming the ones it does.
    """
    now = now or datetime.now(timezone.utc)
    offline = _resolve_offline(offline)
    manifest, resolved = acquire_manifest(
        spec, cache, client, version=version, refresh=refresh, offline=offline, now=now
    )
    entry = _table_entry(manifest, spec, table)
    if not is_partitioned(entry):
        raise ValueError(f"{spec.name} {table!r} is not partitioned; use acquire_table()")

    available = partition_keys(entry)
    keys = available if partitions is None else normalize_partition_keys(partitions)
    unknown = [k for k in keys if k not in entry["partitions"]]
    if unknown:
        raise DataNotAvailableError(
            f"{spec.name} {table}: no data for {', '.join(unknown)} in {resolved.tag}; "
            f"available: {describe_partitions(available)}"
        )

    found: dict[str, Acquired] = {}
    missing: list[str] = []
    for key in keys:
        partition = entry["partitions"][key]
        if _object_ok(cache, spec.name, partition):
            path = cache.object_path(spec.name, partition["sha256"])
            found[key] = Acquired(path, resolved.tag, _mtime(path), True, partition=key)
        else:
            missing.append(key)

    if missing and offline:
        raise DataNotAvailableError(
            f"{spec.name} {table} {resolved.tag}: {', '.join(missing)} not cached and offline=True"
        )

    def fetch(key: str) -> Exception | None:
        return _fetch_partition(client, cache, spec, entry["partitions"][key], entry["columns"])

    if len(missing) > 1:
        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_DOWNLOADS) as pool:
            errors = list(pool.map(fetch, missing))
    else:
        errors = [fetch(key) for key in missing]

    fell_back: list[tuple[str, Exception]] = []
    for key, error in zip(missing, errors, strict=True):
        if error is None:
            path = cache.object_path(spec.name, entry["partitions"][key]["sha256"])
            found[key] = Acquired(path, resolved.tag, _mtime(path), False, partition=key)
            continue
        fallback = _find_partition_fallback(cache, spec, table, key, exclude_tag=resolved.tag)
        if fallback is None:
            raise DataNotAvailableError(
                f"{spec.name} {table} {key} {resolved.tag}: could not fetch it, and no usable "
                "cached version exists"
            ) from error
        tag, path = fallback
        found[key] = Acquired(path, tag, _mtime(path), True, str(error), partition=key)
        fell_back.append((key, error))

    if fell_back:
        names = ", ".join(key for key, _ in fell_back)
        _warn_or_raise(
            StaleDataWarning(
                f"{spec.name} {table}: using older cached data for {names} ({fell_back[0][1]})"
            )
        )
    return [found[key] for key in keys]
