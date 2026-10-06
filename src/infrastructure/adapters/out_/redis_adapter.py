"""Caché en Redis del servicio de usuarios.

Redis aquí es apoyo, no fuente de verdad: guarda permisos ya calculados, el
contador de intentos fallidos y los tokens de refresco. Cuando se cae, lo
correcto es seguir sin la ayuda, no cerrar la puerta — salvo en las tres
llamadas de seguridad, que están abajo y no degradan a propósito.

El 5 de octubre de 2026, con 28 participantes usando el sistema, Redis perdió
la conexión seis veces en un día y ninguna llamada lo manejaba: la excepción
subía hasta el router y la petición respondía 500. Se cayeron un login, una
consulta de notificaciones y una recuperación de contraseña.
"""

import functools
import json
import logging
from uuid import UUID

import redis.asyncio as aioredis
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError
from redis.exceptions import TimeoutError as RedisTimeoutError

from src.application.ports.out_.cache_port import CachePort
from src.infrastructure.config.settings import settings

logger = logging.getLogger(__name__)

# Casi todas las caídas que vimos son la conexión ociosa que el otro extremo
# cierra y que el cliente descubre al escribir. Con reintentos y un ping
# periódico a las conexiones en reposo, eso se reconecta solo y nunca llega a
# la capa de arriba.
REINTENTOS = 3
CHEQUEO_DE_SALUD_SEGUNDOS = 30


def _degrada_a(valor):
    """Si Redis falla, deja constancia y sigue con el valor indicado.

    Se usa solo donde perder la caché no cambia lo que el sistema decide: los
    permisos se recalculan desde la base, un contador de intentos perdido vale
    cero, y un token de refresco que no aparece obliga a iniciar sesión de
    nuevo. Degradar no es callar: cada caída queda registrada.
    """

    def envoltura(fn):
        @functools.wraps(fn)
        async def interna(*args, **kwargs):
            try:
                return await fn(*args, **kwargs)
            except RedisError as e:
                logger.warning(
                    "Redis no respondió en %s (%s): se continúa sin caché",
                    fn.__name__,
                    type(e).__name__,
                )
                return valor

        return interna

    return envoltura


class RedisAdapter(CachePort):
    def __init__(self):
        self._redis = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            retry=Retry(ExponentialBackoff(cap=0.5, base=0.05), REINTENTOS),
            retry_on_error=[RedisConnectionError, RedisTimeoutError],
            health_check_interval=CHEQUEO_DE_SALUD_SEGUNDOS,
        )

    @_degrada_a(None)
    async def get_permisos(self, usuario_id: UUID) -> list[str] | None:
        data = await self._redis.get(f"perms:{usuario_id}")
        return json.loads(data) if data else None

    @_degrada_a(None)
    async def set_permisos(self, usuario_id: UUID, permisos: list[str], ttl: int) -> None:
        await self._redis.setex(f"perms:{usuario_id}", ttl, json.dumps(permisos))

    @_degrada_a(None)
    async def invalidar_permisos(self, usuario_id: UUID) -> None:
        await self._redis.delete(f"perms:{usuario_id}")

    @_degrada_a(0)
    async def incrementar_intentos_login(self, correo: str, ttl: int) -> int:
        key = f"login_attempts:{correo}"
        count = await self._redis.incr(key)
        if count == 1:
            await self._redis.expire(key, ttl)
        return count

    @_degrada_a(0)
    async def get_intentos_login(self, correo: str) -> int:
        val = await self._redis.get(f"login_attempts:{correo}")
        return int(val) if val else 0

    @_degrada_a(None)
    async def limpiar_intentos_login(self, correo: str) -> None:
        await self._redis.delete(f"login_attempts:{correo}")

    # ── Las tres que NO degradan ───────────────────────────────────────────
    # Si al consultar la lista negra asumiéramos «no está revocado», un token
    # que alguien revocó volvería a servir; si revocarlo fallara en silencio,
    # nunca quedaría revocado; y si la invalidación de sesiones se perdiera, las
    # sesiones seguirían vivas después de bloquear una cuenta. En los tres casos
    # el error tiene que verse, aunque cueste una petición fallida.

    async def blacklist_token(self, jti: str, ttl_segundos: int) -> None:
        await self._redis.setex(f"blacklist:{jti}", ttl_segundos, "revoked")

    async def is_token_blacklisted(self, jti: str) -> bool:
        return await self._redis.exists(f"blacklist:{jti}") > 0

    async def invalidar_todos_refresh_tokens(self, usuario_id: UUID) -> None:
        async for key in self._redis.scan_iter(match=f"refresh:{usuario_id}:*"):
            await self._redis.delete(key)

    # ───────────────────────────────────────────────────────────────────────

    @_degrada_a(None)
    async def save_refresh_token(self, usuario_id: UUID, device_id: str, token_hash: str, ttl: int) -> None:
        await self._redis.setex(f"refresh:{usuario_id}:{device_id}", ttl, token_hash)

    @_degrada_a(None)
    async def get_refresh_token(self, usuario_id: UUID, device_id: str) -> str | None:
        return await self._redis.get(f"refresh:{usuario_id}:{device_id}")

    @_degrada_a(None)
    async def marcar_bloqueo_por_intentos(self, usuario_id: UUID) -> None:
        # Sin vencimiento: dura lo mismo que el bloqueo, que tampoco vence solo.
        await self._redis.set(f"bloqueo_intentos:{usuario_id}", "1")

    @_degrada_a(False)
    async def fue_bloqueado_por_intentos(self, usuario_id: UUID) -> bool:
        return await self._redis.exists(f"bloqueo_intentos:{usuario_id}") > 0

    @_degrada_a(None)
    async def limpiar_bloqueo_por_intentos(self, usuario_id: UUID) -> None:
        await self._redis.delete(f"bloqueo_intentos:{usuario_id}")

    @_degrada_a(False)
    async def ping(self) -> bool:
        return bool(await self._redis.ping())

    @_degrada_a(0)
    async def contar_sesiones_activas(self) -> int:
        """Cuenta los refresh tokens vigentes en Redis (= sesiones activas)."""
        total = 0
        async for _ in self._redis.scan_iter(match="refresh:*"):
            total += 1
        return total
