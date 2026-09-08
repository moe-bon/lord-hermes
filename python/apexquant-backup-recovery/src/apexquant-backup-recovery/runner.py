from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Protocol, Sequence

from apexquant_backup_recovery.errors import BackupError


class CommandError(BackupError):
    pass


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class CommandRunner(Protocol):
    def run(self, command: Sequence[str], timeout: int | None = None) -> CommandResult:
        raise NotImplementedError


class SubprocessRunner:
    def run(self, command: Sequence[str], timeout: int | None = None) -> CommandResult:
        completed = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if completed.returncode != 0:
            raise CommandError(
                f"command failed with exit code {completed.returncode}: {completed.stderr}"
            )

        return CommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )