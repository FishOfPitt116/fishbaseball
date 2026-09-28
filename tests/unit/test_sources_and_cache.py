import json

import httpx
import pandas as pd
import polars as pl
import pytest
import respx

from fishbaseball import cache as fb_cache
from fishbaseball import config
from fishbaseball._core.acquire import manifest_url, pointer_url
from fishbaseball._core.cache import Cache
from fishbaseball.lahman._source import SOURCE
from fishbaseball.sources import sources


def _mock(respx_mock, fixtures):
    manifest = json.loads((fixtures / "manifest.json").read_text())
    latest = json.loads((fixtures / "latest.json").read_text())
    tag = manifest["tag"]
    respx_mock.get(pointer_url(SOURCE)).mock(return_value=httpx.Response(200, json=latest))
    respx_mock.get(manifest_url(SOURCE, tag)).mock(return_value=httpx.Response(200, json=manifest))
    for name in ("batting", "people", "teams", "salaries"):
        url = manifest["tables"][name]["url"]
        body = (fixtures / f"{name}.parquet").read_bytes()
        respx_mock.get(url).mock(return_value=httpx.Response(200, content=body))
    return manifest, tag


# ---- sources() -----------------------------------------------------------------------


def test_sources_with_nothing_cached_shows_unknown_state():
    df = sources()
    assert isinstance(df, pl.DataFrame)
    row = df.filter(pl.col("source") == "lahman").row(0, named=True)
    assert row["local"] is None and row["latest"] is None and row["last_checked"] is None


def test_sources_never_hits_the_network():
    with respx.mock(assert_all_called=False) as mock:
        sources()
        assert len(mock.calls) == 0


@respx.mock
def test_sources_reflects_local_and_latest_after_a_load(fixtures):
    from fishbaseball import lahman

    manifest, tag = _mock(respx.mock, fixtures)
    lahman.load("batting")
    df = sources()
    row = df.filter(pl.col("source") == "lahman").row(0, named=True)
    assert row["local"] == tag and row["latest"] == tag
    assert row["last_checked"] is not None


def test_sources_respects_pandas_backend():
    config.set(backend="pandas")
    df = sources()
    assert isinstance(df, pd.DataFrame)


# ---- cache.info() ----------------------------------------------------------------------


def test_cache_info_empty_by_default():
    df = fb_cache.info()
    assert isinstance(df, pl.DataFrame) and df.height == 0
    assert set(df.columns) == {
        "source", "version", "table", "bytes", "last_checked", "next_check",
    }  # fmt: skip


@respx.mock
def test_cache_info_after_a_load_has_a_row_per_table(fixtures):
    from fishbaseball import lahman

    manifest, tag = _mock(respx.mock, fixtures)
    lahman.load("batting")
    lahman.load("people")
    df = fb_cache.info()
    rows = df.filter(pl.col("source") == "lahman")
    assert set(rows["table"].to_list()) == {"batting", "people"}
    row = rows.filter(pl.col("table") == "batting").row(0, named=True)
    assert row["version"] == tag and row["bytes"] > 0


@respx.mock
def test_cache_info_shows_last_checked_and_next_check(fixtures):
    from fishbaseball import lahman

    _mock(respx.mock, fixtures)
    lahman.load("batting")
    df = fb_cache.info()
    row = df.filter(pl.col("source") == "lahman").row(0, named=True)
    assert row["last_checked"] is not None
    assert row["next_check"] > row["last_checked"]


def test_cache_info_last_checked_is_none_when_never_checked():
    Cache().table_path("lahman", "t1", "batting").parent.mkdir(parents=True)
    Cache().table_path("lahman", "t1", "batting").write_bytes(b"x")
    df = fb_cache.info()
    row = df.row(0, named=True)
    assert row["last_checked"] is None and row["next_check"] is None


# ---- cache.purge() ----------------------------------------------------------------------


@respx.mock
def test_cache_purge_source_removes_it(fixtures):
    from fishbaseball import lahman

    _mock(respx.mock, fixtures)
    lahman.load("batting")
    fb_cache.purge("lahman")
    assert fb_cache.info().height == 0


def test_cache_purge_everything_is_a_noop_on_empty_cache():
    fb_cache.purge()  # doesn't raise


# ---- cache.prefetch() -------------------------------------------------------------------


@respx.mock
def test_cache_prefetch_downloads_named_tables_without_calling_load(fixtures):
    manifest, tag = _mock(respx.mock, fixtures)
    fb_cache.prefetch(source="lahman", tables=["batting", "people"])
    assert Cache().table_path("lahman", tag, "batting").exists()
    assert Cache().table_path("lahman", tag, "people").exists()
    assert not Cache().table_path("lahman", tag, "teams").exists()


@respx.mock
def test_cache_prefetch_default_fetches_every_table_in_the_manifest(fixtures):
    manifest, tag = _mock(respx.mock, fixtures)
    fb_cache.prefetch(source="lahman", tables=["batting", "people", "teams", "salaries"])
    for name in ("batting", "people", "teams", "salaries"):
        assert Cache().table_path("lahman", tag, name).exists()


def test_cache_prefetch_unknown_source_raises():
    with pytest.raises(ValueError, match="nope"):
        fb_cache.prefetch(source="nope")
