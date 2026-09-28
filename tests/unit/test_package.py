import re
from pathlib import Path

import fishbaseball as fb

PYPROJECT = Path(__file__).parent.parent.parent / "pyproject.toml"


def test_version_is_exposed_and_matches_pyproject():
    assert re.match(r"^\d+\.\d+\.\d+$", fb.__version__)
    match = re.search(r'(?m)^version = "([^"]+)"', PYPROJECT.read_text())
    assert match is not None, 'couldn\'t find a version = "..." line in pyproject.toml'
    assert fb.__version__ == match.group(1), (
        "src/fishbaseball/_version.py and pyproject.toml disagree"
    )


def test_config_is_exposed():
    assert fb.config.get("backend") == "polars"
