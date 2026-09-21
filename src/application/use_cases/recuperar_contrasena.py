"""Recuperación de contraseña por código enviado al correo.

Tres pasos, en el orden de la pantalla: solicitar el código, verificarlo y fijar
la contraseña nueva. Decisiones que conviene tener a la vista:

- **Nadie averigua qué correos están registrados.** Solicitar un código responde
  lo mismo exista o no la cuenta, y un código incorrecto da el mismo error que un
  correo desconocido.
- **El código no se guarda en claro**, sino su HMAC con la clave del servicio: con
  solo un millón de combinaciones, un hash simple se revertiría probándolas todas.
- **Se limita la fuerza bruta** por tres lados: el código vence, admite pocos
  intentos fallidos y no puede pedirse de nuevo sin esperar.
- **Recuperar la cuenta la desbloquea solo si la bloqueó el propio login** por
  intentos fallidos, que es justo lo que le pasa a quien olvidó su contraseña. Un
  bloqueo o una desactivación puestos por un administrador se respetan.
"""

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from src.application.ports.out_.cache_port import CachePort
from src.application.ports.out_.codigo_recuperacion_port import CodigoRecuperacionPort
from src.application.ports.out_.email_port import EmailPort, EnvioCorreoError
from src.application.ports.out_.password_hasher_port import PasswordHasherPort
from src.application.ports.out_.usuario_repository_port import UsuarioRepositoryPort
from src.domain.value_objects.estado_usuario import EstadoUsuario
from src.domain.value_objects.politica_contrasena import validar_contrasena

logger = logging.getLogger(__name__)

ASUNTO = "Tu código para restablecer la contraseña de SWARD"
CUERPO = """Hola{saludo}:

Recibimos una solicitud para restablecer la contraseña de tu cuenta de SWARD.

Tu código es: {codigo}

Vence en {minutos} minutos. Escríbelo en la pantalla donde lo pediste.

Si no fuiste tú, ignora este correo: tu contraseña no cambiará.

SWARD — Universidad Peruana de Ciencias Aplicadas
"""


@dataclass(frozen=True)
class RecuperacionConfig:
    """Parámetros del flujo, inyectados por el composition root."""

    codigo_ttl: int
    max_intentos: int
    espera_reenvio: int
    max_envios_por_hora: int
    secreto: str


class CodigoInvalidoError(Exception):
    """Código incorrecto, vencido o inexistente. Mismo error en los tres casos."""


class RecuperacionNoDisponibleError(Exception):
    """El servicio corre sin correo configurado: no hay cómo enviar el código."""


class RecuperarContrasenaUseCase:
    def __init__(
        self,
        usuario_repo: UsuarioRepositoryPort,
        codigos: CodigoRecuperacionPort,
        cache: CachePort,
        email: EmailPort,
        password_hasher: PasswordHasherPort,
        config: RecuperacionConfig,
    ):
        self._usuario_repo = usuario_repo
        self._codigos = codigos
        self._cache = cache
        self._email = email
        self._hasher = password_hasher
        self._config = config

    # ------------------------------------------------------------ paso 1
    async def solicitar(self, correo: str) -> None:
        """Envía un código si procede. Nunca informa si la cuenta existe."""
        self._exigir_correo()
        usuario = await self._usuario_repo.find_by_correo(_normalizar(correo))
        if usuario is None or usuario.estado == EstadoUsuario.INACTIVO:
            return
        if await self._codigos.en_espera(usuario.id):
            return
        envios = await self._codigos.contar_envio(usuario.id, 3600)
        if envios > self._config.max_envios_por_hora:
            logger.warning("Recuperación: límite de envíos por hora para %s", usuario.id)
            return

        codigo = f"{secrets.randbelow(10**6):06d}"
        await self._codigos.guardar(usuario.id, self._huella(usuario.id, codigo), self._config.codigo_ttl)
        await self._codigos.iniciar_espera(usuario.id, self._config.espera_reenvio)

        try:
            await self._email.enviar(
                destinatario=usuario.correo_institucional,
                asunto=ASUNTO,
                cuerpo=CUERPO.format(
                    saludo=f", {usuario.nombre}" if usuario.nombre else "",
                    codigo=codigo,
                    minutos=self._config.codigo_ttl // 60,
                ),
            )
        except EnvioCorreoError:
            # La respuesta sigue siendo la misma para no revelar que la cuenta
            # existe; se deshace el código para que pueda pedirse otro enseguida.
            logger.exception("Recuperación: no se pudo enviar el código a %s", usuario.id)
            await self._codigos.eliminar(usuario.id)

    # ------------------------------------------------------------ paso 2
    async def verificar(self, correo: str, codigo: str) -> None:
        """Comprueba el código sin consumirlo. Lanza CodigoInvalidoError."""
        self._exigir_correo()
        usuario = await self._usuario_repo.find_by_correo(_normalizar(correo))
        if usuario is None:
            raise CodigoInvalidoError()
        await self._comprobar(usuario.id, codigo)

    # ------------------------------------------------------------ paso 3
    async def restablecer(self, correo: str, codigo: str, password_nueva: str) -> None:
        """Fija la contraseña nueva y cierra todas las sesiones abiertas.

        La política se revisa antes que el código: una contraseña débil no debe
        gastar un intento ni obligar a pedir otro código.
        """
        self._exigir_correo()
        validar_contrasena(password_nueva)

        usuario = await self._usuario_repo.find_by_correo(_normalizar(correo))
        if usuario is None:
            raise CodigoInvalidoError()
        await self._comprobar(usuario.id, codigo)

        usuario.password_hash = self._hasher.hash(password_nueva)
        if usuario.estado == EstadoUsuario.BLOQUEADO and await self._cache.fue_bloqueado_por_intentos(usuario.id):
            usuario.activar()
            await self._cache.limpiar_bloqueo_por_intentos(usuario.id)
        usuario.updated_at = datetime.now(timezone.utc)
        await self._usuario_repo.save(usuario)

        await self._codigos.eliminar(usuario.id)
        await self._cache.invalidar_todos_refresh_tokens(usuario.id)
        await self._cache.limpiar_intentos_login(usuario.correo_institucional)

    # ------------------------------------------------------------ interno
    def _exigir_correo(self) -> None:
        # Se revisa antes de buscar la cuenta: es una condición del servicio, no
        # de la persona, así que avisarla no revela si el correo está registrado.
        if not self._email.disponible:
            raise RecuperacionNoDisponibleError(
                "La recuperación de contraseña no está disponible en este momento. Contacta al administrador."
            )

    async def _comprobar(self, usuario_id: UUID, codigo: str) -> None:
        guardado = await self._codigos.obtener(usuario_id)
        if guardado is None:
            raise CodigoInvalidoError()
        if not hmac.compare_digest(guardado.huella, self._huella(usuario_id, codigo.strip())):
            fallidos = await self._codigos.registrar_intento_fallido(usuario_id)
            if fallidos >= self._config.max_intentos:
                await self._codigos.eliminar(usuario_id)
            raise CodigoInvalidoError()

    def _huella(self, usuario_id: UUID, codigo: str) -> str:
        mensaje = f"{usuario_id}:{codigo}".encode()
        return hmac.new(self._config.secreto.encode(), mensaje, hashlib.sha256).hexdigest()


def _normalizar(correo: str) -> str:
    return correo.strip().lower()
