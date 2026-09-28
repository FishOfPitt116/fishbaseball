from datetime import datetime, timezone

from fishbaseball._core.acquire import Acquired
from fishbaseball._core.provenance import build_provenance

MANIFEST = {
    "license": "CC BY-SA 3.0",
    "attribution": "Lahman Baseball Database © SABR, via Sean Lahman. CC BY-SA 3.0.",
    "tables": {"batting": {"url": "https://dl.test/lahman-2026-09-28/batting.parquet"}},
}
ACQUIRED = Acquired(
    path=None,  # type: ignore[arg-type]  # not used by build_provenance
    version="lahman-2026-09-28",
    fetched_at=datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc),
    from_cache=True,
    fallback_reason=None,
)


def test_provenance_fields():
    p = build_provenance("lahman", "batting", MANIFEST, ACQUIRED)
    assert p.source == "lahman"
    assert p.table == "batting"
    assert p.version == "lahman-2026-09-28"
    assert p.fetched_at == ACQUIRED.fetched_at
    assert p.from_cache is True
    assert p.fallback_reason is None
    assert p.url == "https://dl.test/lahman-2026-09-28/batting.parquet"
    assert p.license == "CC BY-SA 3.0"
    assert p.attribution == MANIFEST["attribution"]


def test_provenance_carries_a_fallback_reason():
    acquired = Acquired(
        path=None,  # type: ignore[arg-type]
        version="lahman-2026-09-26", fetched_at=ACQUIRED.fetched_at,
        from_cache=True, fallback_reason="download failed",
    )  # fmt: skip
    p = build_provenance("lahman", "batting", MANIFEST, acquired)
    assert p.fallback_reason == "download failed"


def test_provenance_is_immutable():
    p = build_provenance("lahman", "batting", MANIFEST, ACQUIRED)
    try:
        p.source = "x"  # type: ignore[misc]
    except Exception:
        pass
    else:
        raise AssertionError("Provenance should be frozen")
