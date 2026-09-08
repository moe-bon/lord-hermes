import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis

from apexquant_redis.lock import DistributedLock


@pytest_asyncio.fixture
async def fake_redis() -> FakeRedis:
    return FakeRedis()


@pytest.mark.asyncio
async def test_lock_acquire_and_release(fake_redis: FakeRedis) -> None:
    lock = DistributedLock(fake_redis, "test:lock", ttl_seconds=10.0)

    acquired = await lock.acquire()
    assert acquired is True

    released = await lock.release()
    assert released is True


@pytest.mark.asyncio
async def test_lock_prevents_concurrent_acquisition(fake_redis: FakeRedis) -> None:
    lock1 = DistributedLock(fake_redis, "test:lock", ttl_seconds=10.0)
    lock2 = DistributedLock(fake_redis, "test:lock", ttl_seconds=10.0)

    assert await lock1.acquire() is True
    assert await lock2.acquire() is False

    await lock1.release()


@pytest.mark.asyncio
async def test_lock_context_manager(fake_redis: FakeRedis) -> None:
    async with DistributedLock(fake_redis, "test:ctx", ttl_seconds=10.0) as lock:
        assert lock._acquired is True

    assert lock._acquired is False


@pytest.mark.asyncio
async def test_lock_safe_release_prevents_cross_deletion(fake_redis: FakeRedis) -> None:
    lock1 = DistributedLock(fake_redis, "test:safe", ttl_seconds=0.1)
    await lock1.acquire()

    import asyncio
    await asyncio.sleep(0.2)

    lock2 = DistributedLock(fake_redis, "test:safe", ttl_seconds=10.0)
    await lock2.acquire()

    released = await lock1.release()
    assert released is False

    await lock2.release()