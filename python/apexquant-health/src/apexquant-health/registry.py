from __future__ import annotations

import asyncio
import socket
from typing import Any

from psycopg_pool import AsyncConnectionPool


class ServiceRegistryClient:
    def __init__(
        self,
        pool: AsyncConnectionPool,
        service_name: str,
        plane: str,
        environment: str,
        version: str,
        endpoint: str,
        instance_id: str | None = None,
    ) -> None:
        self._pool = pool
        self._service_name = service_name
        self._plane = plane
        self._environment = environment
        self._version = version
        self._endpoint = endpoint
        self._instance_id = instance_id or f"{service_name}-{socket.gethostname()}-{id(self)}"
        self._heartbeat_task: asyncio.Task | None = None

    @property
    def instance_id(self) -> str:
        return self._instance_id

    async def register(self) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                """
                INSERT INTO health.service_registry 
                (instance_id, service_name, plane, environment, version, endpoint, status)
                VALUES (%s, %s, %s, %s, %s, %s, 'HEALTHY')
                ON CONFLICT (instance_id) DO UPDATE SET
                    status = 'HEALTHY',
                    last_heartbeat = now()
                """,
                (
                    self._instance_id,
                    self._service_name,
                    self._plane,
                    self._environment,
                    self._version,
                    self._endpoint,
                ),
            )

    async def heartbeat(self) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                """
                UPDATE health.service_registry
                SET last_heartbeat = now(), status = 'HEALTHY'
                WHERE instance_id = %s
                """,
                (self._instance_id,),
            )

    async def deregister(self) -> None:
        async with self._pool.connection() as conn:
            await conn.execute(
                """
                UPDATE health.service_registry
                SET status = 'SHUTDOWN'
                WHERE instance_id = %s
                """,
                (self._instance_id,),
            )

    async def _heartbeat_loop(self, interval_seconds: float = 15.0) -> None:
        try:
            while True:
                await asyncio.sleep(interval_seconds)
                try:
                    await self.heartbeat()
                except Exception:
                    pass  # Log error in production
        except asyncio.CancelledError:
            pass

    def start_heartbeat(self, interval_seconds: float = 15.0) -> None:
        if self._heartbeat_task is None:
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(interval_seconds))

    async def stop(self) -> None:
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        await self.deregister()