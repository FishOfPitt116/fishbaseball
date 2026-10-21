import copy
import hashlib
import io
import json
import threading
import time
import warnings
from datetime import datetime, timezone

import polars as pl
import pytest

from fishbaseball import config
from fishbaseball._core.acquire import (
    SourceSpec,
    acquire_manifest,
    acquire_partitions,
    manifest_url,
    pointer_url,
)
from fishbaseball._core.cache import Cache
from fishbaseball._core.http import JsonResponse
from fishbaseball.exceptions import (
    ChecksumError,
    DataNotAvailableError,
    SourceUnavailableError,
    StaleDataWarning,
)

SPEC = SourceSpec(name="retrosheet", repo="o/fishbaseball-data")
NOW = datetime(2026, 10, 21, 12, 0, 0, tzinfo=timezone.utc)
TAG = "retrosheet-2026-10-20"
NEWER = "retrosheet-2026-11-01"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


class FakeClient:
    """Serves JSON and file bytes by URL, thread-safely, and records how many downloads were
    ever in flight at once. A route value may be bytes, an Exception, or a list of them
    consumed in order."""

    def __init__(self, json_routes=None, files=None, delay: float = 0.0):
        self.json_routes = dict(json_routes or {})
        self.files = {k: list(v) if isinstance(v, list) else [v] for k, v in (files or {}).items()}
        self.delay = delay
        self.downloads: list[str] = []
        self.in_flight = 0
        self.max_in_flight = 0
        self._lock = threading.Lock()

    def get_json(self, url, *, etag=None):
        item = self.json_routes[url]
        if isinstance(item, Exception):
            raise item
        return JsonResponse(json=item, etag=None, not_modified=False)

    def download(self, url, dest, *, sha256):
        with self._lock:
            self.downloads.append(url)
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
            item = self.files[url].pop(0) if len(self.files[url]) > 1 else self.files[url][0]
        try:
            time.sleep(self.delay)
            if isinstance(item, Exception):
                raise item
            if sha(item) != sha256:
                raise ChecksumError(f"{url}: sha mismatch")
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(item)
            return dest
        finally:
            with self._lock:
                self.in_flight -= 1


@pytest.fixture(autouse=True)
def reset_config():
    config._reset()
    yield
    config._reset()


@pytest.fixture
def cache(tmp_path) -> Cache:
    return Cache(root=tmp_path / "cache")


@pytest.fixture
def release(retro_fixtures):
    """(manifest, files-by-url, pointer) for the three-season Retrosheet fixture release."""
    manifest = json.loads((retro_fixtures / "manifest.json").read_text())
    pointer = json.loads((retro_fixtures / "latest.json").read_text())
    files = {}
    for entry in manifest["tables"].values():
        for e in entry["partitions"].values() if entry.get("partitioned") else [entry]:
            files[e["url"]] = (retro_fixtures / e["file"]).read_bytes()
    return manifest, files, pointer


def routes(manifest, pointer, *extra_manifests):
    out = {pointer_url(SPEC): pointer, manifest_url(SPEC, manifest["tag"]): manifest}
    for m in extra_manifests:
        out[manifest_url(SPEC, m["tag"])] = m
    return out


def make_client(release, **kw) -> FakeClient:
    manifest, files, pointer = release
    return FakeClient(json_routes=routes(manifest, pointer), files=files, **kw)


def acquire(cache, client, partitions, **kw):
    return acquire_partitions(
        SPEC, "plays", partitions, cache, client, offline=kw.pop("offline", False), now=NOW, **kw
    )


def newer_release(release, tmp_path_factory=None):
    """A newer release identical to `release` except plays 1956 has different content (so a
    different sha) at a new URL. Returns (manifest, new_bytes_by_url)."""
    manifest, files, _ = release
    new = copy.deepcopy(manifest)
    new["tag"] = NEWER
    entry = new["tables"]["plays"]["partitions"]["1956"]
    old_bytes = files[entry["url"]]
    df = pl.read_parquet(io.BytesIO(old_bytes)).head(5)
    buf = io.BytesIO()
    df.write_parquet(buf)
    body = buf.getvalue()
    entry.update(url=entry["url"].replace(TAG, NEWER), sha256=sha(body), bytes=len(body), rows=5)
    return new, {entry["url"]: body}


# ---- the basics -------------------------------------------------------------------------


def test_downloads_only_the_requested_partitions_into_the_object_store(cache, release):
    manifest, *_ = release
    client = make_client(release)

    got = acquire(cache, client, [2001, 1927])

    assert [a.partition for a in got] == ["2001", "1927"]  # in the order asked for
    assert len(client.downloads) == 2
    for a in got:
        entry = manifest["tables"]["plays"]["partitions"][a.partition]
        assert a.path == cache.object_path("retrosheet", entry["sha256"])
        assert a.path.exists() and a.version == TAG
        assert a.from_cache is False and a.fallback_reason is None


