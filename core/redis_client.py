import redis.asyncio as redis
from core.config import settings

_redis = redis.from_url(settings.redis_url, decode_responses=False)  # binary for images

async def get_cache(key: str) -> str | None:
    val = await _redis.get(key)
    if val is not None:
        return val.decode('utf-8')
    return None

async def set_cache(key: str, value: str, ttl: int = 3600) -> None:
    await _redis.setex(key, ttl, value.encode('utf-8'))

async def get_binary_cache(key: str) -> bytes | None:
    return await _redis.get(key)

async def set_binary_cache(key: str, value: bytes, ttl: int = 3600) -> None:
    await _redis.setex(key, ttl, value)

async def delete_cache(key: str) -> None:
    await _redis.delete(key)