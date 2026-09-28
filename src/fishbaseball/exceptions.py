"""Public exception and warning hierarchy. Everything this package raises or warns with
subclasses one of the two bases below, so callers can catch broadly with `FishbaseballError`
or `FishbaseballWarning`, or narrowly with a specific type."""

from __future__ import annotations


class FishbaseballError(Exception):
    """Base class for every error this package raises."""


class FishbaseballWarning(UserWarning):
    """Base class for every warning this package issues."""


class DataNotAvailableError(FishbaseballError):
    """No usable data (no cache, and network access is unavailable or forbidden)."""


class SourceUnavailableError(FishbaseballError):
    """The upstream source (e.g. GitHub Releases) could not be reached."""


class SchemaChangedError(FishbaseballError):
    """The published data uses a `schema_version` this version of the package doesn't know."""


class IncompatibleDataError(FishbaseballError):
    """The cached or downloaded data doesn't match what this version of the package expects."""


class ChecksumError(FishbaseballError):
    """A downloaded file's SHA-256 doesn't match the manifest."""


class StaleDataWarning(FishbaseballWarning):
    """Serving cached data older than requested because a refresh failed or was skipped."""
