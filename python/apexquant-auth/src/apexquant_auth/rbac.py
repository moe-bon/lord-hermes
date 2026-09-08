from __future__ import annotations

import hashlib
import os
from enum import Enum
from typing import Any

import yaml


class Plane(str, Enum):
    CONTROL = "CONTROL"
    MARKET_DATA = "MARKET_DATA"
    TRADING = "TRADING"
    RISK = "RISK"
    AI = "AI"
    DATA_RESEARCH = "DATA_RESEARCH"
    OBSERVABILITY = "OBSERVABILITY"


class EvaluationStatus(str, Enum):
    GRANTED = "GRANTED"
    UNPROVISIONED = "UNPROVISIONED"
    INVARIANT_VIOLATION = "INVARIANT_VIOLATION"


GLOBAL_WILDCARD = "*"
SEGMENT_WILDCARD = "*"


def _candidate_matrix_paths() -> list[str]:
    paths = []
    env_path = os.environ.get("APEX_RBAC_MATRIX_PATH")
    if env_path:
        paths.append(env_path)
    here = os.path.dirname(os.path.abspath(__file__))
    # repo-root/data/rbac relative to python/apexquant-auth/src/apexquant_auth
    repo_root = os.path.abspath(os.path.join(here, "..", "..", "..", ".."))
    paths.append(os.path.join(repo_root, "data", "rbac", "forbidden_matrix.yaml"))
    return paths


_MATRIX_CACHE: dict[str, Any] | None = None
_MATRIX_BYTES: bytes | None = None


def _load_matrix_raw() -> bytes:
    global _MATRIX_BYTES
    if _MATRIX_BYTES is not None:
        return _MATRIX_BYTES
    for path in _candidate_matrix_paths():
        if os.path.exists(path):
            with open(path, "rb") as f:
                _MATRIX_BYTES = f.read()
            return _MATRIX_BYTES
    raise FileNotFoundError("forbidden_matrix.yaml not found")


def matrix_sha256() -> str:
    return hashlib.sha256(_load_matrix_raw()).hexdigest()


def load_matrix() -> dict[str, Any]:
    global _MATRIX_CACHE
    if _MATRIX_CACHE is not None:
        return _MATRIX_CACHE
    _MATRIX_CACHE = yaml.safe_load(_load_matrix_raw())
    return _MATRIX_CACHE


def restricted_planes() -> set[str]:
    return set(load_matrix().get("restricted_planes", []))


def forbidden_patterns(plane: str) -> list[str]:
    return list(load_matrix().get("forbidden", {}).get(plane, []))


def is_restricted(plane: str) -> bool:
    return plane in restricted_planes()


class RbacInvariantError(Exception):
    pass


class InvalidPermissionError(Exception):
    pass


def validate_permission(perm: str) -> None:
    """Locked grammar: domain:action[:resource], full-segment wildcards only."""
    grammar = load_matrix().get("grammar", {})
    min_seg = int(grammar.get("segments", [2, 3])[0])
    max_seg = int(grammar.get("segments", [2, 3])[1])

    if perm == GLOBAL_WILDCARD:
        return
    if not perm:
        raise InvalidPermissionError(perm)
    if perm != perm.lower():
        raise InvalidPermissionError(perm)

    segs = perm.split(":")
    if not (min_seg <= len(segs) <= max_seg):
        raise InvalidPermissionError(perm)

    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789_-")
    for seg in segs:
        if seg == SEGMENT_WILDCARD:
            continue
        if not seg or not all(c in allowed for c in seg):
            raise InvalidPermissionError(perm)


def covers(pattern: str, target: str) -> bool:
    if pattern == GLOBAL_WILDCARD:
        return True
    p = pattern.split(":")
    t = target.split(":")
    for i, seg in enumerate(p):
        if seg == SEGMENT_WILDCARD and i == len(p) - 1:
            return True
        if i >= len(t):
            return False
        if seg == SEGMENT_WILDCARD:
            continue
        if seg != t[i]:
            return False
    return True


def overlaps(a: str, b: str) -> bool:
    return covers(a, b) or covers(b, a)


def evaluate(plane: str, permissions: list[str], has_roles: bool) -> EvaluationStatus:
    """Evaluation-time invariant check (fails closed to deny-all)."""
    if not has_roles:
        return EvaluationStatus.UNPROVISIONED

    if is_restricted(plane):
        for g in permissions:
            if g == GLOBAL_WILDCARD:
                return EvaluationStatus.INVARIANT_VIOLATION
            for d in forbidden_patterns(plane):
                if overlaps(g, d):
                    return EvaluationStatus.INVARIANT_VIOLATION
    return EvaluationStatus.GRANTED


def authorize(plane: str, granted: list[str], request: str) -> bool:
    """Request-time authorization with deny-overrides-allow under wildcards."""
    if is_restricted(plane):
        for d in forbidden_patterns(plane):
            if covers(d, request):
                return False
    for g in granted:
        if covers(g, request):
            return True
    return False


# ---------------------------------------------------------------------------
# Grant-time enforcement (Layer 1) — invariant outranks SUPER_ADMIN.
# ---------------------------------------------------------------------------
def validate_grant(plane: str, permission: str) -> None:
    validate_permission(permission)
    if is_restricted(plane):
        if permission == GLOBAL_WILDCARD:
            raise RbacInvariantError(
                f"global wildcard cannot be granted to plane {plane}"
            )
        for d in forbidden_patterns(plane):
            if overlaps(permission, d):
                raise RbacInvariantError(
                    f"permission '{permission}' is forbidden for plane {plane}"
                )