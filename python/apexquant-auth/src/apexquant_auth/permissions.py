from __future__ import annotations


def has_permission(granted_permissions: list[str], required_permission: str) -> bool:
    if not required_permission.strip():
        return False

    required = required_permission.strip()

    for permission in granted_permissions:
        permission = permission.strip()

        if not permission:
            continue

        if permission == "*":
            return True

        if permission == required:
            return True

        if permission.endswith(":*"):
            prefix = permission[:-1]

            if required.startswith(prefix):
                return True

    return False