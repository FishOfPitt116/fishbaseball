"""A shared, lazily-created `Client` for every source's public API, so connections are
pooled across calls instead of opening a new one each time."""

from __future__ import annotations

from fishbaseball._core.http import Client
from fishbaseball._version import __version__

USER_AGENT = f"fishbaseball/{__version__} (+https://github.com/FishOfPitt116/fishbaseball)"

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        _client = Client(user_agent=USER_AGENT)
    return _client


def _reset_client() -> None:
    """Test-only: drop the shared client so the next call builds a fresh one."""
    global _client
    if _client is not None:
        _client.close()
    _client = None
