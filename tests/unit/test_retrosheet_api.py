import pandas as pd
import polars as pl
import pytest

from fishbaseball import config, retrosheet
from fishbaseball._core.provenance import Provenance
from fishbaseball.exceptions import DataNotAvailableError
from tests.conftest import data_requests

RETRO_TABLES = [
    "all_players",
    "batting",
    "fielding",
    "game_info",
    "pitching",
    "plays",
    "team_stats",
]
PARTITIONED = ["batting", "fielding", "pitching", "plays", "team_stats"]


def fixture_df(retro_fixtures, name: str) -> pl.DataFrame:
    return pl.read_parquet(retro_fixtures / f"{name}.parquet")


# ---- general functions --------------------------------------------------------------------


def test_tables_lists_the_seven_retrosheet_tables(mock_release):
    assert retrosheet.tables() == RETRO_TABLES


def test_version_and_releases(mock_release):
    assert retrosheet.version() == "retrosheet-2026-10-20"
    releases = retrosheet.releases()
    assert releases["tag"].to_list() == ["retrosheet-2026-10-20"]


def test_load_one_season_of_a_partitioned_table(mock_release, retro_fixtures):
    df = retrosheet.load("plays", seasons=1956)
    assert isinstance(df, pl.DataFrame)
    assert df.equals(fixture_df(retro_fixtures, "plays_1956"))
    assert data_requests(mock_release) == [
        mock_release.manifest["tables"]["plays"]["partitions"]["1956"]["url"]
    ]


def test_load_accepts_lists_ranges_and_generators(mock_release):
    assert retrosheet.load("batting", seasons=[1927, 2001])["season"].unique().sort().to_list() == [
        1927,
        2001,
    ]
    assert retrosheet.load("batting", seasons=range(1956, 1957))["season"].unique().to_list() == [
        1956
    ]
    gen = (y for y in (1927, 1956))
    assert retrosheet.load("batting", seasons=gen)["season"].unique().sort().to_list() == [
        1927,
        1956,
    ]


@pytest.mark.parametrize("table", PARTITIONED)
def test_a_partitioned_table_needs_seasons_unless_all_seasons_or_lazy(mock_release, table):
    with pytest.raises(ValueError, match=rf"{table}.*seasons.*all_seasons=True.*lazy=True"):
        retrosheet.load(table)
    assert data_requests(mock_release) == []  # refused before downloading anything


def test_seasons_and_all_seasons_together_is_a_value_error(mock_release):
    with pytest.raises(ValueError, match="seasons.*all_seasons"):
        retrosheet.load("plays", seasons=1956, all_seasons=True)


def test_all_seasons_loads_every_published_season(mock_release):
    df = retrosheet.load("team_stats", all_seasons=True)
    assert df["season"].unique().sort().to_list() == [1927, 1956, 2001]


def test_whole_file_tables_need_no_seasons_and_filter_when_given(mock_release):
    assert retrosheet.load("game_info")["season"].unique().sort().to_list() == [1927, 1956, 2001]
    assert retrosheet.load("game_info", seasons=2001)["season"].unique().to_list() == [2001]


def test_a_season_that_was_never_published_names_what_is_available(mock_release):
    with pytest.raises(DataNotAvailableError, match=r"1999.*1927, 1956, 2001"):
        retrosheet.load("plays", seasons=1999)


def test_unknown_table_has_a_did_you_mean(mock_release):
    with pytest.raises(ValueError, match="did you mean 'plays'"):
        retrosheet.load("play", seasons=1956)


def test_columns_projects_and_keeps_the_requested_order(mock_release):
    df = retrosheet.load("plays", seasons=1956, columns=["event", "gid"])
    assert df.columns == ["event", "gid"]


def test_unknown_columns_are_a_value_error_with_a_suggestion(mock_release):
    with pytest.raises(ValueError, match="did you mean 'batter'"):
        retrosheet.load("plays", seasons=1956, columns=["batterr"])


def test_lazy_returns_a_lazyframe_over_the_cached_files(mock_release, retro_fixtures):
    lf = retrosheet.load("plays", seasons=[1927, 1956], lazy=True)
    assert isinstance(lf, pl.LazyFrame)
    expected = (
        fixture_df(retro_fixtures, "plays_1927").height
        + fixture_df(retro_fixtures, "plays_1956").height
    )
    assert lf.select(pl.len()).collect().item() == expected


