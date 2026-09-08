from hypothesis import given, settings

from apexquant_testing.hypothesis_strategies import (
    finite_floats,
    market_symbols,
    prices,
    volumes,
)


@settings(max_examples=20)
@given(prices())
def test_prices_are_positive_and_finite(value: float) -> None:
    assert value > 0
    assert value == value
    assert value != float("inf")


@settings(max_examples=20)
@given(volumes())
def test_volumes_are_nonnegative_and_finite(value: float) -> None:
    assert value >= 0
    assert value == value
    assert value != float("inf")


@settings(max_examples=20)
@given(finite_floats())
def test_finite_floats_are_finite(value: float) -> None:
    assert value == value
    assert value != float("inf")
    assert value != float("-inf")


@settings(max_examples=20)
@given(market_symbols())
def test_market_symbols_are_clean(symbol: str) -> None:
    assert symbol == symbol.strip()
    assert not symbol.startswith("/")
    assert not symbol.endswith("/")