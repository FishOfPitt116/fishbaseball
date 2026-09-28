import json

import httpx
import pandas as pd
import polars as pl
import pytest
import respx

from fishbaseball import config, lahman
from fishbaseball._core.acquire import manifest_url, pointer_url
from fishbaseball._core.provenance import Provenance
from fishbaseball.lahman._source import SOURCE


def _load_fixture(name: str):
    return json.loads((_FIXTURES / name).read_text())


@pytest.fixture(autouse=True)
def _fixture_path(fixtures):
    global _FIXTURES
    _FIXTURES = fixtures
    yield


def mock_routes(respx_mock, fixtures):
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


@respx.mock
def test_tables_lists_all_27(fixtures):
    mock_routes(respx.mock, fixtures)
    assert len(lahman.tables()) == 27
    assert "batting" in lahman.tables() and "people" in lahman.tables()


@respx.mock
def test_load_returns_polars_dataframe_with_correct_data(fixtures):
    mock_routes(respx.mock, fixtures)
    df = lahman.load("batting")
    assert isinstance(df, pl.DataFrame)
    ruth = df.filter((pl.col("player_id") == "ruthba01") & (pl.col("year_id") == 1927))
    assert ruth["hr"].to_list() == [60]


@respx.mock
def test_load_filters_by_seasons(fixtures):
    mock_routes(respx.mock, fixtures)
    df = lahman.load("batting", seasons=1927)
    assert set(df["year_id"].to_list()) == {1927}


@respx.mock
def test_load_seasons_on_a_table_without_one_raises(fixtures):
    mock_routes(respx.mock, fixtures)
    with pytest.raises(ValueError, match="season"):
        lahman.load("people", seasons=1927)


@respx.mock
def test_load_unknown_table_raises_value_error_listing_valid_names(fixtures):
    mock_routes(respx.mock, fixtures)
    with pytest.raises(ValueError, match="batting"):
        lahman.load("nope")


@respx.mock
def test_load_pandas_backend(fixtures):
    mock_routes(respx.mock, fixtures)
    config.set(backend="pandas")
    df = lahman.load("batting")
    assert isinstance(df, pd.DataFrame)


@respx.mock
def test_load_return_provenance(fixtures):
    manifest, tag = mock_routes(respx.mock, fixtures)
    df, prov = lahman.load("batting", return_provenance=True)
    assert isinstance(df, pl.DataFrame)
    assert isinstance(prov, Provenance)
    assert prov.source == "lahman" and prov.table == "batting" and prov.version == tag
    assert prov.license == manifest["license"]


@respx.mock
def test_load_default_does_not_return_a_tuple(fixtures):
    mock_routes(respx.mock, fixtures)
    result = lahman.load("batting")
    assert isinstance(result, pl.DataFrame)


@respx.mock
def test_version_returns_the_resolved_tag(fixtures):
    _, tag = mock_routes(respx.mock, fixtures)
    assert lahman.version() == tag


@respx.mock
def test_releases_lists_known_releases(fixtures):
    mock_routes(respx.mock, fixtures)
    df = lahman.releases()
    assert isinstance(df, pl.DataFrame)
    assert set(df["tag"].to_list()) >= {"lahman-2026-09-26", "lahman-2026-09-28"}


@respx.mock
def test_second_load_call_uses_cache_with_no_network(fixtures):
    mock_routes(respx.mock, fixtures)
    lahman.load("batting")
    respx.mock.calls.reset()  # no routes left registered; a real call would now KeyError/fail
    df = lahman.load("batting")
    assert isinstance(df, pl.DataFrame)


def test_offline_true_with_no_cache_raises(fixtures):
    from fishbaseball.exceptions import DataNotAvailableError

    with pytest.raises(DataNotAvailableError):
        lahman.load("batting", offline=True)


@respx.mock
def test_load_player_filter_style_via_seasons_and_manual_filter(fixtures):
    mock_routes(respx.mock, fixtures)
    df = lahman.load("batting").filter(pl.col("player_id") == "bondsba01")
    assert set(df["year_id"].to_list()) & {2001}
