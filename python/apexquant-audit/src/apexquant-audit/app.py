from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    generate_latest,
)
from psycopg_pool import ConnectionPool
from pydantic_settings import BaseSettings, SettingsConfigDict

from apexquant_audit.hashing import verify_chain
from apexquant_audit.kafka import AuditKafkaPublisher
from apexquant_audit.models import AuditEventRequest
from apexquant_audit.redaction import redact_data
from apexquant_audit.repository import (
    PostgresAuditRepository,
    apply_migrations,
)


class AuditSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APEX_AUDIT_",
        env_file=".env",
        extra="ignore",
    )

    http_addr: str = "0.0.0.0:8087"
    database_url: str
    kafka_bootstrap_servers: str | None = None
    topic: str = "platform.audit.event.v1"
    migrations_dir: str = "/migrations/postgres/audit"
    ingest_shared_secret: str | None = None
    migrate_on_start: bool = True


def create_audit_app(settings: AuditSettings) -> FastAPI:
    registry = CollectorRegistry()

    audit_events_ingested_total = Counter(
        "apex_audit_events_ingested_total",
        "Audit events ingested",
        registry=registry,
    )

    audit_publish_failures_total = Counter(
        "apex_audit_publish_failures_total",
        "Audit event publish failures",
        registry=registry,
    )

    audit_chain_violations_total = Counter(
        "apex_audit_chain_violations_total",
        "Audit chain integrity violations",
        registry=registry,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.migrate_on_start:
            apply_migrations(settings.database_url, settings.migrations_dir)

        pool = ConnectionPool(
            conninfo=settings.database_url,
            max_size=10,
        )

        repository = PostgresAuditRepository(pool)
        publisher = AuditKafkaPublisher(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            topic=settings.topic,
        )

        await publisher.start()

        relay_task: asyncio.Task | None = None

        if publisher.enabled:
            relay_task = asyncio.create_task(relay_loop(repository, publisher))

        app.state.pool = pool
        app.state.repository = repository
        app.state.publisher = publisher

        try:
            yield
        finally:
            if relay_task is not None:
                relay_task.cancel()
                try:
                    await relay_task
                except asyncio.CancelledError:
                    pass

            await publisher.stop()
            pool.close()

    app = FastAPI(
        title="apexquant-audit",
        version="0.13.0",
        lifespan=lifespan,
    )

    app.state.settings = settings
    app.state.metrics_registry = registry
    app.state.audit_events_ingested_total = audit_events_ingested_total
    app.state.audit_publish_failures_total = audit_publish_failures_total
    app.state.audit_chain_violations_total = audit_chain_violations_total

    def get_repository(request: Request) -> PostgresAuditRepository:
        return request.app.state.repository

    def require_ingest_key(
        request: Request,
        x_audit_ingest_key: str | None = Header(default=None),
    ) -> None:
        expected = request.app.state.settings.ingest_shared_secret

        if expected and x_audit_ingest_key != expected:
            raise HTTPException(status_code=401, detail="invalid audit ingest key")

    async def relay_loop(
        repository: PostgresAuditRepository,
        publisher: AuditKafkaPublisher,
    ) -> None:
        while True:
            await asyncio.sleep(5)

            unpublished = await asyncio.to_thread(repository.fetch_unpublished, 100)

            for row in unpublished:
                ok, error = await publisher.publish(row)

                await asyncio.to_thread(
                    repository.record_delivery,
                    row["event_seq"],
                    ok,
                    error,
                )

                if not ok:
                    audit_publish_failures_total.inc()

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    async def readyz(request: Request) -> JSONResponse:
        repository = get_repository(request)

        try:
            await asyncio.to_thread(repository.fetch_events, 1)
            return JSONResponse({"ready": True})
        except Exception:
            return JSONResponse(status_code=503, content={"ready": False})

    @app.get("/metrics")
    async def metrics(request: Request):
        return generate_latest(request.app.state.metrics_registry)

    @app.post(
        "/v1/audit/events",
        dependencies=[Depends(require_ingest_key)],
    )
    async def ingest_audit_event(
        payload: AuditEventRequest,
        request: Request,
    ) -> dict[str, Any]:
        repository = get_repository(request)
        publisher: AuditKafkaPublisher = request.app.state.publisher

        redacted = payload.model_copy(update={"data": redact_data(payload.data)})
        fields = redacted.to_fields()

        record = await asyncio.to_thread(repository.append_event, fields)

        request.app.state.audit_events_ingested_total.inc()

        if publisher.enabled:
            rows = await asyncio.to_thread(
                repository.fetch_events,
                1,
                None,
                None,
                str(record.event_id),
            )

            if rows:
                ok, error = await publisher.publish(rows[0])

                await asyncio.to_thread(
                    repository.record_delivery,
                    record.event_seq,
                    ok,
                    error,
                )

                if not ok:
                    request.app.state.audit_publish_failures_total.inc()

        return {
            "event_seq": record.event_seq,
            "event_id": str(record.event_id),
            "occurred_at": record.occurred_at.isoformat(),
            "event_hash": record.event_hash,
        }

    @app.get(
        "/v1/audit/events",
        dependencies=[Depends(require_ingest_key)],
    )
    async def list_audit_events(
        request: Request,
        limit: int = 100,
        service_name: str | None = None,
        action: str | None = None,
        request_id: str | None = None,
    ) -> list[dict[str, Any]]:
        repository = get_repository(request)

        rows = await asyncio.to_thread(
            repository.fetch_events,
            limit,
            service_name,
            action,
            request_id,
        )

        for row in rows:
            row["event_id"] = str(row["event_id"])
            row["occurred_at"] = row["occurred_at"].isoformat()
            row["received_at"] = row["received_at"].isoformat()

        return rows

    @app.get(
        "/v1/audit/verify",
        dependencies=[Depends(require_ingest_key)],
    )
    async def verify_audit_chain(
        request: Request,
        start_seq: int | None = None,
        end_seq: int | None = None,
        limit: int = 1000,
    ) -> dict[str, Any]:
        repository = get_repository(request)

        initial_prev_hash, rows = await asyncio.to_thread(
            repository.fetch_verification_range,
            start_seq,
            end_seq,
            limit,
        )

        report = verify_chain(rows, initial_prev_hash)

        await asyncio.to_thread(
            repository.record_integrity_check,
            start_seq,
            end_seq,
            report,
        )

        if not report["ok"]:
            request.app.state.audit_chain_violations_total.inc()

        return report

    return app