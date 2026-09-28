import fishbaseball as fb


def test_version_is_exposed():
    assert fb.__version__ == "0.1.0"


def test_config_is_exposed():
    assert fb.config.get("backend") == "polars"