def test_a_second_call_is_served_from_cache_with_no_downloads(cache, release):
    client = make_client(release)
    acquire(cache, client, [1927, 1956])
    before = len(client.downloads)

    again = acquire(cache, client, [1927, 1956])

    assert len(client.downloads) == before
    assert all(a.from_cache for a in again)


def test_only_the_missing_partitions_are_downloaded(cache, release):
    client = make_client(release)
    acquire(cache, client, [1927])
    client.downloads.clear()

    got = acquire(cache, client, [1927, 2001])

    assert len(client.downloads) == 1 and client.downloads[0].endswith("plays_2001.parquet")
    assert [a.from_cache for a in got] == [True, False]


def test_duplicate_requests_are_collapsed(cache, release):
    got = acquire(cache, make_client(release), [1927, "1927", 1927])
    assert [a.partition for a in got] == ["1927"]


def test_a_new_release_reuses_unchanged_partitions_across_tags(cache, release):
    manifest, files, pointer = release
    newer, new_files = newer_release(release)
    pointer = {**pointer, "latest": NEWER, "by_schema": {"1": NEWER}}
    client = FakeClient(routes(manifest, pointer, newer), {**files, **new_files})
    acquire(cache, client, [1927, 1956], version="2026-10-20")
    client.downloads.clear()

    got = acquire(cache, client, [1927, 1956], refresh=True)

    assert [a.version for a in got] == [NEWER, NEWER]
    assert len(client.downloads) == 1 and "plays_1956" in client.downloads[0]
    assert client.downloads[0].startswith(f"https://fixtures.test/{NEWER}/")


def test_a_partition_published_under_an_older_release_downloads_from_that_url(cache, release):
    manifest, files, pointer = release
    newer, _ = newer_release(release)
    # in `newer`, every partition except 1956 still points at the old release's URL
    for key in ("1927", "2001"):
        assert TAG in newer["tables"]["plays"]["partitions"][key]["url"]
    pointer = {**pointer, "latest": NEWER, "by_schema": {"1": NEWER}}
    client = FakeClient(routes(manifest, pointer, newer), files)

    got = acquire(cache, client, [1927])

    assert got[0].version == NEWER
    assert client.downloads == [newer["tables"]["plays"]["partitions"]["1927"]["url"]]
    assert TAG in client.downloads[0]


# ---- verification and failure -----------------------------------------------------------


def test_a_download_with_the_wrong_sha_is_rejected_and_leaves_nothing_behind(cache, release):
    manifest, files, pointer = release
    url = manifest["tables"]["plays"]["partitions"]["1927"]["url"]
    bad = {**files, url: b"corrupt bytes"}
    client = FakeClient(routes(manifest, pointer), bad)

    with pytest.raises(DataNotAvailableError):
        acquire(cache, client, [1927])

    objects = cache.source_dir("retrosheet") / "objects"
    assert not objects.exists() or not list(objects.iterdir())


def test_a_cached_object_that_fails_its_checksum_is_downloaded_again(cache, release):
    manifest, *_ = release
    client = make_client(release)
    [first] = acquire(cache, client, [1927])
    first.path.write_bytes(b"bit rot")
    client.downloads.clear()

    [again] = acquire(cache, client, [1927])

    assert len(client.downloads) == 1 and again.from_cache is False
    assert pl.read_parquet(again.path).height > 0


def test_a_download_whose_columns_dont_match_the_manifest_is_rejected(cache, release):
    manifest, files, pointer = release
    entry = manifest["tables"]["plays"]["partitions"]["1927"]
    buf = io.BytesIO()
    pl.DataFrame({"gid": ["x"]}).write_parquet(buf)
    wrong = buf.getvalue()
    bad_manifest = copy.deepcopy(manifest)
    bad_manifest["tables"]["plays"]["partitions"]["1927"]["sha256"] = sha(wrong)
    client = FakeClient(routes(bad_manifest, pointer), {**files, entry["url"]: wrong})

    with pytest.raises(DataNotAvailableError):
        acquire(cache, client, [1927])


def test_unknown_partition_names_what_is_available(cache, release):
    client = make_client(release)
    with pytest.raises(DataNotAvailableError, match=r"1999.*1927, 1956, 2001"):
        acquire(cache, client, [1999])
    assert client.downloads == []  # nothing fetched before the request was rejected


def test_a_non_partitioned_table_is_a_value_error(cache, release):
    with pytest.raises(ValueError, match="not partitioned"):
        acquire_partitions(SPEC, "game_info", [1927], cache, make_client(release), now=NOW)


