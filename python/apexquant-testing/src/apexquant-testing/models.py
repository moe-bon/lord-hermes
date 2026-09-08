from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class TestStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


class TestCaseResult(BaseModel):
    suite: str
    name: str
    status: TestStatus
    duration_ms: float = Field(default=0.0, ge=0)
    message: str | None = None
    details: dict = Field(default_factory=dict)
    failure_mode: str | None = None


class TestRunReport(BaseModel):
    run_id: UUID | None = None
    environment: str = "local"
    git_sha: str | None = None
    trigger: str = "manual"
    started_at: datetime
    completed_at: datetime
    ok: bool = False
    total: int = Field(default=0, ge=0)
    passed: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    skipped: int = Field(default=0, ge=0)
    errors: int = Field(default=0, ge=0)
    coverage_pct: float | None = None
    results: list[TestCaseResult] = Field(default_factory=list)

    @classmethod
    def from_results(
        cls,
        results: list[TestCaseResult],
        *,
        environment: str,
        git_sha: str | None,
        trigger: str,
        started_at: datetime,
        completed_at: datetime,
        coverage_pct: float | None = None,
    ) -> TestRunReport:
        passed = sum(1 for r in results if r.status == TestStatus.PASSED)
        failed = sum(1 for r in results if r.status == TestStatus.FAILED)
        skipped = sum(1 for r in results if r.status == TestStatus.SKIPPED)
        errors = sum(1 for r in results if r.status == TestStatus.ERROR)

        return cls(
            environment=environment,
            git_sha=git_sha,
            trigger=trigger,
            started_at=started_at,
            completed_at=completed_at,
            ok=failed == 0 and errors == 0,
            total=len(results),
            passed=passed,
            failed=failed,
            skipped=skipped,
            errors=errors,
            coverage_pct=coverage_pct,
            results=results,
        )