import hashlib
from datetime import datetime, timedelta, timezone

import polars as pl
import pytest

from fishbaseball import config
from fishbaseball._core.acquire import Acquired, SourceSpec, acquire_manifest, acquire_table
from fishbaseball._core.cache import Cache
from fishbaseball._core.http import JsonResponse
from fishbaseball.exceptions import (
    ChecksumError,
    DataNotAvailableError,
    SchemaChangedError,
    SourceUnavailableError,
    StaleDataWarning,
)

SPEC = SourceSpec(name="lahman", repo="o/fishbaseball-data")
NOW = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def make_table_bytes(rows: int = 1) -> bytes:
    import io

    buf = io.BytesIO()
    pl.DataFrame(
        {"player_id": ["ruthba01"] * rows, "hr": [60] * rows},
        schema={"player_id": pl.String, "hr": pl.Int32},
    ).write_parquet(buf)
    return buf.getvalue()


def make_manifest(tag: str, *, table_bytes: bytes, schema_version: int = 1) -> dict:
    return {
        "tag": tag,
        "schema_version": schema_version,
        "tables": {
            "batting": {
                "url": f"https://dl.test/{tag}/batting.parquet",
                "sha256": sha(table_bytes),
                "columns": {"player_id": "String", "hr": "Int32"},
            }
        },
    }


def make_pointer(latest: str, *, by_schema=None, releases=None) -> dict:
    return {
        "source": "lahman",
        "latest": latest,
        "by_schema": by_schema or {"1": latest},
        "releases": releases
        or [
            {
                "tag": latest,
                "version": "2025",
                "schema_version": 1,
                "built_at": "t",
                "withdrawn": False,
            }
        ],
    }


class FakeClient:
    """json_routes: url -> JsonResponse | Exception (or list, consumed in order).
    file_routes: url -> bytes | Exception (or list, consumed in order)."""

    def __init__(self, json_routes=None, file_routes=None):
        self.json_routes = {
            k: list(v) if isinstance(v, list) else [v] for k, v in (json_routes or {}).items()
        }
        self.file_routes = {
            k: list(v) if isinstance(v, list) else [v] for k, v in (file_routes or {}).items()
        }
        self.json_calls: list[tuple[str, str | None]] = []
        self.download_calls: list[str] = []

    def get_json(self, url, *, etag=None):
        self.json_calls.append((url, etag))
        item = self.json_routes[url].pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def download(self, url, dest, *, sha256):
        self.download_calls.append(url)
        item = self.file_routes[url].pop(0)
        if isinstance(item, Exception):
            raise item
        digest = hashlib.sha256(item).hexdigest()
        if digest != sha256:
            raise ChecksumError(f"{url}: sha mismatch")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(item)
        return dest


@pytest.fixture(autouse=True)
def reset_config():
    config._reset()
    yield
    config._reset()


@pytest.fixture
def cache(tmp_path) -> Cache:
    return Cache(root=tmp_path / "cache")


def pointer_url() -> str:
    from fishbaseball._core.acquire import pointer_url as f

    return f(SPEC)


def manifest_url(tag: str) -> str:
    from fishbaseball._core.acquire import manifest_url as f

    return f(SPEC, tag)


# ---- acquire_manifest: fresh cache, normal refresh flow ---------------------------------


def test_first_call_fetches_pointer_and_manifest_over_the_network(cache):
    tag = "lahman-2026-10-02"
    table_bytes = make_table_bytes()
    manifest = make_manifest(tag, table_bytes=table_bytes)
    client = FakeClient(
        json_routes={
            pointer_url(): JsonResponse(json=make_pointer(tag), etag='"p1"', not_modified=False),
            manifest_url(tag): JsonResponse(json=manifest, etag=None, not_modified=False),
        }
    )
    got, resolved = acquire_manifest(SPEC, cache, client, offline=False, now=NOW)
    assert got == manifest and resolved.tag == tag and resolved.is_latest is True
    assert cache.read_json(cache.pointer_path("lahman")) == make_pointer(tag)
    assert cache.read_json(cache.manifest_path("lahman", tag)) == manifest
    assert cache.get_metadata("lahman")["etag"] == '"p1"'


