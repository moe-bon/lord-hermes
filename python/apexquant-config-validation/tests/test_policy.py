from apexquant_config_validation.policy import (
    is_secret_key,
    is_secret_reference,
    load_policy,
    scan_secrets,
)


def test_secret_key_detection() -> None:
    policy = load_policy()

    assert is_secret_key("postgres_password", policy)
    assert is_secret_key("broker_api_key", policy)
    assert not is_secret_key("service_name", policy)


def test_secret_reference_detection() -> None:
    policy = load_policy()

    assert is_secret_reference("env://POSTGRES_PASSWORD", policy)
    assert is_secret_reference("vault://apex/postgres/password", policy)
    assert is_secret_reference("secret://postgres-password", policy)
    assert is_secret_reference("${POSTGRES_PASSWORD}", policy)
    assert not is_secret_reference("hunter2", policy)


def test_scan_secrets_detects_literal_secret() -> None:
    policy = load_policy()

    document = {
        "infrastructure": {
            "postgres": {
                "password": "hunter2",
            }
        }
    }

    issues = scan_secrets(document, policy)

    assert len(issues) == 1
    assert issues[0].path == "$.infrastructure.postgres.password"


def test_scan_secrets_accepts_reference() -> None:
    policy = load_policy()

    document = {
        "infrastructure": {
            "postgres": {
                "password": "env://POSTGRES_PASSWORD",
            }
        }
    }

    issues = scan_secrets(document, policy)

    assert issues == []