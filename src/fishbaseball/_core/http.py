"""Thin httpx wrapper: conditional GET for pointer/manifest JSON, and verified atomic
downloads for data files. `pipelines.core.download`/`detect` in `fishbaseball-data` are the
same idea on the publishing side; this is the reading side."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from fishbaseball.exceptions import ChecksumError, SourceUnavailableError

CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 60.0
MAX_RETRIES = 3
BACKOFF_SECONDS = 0.5
RETRYABLE_STATUS = {500, 502, 503, 504}


@dataclass(frozen=True)
class JsonResponse:
    json: Any | None  # None when not_modified
    etag: str | None
    not_modified: bool


class Client:
    """`user_agent` should look like `fishbaseball/<ver> (+<repo url>)`."""

    def __init__(
        self,
        user_agent: str,
        *,
        transport: httpx.BaseTransport | None = None,
        backoff_seconds: float = BACKOFF_SECONDS,
    ):
        self._client = httpx.Client(
            headers={"User-Agent": user_agent},
            timeout=httpx.Timeout(READ_TIMEOUT, connect=CONNECT_TIMEOUT),
            follow_redirects=True,
            transport=transport,
        )
        self._backoff = backoff_seconds

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last: Exception | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = self._client.request(method, url, **kwargs)
            except httpx.TransportError as e:
                last = e
            else:
                if resp.status_code not in RETRYABLE_STATUS:
                    return resp
                last = SourceUnavailableError(f"{method} {url}: HTTP {resp.status_code}")
            if attempt < MAX_RETRIES and self._backoff:
                time.sleep(self._backoff * (2**attempt))
        raise SourceUnavailableError(f"{method} {url} failed after {MAX_RETRIES} retries") from last

    def get_json(self, url: str, *, etag: str | None = None) -> JsonResponse:
        headers = {"If-None-Match": etag} if etag else {}
        resp = self._request("GET", url, headers=headers)
        if resp.status_code == 304:
            return JsonResponse(json=None, etag=etag, not_modified=True)
        if resp.status_code >= 400:
            raise SourceUnavailableError(f"GET {url}: HTTP {resp.status_code}")
        return JsonResponse(json=resp.json(), etag=resp.headers.get("ETag"), not_modified=False)

    def download(self, url: str, dest: Path, *, sha256: str) -> Path:
        """Stream to a temp file next to `dest`, verify its SHA-256, then atomically replace
        `dest`. `dest` is left untouched (old content or absent) on any failure."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        digest = hashlib.sha256()
        try:
            with self._client.stream("GET", url) as resp:
                if resp.status_code >= 400:
                    raise SourceUnavailableError(f"GET {url}: HTTP {resp.status_code}")
                with tmp.open("wb") as f:
                    for chunk in resp.iter_bytes():
                        digest.update(chunk)
                        f.write(chunk)
            if digest.hexdigest() != sha256:
                raise ChecksumError(
                    f"{url}: SHA-256 {digest.hexdigest()} does not match manifest ({sha256})"
                )
            tmp.replace(dest)
        finally:
            tmp.unlink(missing_ok=True)
        return dest
