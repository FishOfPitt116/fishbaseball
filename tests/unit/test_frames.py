import pandas as pd
import polars as pl
import pytest

from fishbaseball._core.frames import filter_values, to_backend

DF = pl.DataFrame(
    {
        "player_id": ["ruthba01", "bondsba01", "aaronha01"],
        "year_id": [1927, 2001, 1974],
        "team_id": ["NYA", "SFN", "ATL"],
    }
)


def test_to_backend_polars_returns_the_same_frame():
    out = to_backend(DF, "polars")
    assert out is DF


def test_to_backend_pandas_converts():
    out = to_backend(DF, "pandas")
    assert isinstance(out, pd.DataFrame)
    assert list(out["player_id"]) == ["ruthba01", "bondsba01", "aaronha01"]


def test_to_backend_unknown_raises():
    with pytest.raises(ValueError, match="excel"):
        to_backend(DF, "excel")


def test_filter_values_none_is_a_noop():
    assert filter_values(DF, "year_id", None).equals(DF)


def test_filter_values_single_value():
    out = filter_values(DF, "player_id", "ruthba01")
    assert out["player_id"].to_list() == ["ruthba01"]


def test_filter_values_list_of_values():
    out = filter_values(DF, "year_id", [1927, 1974])
    assert set(out["year_id"].to_list()) == {1927, 1974}


def test_filter_values_empty_list_gives_empty_frame():
    out = filter_values(DF, "year_id", [])
    assert out.height == 0


def test_filter_values_range():
    out = filter_values(DF, "year_id", range(1974, 2001))
    assert set(out["year_id"].to_list()) == {1974}


def test_filter_values_generator():
    out = filter_values(DF, "year_id", (y for y in (1927, 2001)))
    assert set(out["year_id"].to_list()) == {1927, 2001}


def test_filter_values_numpy_array():
    np = pytest.importorskip("numpy")
    out = filter_values(DF, "year_id", np.array([1927, 2001]))
    assert set(out["year_id"].to_list()) == {1927, 2001}


def test_filter_values_string_is_still_one_value_not_iterated_over_chars():
    out = filter_values(DF, "player_id", "ruthba01")
    assert out["player_id"].to_list() == ["ruthba01"]
