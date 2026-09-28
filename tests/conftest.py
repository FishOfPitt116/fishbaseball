import hashlib
import pathlib

import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "lahman"


@pytest.fixture
def fixtures() -> pathlib.Path:
    return FIXTURES


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
