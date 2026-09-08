from apexquant_tracing.redaction import redact_attributes


def test_redacts_secret_attributes() -> None:
    attributes = {
        "api_key": "abc",
        "nested": {
            "password": "hunter2",
            "safe": "visible",
        },
        "items": [
            {"token": "xyz", "ok": True},
        ],
    }

    redacted = redact_attributes(attributes)

    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["nested"]["password"] == "[REDACTED]"
    assert redacted["nested"]["safe"] == "visible"
    assert redacted["items"][0]["token"] == "[REDACTED]"
    assert redacted["items"][0]["ok"] is True