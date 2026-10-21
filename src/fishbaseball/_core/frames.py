"""DataFrame helpers shared by every source's public API: converting to the configured
backend on the way out, and the single/list-value filters used by `seasons`, `player_id`,
`team_id` and similar keyword filters."""

from __future__ import annotations

import difflib
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, TypeVar

import polars as pl

Frame = TypeVar("Frame", pl.DataFrame, pl.LazyFrame)


def to_backend(df: pl.DataFrame, backend: str) -> Any:
    if backend == "polars":
        return df
    if backend == "pandas":
        return df.to_pandas()
    raise ValueError(f"unknown backend {backend!r}")


def as_list(values: Any) -> list[Any]:
    """One value, or any non-string iterable of values, as a list."""
    if isinstance(values, (str, bytes)) or not hasattr(values, "__iter__"):
        return [values]
    return list(values)


def filter_values(df: Frame, column: str, values: Any) -> Frame:
    """`values` may be `None` (no filter), a single value, or any non-string iterable of
    values — a list, tuple, set, `range`, generator, numpy array, and so on. A string or
    bytes value is treated as one value, not iterated character by character."""
    if values is None:
        return df
    return df.filter(pl.col(column).is_in(as_list(values)))


def scan_files(paths: Iterable[Path]) -> pl.LazyFrame:
    """All of these Parquet files (same columns) as one lazy frame: nothing is read until it's
    collected, and then only the columns and row groups the query needs."""
    return pl.scan_parquet([str(p) for p in paths])


def select_columns(
    lf: pl.LazyFrame, columns: Sequence[str] | None, *, known: Iterable[str]
) -> pl.LazyFrame:
    """Project `columns` (in the order given); `None` keeps them all. Unknown names are a
    `ValueError` with a did-you-mean, rather than polars's late `ColumnNotFoundError`."""
    if columns is None:
        return lf
    if isinstance(columns, (str, bytes)):
        raise ValueError(f"columns must be a list of column names, not the string {columns!r}")
    known = list(known)
    for name in columns:
        if name not in known:
            close = difflib.get_close_matches(name, known, n=1)
            hint = f"; did you mean {close[0]!r}?" if close else ""
            raise ValueError(f"unknown column {name!r}{hint} known columns: {known}")
    return lf.select(list(columns))


def render(lf: pl.LazyFrame, *, lazy: bool, backend: str) -> Any:
    """The finished result: the `LazyFrame` itself if `lazy`, else collected and converted to
    the configured backend. A lazy frame only exists in polars."""
    if lazy:
        if backend != "polars":
            raise ValueError(
                f"lazy=True returns a polars LazyFrame, but the configured backend is {backend!r}; "
                "use fb.config.set(backend='polars') or drop lazy=True"
            )
        return lf
    return to_backend(lf.collect(), backend)
