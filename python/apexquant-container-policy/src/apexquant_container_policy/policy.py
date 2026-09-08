from __future__ import annotations

from datetime import datetime, timezone

from apexquant_container_policy.compose import ComposeDocument, ComposeService
from apexquant_container_policy.models import Severity, VerificationReport, Violation

MANAGED_LABEL = "apexquant.managed"
READ_ONLY_EXEMPT_LABEL = "apexquant.container.read_only_exempt"
HEALTHCHECK_EXEMPT_LABEL = "apexquant.container.healthcheck_exempt"

REQUIRED_LABELS = (
    "apexquant.service.name",
    "apexquant.service.plane",
    "apexquant.environment",
    "apexquant.feature",
    "apexquant.version",
    "apexquant.fail_closed_policy",
)

SECRET_KEY_MARKERS = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "private_key",
    "credential",
)

ROOT_USERS = {
    "root",
    "0",
    "0:0",
    "uid=0",
    "uid=0 gid=0",
}


def verify_document(
    document: ComposeDocument,
    *,
    strict_warnings: bool = False,
) -> VerificationReport:
    started_at = datetime.now(timezone.utc)
    violations: list[Violation] = []
    services_checked: list[str] = []

    for service_name in sorted(document.services.keys()):
        service = document.services[service_name]

        if service.labels.get(MANAGED_LABEL) != "true":
            continue

        services_checked.append(service_name)
        _verify_service(service, violations)

    completed_at = datetime.now(timezone.utc)

    errors_count = sum(1 for violation in violations if violation.severity == Severity.ERROR)
    warnings_count = sum(1 for violation in violations if violation.severity == Severity.WARNING)

    ok = errors_count == 0 and (not strict_warnings or warnings_count == 0)

    return VerificationReport(
        compose_path="",
        started_at=started_at,
        completed_at=completed_at,
        ok=ok,
        errors_count=errors_count,
        warnings_count=warnings_count,
        services_checked=services_checked,
        violations=violations,
    )


def _verify_service(service: ComposeService, violations: list[Violation]) -> None:
    _verify_labels(service, violations)
    _verify_image(service, violations)
    _verify_user(service, violations)
    _verify_privilege(service, violations)
    _verify_capabilities(service, violations)
    _verify_healthcheck(service, violations)
    _verify_networks(service, violations)
    _verify_resource_limits(service, violations)
    _verify_environment_secrets(service, violations)


def _verify_labels(service: ComposeService, violations: list[Violation]) -> None:
    for label in REQUIRED_LABELS:
        value = service.labels.get(label)

        if value is None:
            violations.append(
                Violation(
                    service_name=service.name,
                    code="MISSING_LABEL",
                    severity=Severity.ERROR,
                    message=f"required label is missing: {label}",
                )
            )
            continue

        if not value.strip():
            violations.append(
                Violation(
                    service_name=service.name,
                    code="EMPTY_LABEL",
                    severity=Severity.ERROR,
                    message=f"required label is empty: {label}",
                )
            )


def _verify_image(service: ComposeService, violations: list[Violation]) -> None:
    if not service.image:
        violations.append(
            Violation(
                service_name=service.name,
                code="MISSING_IMAGE",
                severity=Severity.ERROR,
                message="managed services must declare an explicit image",
            )
        )
        return

    if "@sha256:" in service.image:
        return

    if ":" not in service.image:
        violations.append(
            Violation(
                service_name=service.name,
                code="MISSING_IMAGE_TAG",
                severity=Severity.ERROR,
                message="image must include an explicit version tag",
            )
        )
        return

    tag = service.image.split(":", 1)[1]

    if not tag.strip():
        violations.append(
            Violation(
                service_name=service.name,
                code="EMPTY_IMAGE_TAG",
                severity=Severity.ERROR,
                message="image tag must not be empty",
            )
        )
        return

    if tag == "latest":
        violations.append(
            Violation(
                service_name=service.name,
                code="LATEST_IMAGE_TAG_FORBIDDEN",
                severity=Severity.ERROR,
                message="latest image tag is forbidden",
            )
        )


def _verify_user(service: ComposeService, violations: list[Violation]) -> None:
    if not service.user:
        violations.append(
            Violation(
                service_name=service.name,
                code="MISSING_USER",
                severity=Severity.ERROR,
                message="managed services must run as an explicit non-root user",
            )
        )
        return

    normalized_user = service.user.strip().lower()

    if normalized_user in ROOT_USERS:
        violations.append(
            Violation(
                service_name=service.name,
                code="ROOT_USER_FORBIDDEN",
                severity=Severity.ERROR,
                message="managed services must not run as root",
            )
        )


