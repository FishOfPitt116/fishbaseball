"""`Provenance`: what `load(..., return_provenance=True)` returns alongside the DataFrame,
so a caller can tell exactly which release they got and why, without re-reading the manifest."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fishbaseball._core.acquire import Acquired


@dataclass(frozen=True)
class Provenance:
    source: str
    table: str
    version: str  # the release tag actually served
    fetched_at: datetime
    from_cache: bool
    fallback_reason: str | None
    url: str
    license: str
    attribution: str


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
