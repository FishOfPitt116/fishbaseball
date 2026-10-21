"""Hits the real published Retrosheet release. Run with: pytest tests/integration"""

import re

import polars as pl
import pytest

from fishbaseball import cache as fb_cache
from fishbaseball import config, retrosheet
from fishbaseball.exceptions import DataNotAvailableError

pytestmark = pytest.mark.integration

TAG_RE = re.compile(r"^retrosheet-\d{4}-\d{2}-\d{2}(-\d+)?$")
LARSEN = "NYA195610080"  # Don Larsen's perfect game, 1956 World Series game 5


@pytest.fixture(autouse=True)
def _live_check():
    import httpx

    try:
        httpx.get("https://github.com", timeout=10).raise_for_status()
    except httpx.HTTPError as e:
        pytest.skip(f"GitHub unreachable: {e}")


def test_tables_lists_the_real_catalog():
    assert retrosheet.tables() == [
        "all_players",
        "batting",
        "fielding",
        "game_info",
        "pitching",
        "plays",
        "team_stats",
    ]


def test_version_is_a_well_formed_tag():
    assert TAG_RE.match(retrosheet.version())


def test_ruth_hit_60_home_runs_in_1927():
    df = retrosheet.batting(1927, player_id="ruthb101")
    assert df["b_hr"].sum() == 60


def test_ruth_hit_two_more_in_the_1927_world_series():
    df = retrosheet.batting(1927, player_id="ruthb101", game_type="worldseries")
    assert df["b_hr"].sum() == 2


def test_bonds_hit_73_home_runs_in_2001():
    df = retrosheet.batting(2001, player_id="bondb001")
    assert df["b_hr"].sum() == 73


def test_larsens_perfect_game():
    batting = retrosheet.batting(1956, game_id=LARSEN, team="BRO", game_type=None)
    assert batting["b_pa"].sum() == 27
    assert batting["b_h"].sum() == 0 and batting["b_w"].sum() == 0
    plays = retrosheet.plays(1956, game_id=LARSEN, game_type=None)
    assert plays["gid"].unique().to_list() == [LARSEN]
    assert plays.filter(pl.col("batteam") == "BRO")["pa"].sum() == 27


def test_2025_has_2430_regular_season_games():
    assert retrosheet.game_info(2025).height == 2430


def test_a_second_call_needs_no_network():
    retrosheet.plays(2024, team="PIT")
    again = retrosheet.plays(2024, team="PIT", offline=True)
    assert again.height > 0


def test_offline_with_an_empty_cache_raises(tmp_path):
    config.set(cache_dir=tmp_path / "empty")
    with pytest.raises(DataNotAvailableError):
        retrosheet.plays(2024, offline=True)


def test_lazy_over_ten_seasons_aggregates_correctly():
    seasons = range(2015, 2025)
    lf = retrosheet.batting(seasons, lazy=True, game_type=None, stattype=None)
    per_season = lf.group_by("season").len().sort("season").collect()
    assert per_season["season"].to_list() == list(seasons)
    counts = dict(per_season.iter_rows())
    assert counts[2020] < 40_000  # the 60-game season
    assert all(n > 70_000 for season, n in counts.items() if season != 2020)

    hr = retrosheet.batting(seasons, lazy=True).group_by("season").agg(pl.col("b_hr").sum())
    by_season = dict(hr.collect().iter_rows())
    assert 5_000 < by_season[2019] < 6_900  # the 2019 record: 6,776 MLB home runs


def test_multi_season_provenance_names_every_partition():
    _, prov = retrosheet.team_stats([2023, 2024], return_provenance=True)
    assert [p.partition for p in prov.partitions] == ["2023", "2024"]
    assert TAG_RE.match(prov.version)
    assert "Retrosheet" in prov.attribution


def test_cache_info_shows_the_partitions_that_were_loaded():
    retrosheet.team_stats([2023, 2024])
    row = (
        fb_cache.info()
        .filter((pl.col("source") == "retrosheet") & (pl.col("table") == "team_stats"))
        .row(0, named=True)
    )
    assert row["partitions"] == 2 and row["bytes"] > 0