def test_second_call_within_ttl_uses_cache_with_no_network(cache):
    tag = "lahman-2026-10-02"
    manifest = make_manifest(tag, table_bytes=make_table_bytes())
    cache.write_json_atomic(cache.pointer_path("lahman"), make_pointer(tag))
    cache.write_json_atomic(cache.manifest_path("lahman", tag), manifest)
    cache.update_metadata("lahman", etag='"p1"', last_checked=NOW.isoformat())
    client = FakeClient()
    got, resolved = acquire_manifest(
        SPEC, cache, client, offline=False, now=NOW + timedelta(hours=1)
    )
    assert got == manifest and resolved.tag == tag
    assert client.json_calls == []


def test_past_ttl_sends_conditional_get_and_304_touches_last_checked(cache):
    tag = "lahman-2026-10-02"
    manifest = make_manifest(tag, table_bytes=make_table_bytes())
    cache.write_json_atomic(cache.pointer_path("lahman"), make_pointer(tag))
    cache.write_json_atomic(cache.manifest_path("lahman", tag), manifest)
    cache.update_metadata("lahman", etag='"p1"', last_checked=NOW.isoformat())
    later = NOW + timedelta(days=8)
    client = FakeClient(
        json_routes={pointer_url(): JsonResponse(json=None, etag='"p1"', not_modified=True)}
    )
    acquire_manifest(SPEC, cache, client, offline=False, now=later)
    assert client.json_calls == [(pointer_url(), '"p1"')]
    assert cache.get_metadata("lahman")["last_checked"] == later.isoformat()


def test_past_ttl_200_response_replaces_the_cached_pointer(cache):
    old_tag, new_tag = "lahman-2026-09-28", "lahman-2026-10-05"
    cache.write_json_atomic(cache.pointer_path("lahman"), make_pointer(old_tag))
    cache.update_metadata("lahman", etag='"p1"', last_checked=NOW.isoformat())
    new_manifest = make_manifest(new_tag, table_bytes=make_table_bytes())
    client = FakeClient(
        json_routes={
            pointer_url(): JsonResponse(
                json=make_pointer(new_tag), etag='"p2"', not_modified=False
            ),
            manifest_url(new_tag): JsonResponse(json=new_manifest, etag=None, not_modified=False),
        }
    )
    got, resolved = acquire_manifest(
        SPEC, cache, client, offline=False, now=NOW + timedelta(days=8)
    )
    assert resolved.tag == new_tag
    assert cache.read_json(cache.pointer_path("lahman"))["latest"] == new_tag


def test_refresh_true_forces_a_check_even_within_ttl(cache):
    tag = "lahman-2026-10-02"
    cache.write_json_atomic(cache.pointer_path("lahman"), make_pointer(tag))
    cache.write_json_atomic(
        cache.manifest_path("lahman", tag), make_manifest(tag, table_bytes=make_table_bytes())
    )
    cache.update_metadata("lahman", etag='"p1"', last_checked=NOW.isoformat())
    client = FakeClient(
        json_routes={pointer_url(): JsonResponse(json=None, etag='"p1"', not_modified=True)}
    )
    acquire_manifest(SPEC, cache, client, offline=False, refresh=True, now=NOW)
    assert client.json_calls == [(pointer_url(), '"p1"')]


# ---- offline ------------------------------------------------------------------------------


def test_offline_with_no_cache_raises(cache):
    client = FakeClient()
    with pytest.raises(DataNotAvailableError):
        acquire_manifest(SPEC, cache, client, offline=True, now=NOW)
    assert client.json_calls == []


def test_offline_with_cache_uses_it_with_no_network(cache):
    tag = "lahman-2026-10-02"
    manifest = make_manifest(tag, table_bytes=make_table_bytes())
    cache.write_json_atomic(cache.pointer_path("lahman"), make_pointer(tag))
    cache.write_json_atomic(cache.manifest_path("lahman", tag), manifest)
    client = FakeClient()
    got, resolved = acquire_manifest(SPEC, cache, client, offline=True, now=NOW)
    assert got == manifest and client.json_calls == []


def test_offline_config_default_is_used_when_not_overridden(cache):
    config.set(offline=True)
    client = FakeClient()
    with pytest.raises(DataNotAvailableError):
        acquire_manifest(SPEC, cache, client, now=NOW)


