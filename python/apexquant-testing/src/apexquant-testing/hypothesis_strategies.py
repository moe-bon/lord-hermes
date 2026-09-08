from __future__ import annotations

import string
from datetime import datetime, timezone

from hypothesis.strategies import (
    datetimes,
    floats,
    just,
    text,
)


def finite_floats(
    min_value: float = -1e12,
    max_value: float = 1e12,
):
    return floats(
        min_value=min_value,
        max_value=max_value,
        allow_nan=False,
        allow_infinity=False,
    )


def prices():
    return finite_floats(min_value=1e-8, max_value=1e9)


def volumes():
    return finite_floats(min_value=0.0, max_value=1e12)


def market_symbols():
    alphabet = string.ascii_uppercase + string.digits + "/"

    return text(
        alphabet=alphabet,
        min_size=3,
        max_size=20,
    ).filter(
        lambda symbol: symbol == symbol.strip()
        and not symbol.startswith("/")
        and not symbol.endswith("/")
    )


def utc_timestamps():
    return datetimes(
        min_value=datetime(2000, 1, 1),
        max_value=datetime(2100, 1, 1),
        timezones=just(timezone.utc),
    )