from __future__ import annotations


class BackupError(Exception):
    pass


class BackupNotFoundError(BackupError):
    pass


class UnsupportedTargetError(BackupError):
    pass


class ConnectionReferenceError(BackupError):
    pass


class RestoreSafetyError(BackupError):
    pass