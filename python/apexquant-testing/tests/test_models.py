from datetime import datetime, timedelta, timezone

from apexquant_testing.models import TestCaseResult, TestRunReport, TestStatus


def test_report_from_results_counts_correctly() -> None:
    now = datetime.now(timezone.utc)

    results = [
        TestCaseResult(suite="suite", name="one", status=TestStatus.PASSED),
        TestCaseResult(suite="suite", name="two", status=TestStatus.FAILED),
        TestCaseResult(suite="suite", name="three", status=TestStatus.SKIPPED),
        TestCaseResult(suite="suite", name="four", status=TestStatus.ERROR),
    ]

    report = TestRunReport.from_results(
        results=results,
        environment="local",
        git_sha="abc123",
        trigger="unit-test",
        started_at=now,
        completed_at=now + timedelta(seconds=1),
    )

    assert report.total == 4
    assert report.passed == 1
    assert report.failed == 1
    assert report.skipped == 1
    assert report.errors == 1
    assert report.ok is False