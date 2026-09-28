import inspect
import json

import httpx
import polars as pl
import respx

from fishbaseball import lahman
from fishbaseball._core.acquire import manifest_url, pointer_url
from fishbaseball._core.provenance import Provenance
from fishbaseball.lahman._source import SOURCE


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


def test_every_manifest_table_has_a_wrapper(fixtures):
    manifest = json.loads((fixtures / "manifest.json").read_text())
    missing = [t for t in manifest["tables"] if not callable(getattr(lahman, t, None))]
    assert missing == []


@respx.mock
def test_batting_wrapper_filters_by_season_and_player(fixtures):
    mock_routes(respx.mock, fixtures)
    df = lahman.batting(1927, player_id="ruthba01")
    assert df["hr"].to_list() == [60]


@respx.mock
def test_batting_wrapper_with_no_args_returns_everything(fixtures):
    mock_routes(respx.mock, fixtures)
    all_rows = lahman.load("batting").height
    assert lahman.batting().height == all_rows


@respx.mock
def test_batting_wrapper_team_and_lg_filters(fixtures):
    mock_routes(respx.mock, fixtures)
    df = lahman.batting(1927, team_id="NYA", lg_id="AL")
    assert set(df["team_id"].to_list()) <= {"NYA"}


@respx.mock
def test_batting_wrapper_return_provenance_still_filters(fixtures):
    mock_routes(respx.mock, fixtures)
    df, prov = lahman.batting(1927, player_id="ruthba01", return_provenance=True)
    assert df["hr"].to_list() == [60]
    assert isinstance(prov, Provenance)


@respx.mock
def test_people_wrapper_has_player_id_but_no_season_or_team(fixtures):
    mock_routes(respx.mock, fixtures)
    df = lahman.people(player_id="ruthba01")
    assert df["player_id"].to_list() == ["ruthba01"]
    sig = inspect.signature(lahman.people)
    assert "seasons" not in sig.parameters
    assert "team_id" not in sig.parameters
    assert "lg_id" not in sig.parameters


@respx.mock
def test_teams_wrapper_has_season_and_team_and_lg_but_no_player(fixtures):
    mock_routes(respx.mock, fixtures)
    df = lahman.teams(2025, team_id="NYA")
    assert set(df["year_id"].to_list()) <= {2025}
    sig = inspect.signature(lahman.teams)
    assert "player_id" not in sig.parameters
    assert "seasons" in sig.parameters and "team_id" in sig.parameters and "lg_id" in sig.parameters


def test_teams_franchises_wrapper_has_no_filters_at_all():
    sig = inspect.signature(lahman.teams_franchises)
    assert set(sig.parameters) <= {"load_kwargs"} or all(
        p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
    )


def test_awards_players_wrapper_has_no_team_id():
    sig = inspect.signature(lahman.awards_players)
    assert "team_id" not in sig.parameters
    assert (
        "player_id" in sig.parameters and "lg_id" in sig.parameters and "seasons" in sig.parameters
    )


def test_seasons_is_the_first_positional_argument_on_batting():
    sig = inspect.signature(lahman.batting)
    first = next(iter(sig.parameters))
    assert first == "seasons"
    assert sig.parameters["seasons"].kind in (
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.POSITIONAL_ONLY,
    )


@respx.mock
def test_load_still_works_for_a_table_added_before_its_wrapper_exists(fixtures, monkeypatch):
    # simulate an upstream table with no dedicated wrapper: load() is still the fallback.
    mock_routes(respx.mock, fixtures)
    assert isinstance(lahman.load("teams"), pl.DataFrame)


@respx.mock
def test_wrapper_filters_work_with_pandas_backend(fixtures):
    from fishbaseball import config

    mock_routes(respx.mock, fixtures)
    config.set(backend="pandas")
    df = lahman.batting(1927, player_id="ruthba01")
    import pandas as pd

    assert isinstance(df, pd.DataFrame)
    assert df["hr"].tolist() == [60]
