import hashlib
import pathlib

import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "lahman"


@pytest.fixture
def fixtures() -> pathlib.Path:
    return FIXTURES


def sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
