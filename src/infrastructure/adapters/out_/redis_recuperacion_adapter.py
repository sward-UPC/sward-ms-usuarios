from uuid import UUID

import redis.asyncio as aioredis

from src.application.ports.out_.codigo_recuperacion_port import CodigoGuardado, CodigoRecuperacionPort
from src.infrastructure.config.settings import settings


class RedisRecuperacionAdapter(CodigoRecuperacionPort):
    """Códigos de recuperación en Redis, todos con vencimiento.

    La huella y el contador de intentos van en claves separadas a propósito: si
    compartieran un hash, incrementar el contador después de que la huella
    venciera volvería a crear la clave, esta vez sin vencimiento.
    """

    def __init__(self):
        self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)

    @staticmethod
    def _k(usuario_id: UUID, que: str) -> str:
        return f"pwreset:{usuario_id}:{que}"

    async def guardar(self, usuario_id: UUID, huella: str, ttl_segundos: int) -> None:
        async with self._redis.pipeline(transaction=True) as p:
            p.setex(self._k(usuario_id, "huella"), ttl_segundos, huella)
            p.delete(self._k(usuario_id, "intentos"))
            await p.execute()

    async def obtener(self, usuario_id: UUID) -> CodigoGuardado | None:
        huella = await self._redis.get(self._k(usuario_id, "huella"))
        if huella is None:
            return None
        intentos = await self._redis.get(self._k(usuario_id, "intentos"))
        return CodigoGuardado(huella=huella, intentos_fallidos=int(intentos or 0))

    async def registrar_intento_fallido(self, usuario_id: UUID) -> int:
        clave = self._k(usuario_id, "intentos")
        total = await self._redis.incr(clave)
        if total == 1:
            # El contador vive lo mismo que el código al que pertenece.
            restante = await self._redis.ttl(self._k(usuario_id, "huella"))
            await self._redis.expire(clave, restante if restante > 0 else 60)
        return total

    async def eliminar(self, usuario_id: UUID) -> None:
        await self._redis.delete(self._k(usuario_id, "huella"), self._k(usuario_id, "intentos"))

    async def en_espera(self, usuario_id: UUID) -> bool:
        return await self._redis.exists(self._k(usuario_id, "espera")) > 0

    async def iniciar_espera(self, usuario_id: UUID, segundos: int) -> None:
        await self._redis.setex(self._k(usuario_id, "espera"), segundos, "1")

    async def contar_envio(self, usuario_id: UUID, ventana_segundos: int) -> int:
        clave = self._k(usuario_id, "envios")
        total = await self._redis.incr(clave)
        if total == 1:
            await self._redis.expire(clave, ventana_segundos)
        return total
