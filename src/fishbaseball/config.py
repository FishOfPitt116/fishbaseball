"""Global, process-wide settings: `fb.config.set(...)` / `fb.config.get(key)`.

A plain module-level singleton, not a class the user instantiates, matching `fb.config.set(...)`
rather than `fb.Config().set(...)`. Every source and cache access reads through here, so a
setting applies immediately to whatever runs next.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, Literal

Backend = Literal["polars", "pandas"]

_BACKENDS: frozenset[Backend] = frozenset({"polars", "pandas"})
DEFAULT_TTL_SECONDS = 7 * 24 * 3600


@dataclasses.dataclass
class _Config:
    backend: Backend = "polars"
    cache_dir: Path | None = None  # None -> platformdirs default, resolved by cache.py
    offline: bool = False
    strict: bool = False  # raise instead of warning + falling back on a refresh problem
    ttl: float = DEFAULT_TTL_SECONDS  # seconds before a pointer is checked again


_config = _Config()
_KEYS = frozenset(f.name for f in dataclasses.fields(_Config))


def _check_key(key: str) -> None:
    if key not in _KEYS:
        raise ValueError(f"unknown config key {key!r}; valid keys: {sorted(_KEYS)}")


def get(key: str) -> Any:
    """The current value of a setting."""
    _check_key(key)
    return getattr(_config, key)


def set(**kwargs: Any) -> None:  # noqa: A001 - `fb.config.set(...)` is the intended spelling
    """Update one or more settings. Rejects unknown keys and invalid values; on a rejection,
    no setting from this call is applied (partial updates never happen)."""
    updates: dict[str, Any] = {}
    for key, value in kwargs.items():
        _check_key(key)
        if key == "backend":
            if value not in _BACKENDS:
                raise ValueError(f"backend must be one of {sorted(_BACKENDS)}, got {value!r}")
        elif key == "cache_dir":
            if value is not None:
                value = Path(value)
        elif key == "ttl":
            ttl: float = value
            if ttl <= 0:
                raise ValueError(f"ttl must be positive, got {ttl!r}")
        updates[key] = value
    for key, value in updates.items():
        setattr(_config, key, value)


def _reset() -> None:
    """Test-only: restore defaults."""
    global _config
    _config = _Config()
