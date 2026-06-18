import json
from uuid import UUID

import redis.asyncio as aioredis

from src.domain.ports.out_.cache_port import CachePort
from src.infrastructure.config.settings import settings


class RedisAdapter(CachePort):
    def __init__(self):
        self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)

    async def get_permisos(self, usuario_id: UUID) -> list[str] | None:
        data = await self._redis.get(f"perms:{usuario_id}")
        return json.loads(data) if data else None

    async def set_permisos(self, usuario_id: UUID, permisos: list[str], ttl: int) -> None:
        await self._redis.setex(f"perms:{usuario_id}", ttl, json.dumps(permisos))

    async def invalidar_permisos(self, usuario_id: UUID) -> None:
        await self._redis.delete(f"perms:{usuario_id}")

    async def incrementar_intentos_login(self, correo: str, ttl: int) -> int:
        key = f"login_attempts:{correo}"
        count = await self._redis.incr(key)
        if count == 1:
            await self._redis.expire(key, ttl)
        return count

    async def get_intentos_login(self, correo: str) -> int:
        val = await self._redis.get(f"login_attempts:{correo}")
        return int(val) if val else 0

    async def limpiar_intentos_login(self, correo: str) -> None:
        await self._redis.delete(f"login_attempts:{correo}")

    async def blacklist_token(self, jti: str, ttl_segundos: int) -> None:
        await self._redis.setex(f"blacklist:{jti}", ttl_segundos, "revoked")

    async def is_token_blacklisted(self, jti: str) -> bool:
        return await self._redis.exists(f"blacklist:{jti}") > 0

    async def save_refresh_token(self, usuario_id: UUID, device_id: str, token_hash: str, ttl: int) -> None:
        await self._redis.setex(f"refresh:{usuario_id}:{device_id}", ttl, token_hash)

    async def get_refresh_token(self, usuario_id: UUID, device_id: str) -> str | None:
        return await self._redis.get(f"refresh:{usuario_id}:{device_id}")

    async def invalidar_todos_refresh_tokens(self, usuario_id: UUID) -> None:
        async for key in self._redis.scan_iter(match=f"refresh:{usuario_id}:*"):
            await self._redis.delete(key)

    async def ping(self) -> bool:
        return bool(await self._redis.ping())
