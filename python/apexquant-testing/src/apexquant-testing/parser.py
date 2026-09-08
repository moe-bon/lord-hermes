from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from apexquant_testing.models import TestCaseResult, TestStatus


def parse_junit_file(path: Path | str) -> list[TestCaseResult]:
    path = Path(path)

    if not path.exists():
        return []

    tree = ET.parse(path)
    root = tree.getroot()

    suites: list[ET.Element] = []

    if root.tag == "testsuites":
        suites = root.findall("testsuite")
    elif root.tag == "testsuite":
        suites = [root]
    else:
        return []

    results: list[TestCaseResult] = []

    for suite in suites:
        suite_name = suite.get("name", "unknown")

        for case in suite.findall("testcase"):
            name = case.get("name", "unknown")
            duration_seconds = float(case.get("time", "0") or "0")

            status = TestStatus.PASSED
            message: str | None = None
            details: dict = {}

            failure = case.find("failure")
            error = case.find("error")
            skipped = case.find("skipped")

            if failure is not None:
                status = TestStatus.FAILED
                message = failure.get("message")
                details = {"text": failure.text or ""}
            elif error is not None:
                status = TestStatus.ERROR
                message = error.get("message")
                details = {"text": error.text or ""}
            elif skipped is not None:
                status = TestStatus.SKIPPED
                message = skipped.get("message")
                details = {"text": skipped.text or ""}

            results.append(
                TestCaseResult(
                    suite=suite_name,
                    name=name,
                    status=status,
                    duration_ms=duration_seconds * 1000,
                    message=message,
                    details=details,
                )
            )

    return results