# ---- network failure on pointer refresh ---------------------------------------------------


def test_pointer_refresh_failure_falls_back_to_cache_with_warning(cache):
    tag = "lahman-2026-09-28"
    manifest = make_manifest(tag, table_bytes=make_table_bytes())
    cache.write_json_atomic(cache.pointer_path("lahman"), make_pointer(tag))
    cache.write_json_atomic(cache.manifest_path("lahman", tag), manifest)
    cache.update_metadata("lahman", etag='"p1"', last_checked=NOW.isoformat())
    client = FakeClient(json_routes={pointer_url(): SourceUnavailableError("down")})
    with pytest.warns(StaleDataWarning):
        got, resolved = acquire_manifest(
            SPEC, cache, client, offline=False, now=NOW + timedelta(days=8)
        )
    assert resolved.tag == tag


def test_pointer_refresh_failure_with_no_cache_raises(cache):
    client = FakeClient(json_routes={pointer_url(): SourceUnavailableError("down")})
    with pytest.raises(DataNotAvailableError):
        acquire_manifest(SPEC, cache, client, offline=False, now=NOW)


def test_strict_mode_raises_instead_of_warning_on_refresh_failure(cache):
    tag = "lahman-2026-09-28"
    cache.write_json_atomic(cache.pointer_path("lahman"), make_pointer(tag))
    cache.write_json_atomic(
        cache.manifest_path("lahman", tag), make_manifest(tag, table_bytes=make_table_bytes())
    )
    cache.update_metadata("lahman", etag='"p1"', last_checked=NOW.isoformat())
    config.set(strict=True)
    client = FakeClient(json_routes={pointer_url(): SourceUnavailableError("down")})
    with pytest.raises(StaleDataWarning):
        acquire_manifest(SPEC, cache, client, offline=False, now=NOW + timedelta(days=8))


# ---- schema compatibility -------------------------------------------------------------


def test_no_supported_schema_raises_schema_changed(cache):
    tag = "lahman-2026-10-05"
    client = FakeClient(
        json_routes={
            pointer_url(): JsonResponse(
                json=make_pointer(tag, by_schema={"2": tag}), etag=None, not_modified=False
            )
        }
    )
    with pytest.raises(SchemaChangedError):
        acquire_manifest(SPEC, cache, client, offline=False, now=NOW)


def test_warns_when_resolved_tag_is_not_the_true_latest(cache):
    old_tag, true_latest = "lahman-2026-09-28", "lahman-2026-10-05"
    manifest = make_manifest(old_tag, table_bytes=make_table_bytes())
    pointer = make_pointer(
        true_latest,
        by_schema={"1": old_tag, "2": true_latest},
        releases=[
            {
                "tag": old_tag,
                "version": "2025",
                "schema_version": 1,
                "built_at": "t1",
                "withdrawn": False,
            },
            {
                "tag": true_latest,
                "version": "2026",
                "schema_version": 2,
                "built_at": "t2",
                "withdrawn": False,
            },
        ],
    )
    client = FakeClient(
        json_routes={pointer_url(): JsonResponse(json=pointer, etag=None, not_modified=False)},
        file_routes={},
    )
    client.json_routes[manifest_url(old_tag)] = [
        JsonResponse(json=manifest, etag=None, not_modified=False)
    ]
    with pytest.warns(StaleDataWarning):
        got, resolved = acquire_manifest(SPEC, cache, client, offline=False, now=NOW)
    assert resolved.tag == old_tag and resolved.is_latest is False


# ---- version pins ------------------------------------------------------------------------


def test_date_pin_never_touches_the_pointer(cache):
    tag = "lahman-2026-01-05"
    manifest = make_manifest(tag, table_bytes=make_table_bytes())
    client = FakeClient(
        json_routes={manifest_url(tag): JsonResponse(json=manifest, etag=None, not_modified=False)}
    )
    got, resolved = acquire_manifest(
        SPEC, cache, client, version="2026-01-05", offline=False, now=NOW
    )
    assert resolved.tag == tag
    assert pointer_url() not in [u for u, _ in client.json_calls]


