"""Flag lifecycle state machine (Approach A graft).

    DRAFT -> ACTIVE -> DISABLED -> RETIRED (terminal)

RETIRED is immutable and non-reactivatable (DB-enforced as well). Safety-
critical flags additionally lock fail_value=false.
"""
from __future__ import annotations

from enum import Enum


class FlagStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    RETIRED = "RETIRED"


_TRANSITIONS: dict[FlagStatus, set[FlagStatus]] = {
    FlagStatus.DRAFT: {FlagStatus.ACTIVE},
    FlagStatus.ACTIVE: {FlagStatus.DISABLED, FlagStatus.RETIRED},
    FlagStatus.DISABLED: {FlagStatus.ACTIVE, FlagStatus.RETIRED},
    # Terminal: no outbound transitions.
    FlagStatus.RETIRED: set(),
}


class InvalidTransitionError(Exception):
    pass


def assert_transition(current: FlagStatus, target: FlagStatus) -> None:
    if target not in _TRANSITIONS[current]:
        raise InvalidTransitionError(
            f"illegal flag transition {current.value} -> {target.value}"
        )