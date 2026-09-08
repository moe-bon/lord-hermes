from apexquant_config_validation.canonical import canonical_json, hash_config


def test_canonical_json_sorts_keys() -> None:
    a = {"b": 1, "a": {"y": True, "x": "value"}}
    b = {"a": {"x": "value", "y": True}, "b": 1}

    assert canonical_json(a) == canonical_json(b)


def test_hash_is_stable_regardless_of_key_order() -> None:
    a = {"b": 1, "a": {"y": True, "x": "value"}}
    b = {"a": {"x": "value", "y": True}, "b": 1}

    assert hash_config(a) == hash_config(b)