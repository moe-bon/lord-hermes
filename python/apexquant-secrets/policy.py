from __future__ import annotations

from apexquant_secrets.models import (
    PolicyEffect,
    PolicyEvaluation,
    PolicyRule,
    SecretAction,
    SecretClassification,
    SecretPlane,
)

AI_FORBIDDEN_CLASSIFICATIONS = {
    SecretClassification.BROKER,
    SecretClassification.EXECUTION,
    SecretClassification.DATABASE,
    SecretClassification.INFRASTRUCTURE,
}

RESEARCH_FORBIDDEN_CLASSIFICATIONS = {
    SecretClassification.BROKER,
    SecretClassification.EXECUTION,
    SecretClassification.DATABASE,
    SecretClassification.INFRASTRUCTURE,
    SecretClassification.API,
}


def default_policy_rules() -> list[PolicyRule]:
    return [
        PolicyRule(
            subject_plane=SecretPlane.AI,
            classification=SecretClassification.BROKER,
            action=None,
            effect=PolicyEffect.DENY,
        ),
        PolicyRule(
            subject_plane=SecretPlane.AI,
            classification=SecretClassification.EXECUTION,
            action=None,
            effect=PolicyEffect.DENY,
        ),
        PolicyRule(
            subject_plane=SecretPlane.AI,
            classification=SecretClassification.DATABASE,
            action=None,
            effect=PolicyEffect.DENY,
        ),
        PolicyRule(
            subject_plane=SecretPlane.AI,
            classification=SecretClassification.INFRASTRUCTURE,
            action=None,
            effect=PolicyEffect.DENY,
        ),
        PolicyRule(
            subject_plane=SecretPlane.DATA_RESEARCH,
            classification=SecretClassification.BROKER,
            action=None,
            effect=PolicyEffect.DENY,
        ),
        PolicyRule(
            subject_plane=SecretPlane.DATA_RESEARCH,
            classification=SecretClassification.EXECUTION,
            action=None,
            effect=PolicyEffect.DENY,
        ),
        PolicyRule(
            subject_plane=SecretPlane.DATA_RESEARCH,
            classification=SecretClassification.DATABASE,
            action=None,
            effect=PolicyEffect.DENY,
        ),
        PolicyRule(
            subject_plane=SecretPlane.DATA_RESEARCH,
            classification=SecretClassification.INFRASTRUCTURE,
            action=None,
            effect=PolicyEffect.DENY,
        ),
        PolicyRule(
            subject_plane=SecretPlane.CONTROL,
            classification=None,
            action=None,
            effect=PolicyEffect.ALLOW,
        ),
        PolicyRule(
            subject_plane=SecretPlane.RISK,
            classification=SecretClassification.BROKER,
            action=SecretAction.READ,
            effect=PolicyEffect.ALLOW,
        ),
        PolicyRule(
            subject_plane=SecretPlane.RISK,
            classification=SecretClassification.EXECUTION,
            action=SecretAction.READ,
            effect=PolicyEffect.ALLOW,
        ),
        PolicyRule(
            subject_plane=SecretPlane.RISK,
            classification=SecretClassification.DATABASE,
            action=SecretAction.READ,
            effect=PolicyEffect.ALLOW,
        ),
        PolicyRule(
            subject_plane=SecretPlane.RISK,
            classification=SecretClassification.INFRASTRUCTURE,
            action=SecretAction.READ,
            effect=PolicyEffect.ALLOW,
        ),
        PolicyRule(
            subject_plane=SecretPlane.RISK,
            classification=SecretClassification.API,
            action=SecretAction.READ,
            effect=PolicyEffect.ALLOW,
        ),
        PolicyRule(
            subject_plane=SecretPlane.RISK,
            classification=SecretClassification.OBSERVABILITY,
            action=SecretAction.READ,
            effect=PolicyEffect.ALLOW,
        ),
        PolicyRule(
            subject_plane=SecretPlane.MARKET_DATA,
            classification=SecretClassification.INFRASTRUCTURE,
            action=SecretAction.READ,
            effect=PolicyEffect.ALLOW,
        ),
        PolicyRule(
            subject_plane=SecretPlane.MARKET_DATA,
            classification=SecretClassification.DATABASE,
            action=SecretAction.READ,
            effect=PolicyEffect.ALLOW,
        ),
        PolicyRule(
            subject_plane=SecretPlane.MARKET_DATA,
            classification=SecretClassification.API,
            action=SecretAction.READ,
            effect=PolicyEffect.ALLOW,
        ),
        PolicyRule(
            subject_plane=SecretPlane.MARKET_DATA,
            classification=SecretClassification.OBSERVABILITY,
            action=SecretAction.READ,
            effect=PolicyEffect.ALLOW,
        ),
        PolicyRule(
            subject_plane=SecretPlane.TRADING,
            classification=SecretClassification.DATABASE,
            action=SecretAction.READ,
            effect=PolicyEffect.ALLOW,
        ),
        PolicyRule(
            subject_plane=SecretPlane.TRADING,
            classification=SecretClassification.API,
            action=SecretAction.READ,
            effect=PolicyEffect.ALLOW,
        ),
        PolicyRule(
            subject_plane=SecretPlane.TRADING,
            classification=SecretClassification.OBSERVABILITY,
            action=SecretAction.READ,
            effect=PolicyEffect.ALLOW,
        ),
        PolicyRule(
            subject_plane=SecretPlane.AI,
            classification=SecretClassification.MODEL,
            action=SecretAction.READ,
            effect=PolicyEffect.ALLOW,
        ),
        PolicyRule(
            subject_plane=SecretPlane.AI,
            classification=SecretClassification.KNOWLEDGE,
            action=SecretAction.READ,
            effect=PolicyEffect.ALLOW,
        ),
        PolicyRule(
            subject_plane=SecretPlane.AI,
            classification=SecretClassification.API,
            action=SecretAction.READ,
            effect=PolicyEffect.ALLOW,
        ),
        PolicyRule(
            subject_plane=SecretPlane.AI,
            classification=SecretClassification.OBSERVABILITY,
            action=SecretAction.READ,
            effect=PolicyEffect.ALLOW,
        ),
        PolicyRule(
            subject_plane=SecretPlane.DATA_RESEARCH,
            classification=SecretClassification.MODEL,
            action=SecretAction.READ,
            effect=PolicyEffect.ALLOW,
        ),
        PolicyRule(
            subject_plane=SecretPlane.DATA_RESEARCH,
            classification=SecretClassification.KNOWLEDGE,
            action=SecretAction.READ,
            effect=PolicyEffect.ALLOW,
        ),
        PolicyRule(
            subject_plane=SecretPlane.DATA_RESEARCH,
            classification=SecretClassification.OBSERVABILITY,
            action=SecretAction.READ,
            effect=PolicyEffect.ALLOW,
        ),
        PolicyRule(
            subject_plane=SecretPlane.OBSERVABILITY,
            classification=SecretClassification.OBSERVABILITY,
            action=SecretAction.READ,
            effect=PolicyEffect.ALLOW,
        ),
        PolicyRule(
            subject_plane=SecretPlane.OBSERVABILITY,
            classification=SecretClassification.INFRASTRUCTURE,
            action=SecretAction.READ,
            effect=PolicyEffect.ALLOW,
        ),
    ]


