from datetime import datetime, timedelta, timezone

from apexquant_testing.clock import FakeClock


def test_fake_clock_advances() -> None:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clock = FakeClock(start=start)

    assert clock.now() == start

    clock.advance(timedelta(seconds=30))

    assert clock.now() == datetime(2026, 1, 1, 0, 0, 30, tzinfo=timezone.utc)