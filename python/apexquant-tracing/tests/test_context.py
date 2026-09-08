from apexquant_tracing.context import (
    format_traceparent,
    generate_span_id,
    generate_trace_id,
    new_root_context,
    parse_traceparent,
)


def test_generate_ids_are_valid() -> None:
    trace_id = generate_trace_id()
    span_id = generate_span_id()

    assert len(trace_id) == 32
    assert len(span_id) == 16
    assert trace_id != "0" * 32
    assert span_id != "0" * 16


def test_parse_valid_traceparent() -> None:
    header = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"

    context = parse_traceparent(header)

    assert context is not None
    assert context.trace_id == "0af7651916cd43dd8448eb211c80319c"
    assert context.span_id == "b7ad6b7169203331"
    assert context.sampled is True


def test_parse_invalid_traceparent() -> None:
    assert parse_traceparent("invalid") is None
    assert parse_traceparent("00-123-456-01") is None
    assert parse_traceparent("01-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01") is None
    assert parse_traceparent("00-00000000000000000000000000000000-b7ad6b7169203331-01") is None


def test_format_roundtrip() -> None:
    context = new_root_context(sampled=True)

    header = format_traceparent(context)
    parsed = parse_traceparent(header)

    assert parsed is not None
    assert parsed.trace_id == context.trace_id
    assert parsed.span_id == context.span_id
    assert parsed.sampled is True