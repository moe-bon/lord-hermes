from apexquant_logging.redaction import redact_data


def test_redacts_secret_keys() -> None:
    payload = {
        "broker_api_key": "abc",
        "nested": {
            "password": "hunter2",
            "safe": "visible",
        },
        "items": [
            {"token": "xyz", "ok": True},
        ],
    }

    redacted = redact_data(payload)

    assert redacted["broker_api_key"] == "[REDACTED]"
    assert redacted["nested"]["password"] == "[REDACTED]"
    assert redacted["nested"]["safe"] == "visible"
    assert redacted["items"][0]["token"] == "[REDACTED]"
    assert redacted["items"][0]["ok"] is True