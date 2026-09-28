"""`Provenance`: what `load(..., return_provenance=True)` returns alongside the DataFrame,
so a caller can tell exactly which release they got and why, without re-reading the manifest."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fishbaseball._core.acquire import Acquired


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
