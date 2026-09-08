from __future__ import annotations


class DisasterRecoveryError(Exception):
    pass


class DRNotFoundError(DisasterRecoveryError):
    pass


class DRStateError(DisasterRecoveryError):
    pass


class DRDrillError(DisasterRecoveryError):
    pass