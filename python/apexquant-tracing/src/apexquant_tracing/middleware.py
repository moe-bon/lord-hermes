from __future__ import annotations

from typing import Awaitable, Callable

from opentelemetry import trace
from opentelemetry.propagate import extract, inject
from opentelemetry.trace import Status, StatusCode
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from apexquant_tracing.redaction import is_secret_key


class TracingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, service_name: str) -> None:
        super().__init__(app)

        self._service_name = service_name
        self._tracer = trace.get_tracer(service_name)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        carrier = dict(request.headers)

        context = extract(carrier)

        method = request.method
        path = request.url.path

        with self._tracer.start_as_current_span(
            f"{method} {path}",
            context=context,
            kind=trace.SpanKind.SERVER,
        ) as span:
            span.set_attribute("http.method", method)
            span.set_attribute("http.target", path)
            span.set_attribute("apex.service", self._service_name)

            request_id = request.headers.get("x-request-id")

            if request_id:
                span.set_attribute("apex.request_id", request_id)

            correlation_id = request.headers.get("x-correlation-id")

            if correlation_id:
                span.set_attribute("apex.correlation_id", correlation_id)

            try:
                response = await call_next(request)
            except Exception as exc:
                span.set_status(Status(StatusCode.ERROR))
                span.record_exception(exc)
                raise

            span.set_attribute("http.status_code", response.status_code)

            span_context = trace.get_current_span().get_span_context()

            if span_context.is_valid:
                response.headers["traceparent"] = (
                    f"00-{format(span_context.trace_id, '032x')}-"
                    f"{format(span_context.span_id, '016x')}-"
                    f"{span_context.trace_flags:02x}"
                )

            return response


def safe_set_attribute(span, key: str, value: object) -> None:
    if is_secret_key(key):
        span.set_attribute(key, "[REDACTED]")
    else:
        span.set_attribute(key, value)