def test_date_pin_uses_cached_manifest_with_no_network(cache):
    tag = "lahman-2026-01-05"
    manifest = make_manifest(tag, table_bytes=make_table_bytes())
    cache.write_json_atomic(cache.manifest_path("lahman", tag), manifest)
    client = FakeClient()
    got, resolved = acquire_manifest(
        SPEC, cache, client, version="2026-01-05", offline=False, now=NOW
    )
    assert got == manifest and client.json_calls == []


def test_version_pin_resolves_from_cached_pointer_without_network(cache):
    releases = [
        {
            "tag": "lahman-2026-01-05",
            "version": "2025",
            "schema_version": 1,
            "built_at": "t1",
            "withdrawn": False,
        },
        {
            "tag": "lahman-2026-09-28",
            "version": "2025",
            "schema_version": 1,
            "built_at": "t2",
            "withdrawn": False,
        },
    ]
    cache.write_json_atomic(
        cache.pointer_path("lahman"), make_pointer("lahman-2026-09-28", releases=releases)
    )
    manifest = make_manifest("lahman-2026-09-28", table_bytes=make_table_bytes())
    cache.write_json_atomic(cache.manifest_path("lahman", "lahman-2026-09-28"), manifest)
    client = FakeClient()
    got, resolved = acquire_manifest(SPEC, cache, client, version="2025", offline=False, now=NOW)
    assert resolved.tag == "lahman-2026-09-28" and client.json_calls == []


def test_version_pin_not_in_cached_pointer_refreshes_over_network(cache):
    cache.write_json_atomic(
        cache.pointer_path("lahman"),
        make_pointer(
            "lahman-2026-09-28",
            releases=[
                {
                    "tag": "lahman-2026-09-28",
                    "version": "2025",
                    "schema_version": 1,
                    "built_at": "t",
                    "withdrawn": False,
                }
            ],
        ),
    )
    new_pointer = make_pointer(
        "lahman-2027-01-01",
        releases=[
            {
                "tag": "lahman-2026-09-28",
                "version": "2025",
                "schema_version": 1,
                "built_at": "t",
                "withdrawn": False,
            },
            {
                "tag": "lahman-2027-01-01",
                "version": "2026",
                "schema_version": 1,
                "built_at": "t2",
                "withdrawn": False,
            },
        ],
    )
    manifest = make_manifest("lahman-2027-01-01", table_bytes=make_table_bytes())
    client = FakeClient(
        json_routes={
            pointer_url(): JsonResponse(json=new_pointer, etag=None, not_modified=False),
            manifest_url("lahman-2027-01-01"): JsonResponse(
                json=manifest, etag=None, not_modified=False
            ),
        }
    )
    got, resolved = acquire_manifest(SPEC, cache, client, version="2026", offline=False, now=NOW)
    assert resolved.tag == "lahman-2027-01-01"


def test_version_pin_offline_and_unknown_raises_data_not_available(cache):
    cache.write_json_atomic(
        cache.pointer_path("lahman"),
        make_pointer(
            "lahman-2026-09-28",
            releases=[
                {
                    "tag": "lahman-2026-09-28",
                    "version": "2025",
                    "schema_version": 1,
                    "built_at": "t",
                    "withdrawn": False,
                }
            ],
        ),
    )
    client = FakeClient()
    with pytest.raises(DataNotAvailableError):
        acquire_manifest(SPEC, cache, client, version="2099", offline=True, now=NOW)


def test_unresolvable_version_pin_raises_value_error(cache):
    cache.write_json_atomic(
        cache.pointer_path("lahman"),
        make_pointer(
            "lahman-2026-09-28",
            releases=[
                {
                    "tag": "lahman-2026-09-28",
                    "version": "2025",
                    "schema_version": 1,
                    "built_at": "t",
                    "withdrawn": False,
                }
            ],
        ),
    )
    client = FakeClient(
        json_routes={
            pointer_url(): JsonResponse(
                json=make_pointer("lahman-2026-09-28"), etag=None, not_modified=False
            )
        }
    )
    with pytest.raises(ValueError):
        acquire_manifest(SPEC, cache, client, version="2099", offline=False, now=NOW)


# ---- acquire_table --------------------------------------------------------------------


