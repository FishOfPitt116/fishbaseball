import warnings

import pytest

from fishbaseball.exceptions import (
    ChecksumError,
    DataNotAvailableError,
    FishbaseballError,
    FishbaseballWarning,
    IncompatibleDataError,
    SchemaChangedError,
    SourceUnavailableError,
    StaleDataWarning,
)


@pytest.mark.parametrize(
    "exc",
    [DataNotAvailableError, SourceUnavailableError, SchemaChangedError,
     IncompatibleDataError, ChecksumError],
)  # fmt: skip
def test_errors_subclass_the_base_error(exc):
    assert issubclass(exc, FishbaseballError)
    assert issubclass(exc, Exception)
    with pytest.raises(FishbaseballError):
        raise exc("boom")


def test_stale_data_warning_subclasses_the_base_warning():
    assert issubclass(StaleDataWarning, FishbaseballWarning)
    assert issubclass(FishbaseballWarning, UserWarning)
    with pytest.warns(FishbaseballWarning):
        warnings.warn("stale", StaleDataWarning, stacklevel=1)


def test_errors_are_distinct_types():
    assert DataNotAvailableError is not SourceUnavailableError
    assert not issubclass(DataNotAvailableError, SourceUnavailableError)
