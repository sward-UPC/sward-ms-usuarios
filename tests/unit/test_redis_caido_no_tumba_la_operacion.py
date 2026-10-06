"""Que se caiga Redis no puede dejar a nadie fuera del sistema.

El 5 de octubre de 2026, con 28 participantes usando SWARD, Redis perdió la
conexión seis veces en un día. Ninguna de las llamadas del adaptador lo
manejaba, así que la excepción subía hasta el router y la petición respondía
500. Se cayeron un login, una consulta de notificaciones y una recuperación de
contraseña.

Redis aquí es apoyo: guarda permisos ya calculados, el contador de intentos
fallidos y los tokens de refresco. Nada de eso es la fuente de verdad —los
permisos están en la base— así que cuando no se puede leer, lo correcto es
seguir sin la ayuda, no cerrar la puerta.

**Con una excepción, y es deliberada.** La lista negra de tokens y la
invalidación de sesiones NO degradan. Si al consultar la lista negra
asumiéramos «no está revocado», un token que alguien revocó volvería a
funcionar; y si la invalidación fallara en silencio, las sesiones seguirían
vivas después de bloquear una cuenta. Ahí el error tiene que verse.
"""

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from src.infrastructure.adapters.out_ import redis_adapter as modulo
from src.infrastructure.adapters.out_.redis_adapter import RedisAdapter

USUARIO = "11111111-1111-1111-1111-111111111111"


class _RedisCaido:
    """Un Redis que siempre pierde la conexión, como el del 5 de octubre."""

    def __getattr__(self, nombre):
        async def falla(*args, **kwargs):
            raise RedisConnectionError("Error UNKNOWN while writing to socket.")

        return falla

    def scan_iter(self, *args, **kwargs):
        raise RedisConnectionError("Error UNKNOWN while writing to socket.")


@pytest.fixture
def adaptador(monkeypatch):
    monkeypatch.setattr(modulo.aioredis, "from_url", lambda *a, **k: _RedisCaido())
    return RedisAdapter()


# ── Lo que debe seguir funcionando sin Redis ────────────────────────────────


async def test_el_contador_de_intentos_no_tumba_el_login(adaptador):
    # Este fue el 500 del domingo: alguien no pudo entrar.
    assert await adaptador.get_intentos_login("alguien@ejemplo.com") == 0


async def test_incrementar_intentos_no_tumba_el_login(adaptador):
    assert await adaptador.incrementar_intentos_login("alguien@ejemplo.com", 300) == 0


async def test_los_permisos_caen_a_fallo_de_cache(adaptador):
    # Devolver None significa «no está en caché»: quien llama va a la base.
    assert await adaptador.get_permisos(USUARIO) is None


async def test_guardar_permisos_no_estalla(adaptador):
    await adaptador.set_permisos(USUARIO, ["leer"], 300)


async def test_el_refresh_token_ausente_obliga_a_entrar_de_nuevo(adaptador):
    # Peor que volver a iniciar sesión es no poder usar el sistema.
    assert await adaptador.get_refresh_token(USUARIO, "dispositivo") is None


async def test_el_ping_responde_que_no_en_vez_de_estallar(adaptador):
    assert await adaptador.ping() is False


async def test_contar_sesiones_no_estalla(adaptador):
    assert await adaptador.contar_sesiones_activas() == 0


# ── Lo que NO debe degradar ────────────────────────────────────────────────


async def test_la_lista_negra_no_degrada(adaptador):
    # Asumir «no revocado» dejaría entrar con un token que alguien revoco.
    with pytest.raises(RedisConnectionError):
        await adaptador.is_token_blacklisted("un-jti")


async def test_revocar_un_token_no_degrada(adaptador):
    with pytest.raises(RedisConnectionError):
        await adaptador.blacklist_token("un-jti", 300)


async def test_invalidar_las_sesiones_no_degrada(adaptador):
    # Si falla en silencio, las sesiones siguen vivas tras bloquear la cuenta.
    with pytest.raises(RedisConnectionError):
        await adaptador.invalidar_todos_refresh_tokens(USUARIO)
