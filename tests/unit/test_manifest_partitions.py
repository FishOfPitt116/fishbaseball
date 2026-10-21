"""Partitioned manifest entries (Retrosheet) and the helpers around them. Unpartitioned
entries (all of Lahman) must keep working unchanged."""

import json

import pytest

from fishbaseball._compat import SUPPORTED_SCHEMAS
from fishbaseball._core.manifest import (
    describe_partitions,
    is_partitioned,
    normalize_partition_keys,
    partition_keys,
)
from tests.conftest import sha256_file


def retro_manifest(retro_fixtures) -> dict:
    return json.loads((retro_fixtures / "manifest.json").read_text())


def test_retrosheet_schema_1_is_supported():
    assert SUPPORTED_SCHEMAS["retrosheet"] == {1}


def test_partitioned_entries_are_recognized(retro_fixtures):
    tables = retro_manifest(retro_fixtures)["tables"]
    for name in ("plays", "batting", "pitching", "fielding", "team_stats"):
        assert is_partitioned(tables[name])
    for name in ("game_info", "all_players"):
        assert not is_partitioned(tables[name])


def test_lahman_entries_are_not_partitioned(fixtures):
    tables = json.loads((fixtures / "manifest.json").read_text())["tables"]
    assert not any(is_partitioned(e) for e in tables.values())


def test_partition_keys_are_sorted_numerically(retro_fixtures):
    entry = retro_manifest(retro_fixtures)["tables"]["plays"]
    assert partition_keys(entry) == ["1927", "1956", "2001"]
    assert partition_keys({"partitions": {"1000": {}, "999": {}, "2000": {}}}) == [
        "999",
        "1000",
        "2000",
    ]


def test_retrosheet_fixture_files_match_the_manifest(retro_fixtures):
    tables = retro_manifest(retro_fixtures)["tables"]
    for name, entry in tables.items():
        files = [e for e in entry["partitions"].values()] if is_partitioned(entry) else [entry]
        for f in files:
            assert sha256_file(retro_fixtures / f["file"]) == f["sha256"]
            assert f["url"].startswith("https://fixtures.test/")


def test_normalize_partition_keys_accepts_scalars_and_iterables():
    assert normalize_partition_keys(2024) == ["2024"]
    assert normalize_partition_keys("2024") == ["2024"]
    assert normalize_partition_keys([2024, 2023]) == ["2024", "2023"]
    assert normalize_partition_keys(range(2020, 2023)) == ["2020", "2021", "2022"]
    assert normalize_partition_keys(y for y in (1999, 2000)) == ["1999", "2000"]
    assert normalize_partition_keys([2024, 2024, "2024"]) == ["2024"]  # deduplicated


def test_describe_partitions_compresses_ranges():
    assert describe_partitions(["1897", "1898", "1899"]) == "1897-1899"
    assert describe_partitions(["1927", "1956", "2001"]) == "1927, 1956, 2001"
    assert describe_partitions(["1897", "1898", "1899", "2001"]) == "1897-1899, 2001"
    assert describe_partitions(["2001"]) == "2001"


@pytest.mark.parametrize("bad", [None, 3.5])
def test_normalize_partition_keys_rejects_unusable_values(bad):
    with pytest.raises((TypeError, ValueError)):
        normalize_partition_keys(bad)
