"""`fb.sources()`: a status view of every known source, read entirely from the local cache —
it never touches the network, so it's safe and instant to call at any time.
"""

from __future__ import annotations

from typing import Any

import polars as pl

from fishbaseball import config
from fishbaseball._core.acquire import SourceSpec
from fishbaseball._core.cache import Cache
from fishbaseball._core.frames import to_backend
from fishbaseball.lahman._source import SOURCE as _LAHMAN_SOURCE

REGISTRY: dict[str, SourceSpec] = {"lahman": _LAHMAN_SOURCE}

_SCHEMA = {
    "source": pl.Utf8,
    "local": pl.Utf8,
    "latest": pl.Utf8,
    "released": pl.Utf8,
    "last_checked": pl.Utf8,
}


def _local_version(cache: Cache, source: str) -> str | None:
    """The newest tag that actually has a manifest cached on disk (not just referenced by a
    pointer) — what you have, as opposed to `latest`, which is what's published."""
    source_dir = cache.source_dir(source)
    if not source_dir.is_dir():
        return None
    tags = [
        d.name for d in source_dir.iterdir()
        if d.is_dir() and cache.manifest_path(source, d.name).exists()
    ]  # fmt: skip
    return max(tags) if tags else None


def sources() -> Any:
    cache = Cache()
    rows = []
    for name in sorted(REGISTRY):
        pointer = cache.read_json(cache.pointer_path(name))
        meta = cache.get_metadata(name)
        latest = pointer.get("latest") if pointer else None
        released = None
        if pointer and latest:
            match = next((r for r in pointer.get("releases", []) if r["tag"] == latest), None)
            released = match["built_at"] if match else None
        rows.append(
            {
                "source": name,
                "local": _local_version(cache, name),
                "latest": latest,
                "released": released,
                "last_checked": (meta or {}).get("last_checked"),
            }
        )
    df = pl.DataFrame(rows, schema=_SCHEMA)
    return to_backend(df, config.get("backend"))