def test_acquire_table_downloads_and_verifies(cache):
    tag = "lahman-2026-10-02"
    table_bytes = make_table_bytes()
    manifest = make_manifest(tag, table_bytes=table_bytes)
    client = FakeClient(
        json_routes={
            pointer_url(): JsonResponse(json=make_pointer(tag), etag=None, not_modified=False),
            manifest_url(tag): JsonResponse(json=manifest, etag=None, not_modified=False),
        },
        file_routes={f"https://dl.test/{tag}/batting.parquet": table_bytes},
    )
    result = acquire_table(SPEC, "batting", cache, client, offline=False, now=NOW)
    assert isinstance(result, Acquired)
    assert result.path == cache.table_path("lahman", tag, "batting")
    assert result.path.read_bytes() == table_bytes
    assert result.version == tag and result.from_cache is False and result.fallback_reason is None


def test_acquire_table_second_call_uses_cache_no_network(cache):
    tag = "lahman-2026-10-02"
    table_bytes = make_table_bytes()
    manifest = make_manifest(tag, table_bytes=table_bytes)
    cache.write_json_atomic(cache.pointer_path("lahman"), make_pointer(tag))
    cache.write_json_atomic(cache.manifest_path("lahman", tag), manifest)
    cache.update_metadata("lahman", etag="e", last_checked=NOW.isoformat())
    cache.table_path("lahman", tag, "batting").parent.mkdir(parents=True, exist_ok=True)
    cache.table_path("lahman", tag, "batting").write_bytes(table_bytes)
    client = FakeClient()
    result = acquire_table(SPEC, "batting", cache, client, offline=False, now=NOW)
    assert result.from_cache is True and client.download_calls == []


def test_acquire_table_unknown_table_raises_value_error(cache):
    tag = "lahman-2026-10-02"
    manifest = make_manifest(tag, table_bytes=make_table_bytes())
    client = FakeClient(
        json_routes={
            pointer_url(): JsonResponse(json=make_pointer(tag), etag=None, not_modified=False),
            manifest_url(tag): JsonResponse(json=manifest, etag=None, not_modified=False),
        }
    )
    with pytest.raises(ValueError, match="nope"):
        acquire_table(SPEC, "nope", cache, client, offline=False, now=NOW)


def test_acquire_table_cache_with_wrong_hash_is_redownloaded(cache):
    tag = "lahman-2026-10-02"
    table_bytes = make_table_bytes()
    manifest = make_manifest(tag, table_bytes=table_bytes)
    cache.write_json_atomic(cache.pointer_path("lahman"), make_pointer(tag))
    cache.write_json_atomic(cache.manifest_path("lahman", tag), manifest)
    cache.update_metadata("lahman", etag="e", last_checked=NOW.isoformat())
    stale_path = cache.table_path("lahman", tag, "batting")
    stale_path.parent.mkdir(parents=True, exist_ok=True)
    stale_path.write_bytes(b"corrupt")
    client = FakeClient(file_routes={f"https://dl.test/{tag}/batting.parquet": table_bytes})
    result = acquire_table(SPEC, "batting", cache, client, offline=False, now=NOW)
    assert result.from_cache is False and result.path.read_bytes() == table_bytes


def test_acquire_table_download_failure_falls_back_to_older_cached_version(cache):
    old_tag, new_tag = "lahman-2026-09-28", "lahman-2026-10-05"
    table_bytes = make_table_bytes()
    old_manifest = make_manifest(old_tag, table_bytes=table_bytes)
    cache.write_json_atomic(cache.manifest_path("lahman", old_tag), old_manifest)
    cache.table_path("lahman", old_tag, "batting").parent.mkdir(parents=True, exist_ok=True)
    cache.table_path("lahman", old_tag, "batting").write_bytes(table_bytes)

    new_manifest = make_manifest(new_tag, table_bytes=make_table_bytes(rows=2))
    client = FakeClient(
        json_routes={
            pointer_url(): JsonResponse(json=make_pointer(new_tag), etag=None, not_modified=False),
            manifest_url(new_tag): JsonResponse(json=new_manifest, etag=None, not_modified=False),
        },
        file_routes={new_manifest["tables"]["batting"]["url"]: SourceUnavailableError("down")},
    )
    with pytest.warns(StaleDataWarning):
        result = acquire_table(SPEC, "batting", cache, client, offline=False, now=NOW)
    assert result.version == old_tag and result.from_cache is True
    assert result.fallback_reason is not None
    assert result.path.read_bytes() == table_bytes


