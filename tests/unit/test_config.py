from pathlib import Path

import pytest

from fishbaseball import config


@pytest.fixture(autouse=True)
def reset_config():
    config._reset()
    yield
    config._reset()


def test_defaults():
    assert config.get("backend") == "polars"
    assert config.get("cache_dir") is None
    assert config.get("offline") is False
    assert config.get("strict") is False
    assert config.get("ttl") == 7 * 24 * 3600


def test_set_and_get_roundtrip():
    config.set(backend="pandas", offline=True, strict=True, ttl=60)
    assert config.get("backend") == "pandas"
    assert config.get("offline") is True
    assert config.get("strict") is True
    assert config.get("ttl") == 60


def test_set_cache_dir_converts_to_path():
    config.set(cache_dir="/tmp/somewhere")
    assert config.get("cache_dir") == Path("/tmp/somewhere")


def test_set_cache_dir_none_is_allowed_and_resets_to_default():
    config.set(cache_dir="/tmp/somewhere")
    config.set(cache_dir=None)
    assert config.get("cache_dir") is None


def test_invalid_backend_rejected():
    with pytest.raises(ValueError, match="backend"):
        config.set(backend="excel")
    assert config.get("backend") == "polars"  # unchanged


def test_non_positive_ttl_rejected():
    with pytest.raises(ValueError, match="ttl"):
        config.set(ttl=0)
    with pytest.raises(ValueError, match="ttl"):
        config.set(ttl=-1)


def test_unknown_key_rejected_on_set_and_get():
    with pytest.raises(ValueError, match="unknown"):
        config.set(nope=True)
    with pytest.raises(ValueError, match="unknown"):
        config.get("nope")


def test_set_partial_leaves_other_keys_unchanged():
    config.set(strict=True)
    config.set(offline=True)
    assert config.get("strict") is True
    assert config.get("offline") is True


def test_set_is_atomic_across_keys_in_one_call():
    with pytest.raises(ValueError, match="ttl"):
        config.set(strict=True, ttl=-1)
    assert config.get("strict") is False  # neither change applied
