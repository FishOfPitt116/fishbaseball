from fishbaseball._compat import SUPPORTED_SCHEMAS


def test_lahman_schema_1_is_supported():
    assert SUPPORTED_SCHEMAS["lahman"] == {1}


def test_supported_schemas_are_sets_of_int():
    for source, versions in SUPPORTED_SCHEMAS.items():
        assert isinstance(source, str)
        assert isinstance(versions, set) and all(isinstance(v, int) for v in versions)
