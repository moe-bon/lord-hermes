import pytest
from pydantic import ValidationError

from apexquant_audit.models import AuditEventRequest


def test_valid_audit_event_request() -> None:
    request = AuditEventRequest(
        actor_type="SERVICE",
        service_name="audit-core",
        plane="OBSERVABILITY",
        action="audit.test.created",
    )

    assert request.decision.value == "INFO"
    assert request.severity.value == "INFO"


def test_missing_action_is_invalid() -> None:
    with pytest.raises(ValidationError):
        AuditEventRequest(
            actor_type="SERVICE",
            service_name="audit-core",
            plane="OBSERVABILITY",
            action="   ",
        )