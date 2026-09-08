from __future__ import annotations

import asyncio
import uuid
from types import TracebackType
from typing import Self

from redis.asyncio import Redis

UNLOCK_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


class DistributedLock:
    def __init__(
        self,
        redis_client: Redis,
        key: str,
        ttl_seconds: float,
        *,
        blocking: bool = False,
        retry_delay: float = 0.1,
    ) -> None:
        self._redis = redis_client
        self._key = key
        self._ttl_seconds = ttl_seconds
        self._blocking = blocking
        self._retry_delay = retry_delay
        self._token = str(uuid.uuid4())
        self._acquired = False

    async def acquire(self) -> bool:
        if self._blocking:
            while True:
                if await self._try_acquire():
                    return True
                await asyncio.sleep(self._retry_delay)
        else:
            return await self._try_acquire()

    async def _try_acquire(self) -> bool:
        result = await self._redis.set(
            self._key,
            self._token,
            nx=True,
            px=int(self._ttl_seconds * 1000),
        )
        self._acquired = bool(result)
        return self._acquired

    async def release(self) -> bool:
        if not self._acquired:
            return False

        result = await self._redis.eval(UNLOCK_SCRIPT, 1, self._key, self._token)
        self._acquired = False
        return bool(result)

    async def __aenter__(self) -> Self:
        acquired = await self.acquire()
        if not acquired and not self._blocking:
            raise RuntimeError(f"failed to acquire lock: {self._key}")
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.release()