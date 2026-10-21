"""Content-addressed partition storage: `<cache>/<source>/objects/<sha256>.parquet`, shared by
every release whose manifest references that sha, with per-release manifests alongside."""

import pytest

from fishbaseball._core.cache import Cache


@pytest.fixture
def cache(tmp_path):
    return Cache(root=tmp_path / "cache")


def manifest(tag: str, shas: dict[str, str], *, table: str = "plays") -> dict:
    return {
        "tag": tag,
        "tables": {
            table: {
                "partitioned": True,
                "partitions": {
                    season: {"sha256": sha, "bytes": 10} for season, sha in shas.items()
                },
            },
            "game_info": {"url": "u", "sha256": "z" * 64},
        },
    }


def put_object(cache: Cache, sha: str, size: int = 10) -> None:
    path = cache.object_path("retrosheet", sha)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


def put_release(cache: Cache, tag: str, shas: dict[str, str]) -> None:
    cache.write_json_atomic(cache.manifest_path("retrosheet", tag), manifest(tag, shas))


def test_object_path_is_content_addressed_under_the_source(cache, tmp_path):
    sha = "ab" * 32
    assert cache.object_path("retrosheet", sha) == (
        tmp_path / "cache" / "retrosheet" / "objects" / f"{sha}.parquet"
    )


def test_one_object_serves_every_release_that_references_it(cache):
    put_object(cache, "a" * 64)
    put_release(cache, "retrosheet-2026-10-20", {"1927": "a" * 64})
    put_release(cache, "retrosheet-2026-11-01", {"1927": "a" * 64})

    cache.purge("retrosheet", version="retrosheet-2026-10-20")
    assert cache.object_path("retrosheet", "a" * 64).exists()  # newer release still needs it

    cache.purge("retrosheet", version="retrosheet-2026-11-01")
    assert not cache.object_path("retrosheet", "a" * 64).exists()


def test_purging_a_release_removes_only_objects_nothing_else_references(cache):
    for sha in ("a" * 64, "b" * 64, "c" * 64):
        put_object(cache, sha)
    put_release(cache, "retrosheet-old", {"1927": "a" * 64, "1956": "b" * 64})
    put_release(cache, "retrosheet-new", {"1927": "a" * 64, "1956": "c" * 64})

    cache.purge("retrosheet", version="retrosheet-old")

    assert cache.object_path("retrosheet", "a" * 64).exists()  # shared with new
    assert not cache.object_path("retrosheet", "b" * 64).exists()  # only old used it
    assert cache.object_path("retrosheet", "c" * 64).exists()


def test_purging_a_whole_source_removes_its_objects_too(cache):
    put_object(cache, "a" * 64)
    put_release(cache, "retrosheet-x", {"1927": "a" * 64})
    cache.purge("retrosheet")
    assert not cache.source_dir("retrosheet").exists()


def test_info_reports_partition_counts_and_bytes_per_table(cache):
    put_object(cache, "a" * 64, size=100)
    put_object(cache, "b" * 64, size=50)
    put_release(cache, "retrosheet-x", {"1927": "a" * 64, "1956": "b" * 64, "2001": "c" * 64})

    rows = cache.info()

    assert rows == [
        {
            "source": "retrosheet",
            "version": "retrosheet-x",
            "table": "plays",
            "bytes": 150,
            "partitions": 2,  # 2001's object isn't cached
        }
    ]


def test_info_omits_partitioned_tables_with_nothing_cached_and_the_objects_dir(cache):
    put_release(cache, "retrosheet-x", {"1927": "a" * 64})
    assert cache.info() == []


def test_info_keeps_whole_file_rows_with_no_partition_count(cache):
    path = cache.table_path("lahman", "lahman-1", "batting")
    path.parent.mkdir(parents=True)
    path.write_bytes(b"x" * 7)
    assert cache.info() == [
        {
            "source": "lahman",
            "version": "lahman-1",
            "table": "batting",
            "bytes": 7,
            "partitions": None,
        }
    ]
