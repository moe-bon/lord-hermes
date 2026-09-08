import pytest

from apexquant_testing.failure import (
    SimulatedFailure,
    corrupt_payload,
    duplicate_event,
    duplicate_events,
    inject_dependency_unavailable,
    remove_required_fields,
)


def test_duplicate_event() -> None:
    event = {"price": 100.0}

    duplicated = duplicate_event(event, copies=2)

    assert len(duplicated) == 3
    assert all(item == event for item in duplicated)


def test_duplicate_events_at_index() -> None:
    events = [{"id": 1}, {"id": 2}, {"id": 3}]

    duplicated = duplicate_events(events, index=1, copies=1)

    assert len(duplicated) == 4
    assert duplicated[3] == {"id": 2}


def test_corrupt_payload() -> None:
    payload = {"price": 100.0, "symbol": "EURUSD"}

    corrupted = corrupt_payload(payload, key="price", corrupt_value=float("nan"))

    assert corrupted["symbol"] == "EURUSD"
    assert isinstance(corrupted["price"], float)
    assert corrupted["price"] != corrupted["price"]


def test_remove_required_fields() -> None:
    payload = {"symbol": "EURUSD", "price": 1.1, "timestamp": "2026-01-01"}

    reduced = remove_required_fields(payload, ["price", "timestamp"])

    assert reduced == {"symbol": "EURUSD"}


def test_dependency_unavailable_raises() -> None:
    with pytest.raises(SimulatedFailure):
        inject_dependency_unavailable("postgres")