def test_unknown_table_is_a_value_error_with_a_hint(cache, release):
    with pytest.raises(ValueError, match="did you mean 'plays'"):
        acquire_partitions(SPEC, "play", [1927], cache, make_client(release), now=NOW)


# ---- per-partition fallback --------------------------------------------------------------


def _cached_old_then_newer_fails(cache, release, error):
    manifest, files, pointer = release
    newer, new_files = newer_release(release)
    pointer = {**pointer, "latest": NEWER, "by_schema": {"1": NEWER}}
    client = FakeClient(
        routes(manifest, pointer, newer),
        {**files, **{url: error for url in new_files}},
    )
    acquire(cache, client, [1927, 1956], version="2026-10-20")
    return client, newer


def test_a_failed_download_falls_back_to_the_newest_good_cached_partition(cache, release):
    client, newer = _cached_old_then_newer_fails(cache, release, SourceUnavailableError("down"))

    with pytest.warns(StaleDataWarning, match="1956"):
        got = acquire(cache, client, [1927, 1956], refresh=True)

    by_key = {a.partition: a for a in got}
    assert by_key["1927"].version == NEWER and by_key["1927"].fallback_reason is None
    assert by_key["1956"].version == TAG and "down" in (by_key["1956"].fallback_reason or "")
    assert by_key["1956"].from_cache is True


def test_strict_mode_raises_instead_of_falling_back(cache, release):
    client, _ = _cached_old_then_newer_fails(cache, release, SourceUnavailableError("down"))
    config.set(strict=True)
    with pytest.raises(StaleDataWarning):
        acquire(cache, client, [1956], refresh=True)


def test_one_warning_covers_every_partition_that_fell_back(cache, release):
    client, _ = _cached_old_then_newer_fails(cache, release, SourceUnavailableError("down"))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        acquire(cache, client, [1927, 1956], refresh=True)
    assert len([w for w in caught if issubclass(w.category, StaleDataWarning)]) == 1


# ---- offline ----------------------------------------------------------------------------


def test_offline_serves_cached_partitions_without_touching_the_network(cache, release):
    acquire(cache, make_client(release), [1927, 1956])
    silent = FakeClient()  # any get_json/download would KeyError

    got = acquire(cache, silent, [1927, 1956], offline=True)

    assert all(a.from_cache for a in got) and silent.downloads == []


def test_offline_with_a_partition_that_is_not_cached_raises(cache, release):
    acquire(cache, make_client(release), [1927])
    with pytest.raises(DataNotAvailableError, match="2001.*offline"):
        acquire(cache, FakeClient(), [1927, 2001], offline=True)


def test_offline_with_nothing_cached_raises(cache):
    with pytest.raises(DataNotAvailableError):
        acquire(cache, FakeClient(), [1927], offline=True)


# ---- parallelism ------------------------------------------------------------------------


def _wide_release(n: int):
    """A synthetic partitioned table with `n` one-row partitions of distinct content."""
    files, partitions = {}, {}
    for i in range(n):
        season = str(1900 + i)
        buf = io.BytesIO()
        pl.DataFrame({"gid": [f"g{i}"]}).write_parquet(buf)
        body = buf.getvalue()
        url = f"https://fixtures.test/{TAG}/plays_{season}.parquet"
        files[url] = body
        partitions[season] = {"file": f"plays_{season}.parquet", "url": url, "sha256": sha(body)}
    manifest = {
        "source": "retrosheet",
        "tag": TAG,
        "schema_version": 1,
        "tables": {
            "plays": {
                "partitioned": True,
                "columns": {"gid": "String"},
                "season_column": "season",
                "partitions": partitions,
            }
        },
    }
    pointer = {
        "source": "retrosheet",
        "latest": TAG,
        "by_schema": {"1": TAG},
        "releases": [
            {"tag": TAG, "version": "x", "schema_version": 1, "built_at": "t", "withdrawn": False}
        ],
    }
    return manifest, files, pointer


def test_downloads_run_in_parallel_but_never_more_than_four_at_once(cache):
    manifest, files, pointer = _wide_release(12)
    client = FakeClient(routes(manifest, pointer), files, delay=0.05)

    got = acquire(cache, client, list(range(1900, 1912)))

    assert len(got) == 12
    assert 2 <= client.max_in_flight <= 4


def test_manifest_is_resolved_once_for_a_multi_partition_call(cache):
    manifest, files, pointer = _wide_release(5)
    client = FakeClient(routes(manifest, pointer), files)
    seen = []
    orig = client.get_json
    client.get_json = lambda url, **kw: (seen.append(url), orig(url, **kw))[1]

    acquire(cache, client, list(range(1900, 1905)))

    assert seen.count(manifest_url(SPEC, TAG)) == 1
    assert acquire_manifest(SPEC, cache, client, offline=True, now=NOW)[0] == manifest
