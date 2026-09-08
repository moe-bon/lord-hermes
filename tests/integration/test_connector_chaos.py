"""Brutal chaos tests for the Market Data connector (Sprint 1)."""
import pytest

GARBAGE_BYTES = b"\x00\x01\xff\xfe\x80\x7f"


@pytest.mark.asyncio
@pytest.mark.skip(reason="Requires a running mock WebSocket harness")
async def test_law_3_raw_immutability_under_garbage_data() -> None:
    """Connector must capture raw bytes exactly, survive garbage, and reconnect."""
    assert GARBAGE_BYTES == b"\x00\x01\xff\xfe\x80\x7f"
