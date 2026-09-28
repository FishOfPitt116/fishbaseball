import pytest

from fishbaseball._core.manifest import Resolved, resolve
from fishbaseball.exceptions import IncompatibleDataError, SchemaChangedError


def pointer(**overrides):
    base = {
        "source": "lahman",
        "latest": "lahman-2026-09-28",
        "by_schema": {"1": "lahman-2026-09-28"},
        "releases": [
            {
                "tag": "lahman-2026-09-26",
                "version": "2025",
                "schema_version": 1,
                "built_at": "2026-09-26T03:29:16Z",
                "withdrawn": False,
            },
            {
                "tag": "lahman-2026-09-28",
                "version": "2025",
                "schema_version": 1,
                "built_at": "2026-09-28T00:25:04Z",
                "withdrawn": False,
            },
        ],  # fmt: skip
    }
    return {**base, **overrides}


def test_no_pin_resolves_to_latest_when_its_schema_is_supported():
    r = resolve(pointer(), {1})
    assert r == Resolved(
        tag="lahman-2026-09-28", is_latest=True, latest_tag="lahman-2026-09-28", withdrawn=False
    )


def test_no_pin_falls_back_to_newest_supported_schema_when_latest_is_not():
    p = pointer(
        latest="lahman-2026-10-05",
        by_schema={"1": "lahman-2026-09-28", "2": "lahman-2026-10-05"},
    )
    r = resolve(p, {1})
    assert (
        r.tag == "lahman-2026-09-28"
        and r.is_latest is False
        and r.latest_tag == "lahman-2026-10-05"
    )


def test_no_pin_raises_when_no_schema_is_supported():
    p = pointer(by_schema={"2": "lahman-2026-10-05"})
    with pytest.raises(SchemaChangedError):
        resolve(p, {1})


def test_no_pin_picks_the_newest_of_several_supported_schemas():
    p = pointer(by_schema={"1": "lahman-old", "2": "lahman-new"}, latest="lahman-new")
    r = resolve(p, {1, 2})
    assert r.tag == "lahman-new" and r.is_latest is True


def test_pin_by_date_matches_an_indexed_release():
    r = resolve(pointer(), {1}, pin="2026-09-26")
    assert r.tag == "lahman-2026-09-26" and r.is_latest is False
    assert r.latest_tag == "lahman-2026-09-28" and r.withdrawn is False


def test_pin_by_date_not_in_the_index_still_computes_the_tag():
    # a release published before the `releases` index existed
    r = resolve(pointer(), {1}, pin="2025-01-01")
    assert r.tag == "lahman-2025-01-01"


def test_pin_by_date_reports_withdrawn():
    p = pointer(
        releases=[
            {"tag": "lahman-2026-09-26", "version": "2025", "schema_version": 1,
             "built_at": "x", "withdrawn": True},
        ]
    )  # fmt: skip
    r = resolve(p, {1}, pin="2026-09-26")
    assert r.withdrawn is True


def test_pin_by_date_with_unsupported_schema_raises_incompatible():
    p = pointer(
        releases=[
            {"tag": "lahman-2026-10-05", "version": "2026", "schema_version": 2,
             "built_at": "x", "withdrawn": False},
        ]
    )  # fmt: skip
    with pytest.raises(IncompatibleDataError):
        resolve(p, {1}, pin="2026-10-05")


def test_pin_by_sabr_version_picks_the_newest_matching_release():
    p = pointer(
        releases=[
            {"tag": "lahman-2026-01-05", "version": "2025", "schema_version": 1,
             "built_at": "2026-01-05T00:00:00Z", "withdrawn": False},
            {"tag": "lahman-2026-09-28", "version": "2025", "schema_version": 1,
             "built_at": "2026-09-28T00:25:04Z", "withdrawn": False},
        ]
    )  # fmt: skip
    r = resolve(p, {1}, pin="2025")
    assert r.tag == "lahman-2026-09-28"


def test_pin_by_sabr_version_skips_withdrawn_releases():
    p = pointer(
        releases=[
            {"tag": "lahman-bad", "version": "2025", "schema_version": 1,
             "built_at": "2026-09-29T00:00:00Z", "withdrawn": True},
            {"tag": "lahman-2026-09-28", "version": "2025", "schema_version": 1,
             "built_at": "2026-09-28T00:25:04Z", "withdrawn": False},
        ]
    )  # fmt: skip
    r = resolve(p, {1}, pin="2025")
    assert r.tag == "lahman-2026-09-28" and r.withdrawn is False


def test_pin_by_unknown_sabr_version_raises_value_error():
    with pytest.raises(ValueError, match="2099"):
        resolve(pointer(), {1}, pin="2099")


def test_pin_by_sabr_version_with_unsupported_schema_raises_incompatible():
    p = pointer(
        releases=[
            {"tag": "lahman-2026-10-05", "version": "2026", "schema_version": 2,
             "built_at": "x", "withdrawn": False},
        ]
    )  # fmt: skip
    with pytest.raises(IncompatibleDataError):
        resolve(p, {1}, pin="2026")


def test_missing_releases_key_is_treated_as_empty():
    p = pointer()
    del p["releases"]
    r = resolve(p, {1})
    assert r.tag == "lahman-2026-09-28"
    with pytest.raises(ValueError):
        resolve(p, {1}, pin="2025")
