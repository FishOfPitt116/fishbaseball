import httpx
import pytest
import respx

from fishbaseball._core.http import Client
from fishbaseball.exceptions import ChecksumError, SourceUnavailableError

URL = "https://fixtures.test/thing.json"
FILE_URL = "https://fixtures.test/thing.parquet"


@pytest.fixture
def client():
    c = Client(user_agent="fishbaseball/0.1.0 (+https://github.com/x/y)", backoff_seconds=0)
    yield c
    c.close()


@respx.mock
def test_get_json_returns_body_and_etag(client):
    respx.get(URL).mock(return_value=httpx.Response(200, json={"a": 1}, headers={"ETag": '"abc"'}))
    resp = client.get_json(URL)
    assert resp.json == {"a": 1}
    assert resp.etag == '"abc"' and resp.not_modified is False


@respx.mock
def test_get_json_sends_the_user_agent(client):
    route = respx.get(URL).mock(return_value=httpx.Response(200, json={}))
    client.get_json(URL)
    assert (
        route.calls.last.request.headers["User-Agent"]
        == "fishbaseball/0.1.0 (+https://github.com/x/y)"
    )


@respx.mock
def test_get_json_sends_if_none_match_when_etag_given(client):
    route = respx.get(URL).mock(return_value=httpx.Response(304))
    resp = client.get_json(URL, etag='"abc"')
    assert route.calls.last.request.headers["If-None-Match"] == '"abc"'
    assert resp.not_modified is True and resp.json is None


@respx.mock
def test_get_json_304_without_etag_argument_is_not_sent(client):
    route = respx.get(URL).mock(return_value=httpx.Response(200, json={}))
    client.get_json(URL)
    assert "If-None-Match" not in route.calls.last.request.headers


@respx.mock
def test_get_json_404_raises_source_unavailable(client):
    respx.get(URL).mock(return_value=httpx.Response(404))
    with pytest.raises(SourceUnavailableError):
        client.get_json(URL)


@respx.mock
def test_get_json_connection_error_raises_source_unavailable_after_retries(client):
    route = respx.get(URL).mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(SourceUnavailableError):
        client.get_json(URL)
    assert route.call_count == 4  # 1 try + 3 retries


@respx.mock
def test_get_json_retries_on_5xx_then_succeeds(client):
    route = respx.get(URL).mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json={"ok": True})]
    )
    resp = client.get_json(URL)
    assert resp.json == {"ok": True} and route.call_count == 2


@respx.mock
def test_get_json_does_not_retry_on_4xx(client):
    route = respx.get(URL).mock(return_value=httpx.Response(400))
    with pytest.raises(SourceUnavailableError):
        client.get_json(URL)
    assert route.call_count == 1


@respx.mock
def test_download_writes_the_file_and_verifies_checksum(client, tmp_path):
    body = b"parquet-bytes"
    import hashlib

    sha = hashlib.sha256(body).hexdigest()
    respx.get(FILE_URL).mock(return_value=httpx.Response(200, content=body))
    dest = tmp_path / "thing.parquet"
    out = client.download(FILE_URL, dest, sha256=sha)
    assert out == dest and dest.read_bytes() == body


@respx.mock
def test_download_rejects_a_checksum_mismatch_and_leaves_no_file(client, tmp_path):
    respx.get(FILE_URL).mock(return_value=httpx.Response(200, content=b"wrong-bytes"))
    dest = tmp_path / "thing.parquet"
    with pytest.raises(ChecksumError):
        client.download(FILE_URL, dest, sha256="0" * 64)
    assert not dest.exists()
    assert not any(tmp_path.iterdir())  # no leftover temp file either


@respx.mock
def test_download_is_atomic_does_not_clobber_dest_until_verified(client, tmp_path):
    dest = tmp_path / "thing.parquet"
    dest.write_bytes(b"old-good-content")
    respx.get(FILE_URL).mock(return_value=httpx.Response(200, content=b"wrong-bytes"))
    with pytest.raises(ChecksumError):
        client.download(FILE_URL, dest, sha256="0" * 64)
    assert dest.read_bytes() == b"old-good-content"


@respx.mock
def test_download_follows_redirects(client, tmp_path):
    import hashlib

    body = b"redirected-bytes"
    sha = hashlib.sha256(body).hexdigest()
    respx.get(FILE_URL).mock(
        return_value=httpx.Response(302, headers={"Location": "https://cdn.test/x"})
    )
    respx.get("https://cdn.test/x").mock(return_value=httpx.Response(200, content=body))
    dest = tmp_path / "thing.parquet"
    client.download(FILE_URL, dest, sha256=sha)
    assert dest.read_bytes() == body


@respx.mock
def test_download_source_unavailable_on_404(client, tmp_path):
    respx.get(FILE_URL).mock(return_value=httpx.Response(404))
    with pytest.raises(SourceUnavailableError):
        client.download(FILE_URL, tmp_path / "thing.parquet", sha256="0" * 64)


def test_default_backoff_is_nonzero():
    c = Client(user_agent="x")
    try:
        assert c._backoff > 0
    finally:
        c.close()
