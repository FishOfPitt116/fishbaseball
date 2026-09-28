"""Hits the real published fishbaseball-data release. Run with: pytest tests/integration"""

import re

import polars as pl
import pytest

from fishbaseball import cache as fb_cache
from fishbaseball import config, lahman
from fishbaseball.exceptions import DataNotAvailableError

pytestmark = pytest.mark.integration

TAG_RE = re.compile(r"^lahman-\d{4}-\d{2}-\d{2}(-\d+)?$")


@pytest.fixture(autouse=True)
def _live_check():
    import httpx

    try:
        httpx.get("https://github.com", timeout=10).raise_for_status()
    except httpx.HTTPError as e:
        pytest.skip(f"GitHub unreachable: {e}")


def test_tables_lists_the_real_catalog():
    names = lahman.tables()
    assert len(names) == 27
    assert "batting" in names and "people" in names


def test_load_batting_has_ruth_1927():
    df = lahman.load("batting")
    assert isinstance(df, pl.DataFrame)
    ruth = df.filter((pl.col("player_id") == "ruthba01") & (pl.col("year_id") == 1927))
    assert ruth["hr"].to_list() == [60]


def test_batting_wrapper_matches_the_doc_example():
    df = lahman.batting(1927, player_id="ruthba01")
    assert df["hr"].to_list() == [60]


def test_version_returns_a_well_formed_tag():
    tag = lahman.version()
    assert TAG_RE.match(tag), tag


def test_releases_lists_at_least_the_known_releases():
    df = lahman.releases()
    tags = set(df["tag"].to_list())
    assert {"lahman-2026-09-26", "lahman-2026-09-28"} <= tags


def test_offline_works_after_a_warm_up_load():
    lahman.load("people")  # warms the cache
    df = lahman.load("people", offline=True)
    assert isinstance(df, pl.DataFrame) and df.height > 0


def test_pin_by_sabr_version():
    df = lahman.load("teams", version="2025")
    assert isinstance(df, pl.DataFrame) and df.height > 0


def test_pin_by_exact_date():
    df = lahman.load("teams", version="2026-09-28")
    assert isinstance(df, pl.DataFrame) and df.height > 0


def test_offline_with_a_never_loaded_source_and_empty_cache_raises(tmp_path):
    config.set(cache_dir=tmp_path / "empty")
    with pytest.raises(DataNotAvailableError):
        lahman.load("schools", offline=True)


def test_cache_info_reflects_real_loads():
    lahman.load("salaries")
    df = fb_cache.info()
    row = df.filter(pl.col("source") == "lahman").row(0, named=True)
    assert row["tables"] >= 1 and row["bytes"] > 0
