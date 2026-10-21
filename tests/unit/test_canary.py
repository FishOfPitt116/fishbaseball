"""The downstream canary's Retrosheet checks, run against the fixture release instead of the
live one (the script is not part of the package, so it is loaded from scripts/)."""

import importlib.util
import json
from pathlib import Path

import httpx
import pytest
import respx

from fishbaseball._core.acquire import pointer_url
from fishbaseball.retrosheet._source import SOURCE

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "canary.py"


@pytest.fixture(scope="module")
def canary():
    spec = importlib.util.spec_from_file_location("canary_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_retrosheet_checks_pass_on_a_healthy_release(canary, mock_release, capsys):
    assert canary.run_retrosheet_checks() == []
    out = capsys.readouterr().out
    assert "retrosheet-2026-10-20" in out
    for table in ("plays", "batting", "game_info", "all_players", "team_stats"):
        assert f"load({table!r})" in out
    assert "73" in out  # Bonds' 2001 home runs


def test_retrosheet_checks_report_a_schema_this_package_cannot_read(canary, retro_fixtures, capsys):
    pointer = json.loads((retro_fixtures / "latest.json").read_text())
    pointer["by_schema"] = {"2": "retrosheet-2027-01-01"}
    with respx.mock(assert_all_called=False) as mock:
        mock.get(pointer_url(SOURCE)).mock(return_value=httpx.Response(200, json=pointer))
        failures = canary.run_retrosheet_checks()
    assert len(failures) == 1 and "SchemaChangedError" in failures[0]


def test_a_failing_table_is_reported_without_stopping_the_others(
    canary,
    retro_fixtures,
    mock_release,
    capsys,
):
    manifest = mock_release.manifest
    url = manifest["tables"]["batting"]["partitions"]["2001"]["url"]
    mock_release.get(url).mock(return_value=httpx.Response(200, content=b"corrupt"))

    failures = canary.run_retrosheet_checks()

    assert any("load('batting')" in f for f in failures)
    assert not any("load('plays')" in f for f in failures)


def test_run_checks_skips_retrosheet_when_the_installed_package_predates_it(
    canary, monkeypatch, capsys
):
    import fishbaseball as fb

    monkeypatch.delattr(fb, "retrosheet")
    assert canary.run_retrosheet_checks() == []
    assert "skip" in capsys.readouterr().out.lower()