def evaluate_access(
    subject_plane: SecretPlane,
    classification: SecretClassification,
    action: SecretAction,
    extra_rules: list[PolicyRule] | None = None,
) -> PolicyEvaluation:
    rules = default_policy_rules()

    if extra_rules:
        rules.extend(extra_rules)

    matched: list[PolicyRule] = []

    for rule in rules:
        if rule.subject_plane is not None and rule.subject_plane != subject_plane:
            continue

        if rule.classification is not None and rule.classification != classification:
            continue

        if rule.action is not None and rule.action != action:
            continue

        matched.append(rule)

    if any(rule.effect == PolicyEffect.DENY for rule in matched):
        return PolicyEvaluation(
            allowed=False,
            reason=(
                f"{subject_plane.value} is denied access to "
                f"{classification.value} for action {action.value}"
            ),
            matched_rules=matched,
        )

    if any(rule.effect == PolicyEffect.ALLOW for rule in matched):
        return PolicyEvaluation(
            allowed=True,
            reason=(
                f"{subject_plane.value} is allowed access to "
                f"{classification.value} for action {action.value}"
            ),
            matched_rules=matched,
        )

    return PolicyEvaluation(
        allowed=False,
        reason=(
            f"default deny: no matching allow rule for {subject_plane.value} "
            f"accessing {classification.value} with action {action.value}"
        ),
        matched_rules=matched,
    )