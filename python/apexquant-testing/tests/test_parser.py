from pathlib import Path

from apexquant_testing.models import TestStatus
from apexquant_testing.parser import parse_junit_file


def test_parse_junit_xml(tmp_path: Path) -> None:
    xml = """
<testsuites>
  <testsuite name="example" tests="3">
    <testcase classname="tests.test_example" name="test_ok" time="0.010"/>
    <testcase classname="tests.test_example" name="test_failed" time="0.020">
      <failure message="boom">traceback</failure>
    </testcase>
    <testcase classname="tests.test_example" name="test_skipped" time="0.000">
      <skipped/>
    </testcase>
  </testsuite>
</testsuites>
"""

    path = tmp_path / "junit.xml"
    path.write_text(xml, encoding="utf-8")

    results = parse_junit_file(path)

    assert len(results) == 3

    assert results[0].name == "test_ok"
    assert results[0].status == TestStatus.PASSED
    assert results[0].duration_ms == 10.0

    assert results[1].name == "test_failed"
    assert results[1].status == TestStatus.FAILED
    assert results[1].message == "boom"

    assert results[2].name == "test_skipped"
    assert results[2].status == TestStatus.SKIPPED