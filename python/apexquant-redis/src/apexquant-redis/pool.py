from __future__ import annotations

from redis.asyncio import ConnectionPool, Redis

from apexquant_redis.config import RedisSettings


def create_redis_pool(settings: RedisSettings) -> Redis:
    pool = ConnectionPool.from_url(
        settings.url,
        max_connections=50,
        socket_timeout=settings.socket_timeout,
        socket_connect_timeout=settings.socket_connect_timeout,
        retry_on_timeout=True,
    )

    return Redis(connection_pool=pool)