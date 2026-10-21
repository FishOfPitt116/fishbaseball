"""`Provenance`: what `load(..., return_provenance=True)` returns alongside the DataFrame,
so a caller can tell exactly which release they got and why, without re-reading the manifest."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fishbaseball._core.acquire import Acquired


@dataclass(frozen=True)
class PartitionProvenance:
    """One partition (season) of a partitioned table, within a `Provenance`.

    Attributes:
        partition: the partition key, e.g. `"2024"`.
        version: the release tag this partition's file was served from (differs from the
            others' only if it fell back to an older cached release).
        url: where this file was downloaded from (may be an older release's URL: a release
            only re-publishes the partitions that changed).
        from_cache: `True` if this call didn't hit the network for the file.
        fallback_reason: `None` normally; otherwise why this partition's newer file couldn't
            be used and an older cached one was served.
    """

    partition: str
    version: str
    url: str
    from_cache: bool
    fallback_reason: str | None


@dataclass(frozen=True)
class Provenance:
    """Returned alongside the DataFrame from `load(..., return_provenance=True)`.

    Attributes:
        source: the source name, e.g. `"lahman"`.
        table: the table name, e.g. `"batting"`.
        version: the release tag actually served, e.g. `"lahman-2026-09-28"` — may differ
            from what was resolved if a fresh download failed and an older cached release
            was served instead (see `fallback_reason`).
        fetched_at: when this file was first downloaded (not necessarily this call).
        from_cache: `True` if this call didn't hit the network for the table itself.
        fallback_reason: `None` normally; otherwise why the newer release couldn't be used
            and this older cached one was served instead.
        url: where this table was downloaded from.
        license: the data's license, e.g. `"CC BY-SA 3.0"`.
        attribution: the exact attribution string to cite when using this data.
        partitions: for a table published in per-season partitions, one entry per partition
            this call used (empty otherwise). The top-level `version` is then the newest tag
            among them, `fetched_at` the oldest download time, `from_cache` is `True` only if
            every partition was, `fallback_reason` the first partition's if any fell back, and
            `url` the release download location of the first partition.
    """

    source: str
    table: str
    version: str
    fetched_at: datetime
    from_cache: bool
    fallback_reason: str | None
    url: str
    license: str
    attribution: str
    partitions: tuple[PartitionProvenance, ...] = ()


def build_provenance(
    source: str, table: str, manifest: dict[str, Any], acquired: Acquired
) -> Provenance:
    return Provenance(
        source=source,
        table=table,
        version=acquired.version,
        fetched_at=acquired.fetched_at,
        from_cache=acquired.from_cache,
        fallback_reason=acquired.fallback_reason,
        url=manifest["tables"][table]["url"],
        license=manifest["license"],
        attribution=manifest["attribution"],
    )


def build_partitioned_provenance(
    source: str, table: str, manifest: dict[str, Any], acquired: Sequence[Acquired]
) -> Provenance:
    """One `Provenance` for a multi-partition load (`acquired` is never empty)."""
    entry_partitions = manifest["tables"][table]["partitions"]
    parts = tuple(
        PartitionProvenance(
            partition=str(a.partition),
            version=a.version,
            url=entry_partitions[str(a.partition)]["url"],
            from_cache=a.from_cache,
            fallback_reason=a.fallback_reason,
        )
        for a in acquired
    )
    return Provenance(
        source=source,
        table=table,
        version=max(a.version for a in acquired),
        fetched_at=min(a.fetched_at for a in acquired),
        from_cache=all(a.from_cache for a in acquired),
        fallback_reason=next((a.fallback_reason for a in acquired if a.fallback_reason), None),
        url=parts[0].url.rsplit("/", 1)[0],
        license=manifest["license"],
        attribution=manifest["attribution"],
        partitions=parts,
    )
