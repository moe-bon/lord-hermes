from __future__ import annotations

from contextvars import ContextVar
from typing import TypedDict

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)
correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)
actor_id_var: ContextVar[str | None] = ContextVar("actor_id", default=None)


class LoggingContext(TypedDict, total=False):
    request_id: str | None
    trace_id: str | None
    correlation_id: str | None
    actor_id: str | None


def set_context(
    request_id: str | None = None,
    trace_id: str | None = None,
    correlation_id: str | None = None,
    actor_id: str | None = None,
) -> None:
    if request_id is not None:
        request_id_var.set(request_id)

    if trace_id is not None:
        trace_id_var.set(trace_id)

    if correlation_id is not None:
        correlation_id_var.set(correlation_id)

    if actor_id is not None:
        actor_id_var.set(actor_id)


def get_context() -> LoggingContext:
    return {
        "request_id": request_id_var.get(),
        "trace_id": trace_id_var.get(),
        "correlation_id": correlation_id_var.get(),
        "actor_id": actor_id_var.get(),
    }


def clear_context() -> None:
    request_id_var.set(None)
    trace_id_var.set(None)
    correlation_id_var.set(None)
    actor_id_var.set(None)