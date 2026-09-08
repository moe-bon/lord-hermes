from __future__ import annotations

from apexquant_secrets.models import (
    SecretAction,
    SecretClassification,
    SecretPlane,
)
from apexquant_secrets.policy import evaluate_access


def test_control_plane_can_administer() -> None:
    evaluation = evaluate_access(
        SecretPlane.CONTROL,
        SecretClassification.BROKER,
        SecretAction.ADMIN,
    )

    assert evaluation.allowed is True


def test_ai_cannot_read_broker_secret() -> None:
    evaluation = evaluate_access(
        SecretPlane.AI,
        SecretClassification.BROKER,
        SecretAction.READ,
    )

    assert evaluation.allowed is False


def test_ai_cannot_read_database_secret() -> None:
    evaluation = evaluate_access(
        SecretPlane.AI,
        SecretClassification.DATABASE,
        SecretAction.READ,
    )

    assert evaluation.allowed is False


def test_research_cannot_read_execution_secret() -> None:
    evaluation = evaluate_access(
        SecretPlane.DATA_RESEARCH,
        SecretClassification.EXECUTION,
        SecretAction.READ,
    )

    assert evaluation.allowed is False


def test_risk_can_read_broker_secret() -> None:
    evaluation = evaluate_access(
        SecretPlane.RISK,
        SecretClassification.BROKER,
        SecretAction.READ,
    )

    assert evaluation.allowed is True


def test_risk_cannot_administer_secrets() -> None:
    evaluation = evaluate_access(
        SecretPlane.RISK,
        SecretClassification.BROKER,
        SecretAction.ADMIN,
    )

    assert evaluation.allowed is False