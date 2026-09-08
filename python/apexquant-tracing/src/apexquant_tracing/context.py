from __future__ import annotations

import re
import secrets

from pydantic import BaseModel, Field

TRACEPARENT_PATTERN = re.compile(
    r"^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$"
)

ZERO_TRACE_ID = "0" * 32
ZERO_SPAN_ID = "0" * 16


class TraceContext(BaseModel):
    trace_id: str = Field(min_length=32, max_length=32)
    span_id: str = Field(min_length=16, max_length=16)
    trace_flags: int = Field(ge=0, le=255)
    tracestate: str | None = None

    @property
    def sampled(self) -> bool:
        return bool(self.trace_flags & 0x01)


def generate_trace_id() -> str:
    while True:
        value = secrets.token_hex(16)

        if value != ZERO_TRACE_ID:
            return value


def generate_span_id() -> str:
    while True:
        value = secrets.token_hex(8)

        if value != ZERO_SPAN_ID:
            return value


def parse_traceparent(header: str) -> TraceContext | None:
    value = header.strip()

    if not TRACEPARENT_PATTERN.match(value):
        return None

    version, trace_id, span_id, flags_hex = value.split("-")

    if version != "00":
        return None

    if trace_id == ZERO_TRACE_ID or span_id == ZERO_SPAN_ID:
        return None

    return TraceContext(
        trace_id=trace_id,
        span_id=span_id,
        trace_flags=int(flags_hex, 16),
    )


def format_traceparent(context: TraceContext) -> str:
    return f"00-{context.trace_id}-{context.span_id}-{context.trace_flags:02x}"


def new_root_context(sampled: bool = True) -> TraceContext:
    return TraceContext(
        trace_id=generate_trace_id(),
        span_id=generate_span_id(),
        trace_flags=1 if sampled else 0,
    )


def child_context(parent: TraceContext, sampled: bool | None = None) -> TraceContext:
    flags = parent.trace_flags if sampled is None else (1 if sampled else 0)

    return TraceContext(
        trace_id=parent.trace_id,
        span_id=generate_span_id(),
        trace_flags=flags,
        tracestate=parent.tracestate,
    )