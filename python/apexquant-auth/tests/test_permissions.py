from apexquant_auth.permissions import has_permission


def test_exact_permission_matches() -> None:
    assert has_permission(["auth:api_keys:write"], "auth:api_keys:write") is True


def test_wildcard_permission_matches() -> None:
    assert has_permission(["*"], "auth:api_keys:write") is True


def test_prefix_wildcard_matches() -> None:
    assert has_permission(["auth:*"], "auth:api_keys:write") is True


def test_missing_permission_denied() -> None:
    assert has_permission(["auth:api_keys:read"], "auth:api_keys:write") is False


def test_empty_permission_denied() -> None:
    assert has_permission(["*"], "") is False