def test_lazy_without_seasons_covers_every_season(mock_release):
    lf = retrosheet.load("plays", lazy=True)
    assert lf.select(pl.col("season").n_unique()).collect().item() == 3


def test_lazy_with_the_pandas_backend_fails_before_downloading(mock_release):
    config.set(backend="pandas")
    with pytest.raises(ValueError, match="lazy=True.*polars"):
        retrosheet.load("plays", seasons=1956, lazy=True)
    assert data_requests(mock_release) == []


def test_pandas_backend_returns_a_pandas_frame(mock_release):
    config.set(backend="pandas")
    assert isinstance(retrosheet.load("batting", seasons=1956), pd.DataFrame)


def test_a_second_call_makes_no_data_requests(mock_release):
    retrosheet.load("plays", seasons=[1927, 1956])
    before = len(mock_release.calls)
    retrosheet.load("plays", seasons=[1927, 1956])
    assert data_requests(mock_release, since=before) == []


# ---- plays --------------------------------------------------------------------------------


def test_plays_defaults_to_regular_season(mock_release):
    df = retrosheet.plays(1956)
    assert set(df["gametype"].unique()) == {"regular"}


def test_plays_game_type_none_includes_everything(mock_release):
    df = retrosheet.plays(1956, game_type=None)
    assert set(df["gametype"].unique()) == {"regular", "worldseries"}


def test_plays_game_type_accepts_a_list(mock_release):
    df = retrosheet.plays(1956, game_type=["regular", "worldseries"])
    assert set(df["gametype"].unique()) == {"regular", "worldseries"}
    assert set(retrosheet.plays(1956, game_type="worldseries")["gametype"]) == {"worldseries"}


def test_unknown_game_type_is_a_value_error_with_a_suggestion(mock_release):
    with pytest.raises(ValueError, match="did you mean 'regular'"):
        retrosheet.plays(1956, game_type="regulr")


def test_plays_team_matches_either_side_of_the_game(mock_release, retro_fixtures):
    raw = fixture_df(retro_fixtures, "plays_2001").filter(pl.col("gametype") == "regular")
    expected = raw.filter((pl.col("batteam") == "PIT") | (pl.col("pitteam") == "PIT"))
    got = retrosheet.plays(2001, team="PIT")
    assert got.height == expected.height > 0
    assert got.filter(pl.col("batteam") != "PIT").height > 0  # PIT pitching rows are in there
    assert got.filter(pl.col("pitteam") != "PIT").height > 0  # ...and PIT batting rows


def test_plays_team_accepts_a_list(mock_release):
    both = retrosheet.plays(2001, team=["PIT", "SFN"])
    assert both.height >= retrosheet.plays(2001, team="PIT").height


def test_plays_game_id_selects_one_game(mock_release):
    df = retrosheet.plays(1956, game_id="NYA195610080", game_type=None)
    assert df["gid"].unique().to_list() == ["NYA195610080"]
    assert df.height == 56  # both teams' plate appearances (27 of them Brooklyn's)


def test_plays_game_id_accepts_a_list(mock_release):
    df = retrosheet.plays(1956, game_id=["NYA195610080"], game_type=None)
    assert df["gid"].n_unique() == 1


def test_plays_columns_and_filters_combine_without_the_filter_columns(mock_release):
    df = retrosheet.plays(2001, team="PIT", columns=["gid", "event"])
    assert df.columns == ["gid", "event"] and df.height > 0


def test_plays_lazy_applies_filters_lazily(mock_release):
    lf = retrosheet.plays([1927, 1956], team="PIT", lazy=True, columns=["gid"])
    assert isinstance(lf, pl.LazyFrame)
    assert lf.collect().height > 0


def test_plays_all_seasons(mock_release):
    assert retrosheet.plays(all_seasons=True)["season"].n_unique() == 3


def test_plays_without_seasons_is_the_clear_error(mock_release):
    with pytest.raises(ValueError, match="seasons"):
        retrosheet.plays()


