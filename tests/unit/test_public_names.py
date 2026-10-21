import pytest

import fishbaseball as fb


@pytest.mark.parametrize("module", [fb.lahman, fb.retrosheet], ids=lambda m: m.__name__)
def test_dir_shows_only_the_intended_public_names(module):
    public = {name for name in dir(module) if not name.startswith("_")}
    assert public == set(module.__all__)
    assert "annotations" not in public
