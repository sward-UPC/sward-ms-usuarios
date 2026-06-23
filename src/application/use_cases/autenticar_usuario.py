import hashlib
from dataclasses import dataclass

from src.application.ports.out_.cache_port import CachePort
from src.application.ports.out_.event_publisher_port import EventPublisherPort
from src.application.ports.out_.password_hasher_port import PasswordHasherPort
from src.application.ports.out_.rol_repository_port import RolRepositoryPort
from src.application.ports.out_.token_port import TokenPair, TokenPort
from src.application.ports.out_.usuario_repository_port import UsuarioRepositoryPort
from src.domain.entities.rol import TipoRol
from src.domain.events.usuario_autenticado_event import UsuarioAutenticadoEvent
from src.domain.value_objects.estado_usuario import EstadoUsuario


@dataclass
class AutenticarUsuarioCommand:
    correo: str
    password: str
    device_id: str = "default"


@dataclass(frozen=True)
class AutenticacionConfig:
    """Parámetros de configuración del flujo de autenticación.

    Datos planos inyectados por el composition root: el núcleo no conoce de
    dónde provienen (settings, env, etc.), solo recibe valores.
    """

    max_login_attempts: int
    login_attempts_ttl: int
    permissions_cache_ttl: int
    refresh_token_expire_days: int


class AutenticacionError(Exception):
    pass


class CuentaBloqueadaError(AutenticacionError):
    pass


class AutenticarUsuarioUseCase:
    def __init__(
        self,
        usuario_repo: UsuarioRepositoryPort,
        rol_repo: RolRepositoryPort,
        token_port: TokenPort,
        cache: CachePort,
        event_publisher: EventPublisherPort,
        password_hasher: PasswordHasherPort,
        config: AutenticacionConfig,
    ):
        self._usuario_repo = usuario_repo
        self._rol_repo = rol_repo
        self._token_port = token_port
        self._cache = cache
        self._event_publisher = event_publisher
        self._password_hasher = password_hasher
        self._config = config

    async def execute(self, command: AutenticarUsuarioCommand) -> TokenPair:
        intentos = await self._cache.get_intentos_login(command.correo)
        if intentos >= self._config.max_login_attempts:
            raise CuentaBloqueadaError("Cuenta bloqueada temporalmente. Intente en 15 minutos.")

        usuario = await self._usuario_repo.find_by_correo(command.correo)

        if not usuario or not self._password_hasher.verify(command.password, usuario.password_hash):
            nuevos = await self._cache.incrementar_intentos_login(command.correo, self._config.login_attempts_ttl)
            if nuevos >= self._config.max_login_attempts and usuario:
                usuario.bloquear()
                await self._usuario_repo.save(usuario)
            raise AutenticacionError("Credenciales inválidas.")

        if usuario.estado == EstadoUsuario.BLOQUEADO:
            raise CuentaBloqueadaError("Tu cuenta está bloqueada. Contacta al administrador.")
        if usuario.estado == EstadoUsuario.INACTIVO:
            raise AutenticacionError("Tu cuenta está inactiva. Contacta al administrador.")

        await self._cache.limpiar_intentos_login(command.correo)

        roles = await self._rol_repo.find_by_usuario_id(usuario.id)
        rol_principal = roles[0].nombre if roles else TipoRol.ESTUDIANTE
        permisos = [p.codigo for r in roles for p in r.permisos]

        await self._cache.set_permisos(usuario.id, permisos, self._config.permissions_cache_ttl)

        token_pair = self._token_port.generar_par(
            usuario_id=usuario.id,
            rol=str(rol_principal),
            permisos=permisos,
            device_id=command.device_id,
            nombre=usuario.nombre,
            moodle_user_id=usuario.moodle_user_id,
        )

        refresh_hash = hashlib.sha256(token_pair.refresh_token.encode()).hexdigest()
        await self._cache.save_refresh_token(
            usuario.id,
            command.device_id,
            refresh_hash,
            self._config.refresh_token_expire_days * 86400,
        )

        self._event_publisher.publish(
            UsuarioAutenticadoEvent(
                usuario_id=usuario.id,
                rol=str(rol_principal),
                correo=usuario.correo_institucional,
            )
        )

        return token_pair