# ---- game_info ----------------------------------------------------------------------------


def test_game_info_team_matches_visitor_or_home(mock_release, retro_fixtures):
    raw = fixture_df(retro_fixtures, "game_info").filter(pl.col("gametype") == "regular")
    expected = raw.filter((pl.col("visteam") == "PIT") | (pl.col("hometeam") == "PIT"))
    got = retrosheet.game_info(team="PIT")
    assert got.height == expected.height > 0
    assert got.filter(pl.col("visteam") == "PIT").height > 0
    assert got.filter(pl.col("hometeam") == "PIT").height > 0


def test_game_info_defaults_to_regular_and_none_returns_all(mock_release):
    assert set(retrosheet.game_info()["gametype"].unique()) == {"regular"}
    assert "worldseries" in set(retrosheet.game_info(game_type=None)["gametype"].unique())


def test_game_info_seasons_and_game_id(mock_release):
    df = retrosheet.game_info(1956, game_id="NYA195610080", game_type=None)
    assert df.height == 1 and df["season"].to_list() == [1956]


# ---- stat tables --------------------------------------------------------------------------


def test_batting_season_totals_for_ruth_and_bonds(mock_release):
    ruth = retrosheet.batting(1927, player_id="ruthb101")
    assert ruth["b_hr"].sum() == 60
    bonds = retrosheet.batting(2001, player_id="bondb001")
    assert bonds["b_hr"].sum() == 73


def test_batting_game_type_default_leaves_out_the_world_series(mock_release):
    with_ws = retrosheet.batting(1927, player_id="ruthb101", game_type=None)
    assert with_ws["b_hr"].sum() == 62  # 60 regular season + 2 in the World Series
    ws_only = retrosheet.batting(1927, player_id="ruthb101", game_type="worldseries")
    assert ws_only["b_hr"].sum() == 2


def test_stattype_defaults_to_value(mock_release):
    df = retrosheet.batting(1927, player_id="ruthb101", game_type=None)
    assert df["stattype"].unique().to_list() == ["value"]


def test_stattype_can_be_overridden_with_one_value_a_list_or_none(mock_release):
    official = retrosheet.batting(1927, stattype="official", game_type=None)
    assert official["stattype"].unique().to_list() == ["official"]
    every = retrosheet.batting(1927, stattype=None, game_type=None)
    assert set(every["stattype"]) == {"value", "official"}
    both = retrosheet.batting(1927, stattype=["value", "official"], game_type=None)
    assert both.height == every.height


def test_batting_team_and_player_filters(mock_release):
    df = retrosheet.batting(1956, team="BRO", game_id="NYA195610080", game_type=None)
    assert df["team"].unique().to_list() == ["BRO"]
    assert df["b_pa"].sum() == 27 and df["b_h"].sum() == 0 and df["b_w"].sum() == 0


def test_larsens_perfect_game(mock_release):
    pit = retrosheet.pitching(1956, player_id="larsd102", game_id="NYA195610080", game_type=None)
    assert pit["p_ipouts"].sum() == 27 and pit["p_h"].sum() == 0


def test_pitching_and_team_stats_share_the_stat_filters(mock_release):
    assert set(retrosheet.pitching(2001, team="PIT")["team"]) == {"PIT"}
    ts = retrosheet.team_stats(2001, team="PIT")
    assert set(ts["team"]) == {"PIT"} and set(ts["stattype"]) == {"value"}
    assert ts["gametype"].unique().to_list() == ["regular"]


def test_fielding_position_by_number_or_name(mock_release):
    by_number = retrosheet.fielding(2001, team="PIT", position=6)
    by_name = retrosheet.fielding(2001, team="PIT", position="SS")
    assert by_number.height == by_name.height > 0
    assert by_number["d_pos"].unique().to_list() == [6]
    both = retrosheet.fielding(2001, team="PIT", position=["SS", 2])
    assert set(both["d_pos"].unique()) == {2, 6}


def test_unknown_fielding_position_is_a_value_error(mock_release):
    with pytest.raises(ValueError, match="position"):
        retrosheet.fielding(2001, position="shortstop")


def test_position_is_only_for_fielding(mock_release):
    with pytest.raises(ValueError, match="no filter 'position'"):
        retrosheet.batting(2001, position=6)


