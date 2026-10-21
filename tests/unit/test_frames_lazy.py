from pathlib import Path

import pandas as pd
import polars as pl
import pytest

from fishbaseball._core.frames import filter_values, render, scan_files, select_columns


@pytest.fixture
def files(tmp_path: Path) -> list[Path]:
    paths = []
    for season, hr in ((1927, [60, 47]), (1956, [52, 37])):
        p = tmp_path / f"b_{season}.parquet"
        pl.DataFrame(
            {"season": [season, season], "id": ["a", "b"], "hr": hr},
            schema={"season": pl.Int16, "id": pl.String, "hr": pl.Int8},
        ).write_parquet(p)
        paths.append(p)
    return paths


def test_scan_files_concatenates_every_file_lazily(files):
    lf = scan_files(files)
    assert isinstance(lf, pl.LazyFrame)
    assert lf.collect().height == 4
    assert lf.collect_schema()["hr"] == pl.Int8


def test_scan_files_with_one_file(files):
    assert scan_files(files[:1]).collect().height == 2


def test_filter_values_works_on_lazy_frames_too(files):
    out = filter_values(scan_files(files), "id", ["a"])
    assert isinstance(out, pl.LazyFrame)
    assert out.collect()["hr"].to_list() == [60, 52]


def test_select_columns_keeps_the_requested_order(files):
    lf = select_columns(scan_files(files), ["hr", "id"], known=["season", "id", "hr"])
    assert lf.collect().columns == ["hr", "id"]


def test_select_columns_none_keeps_everything(files):
    lf = select_columns(scan_files(files), None, known=["season", "id", "hr"])
    assert lf.collect().columns == ["season", "id", "hr"]


def test_select_columns_rejects_unknown_names_with_a_suggestion(files):
    with pytest.raises(ValueError, match="did you mean 'hr'"):
        select_columns(scan_files(files), ["hrr"], known=["season", "id", "hr"])


def test_select_columns_rejects_a_bare_string(files):
    # "hr" would otherwise be iterated as "h", "r"
    with pytest.raises(ValueError, match="list of column names"):
        select_columns(scan_files(files), "hr", known=["season", "id", "hr"])


def test_render_eager_collects_to_the_backend(files):
    assert isinstance(render(scan_files(files), lazy=False, backend="polars"), pl.DataFrame)
    assert isinstance(render(scan_files(files), lazy=False, backend="pandas"), pd.DataFrame)


def test_render_lazy_returns_the_lazyframe_untouched(files):
    lf = scan_files(files)
    assert render(lf, lazy=True, backend="polars") is lf


def test_render_lazy_with_pandas_is_a_value_error(files):
    with pytest.raises(ValueError, match="lazy=True.*polars"):
        render(scan_files(files), lazy=True, backend="pandas")
