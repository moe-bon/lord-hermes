from __future__ import annotations

from redis.asyncio import Redis


async def check_health(redis_client: Redis) -> bool:
    try:
        result = await redis_client.ping()
        return bool(result)
    except Exception:
        return False