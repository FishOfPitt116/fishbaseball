from datetime import datetime, timedelta, timezone

import pytest

from fishbaseball import config
from fishbaseball._core.cache import Cache, default_cache_dir


@pytest.fixture(autouse=True)
def reset_config():
    config._reset()
    yield
    config._reset()


@pytest.fixture
def cache(tmp_path):
    return Cache(root=tmp_path / "cache")


def test_default_cache_dir_uses_platformdirs_by_default():
    d = default_cache_dir()
    assert d.name == "fishbaseball"


def test_default_cache_dir_respects_config_override(tmp_path):
    config.set(cache_dir=tmp_path / "custom")
    assert default_cache_dir() == tmp_path / "custom"


def test_cache_root_created_lazily(tmp_path):
    root = tmp_path / "cache"
    Cache(root=root)
    assert not root.exists()  # not created until something is written


def test_paths(cache, tmp_path):
    assert cache.source_dir("lahman") == tmp_path / "cache" / "lahman"
    assert cache.version_dir("lahman", "lahman-2026-10-02") == (
        tmp_path / "cache" / "lahman" / "lahman-2026-10-02"
    )
    assert cache.table_path("lahman", "lahman-2026-10-02", "batting") == (
        tmp_path / "cache" / "lahman" / "lahman-2026-10-02" / "batting.parquet"
    )
    assert cache.manifest_path("lahman", "lahman-2026-10-02").name == "manifest.json"
    assert cache.pointer_path("lahman").name == "latest.json"


def test_write_and_read_json_roundtrip(cache):
    path = cache.pointer_path("lahman")
    cache.write_json_atomic(path, {"latest": "t1"})
    assert cache.read_json(path) == {"latest": "t1"}


def test_read_json_missing_file_is_none(cache):
    assert cache.read_json(cache.pointer_path("lahman")) is None


def test_read_json_corrupt_file_is_none_not_a_crash(cache):
    path = cache.pointer_path("lahman")
    path.parent.mkdir(parents=True)
    path.write_text("{not json")
    assert cache.read_json(path) is None


def test_write_json_atomic_leaves_no_partial_file_visible(cache):
    path = cache.pointer_path("lahman")
    cache.write_json_atomic(path, {"a": 1})
    siblings = list(path.parent.iterdir())
    assert siblings == [path]


def test_metadata_roundtrip(cache):
    assert cache.read_metadata() == {}
    cache.update_metadata("lahman", etag='"abc"', last_checked="2026-10-02T00:00:00Z")
    assert cache.get_metadata("lahman") == {
        "etag": '"abc"',
        "last_checked": "2026-10-02T00:00:00Z",
    }


def test_metadata_updates_do_not_clobber_other_sources(cache):
    cache.update_metadata("lahman", etag='"a"', last_checked="t1")
    cache.update_metadata("retrosheet", etag='"b"', last_checked="t2")
    assert cache.get_metadata("lahman")["etag"] == '"a"'
    assert cache.get_metadata("retrosheet")["etag"] == '"b"'


def test_metadata_partial_update_merges_fields(cache):
    cache.update_metadata("lahman", etag='"a"', last_checked="t1")
    cache.update_metadata("lahman", last_checked="t2")
    assert cache.get_metadata("lahman") == {"etag": '"a"', "last_checked": "t2"}


def test_get_metadata_for_unknown_source_is_none(cache):
    assert cache.get_metadata("nope") is None


def test_is_stale_with_no_metadata_is_stale(cache):
    assert cache.is_stale("lahman", ttl=3600, now=datetime.now(timezone.utc)) is True


def test_is_stale_within_ttl_is_fresh(cache):
    now = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)
    cache.update_metadata("lahman", etag=None, last_checked=now.isoformat())
    later = now + timedelta(seconds=100)
    assert cache.is_stale("lahman", ttl=3600, now=later) is False


def test_is_stale_past_ttl_is_stale(cache):
    now = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)
    cache.update_metadata("lahman", etag=None, last_checked=now.isoformat())
    later = now + timedelta(seconds=7200)
    assert cache.is_stale("lahman", ttl=3600, now=later) is True


def test_purge_one_version_removes_only_that_directory(cache):
    cache.write_json_atomic(cache.manifest_path("lahman", "t1"), {"tag": "t1"})
    cache.write_json_atomic(cache.manifest_path("lahman", "t2"), {"tag": "t2"})
    cache.purge("lahman", version="t1")
    assert not cache.version_dir("lahman", "t1").exists()
    assert cache.version_dir("lahman", "t2").exists()


def test_purge_source_removes_everything_for_it(cache):
    cache.write_json_atomic(cache.manifest_path("lahman", "t1"), {"tag": "t1"})
    cache.update_metadata("lahman", etag='"a"', last_checked="t1")
    cache.purge("lahman")
    assert not cache.source_dir("lahman").exists()
    assert cache.get_metadata("lahman") is None


def test_purge_source_does_not_touch_other_sources(cache):
    cache.write_json_atomic(cache.manifest_path("lahman", "t1"), {"tag": "t1"})
    cache.write_json_atomic(cache.manifest_path("retrosheet", "t1"), {"tag": "t1"})
    cache.purge("lahman")
    assert cache.version_dir("retrosheet", "t1").exists()


def test_purge_everything(cache, tmp_path):
    cache.write_json_atomic(cache.manifest_path("lahman", "t1"), {"tag": "t1"})
    cache.purge()
    assert not (tmp_path / "cache").exists()


def test_purge_missing_source_is_a_noop(cache):
    cache.purge("nope")  # doesn't raise


def test_info_lists_a_row_per_cached_version_with_size(cache):
    table = cache.table_path("lahman", "t1", "batting")
    table.parent.mkdir(parents=True)
    table.write_bytes(b"x" * 100)
    cache.write_json_atomic(cache.manifest_path("lahman", "t1"), {"tag": "t1"})
    rows = cache.info()
    assert len(rows) == 1
    row = rows[0]
    assert row["source"] == "lahman" and row["version"] == "t1"
    assert row["bytes"] >= 100
    assert row["tables"] == 1


def test_info_is_empty_for_a_fresh_cache(cache):
    assert cache.info() == []


def test_info_lists_multiple_sources_and_versions(cache):
    for source, tag in [("lahman", "t1"), ("lahman", "t2"), ("retrosheet", "t1")]:
        cache.write_json_atomic(cache.manifest_path(source, tag), {"tag": tag})
    rows = cache.info()
    assert {(r["source"], r["version"]) for r in rows} == {
        ("lahman", "t1"), ("lahman", "t2"), ("retrosheet", "t1"),
    }  # fmt: skip
