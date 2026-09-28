"""Sanity checks on the fixture data itself, so a bad regeneration fails loudly here rather
than as a confusing failure somewhere else."""

import json
from pathlib import Path

import polars as pl

from tests.conftest import sha256_file


def manifest(fixtures: Path) -> dict:
    return json.loads((fixtures / "manifest.json").read_text())


def test_fixture_parquet_matches_its_manifest_sha256(fixtures: Path):
    m = manifest(fixtures)
    for name in ("batting", "people", "teams", "salaries"):
        entry = m["tables"][name]
        assert sha256_file(fixtures / f"{name}.parquet") == entry["sha256"]
        assert entry["url"].startswith("https://fixtures.test/")


def test_fixture_urls_point_at_the_same_tag(fixtures: Path):
    m = manifest(fixtures)
    tag = m["tag"]
    for name in ("batting", "people", "teams", "salaries"):
        assert f"/{tag}/" in m["tables"][name]["url"]


def test_manifest_lists_all_27_tables_but_only_four_are_downloadable(fixtures: Path):
    m = manifest(fixtures)
    assert len(m["tables"]) == 27
    on_disk = {p.stem for p in fixtures.glob("*.parquet")}
    assert on_disk == {"batting", "people", "teams", "salaries"}


def test_ruth_1927_and_bonds_2001_and_aaron_career(fixtures: Path):
    b = pl.read_parquet(fixtures / "batting.parquet")
    ruth = b.filter((pl.col("player_id") == "ruthba01") & (pl.col("year_id") == 1927))
    assert ruth["hr"].to_list() == [60]
    bonds = b.filter((pl.col("player_id") == "bondsba01") & (pl.col("year_id") == 2001))
    assert bonds["hr"].to_list() == [73]
    aaron = b.filter(pl.col("player_id") == "aaronha01")
    assert aaron["hr"].sum() == 755


def test_people_has_the_three_golden_players(fixtures: Path):
    p = pl.read_parquet(fixtures / "people.parquet")
    assert set(p["player_id"]) == {"ruthba01", "bondsba01", "aaronha01"}


def test_teams_has_a_full_2025_season(fixtures: Path):
    t = pl.read_parquet(fixtures / "teams.parquet")
    latest = t.filter(pl.col("year_id") == 2025)
    assert latest.height >= 30


def test_latest_json_points_at_the_manifest_tag(fixtures: Path):
    m = manifest(fixtures)
    latest = json.loads((fixtures / "latest.json").read_text())
    assert latest["latest"] == m["tag"]
    assert latest["by_schema"]["1"] == m["tag"]
    assert {r["tag"] for r in latest["releases"]} >= {m["tag"]}