def _verify_privilege(service: ComposeService, violations: list[Violation]) -> None:
    if service.privileged:
        violations.append(
            Violation(
                service_name=service.name,
                code="PRIVILEGED_FORBIDDEN",
                severity=Severity.ERROR,
                message="privileged containers are forbidden",
            )
        )

    if "no-new-privileges:true" not in service.security_opt:
        violations.append(
            Violation(
                service_name=service.name,
                code="NO_NEW_PRIVILEGES_MISSING",
                severity=Severity.ERROR,
                message="security_opt must include no-new-privileges:true",
            )
        )


def _verify_capabilities(service: ComposeService, violations: list[Violation]) -> None:
    if not any(cap.upper() == "ALL" for cap in service.cap_drop):
        violations.append(
            Violation(
                service_name=service.name,
                code="CAP_DROP_ALL_MISSING",
                severity=Severity.ERROR,
                message="cap_drop must include ALL",
            )
        )

    if not service.read_only and service.labels.get(READ_ONLY_EXEMPT_LABEL) != "true":
        violations.append(
            Violation(
                service_name=service.name,
                code="READ_ONLY_REQUIRED",
                severity=Severity.ERROR,
                message="managed services must use a read-only root filesystem",
            )
        )


def _verify_healthcheck(service: ComposeService, violations: list[Violation]) -> None:
    if service.labels.get(HEALTHCHECK_EXEMPT_LABEL) == "true":
        return

    if service.healthcheck is None:
        violations.append(
            Violation(
                service_name=service.name,
                code="HEALTHCHECK_MISSING",
                severity=Severity.ERROR,
                message="managed services must define a healthcheck",
            )
        )
        return

    if not service.healthcheck.test:
        violations.append(
            Violation(
                service_name=service.name,
                code="INVALID_HEALTHCHECK",
                severity=Severity.ERROR,
                message="healthcheck test must not be empty",
            )
        )


def _verify_networks(service: ComposeService, violations: list[Violation]) -> None:
    if not service.networks:
        violations.append(
            Violation(
                service_name=service.name,
                code="NETWORKS_MISSING",
                severity=Severity.ERROR,
                message="managed services must attach to explicit networks",
            )
        )
        return

    if "default" in service.networks:
        violations.append(
            Violation(
                service_name=service.name,
                code="DEFAULT_NETWORK_FORBIDDEN",
                severity=Severity.ERROR,
                message="managed services must not use the default network",
            )
        )


def _verify_resource_limits(service: ComposeService, violations: list[Violation]) -> None:
    deploy = service.deploy

    if not isinstance(deploy, dict):
        violations.append(
            Violation(
                service_name=service.name,
                code="RESOURCE_LIMITS_MISSING",
                severity=Severity.ERROR,
                message="managed services must define deploy resource limits",
            )
        )
        return

    resources = deploy.get("resources")

    if not isinstance(resources, dict):
        violations.append(
            Violation(
                service_name=service.name,
                code="RESOURCE_LIMITS_MISSING",
                severity=Severity.ERROR,
                message="deploy.resources must be defined",
            )
        )
        return

    limits = resources.get("limits")

    if not isinstance(limits, dict):
        violations.append(
            Violation(
                service_name=service.name,
                code="RESOURCE_LIMITS_MISSING",
                severity=Severity.ERROR,
                message="deploy.resources.limits must be defined",
            )
        )
        return

    if limits.get("memory") is None:
        violations.append(
            Violation(
                service_name=service.name,
                code="MEMORY_LIMIT_MISSING",
                severity=Severity.ERROR,
                message="memory limit must be defined",
            )
        )

    if limits.get("cpus") is None:
        violations.append(
            Violation(
                service_name=service.name,
                code="CPU_LIMIT_MISSING",
                severity=Severity.ERROR,
                message="CPU limit must be defined",
            )
        )


def _verify_environment_secrets(service: ComposeService, violations: list[Violation]) -> None:
    for key, value in service.environment.items():
        normalized_key = key.lower()

        if not any(marker in normalized_key for marker in SECRET_KEY_MARKERS):
            continue

        if not value:
            continue

        if value.startswith("${") and value.endswith("}"):
            continue

        violations.append(
            Violation(
                service_name=service.name,
                code="LITERAL_SECRET_IN_ENVIRONMENT",
                severity=Severity.ERROR,
                message=f"environment variable {key} appears to contain a literal secret",
            )
        )