def test_acquire_table_download_failure_with_no_fallback_raises(cache):
    tag = "lahman-2026-10-02"
    manifest = make_manifest(tag, table_bytes=make_table_bytes())
    client = FakeClient(
        json_routes={
            pointer_url(): JsonResponse(json=make_pointer(tag), etag=None, not_modified=False),
            manifest_url(tag): JsonResponse(json=manifest, etag=None, not_modified=False),
        },
        file_routes={manifest["tables"]["batting"]["url"]: SourceUnavailableError("down")},
    )
    with pytest.raises(DataNotAvailableError):
        acquire_table(SPEC, "batting", cache, client, offline=False, now=NOW)


def test_acquire_table_offline_without_cache_raises(cache):
    client = FakeClient()
    with pytest.raises(DataNotAvailableError):
        acquire_table(SPEC, "batting", cache, client, offline=True, now=NOW)


def test_acquire_table_checksum_mismatch_falls_back(cache):
    old_tag, new_tag = "lahman-2026-09-28", "lahman-2026-10-05"
    table_bytes = make_table_bytes()
    cache.write_json_atomic(
        cache.manifest_path("lahman", old_tag), make_manifest(old_tag, table_bytes=table_bytes)
    )
    cache.table_path("lahman", old_tag, "batting").parent.mkdir(parents=True, exist_ok=True)
    cache.table_path("lahman", old_tag, "batting").write_bytes(table_bytes)

    new_manifest = make_manifest(new_tag, table_bytes=make_table_bytes(rows=2))
    client = FakeClient(
        json_routes={
            pointer_url(): JsonResponse(json=make_pointer(new_tag), etag=None, not_modified=False),
            manifest_url(new_tag): JsonResponse(json=new_manifest, etag=None, not_modified=False),
        },
        file_routes={new_manifest["tables"]["batting"]["url"]: b"wrong-bytes"},
    )
    with pytest.warns(StaleDataWarning):
        result = acquire_table(SPEC, "batting", cache, client, offline=False, now=NOW)
    assert result.version == old_tag


def test_acquire_table_schema_mismatch_after_download_falls_back(cache):
    old_tag, new_tag = "lahman-2026-09-28", "lahman-2026-10-05"
    table_bytes = make_table_bytes()
    cache.write_json_atomic(
        cache.manifest_path("lahman", old_tag), make_manifest(old_tag, table_bytes=table_bytes)
    )
    cache.table_path("lahman", old_tag, "batting").parent.mkdir(parents=True, exist_ok=True)
    cache.table_path("lahman", old_tag, "batting").write_bytes(table_bytes)

    import io as _io

    _buf = _io.BytesIO()
    pl.DataFrame({"totally_different_column": [1, 2, 3]}).write_parquet(_buf)
    bad_bytes = _buf.getvalue()
    new_manifest = make_manifest(new_tag, table_bytes=bad_bytes)
    client = FakeClient(
        json_routes={
            pointer_url(): JsonResponse(json=make_pointer(new_tag), etag=None, not_modified=False),
            manifest_url(new_tag): JsonResponse(json=new_manifest, etag=None, not_modified=False),
        },
        file_routes={new_manifest["tables"]["batting"]["url"]: bad_bytes},
    )
    with pytest.warns(StaleDataWarning):
        result = acquire_table(SPEC, "batting", cache, client, offline=False, now=NOW)
    assert result.version == old_tag


def test_acquire_table_fetched_at_reflects_file_mtime(cache):
    tag = "lahman-2026-10-02"
    table_bytes = make_table_bytes()
    manifest = make_manifest(tag, table_bytes=table_bytes)
    client = FakeClient(
        json_routes={
            pointer_url(): JsonResponse(json=make_pointer(tag), etag=None, not_modified=False),
            manifest_url(tag): JsonResponse(json=manifest, etag=None, not_modified=False),
        },
        file_routes={manifest["tables"]["batting"]["url"]: table_bytes},
    )
    before = datetime.now(timezone.utc) - timedelta(seconds=5)
    result = acquire_table(SPEC, "batting", cache, client, offline=False, now=NOW)
    assert result.fetched_at >= before
