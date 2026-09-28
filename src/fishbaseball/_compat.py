"""Which published `schema_version`s this version of the package can read, per source.

Bump this (and release) before a data repo publishes a new schema version. `latest.json`'s
`by_schema` then keeps installs pinned to an old-supported version working: they resolve to
the last release of the newest schema version they support, not the newest release overall.
"""

from __future__ import annotations

SUPPORTED_SCHEMAS: dict[str, set[int]] = {
    "lahman": {1},
}