def test_an_unsupported_filter_suggests_the_right_name(mock_release):
    with pytest.raises(ValueError, match="did you mean 'player_id'"):
        retrosheet.batting(2001, playerid="bondb001")


def test_stat_tables_need_seasons(mock_release):
    for fn in (retrosheet.batting, retrosheet.pitching, retrosheet.fielding, retrosheet.team_stats):
        with pytest.raises(ValueError, match="seasons"):
            fn()


# ---- all_players --------------------------------------------------------------------------


def test_all_players_filters(mock_release):
    ruth = retrosheet.all_players(player_id="ruthb101")
    assert ruth["id"].unique().to_list() == ["ruthb101"] and ruth.height >= 1
    nya = retrosheet.all_players(1927, team="NYA")
    assert set(nya["team"]) == {"NYA"} and set(nya["season"]) == {1927}


def test_all_players_has_no_game_type(mock_release):
    with pytest.raises(ValueError, match="no filter 'game_type'"):
        retrosheet.all_players(game_type="regular")


# ---- provenance ---------------------------------------------------------------------------


def test_multi_season_provenance_lists_every_partition(mock_release):
    df, prov = retrosheet.plays([1927, 1956], return_provenance=True)
    assert isinstance(df, pl.DataFrame) and isinstance(prov, Provenance)
    assert (prov.source, prov.table, prov.version) == (
        "retrosheet",
        "plays",
        "retrosheet-2026-10-20",
    )
    assert [p.partition for p in prov.partitions] == ["1927", "1956"]
    assert all(p.version == prov.version and not p.from_cache for p in prov.partitions)
    assert prov.from_cache is False and prov.fallback_reason is None
    assert "Retrosheet" in prov.attribution and "www.retrosheet.org" in prov.attribution
    assert "NOTICE" in prov.license


def test_provenance_reports_which_partitions_came_from_cache(mock_release):
    retrosheet.plays(1927)
    _, prov = retrosheet.plays([1927, 1956], return_provenance=True)
    assert {p.partition: p.from_cache for p in prov.partitions} == {"1927": True, "1956": False}
    assert prov.from_cache is False  # at least one partition hit the network


def test_provenance_for_a_whole_file_table_has_no_partitions(mock_release):
    _, prov = retrosheet.game_info(return_provenance=True)
    assert prov.partitions == () and prov.table == "game_info" and prov.url.endswith(".parquet")


def test_lazy_results_carry_provenance_too(mock_release):
    lf, prov = retrosheet.plays(1956, lazy=True, return_provenance=True)
    assert isinstance(lf, pl.LazyFrame) and prov.partitions[0].partition == "1956"


# ---- game_id and the game_type default ------------------------------------------------------

LARSEN = "NYA195610080"  # a 1956 World Series game


def test_asking_for_a_game_by_id_ignores_the_regular_season_default(mock_release):
    assert retrosheet.plays(1956, game_id=LARSEN).height == 56
    assert retrosheet.game_info(1956, game_id=LARSEN)["gid"].to_list() == [LARSEN]
    assert retrosheet.batting(1956, game_id=LARSEN, team="BRO")["b_pa"].sum() == 27
    assert retrosheet.pitching(1956, game_id=LARSEN).height == 2
    assert retrosheet.fielding(1956, game_id=LARSEN).height > 0
    assert retrosheet.team_stats(1956, game_id=LARSEN).height == 2


def test_game_id_lists_also_skip_the_default(mock_release):
    assert retrosheet.plays(1956, game_id=[LARSEN]).height == 56


def test_an_explicit_game_type_still_applies_with_a_game_id(mock_release):
    assert retrosheet.plays(1956, game_id=LARSEN, game_type="regular").height == 0
    assert retrosheet.plays(1956, game_id=LARSEN, game_type="worldseries").height == 56
    assert retrosheet.plays(1956, game_id=LARSEN, game_type=None).height == 56


def test_without_a_game_id_the_default_is_still_the_regular_season(mock_release):
    assert set(retrosheet.plays(1956)["gametype"]) == {"regular"}
    assert set(retrosheet.game_info(1956)["gametype"]) == {"regular"}
