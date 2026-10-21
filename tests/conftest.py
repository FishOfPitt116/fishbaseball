import hashlib
import json
import pathlib

import httpx
import pytest
import respx

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "lahman"
RETRO_FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "retrosheet"


@pytest.fixture
def fixtures() -> pathlib.Path:
    return FIXTURES


@pytest.fixture
def retro_fixtures() -> pathlib.Path:
    return RETRO_FIXTURES


def sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):
    """Every test gets its own cache dir and a config reset, so tests never share state or
    touch the real user cache. Individual tests may still override config as needed."""
    from fishbaseball import _client, config

    config._reset()
    config.set(cache_dir=tmp_path / "fb-cache")
    _client._reset_client()
    yield
    config._reset()
    _client._reset_client()


@pytest.fixture
def mock_release(retro_fixtures):
    """Route the pointer, manifest and every data file to the Retrosheet fixtures, inside an
    active `respx` mock. Yields the manifest; `mock.calls` shows what was requested."""
    manifest = json.loads((retro_fixtures / "manifest.json").read_text())
    pointer = json.loads((retro_fixtures / "latest.json").read_text())
    from fishbaseball._core.acquire import manifest_url, pointer_url
    from fishbaseball.retrosheet._source import SOURCE

    with respx.mock(assert_all_called=False) as mock:
        mock.get(pointer_url(SOURCE)).mock(return_value=httpx.Response(200, json=pointer))
        mock.get(manifest_url(SOURCE, manifest["tag"])).mock(
            return_value=httpx.Response(200, json=manifest)
        )
        for entry in manifest["tables"].values():
            for e in entry["partitions"].values() if entry.get("partitioned") else [entry]:
                body = (retro_fixtures / e["file"]).read_bytes()
                mock.get(e["url"]).mock(return_value=httpx.Response(200, content=body))
        mock.manifest = manifest  # type: ignore[attr-defined]
        yield mock


def data_requests(mock, since: int = 0) -> list[str]:
    """Data-file URLs requested so far (or after the first `since` calls)."""
    urls = [str(c.request.url) for c in list(mock.calls)[since:]]
    return [u for u in urls if u.endswith(".parquet")]
