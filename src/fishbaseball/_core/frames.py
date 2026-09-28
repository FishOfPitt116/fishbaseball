"""DataFrame helpers shared by every source's public API: converting to the configured
backend on the way out, and the single/list-value filters used by `seasons`, `player_id`,
`team_id` and similar keyword filters."""

from __future__ import annotations

from typing import Any

import polars as pl


def to_backend(df: pl.DataFrame, backend: str) -> Any:
    if backend == "polars":
        return df
    if backend == "pandas":
        return df.to_pandas()
    raise ValueError(f"unknown backend {backend!r}")


def filter_values(df: pl.DataFrame, column: str, values: Any) -> pl.DataFrame:
    """`values` may be `None` (no filter), a single value, or a list/tuple/set of values."""
    if values is None:
        return df
    if not isinstance(values, (list, tuple, set)):
        values = [values]
    return df.filter(pl.col(column).is_in(list(values)))
