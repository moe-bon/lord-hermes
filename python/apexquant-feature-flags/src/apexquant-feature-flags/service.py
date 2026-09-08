"""Flag control service: RBAC-gated mutations + audit + event propagation.

Binding Decisions #7 (authorization/audit), #6 (propagation), #5 (fail policy),
#10 (no secrets, mandate). The emergency kill switch NEVER routes through here
(Binding Improvement #1).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone

from apexquant_feature_flags.lifecycle import FlagStatus, assert_transition

# RBAC permission required for standard mutations (0.12). Safety-critical
# flags declare a stronger authority stored on the flag row.
FLAG_WRITE_PERMISSION = "flags:write"

# Permissions that may never be stored in a flag (no secrets in flags).
_FORBIDDEN_VALUE_MARKERS = (
    "password", "secret", "token", "api_key", "private_key", "credential",
)


class FlagAuthorizationError(Exception):
    pass


class FlagValidationError(Exception):
    pass


@dataclass
class MutationRequest:
    flag_key: str
    actor: str
    reason: str
    authority: str          # the caller's granted RBAC permission set marker
    payload: dict


class FlagControlService:
    def __init__(self, repository, event_bus, audit) -> None:
        self._repo = repository
        self._bus = event_bus
        self._audit = audit

    # -- authorization -------------------------------------------------------
    def _authorize(self, flag_row: dict | None, request: MutationRequest) -> None:
        required = (
            flag_row["required_authority"]
            if flag_row is not None
            else FLAG_WRITE_PERMISSION
        )
        if request.authority != required and request.authority != "flags:admin":
            raise FlagAuthorizationError(
                f"mutation requires authority '{required}', got '{request.authority}'"
            )

    def _reject_secrets(self, payload: dict) -> None:
        blob = json.dumps(payload).lower()
        for marker in _FORBIDDEN_VALUE_MARKERS:
            if marker in blob:
                raise FlagValidationError(
                    "flags must never carry secrets or credential material"
                )

    # -- mutations -----------------------------------------------------------
    def create_flag(self, request: MutationRequest) -> dict:
        self._authorize(None, request)
        self._reject_secrets(request.payload)

        flag = self._repo.create_flag(request.payload)
        self._audit.record(
            flag_key=flag["flag_key"],
            generation=flag["generation"],
            event_type="CREATED",
            actor=request.actor,
            reason=request.reason,
            authority=request.authority,
            after_state=flag,
        )
        self._bus.publish("flags.changed.v1", self._change_envelope(flag, "CREATED"))
        return flag

    def transition(self, request: MutationRequest, target: FlagStatus) -> dict:
        before = self._repo.get_flag(request.flag_key)
        if before is None:
            raise FlagValidationError(f"flag not found: {request.flag_key}")

        self._authorize(before, request)
        assert_transition(FlagStatus(before["status"]), target)

        after = self._repo.set_status(request.flag_key, target)
        event_type = {
            FlagStatus.ACTIVE: "ACTIVATED",
            FlagStatus.DISABLED: "DISABLED",
            FlagStatus.RETIRED: "RETIRED",
        }[target]

        self._audit.record(
            flag_key=request.flag_key,
            generation=after["generation"],
            event_type=event_type,
            actor=request.actor,
            reason=request.reason,
            authority=request.authority,
            before_state=before,
            after_state=after,
        )
        self._bus.publish("flags.changed.v1", self._change_envelope(after, event_type))
        return after

    def update_rollout(self, request: MutationRequest, rollout_bps: int) -> dict:
        """Rollout-percentage changes are explicit canary-step audit events."""
        before = self._repo.get_flag(request.flag_key)
        if before is None:
            raise FlagValidationError(f"flag not found: {request.flag_key}")

        self._authorize(before, request)

        if before["status"] != FlagStatus.ACTIVE.value:
            raise FlagValidationError("rollout changes require an ACTIVE flag")

        previous = int(before["rollout_bps"])
        if rollout_bps < previous:
            # Rollbacks are allowed but still audited as a step.
            step = "ROLLOUT_DECREASE"
        elif rollout_bps == previous:
            raise FlagValidationError("rollout value unchanged")
        else:
            step = "ROLLOUT_STEP"

        after = self._repo.set_rollout(request.flag_key, rollout_bps)

        self._audit.record(
            flag_key=request.flag_key,
            generation=after["generation"],
            event_type=step,
            actor=request.actor,
            reason=request.reason,
            authority=request.authority,
            before_state=before,
            after_state=after,
        )
        self._bus.publish("flags.changed.v1", self._change_envelope(after, step))
        return after

    @staticmethod
    def _change_envelope(flag: dict, event_type: str) -> dict:
        return {
            "flag_key": flag["flag_key"],
            "event_type": event_type,
            "generation": flag["generation"],
            "flag_class": flag["flag_class"],
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }