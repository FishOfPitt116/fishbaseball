"""Resolve a `latest.json` pointer to a specific release tag, either the newest one this
package's `_compat.SUPPORTED_SCHEMAS` can read, or a pin the caller asked for.

A pin is either a release date (`"2026-10-02"`, matching a tag `<source>-2026-10-02`) or a
SABR-style upstream version (`"2025"`, resolving to the newest non-withdrawn release of that
version). See `fishbaseball-data`'s manifest docs for the pointer/manifest JSON shapes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from fishbaseball.exceptions import IncompatibleDataError, SchemaChangedError

DATE_PIN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ---- partitioned tables ---------------------------------------------------------------
#
# A manifest table entry is either one file (`url`, `sha256`, ...) or, for sources whose big
# tables are published per season, `{"partitioned": true, "partitions": {"1927": {url,
# sha256, bytes, rows, ...}, ...}, "columns": ..., "season_column": ...}`. Partition keys are
# strings (the season) so they survive JSON; callers pass ints freely and `normalize_partition_keys`
# makes them match.


def is_partitioned(entry: dict[str, Any]) -> bool:
    return bool(entry.get("partitioned"))


def _natural(key: str) -> tuple[int, int | str]:
    return (0, int(key)) if key.isdigit() else (1, key)


def partition_keys(entry: dict[str, Any]) -> list[str]:
    """A partitioned entry's partition keys, in numeric order for year-like keys."""
    return sorted(entry["partitions"], key=_natural)


def normalize_partition_keys(values: Any) -> list[str]:
    """One partition, or any non-string iterable of them (list, `range`, generator, numpy
    array, ...), as a deduplicated list of manifest keys in the order given. Ints and digit
    strings are both fine (`2024` and `"2024"` are the same partition)."""
    if isinstance(values, (str, bytes)) or not hasattr(values, "__iter__"):
        values = [values]
    keys: list[str] = []
    for v in values:
        if isinstance(v, bool) or not isinstance(v, (int, str)) and not hasattr(v, "__index__"):
            raise TypeError(f"seasons must be integers (or digit strings), not {v!r}")
        key = str(int(v)) if not isinstance(v, str) else v
        if key not in keys:
            keys.append(key)
    return keys


def describe_partitions(keys: list[str]) -> str:
    """`["1897", "1898", "1899", "2001"]` -> `"1897-1899, 2001"`, for error messages."""
    ordered = sorted(keys, key=_natural)
    if not all(k.isdigit() for k in ordered):
        return ", ".join(ordered)
    runs: list[list[int]] = []
    for n in map(int, ordered):
        if runs and n == runs[-1][1] + 1:
            runs[-1][1] = n
        else:
            runs.append([n, n])
    return ", ".join(str(a) if a == b else (f"{a}, {b}" if b == a + 1 else f"{a}-{b}") for a, b in runs)


@dataclass(frozen=True)
class Resolved:
    tag: str
    is_latest: bool
    latest_tag: str | None
    withdrawn: bool = False


def _releases(pointer: dict[str, Any]) -> list[dict[str, Any]]:
    return pointer.get("releases") or []


def _check_schema(release: dict[str, Any], supported: set[int]) -> None:
    version = release["schema_version"]
    if version not in supported:
        raise IncompatibleDataError(
            f"release {release['tag']!r} uses schema_version {version}, but this version of "
            f"fishbaseball supports {sorted(supported)}. Upgrade fishbaseball to read it."
        )


def _resolve_latest_compatible(pointer: dict[str, Any], supported: set[int]) -> Resolved:
    by_schema: dict[str, str] = pointer.get("by_schema", {})
    compatible = {int(k): v for k, v in by_schema.items() if int(k) in supported}
    if not compatible:
        published = sorted(int(k) for k in by_schema)
        raise SchemaChangedError(
            f"none of the published schema versions {published} are supported by this "
            f"version of fishbaseball (supports {sorted(supported)}). Upgrade fishbaseball."
        )
    tag = compatible[max(compatible)]
    latest = pointer.get("latest")
    return Resolved(tag=tag, is_latest=(tag == latest), latest_tag=latest)


def _resolve_date_pin(pointer: dict[str, Any], pin: str, supported: set[int]) -> Resolved:
    source = pointer["source"]
    tag = f"{source}-{pin}"
    latest = pointer.get("latest")
    release = next((r for r in _releases(pointer) if r["tag"] == tag), None)
    if release is None:
        # Predates the releases index, or an unindexed tag; let the caller try to fetch it.
        return Resolved(tag=tag, is_latest=(tag == latest), latest_tag=latest)
    _check_schema(release, supported)
    return Resolved(
        tag=tag, is_latest=(tag == latest), latest_tag=latest, withdrawn=bool(release["withdrawn"])
    )


def _resolve_version_pin(pointer: dict[str, Any], pin: str, supported: set[int]) -> Resolved:
    candidates = [r for r in _releases(pointer) if r["version"] == pin and not r.get("withdrawn")]
    if not candidates:
        raise ValueError(
            f"no release found for version {pin!r} (and it isn't a YYYY-MM-DD release date)"
        )
    best = max(candidates, key=lambda r: r["built_at"])
    _check_schema(best, supported)
    latest = pointer.get("latest")
    return Resolved(tag=best["tag"], is_latest=(best["tag"] == latest), latest_tag=latest)


def resolve(pointer: dict[str, Any], supported: set[int], *, pin: str | None = None) -> Resolved:
    if pin is None:
        return _resolve_latest_compatible(pointer, supported)
    if DATE_PIN.match(pin):
        return _resolve_date_pin(pointer, pin, supported)
    return _resolve_version_pin(pointer, pin, supported)
