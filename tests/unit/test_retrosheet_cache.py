"""`fb.sources()`, `fb.cache.*` and offline behavior for the partitioned Retrosheet source."""

import polars as pl
import pytest

from fishbaseball import cache as fb_cache
from fishbaseball import config, retrosheet
from fishbaseball.exceptions import DataNotAvailableError
from fishbaseball.sources import sources
from tests.conftest import data_requests


def retro_row(df: pl.DataFrame, **match) -> pl.DataFrame:
    for column, value in match.items():
        df = df.filter(pl.col(column) == value)
    return df


def test_sources_has_a_retrosheet_row_with_nothing_cached():
    row = sources().filter(pl.col("source") == "retrosheet").row(0, named=True)
    assert row["local"] is None and row["latest"] is None and row["last_checked"] is None


def test_sources_shows_local_and_latest_after_a_load(mock_release):
    retrosheet.plays(1956)
    row = sources().filter(pl.col("source") == "retrosheet").row(0, named=True)
    assert row["local"] == row["latest"] == "retrosheet-2026-10-20"
    assert row["released"] == "2026-10-20T23:49:09Z"
    assert row["last_checked"] is not None


def test_sources_never_hits_the_network(mock_release):
    sources()
    assert len(mock_release.calls) == 0


# ---- prefetch ---------------------------------------------------------------------------


def test_prefetch_selected_seasons_of_a_table_then_work_offline(mock_release):
    fb_cache.prefetch("retrosheet", tables=["plays"], seasons=[1927, 1956])
    assert len(data_requests(mock_release)) == 2

    config.set(offline=True)
    assert retrosheet.plays([1927, 1956]).height > 0
    with pytest.raises(DataNotAvailableError, match="2001.*offline"):
        retrosheet.plays(2001)


def test_prefetch_with_no_seasons_takes_every_season(mock_release):
    fb_cache.prefetch("retrosheet", tables=["batting"])
    assert len(data_requests(mock_release)) == 3


def test_prefetch_with_no_tables_takes_every_table(mock_release):
    fb_cache.prefetch("retrosheet")
    # 5 partitioned tables x 3 seasons + game_info + all_players
    assert len(data_requests(mock_release)) == 17
    config.set(offline=True)
    assert retrosheet.game_info().height > 0
    assert retrosheet.fielding(all_seasons=True).height > 0


def test_prefetch_seasons_is_ignored_by_whole_file_tables(mock_release):
    fb_cache.prefetch("retrosheet", tables=["game_info"], seasons=[1927])
    assert len(data_requests(mock_release)) == 1
    config.set(offline=True)
    assert retrosheet.game_info()["season"].n_unique() == 3  # the whole file, all seasons


def test_prefetch_unknown_season_names_what_is_published(mock_release):
    with pytest.raises(DataNotAvailableError, match=r"1999.*1927, 1956, 2001"):
        fb_cache.prefetch("retrosheet", tables=["plays"], seasons=[1999])


def test_prefetch_unknown_table_has_a_did_you_mean(mock_release):
    with pytest.raises(ValueError, match="did you mean 'plays'"):
        fb_cache.prefetch("retrosheet", tables=["play"])


def test_prefetch_still_rejects_an_unknown_source():
    with pytest.raises(ValueError, match="unknown source"):
        fb_cache.prefetch("statcast")


# ---- cache.info / purge -------------------------------------------------------------------


def test_cache_info_counts_partitions_per_table(mock_release):
    retrosheet.plays([1927, 1956])
    retrosheet.game_info()
    df = fb_cache.info()
    plays = retro_row(df, source="retrosheet", table="plays").row(0, named=True)
    assert plays["partitions"] == 2 and plays["bytes"] > 0
    assert plays["version"] == "retrosheet-2026-10-20"
    game_info = retro_row(df, source="retrosheet", table="game_info").row(0, named=True)
    assert game_info["partitions"] is None
    assert retro_row(df, table="batting").height == 0  # nothing of it is cached


def test_cache_info_grows_as_more_partitions_arrive(mock_release):
    retrosheet.plays(1927)
    first = retro_row(fb_cache.info(), table="plays").row(0, named=True)
    retrosheet.plays(2001)
    second = retro_row(fb_cache.info(), table="plays").row(0, named=True)
    assert (first["partitions"], second["partitions"]) == (1, 2)
    assert second["bytes"] > first["bytes"]


def test_purging_the_release_removes_the_shared_partition_files(mock_release):
    retrosheet.plays([1927, 1956])
    fb_cache.purge("retrosheet", version="retrosheet-2026-10-20")
    assert fb_cache.info().height == 0
    config.set(offline=True)
    with pytest.raises(DataNotAvailableError):
        retrosheet.plays(1927)


def test_purging_the_source_empties_it(mock_release):
    retrosheet.plays(1927)
    fb_cache.purge("retrosheet")
    assert fb_cache.info().height == 0
